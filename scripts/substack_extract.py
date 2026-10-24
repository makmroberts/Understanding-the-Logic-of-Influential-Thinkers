"""Extract Substack posts into annotation-ready Markdown.

The second publisher adapter. Everything publisher-neutral - fetching, the
cache, `to_markdown`, `render`, the driver - lives in `extract_lib.py`; this
file is only the part that knows how Substack builds a page.

Usage:
    python scripts/substack_extract.py --url https://www.feelingthestones.com/p/the-confidence-machine
    python scripts/substack_extract.py --url <url> --owner isaac --no-cache
    python scripts/substack_extract.py --url <url> --check     # parse, print, write nothing

What differs from CFR, concretely - these are the four places
scripts/README.md predicted would be publisher-specific:

  fetch         shared after all. The only CFR-ness was a hardcoded cache dir.
  body selector CFR: `<p class="rich-text">`. Substack: bare `<p>` and `<h3>`
                inside `<div class="body markup">`, so the container has to be
                found first and the blocks taken from inside it.
  jsonld        CFR tags its block `id="parsely-*"`. Substack ships an untagged
                block followed by a BreadcrumbList, so the shared `jsonld()`
                scans for the first object that actually has a headline.
  figure_title  CFR names chart files after the chart, so the filename IS the
                caption. Substack serves through a CDN with hashed filenames,
                so the caption has to come from `<figcaption>`.

Two Substack-specific decisions worth knowing about:

  Footnotes are body paragraphs. Substack renders them in a separate block
  after the post, and this adapter appends them to `paragraphs` as `[fnN] ...`
  so a claim sourced only in a footnote can still anchor to a passage. On the
  first post extracted this mattered immediately: the one reconstructed number
  in the argument (24/30 = ~80 percent of non-consumed income going to
  property) exists nowhere but footnote 11.

  Headings are paragraphs too. Substack section headings carry argument content
  on this author - "Houses are For Living" is a policy slogan, not decoration -
  so `<h1>`-`<h4>` are numbered alongside `<p>` rather than dropped.
"""

import argparse
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract_lib as lib

# The post body container. `dir="auto"` rides along on the real pages, so the
# class match cannot be anchored to the closing bracket.
BODY_OPEN_RE = re.compile(r'<div class="body markup"[^>]*>')

# Where the body stops. Substack appends a subscribe widget, then the footnote
# block, then the post footer; whichever comes first ends the body.
BODY_END_MARKERS = (
    '<div class="subscription-widget-wrap',
    '<div class="footnote"',
    '<div class="post-footer',
)

BLOCK_RE = re.compile(
    r"<(p|h1|h2|h3|h4|blockquote)\b[^>]*>(.*?)</\1>", re.S)
FIGCAPTION_RE = re.compile(r"<figcaption[^>]*>(.*?)</figcaption>", re.S)
IMG_ALT_RE = re.compile(r'<img[^>]*alt="([^"]*)"')

FOOTNOTE_RE = re.compile(
    r'<div class="footnote"[^>]*>(.*?)</div>\s*</div>', re.S)
FOOTNOTE_NUM_RE = re.compile(
    r'(?:id="footnote-(\d+)"|class="footnote-number"[^>]*>\s*(\d+))')
FOOTNOTE_BODY_RE = re.compile(
    r'<div class="footnote-content"[^>]*>(.*?)</div>', re.S)
# The footnote's own back-link to its anchor in the body survives to_markdown as
# a leading "[7](#footnote-anchor-7)". It is navigation, not footnote text, and
# left in it becomes the first thing a passage matcher sees.
FOOTNOTE_BACKLINK_RE = re.compile(r"^\s*\[\d+\]\(#footnote-anchor-\d+\)\s*")

# Substack marks a truncated post with one of these. A paywalled page parses
# perfectly and yields half an article, which is the worst failure mode here -
# every claim past the cut silently loses its passage - so it is called out.
PAYWALL_MARKERS = ('class="paywall"', "audience-locked", "paywall-jump")

