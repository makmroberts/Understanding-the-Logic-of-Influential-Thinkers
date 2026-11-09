"""Extract CFR "Follow the Money" articles into annotation-ready Markdown.

The first publisher adapter. Everything publisher-neutral - fetching, the HTML
cache, `to_markdown`, `render`, the driver - moved to `common.py` on
2026-10-19 when a second publisher arrived; what is left here is only the part
that knows how CFR builds a page. Output is byte-identical to the pre-split
version (verified against all 20 cached pages, `retrieved_at` excepted since it
is a clock reading).

Stdlib only, so it runs anywhere without a virtualenv. Output is one Markdown
file per article: YAML frontmatter carrying the deterministic (Stage 1a)
metadata, then the body with inline citations preserved, then the figure and
reference inventories that Level 2 (Evidence) annotation depends on.

Usage:
    python scripts/parsers/cfr.py --owner sicheng
    python scripts/parsers/cfr.py --year 2020 --year 2024
    python scripts/parsers/cfr.py --all
    python scripts/parsers/cfr.py --url https://www.cfr.org/articles/<slug>

See scripts/README.md for what is verified to work and what the future
large-scale skill will need to change.
"""

import argparse
import csv
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import common as lib

ROOT = lib.ROOT
REGISTRY = os.path.join(ROOT, "scripts", "sources_followthemoney.csv")
OUT_DIR = lib.OUT_DIR

# CFR renders body copy as <p class="rich-text ...">, lists as <ol|ul
# class="type-serif-body4">, and in-article subheads as <h4 class="type-sans-h5">.
# Matching only the first lost argument text in 3 articles, found 2026-11-09.
BLOCK_RE = re.compile(
    r'<p[^>]*class="rich-text[^"]*"[^>]*>(?P<para>.*?)</p>'
    r'|<(?P<list>ol|ul)[^>]*class="type-serif-body4"[^>]*>(?P<items>.*?)</(?P=list)>'
    r'|<h4[^>]*class="type-sans-h5[^"]*"[^>]*>(?P<head>.*?)</h4>',
    re.S)
LI_RE = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S)

SERIES = "Follow the Money"
DESCRIPTION_RE = re.compile(r'<meta[^>]*name="description"[^>]*content="([^"]*)"')
# The footer after the last body block: "Information From <programs> Creative
# Commons: ... (CC BY-NC-ND 4.0) License. <tag links> Tags".
SCRIPT_STYLE_RE = re.compile(r"<script.*?</script>|<style.*?</style>", re.S)
PROGRAMS_RE = re.compile(r"Information\s*From (.*?)Creative Commons")
PROGRAM_SPLIT_RE = re.compile(r",\s*(?:and\s+)?|\s+and\s+")
LICENSE_RE = re.compile(r"\((CC [A-Z\-]+ [\d.]+)\)")
TAG_LINK_RE = re.compile(r'<a[^>]*href="/(?:topics|regions|tags)/[^"]*"[^>]*>(.*?)</a>', re.S)

# CFR tags its schema.org block with `id="parsely-*"`. The shared `lib.jsonld`
# would find it anyway by scanning for a headline, but keeping the precise
# selector means a CFR restyle shows up here rather than silently falling back.
LD_RE = re.compile(
    r'<script[^>]*id="parsely-[^"]*"[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.S,
)


def figure_title(src):
    """CFR names chart files after the chart title, so the filename is the caption.

    This is the clearest publisher-specific assumption in the file: Substack
    serves through a CDN with hashed filenames, so its adapter has to read
    `<figcaption>` instead.
    """
    name = urllib.parse.unquote(src.rsplit("/", 1)[-1])
    name = re.sub(r"_\d+(?=\.)", "", name)
    name = re.sub(r"\.(png|jpe?g|gif|webp|svg)$", "", name, flags=re.I)
    return name.strip()


def body_blocks(page):
    """[(offset, html)] in page order: one entry per paragraph, list item or subhead."""
    blocks = []
    for m in BLOCK_RE.finditer(page):
        if m.group("items") is not None:
            base = m.start("items")
            blocks += [(base + li.start(), li.group(1)) for li in LI_RE.finditer(m.group("items"))]
        else:
            name = "para" if m.group("para") is not None else "head"
            blocks.append((m.start(name), m.group(name)))
    return blocks