# Boilerplate Substack adds inside the body that is not the author writing.
BOILERPLATE_RE = re.compile(
    r"^(subscribe|share|leave a comment|give a gift subscription|"
    r"thanks for reading.*subscribe|if you don.t want to miss the next one)",
    re.I)


def body_html(page):
    """The post body, or "" if the container is gone."""
    m = BODY_OPEN_RE.search(page)
    if not m:
        return ""
    start = m.end()
    ends = [p for p in (page.find(mk, start) for mk in BODY_END_MARKERS) if p > 0]
    return page[start:min(ends)] if ends else page[start:]


def body_blocks(body):
    """Ordered Markdown blocks: paragraphs and headings, boilerplate dropped."""
    out = []
    for m in BLOCK_RE.finditer(body):
        text = lib.to_markdown(m.group(2))
        if not text or BOILERPLATE_RE.match(text):
            continue
        out.append(text)
    return out


def figures(body):
    """Substack serves figures through a CDN with hashed filenames, so the
    caption is the only title available - `<figcaption>`, else the img alt."""
    out = []
    for fig in lib.FIG_RE.finditer(body):
        frag = fig.group(0)
        src = lib.IMG_SRC_RE.search(frag)
        if not src:
            continue
        cap = FIGCAPTION_RE.search(frag)
        alt = IMG_ALT_RE.search(frag)
        title = (lib.clean(cap.group(1)) if cap
                 else (alt.group(1).strip() if alt else ""))
        out.append({"title": title or "untitled figure", "src": src.group(1)})
    return out


def footnotes(page):
    """[(n, html)] in document order - raw HTML, not Markdown.

    Returned as HTML because the caller needs it twice: once through
    `to_markdown` to become a paragraph, and once through
    `references_from`, which reads `<a href>` and would find nothing in a
    string that had already been flattened. Passing Markdown here is what
    silently dropped most of this post's citations on the first run.

    Kept separate from the body so the caller can decide whether footnotes are
    citable passages. This adapter says they are.
    """
    out = []
    for m in FOOTNOTE_RE.finditer(page):
        frag = m.group(1)
        num = FOOTNOTE_NUM_RE.search(frag)
        n = int(num.group(1) or num.group(2)) if num else len(out) + 1
        body = FOOTNOTE_BODY_RE.search(frag)
        html_frag = body.group(1) if body else frag
        if lib.clean(html_frag):
            out.append((n, html_frag))
    return out


def footnote_text(html_frag):
    """Footnote HTML -> paragraph text, without its back-link to the body."""
    return FOOTNOTE_BACKLINK_RE.sub("", lib.to_markdown(html_frag)).strip()


def slug_of(url):
    path = urllib.parse.urlparse(url).path.rstrip("/")
    return path.rsplit("/", 1)[-1] or "untitled"