def page_footer(page, last_block):
    """(programs, tags, license) from the footer after the article body."""
    tail = SCRIPT_STYLE_RE.sub(" ", page[last_block:])
    text = lib.clean(tail)
    found = PROGRAMS_RE.search(text)
    programs = [p for p in PROGRAM_SPLIT_RE.split(found.group(1).strip()) if p] if found else []
    license_id = LICENSE_RE.search(text)
    start, stop = tail.find("Creative Commons"), tail.find(">Tags<")
    tags = []
    if 0 <= start < stop:
        tags = list(dict.fromkeys(lib.clean(t) for t in TAG_LINK_RE.findall(tail[start:stop])))
    return programs, tags, license_id.group(1) if license_id else ""


def parse(url, page, row=None):
    """CFR page -> the doc dict `common.render` expects."""
    row = row or {}
    ld = lib.jsonld(page, script_re=LD_RE)
    programs, tags, license_id = page_footer(page, body_blocks(page)[-1][0]) if BLOCK_RE.search(page) else ([], [], "")
    description = DESCRIPTION_RE.search(page)

    blocks = [(pos, frag) for pos, frag in body_blocks(page) if lib.to_markdown(frag)]
    paragraphs = [lib.to_markdown(frag) for _, frag in blocks]
    body_plain = " ".join(lib.clean(frag) for _, frag in blocks)

    figures = []
    for fig in lib.FIG_RE.finditer(page):
        src = lib.IMG_SRC_RE.search(fig.group(0))
        if src and "static.cfr.org" in src.group(1):
            figures.append({
                "title": figure_title(src.group(1)),
                "src": src.group(1),
                "after": sum(1 for pos, _ in blocks if pos < fig.start()),
            })

    return {
        "url": url,
        "slug": url.rstrip("/").rsplit("/", 1)[-1],
        "title": ld.get("headline") or row.get("title", ""),
        "authors": lib.ld_authors(ld, default=["Brad W. Setser"]),
        "publisher": "Council on Foreign Relations",
        "series": SERIES if SERIES in programs else "",
        "programs": programs,
        "source_tags": tags,
        "license": license_id,
        "subtitle": lib.clean(description.group(1)) if description else "",
        "section": ld.get("articleSection", ""),
        "doc_type": ld.get("@type", ""),
        "date_published": ld.get("datePublished", ""),
        "date_modified": ld.get("dateModified", ""),
        "paragraphs": paragraphs,
        "figures": figures,
        "references": lib.references_from([frag for _, frag in blocks]),
        "word_count": len(body_plain.split()),
        "owner": row.get("owner", ""),
        "year": row.get("year", ""),
        "date_label": row.get("date_label", ""),
    }


def load_registry():
    with open(REGISTRY, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser(description="Extract CFR Follow the Money articles.")
    ap.add_argument("--owner", action="append", default=[], help="registry owner, e.g. sicheng")
    ap.add_argument("--year", action="append", default=[], help="registry year, e.g. 2020")
    ap.add_argument("--url", action="append", default=[], help="ad-hoc CFR article URL")
    ap.add_argument("--all", action="store_true", help="every article in the registry")
    ap.add_argument("--no-cache", action="store_true", help="always re-fetch")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    rows = load_registry()
    selected = []
    if args.all:
        selected = list(rows)
    else:
        if args.owner:
            owners = set(o.lower() for o in args.owner)
            selected += [r for r in rows if r["owner"].lower() in owners]
        if args.year:
            years = set(args.year)
            selected += [r for r in rows if r["year"] in years]
        for url in args.url:
            selected.append({"url": url, "owner": "", "year": "", "title": "", "date_label": ""})

    unique = lib.dedupe(selected)
    if not unique:
        ap.error("nothing selected - pass --owner, --year, --url or --all")

    _, failures = lib.process(
        unique, parse, out_dir=args.out, use_cache=not args.no_cache,
        selector_hint="the body selector (BLOCK_RE)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