def parse(url, page, row=None):
    """Substack page -> the doc dict `extract_lib.render` expects."""
    row = row or {}
    ld = lib.jsonld(page)
    body = body_html(page)
    blocks = body_blocks(body)
    notes = []

    if not body:
        notes.append("WARNING: the `div.body markup` container did not match - "
                     "Substack has restyled, or this is not a post page.")

    fns = footnotes(page)
    fn_text = [(n, footnote_text(h)) for n, h in fns]
    paragraphs = list(blocks) + ["[fn%d] %s" % (n, t) for n, t in fn_text if t]
    if fns:
        notes.append("Footnotes %d-%d are body paragraphs %d-%d, prefixed [fnN], so a "
                     "claim sourced only in a footnote can anchor to a passage."
                     % (fns[0][0], fns[-1][0], len(blocks) + 1, len(paragraphs)))
    notes.append("Section headings are numbered paragraphs alongside body text; "
                 "this author argues in them.")

    # Substack authors break rhetorical structures - a decision tree, a beat of
    # silence - into one <p> per line, so a single argumentative move can span a
    # RANGE of paragraphs and some of those paragraphs carry no words at all
    # ("..."). Nothing is merged or dropped here: the markup is the author's and
    # renumbering would move every passage link. But `link_passages.py` grades
    # one claim against one paragraph, so a claim sourced in such a range can
    # only ever cite one line of it - which is a modelling decision for the
    # team, not something an extractor should quietly make. Hence the count.
    terse = [i for i, p in enumerate(blocks, 1) if len(p) < 25]
    if terse:
        notes.append("%d body paragraphs are under 25 characters (%s%s) - lines of a "
                     "multi-paragraph rhetorical structure, kept as the author wrote "
                     "them. A claim whose source is such a range can cite only one of "
                     "them under the current one-claim-one-paragraph passage model."
                     % (len(terse), ", ".join("p%d" % i for i in terse[:8]),
                        ", ..." if len(terse) > 8 else ""))

    truncated = [mk for mk in PAYWALL_MARKERS if mk in page]
    if truncated:
        notes.append("WARNING: paywall markers present (%s) - the body may be "
                     "truncated and every claim past the cut will fail to anchor."
                     % ", ".join(truncated))

    publisher = ""
    pub = ld.get("publisher")
    if isinstance(pub, dict):
        publisher = pub.get("name", "")
    publisher = publisher or urllib.parse.urlparse(url).netloc

    plain = " ".join(lib.clean(m.group(2)) for m in BLOCK_RE.finditer(body))
    plain += " " + " ".join(t for _, t in fn_text)

    return {
        "url": url,
        "slug": slug_of(url),
        "title": ld.get("headline") or ld.get("name") or row.get("title", ""),
        "authors": lib.ld_authors(ld, default=["unknown"]),
        "publisher": publisher,
        "series": publisher,          # on Substack the newsletter IS the series
        "section": ld.get("articleSection", ""),
        "doc_type": ld.get("@type") or "SubstackPost",
        "date_published": ld.get("datePublished", ""),
        "date_modified": ld.get("dateModified", ""),
        "paragraphs": paragraphs,
        "figures": figures(body),
        "references": lib.references_from(
            [m.group(2) for m in BLOCK_RE.finditer(body)] + [h for _, h in fns]),
        "word_count": len(plain.split()),
        "owner": row.get("owner", ""),
        "year": row.get("year", ""),
        "date_label": row.get("date_label", ""),
        "notes": notes,
    }


def main():
    ap = argparse.ArgumentParser(description="Extract Substack posts.")
    ap.add_argument("--url", action="append", default=[], required=True,
                    help="post URL, repeatable")
    ap.add_argument("--owner", default="", help="who is annotating it")
    ap.add_argument("--no-cache", action="store_true", help="always re-fetch")
    ap.add_argument("--out", default=lib.OUT_DIR)
    ap.add_argument("--check", action="store_true",
                    help="parse and report, write nothing")
    args = ap.parse_args()

    rows = lib.dedupe([{"url": u, "owner": args.owner, "year": "",
                        "title": "", "date_label": ""} for u in args.url])

    if args.check:
        bad = 0
        for row in rows:
            page, cached = lib.fetch(row["url"], use_cache=not args.no_cache)
            doc = parse(row["url"], page, row)
            print("%s%s" % (row["url"], "  (cached)" if cached else ""))
            print("  title      : %s" % doc["title"])
            print("  authors    : %s" % ", ".join(doc["authors"]))
            print("  publisher  : %s" % doc["publisher"])
            print("  date       : %s" % (doc["date_published"] or "MISSING"))
            print("  paragraphs : %d  (%d words)" % (len(doc["paragraphs"]),
                                                     doc["word_count"]))
            print("  figures    : %d" % len(doc["figures"]))
            print("  references : %d" % len(doc["references"]))
            for note in doc["notes"]:
                print("  note       : %s" % note)
            if lib.warn_empty(doc, "BODY_OPEN_RE / BLOCK_RE in substack_extract.py"):
                bad += 1
            if not doc["date_published"]:
                print("    WARNING: no datePublished - the map filename convention "
                      "needs a day, and nothing downstream flags an empty date")
                bad += 1
        return 1 if bad else 0

    _, failures = lib.process(
        rows, parse, out_dir=args.out, use_cache=not args.no_cache,
        selector_hint="BODY_OPEN_RE / BLOCK_RE in substack_extract.py")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
