"""Publisher-neutral core for the article extractors.

`cfr_extract.py` was the first extractor and was CFR-specific in four places -
`fetch`, `P_RE`, `parse_jsonld` and `figure_title` - which scripts/README.md
flagged as the thing to split before a second publisher arrived. A second
publisher arrived (Substack, 2026-10-19), so this is that split: everything
that is NOT about one publisher's HTML lives here, and each publisher ships an
adapter that only has to turn a fetched page into a `doc` dict.

Stdlib only, like `cfr_extract.py`, so it runs without a virtualenv. No
`bs4`/`lxml`/`trafilatura`: the parsing stays regex-based on purpose, and an
adapter that stops matching is expected to SAY SO rather than write an empty
file - see `warn_empty` below.

The doc dict an adapter returns:

    url            canonical article URL - the join key to scripts/source_urls.yaml
    slug           doc_id; filename becomes <date>_<slug>.md
    title          headline
    authors        list of names
    publisher      e.g. "Council on Foreign Relations"
    series         e.g. "Follow the Money"   ("" if the publisher has none)
    section        publisher's own section label, or ""
    doc_type       schema.org @type, or a publisher-specific label
    date_published ISO date or datetime; sliced to 10 chars for the frontmatter
    date_modified  same
    paragraphs     ordered list of Markdown paragraphs - these become <!-- pN -->
    figures        [{"title", "src"}]
    references     [{"label", "href"}] in order of appearance
    word_count     int, over the plain-text body
    page_sha256    hash of the fetched page, so a re-extraction is detectable
    owner          who is annotating it, or ""
    date_label     human date from a registry, used only if date_published is ""
    notes          optional list of lines appended to the frontmatter as
                   `extraction_note:` - say here anything a reader needs to know
                   about how this particular page was read

`paragraphs` is the contract that matters downstream: `link_passages.py` reads
`<!-- pN -->` anchors and nothing else, so whatever an adapter decides is a
paragraph is what a claim can cite. Footnotes are a real example - the Substack
adapter emits them as body paragraphs, because a claim whose only source is a
footnote has to be able to anchor to one.
"""

import csv
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "internal", "extracted")
CACHE_DIR = os.path.join(ROOT, "internal", ".cache_html")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CapstoneResearch/1.0 (academic use)"
DELAY_SECONDS = 2.0
RETRIES = 3

A_RE = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
TAG_RE = re.compile(r"<[^>]+>")
# A line break is whitespace, not nothing. Stripping <br> outright fused two
# bare URLs on adjacent lines of a Substack footnote into one unreachable
# string ("...13/4/521https://www.bis.org/..."), so it becomes a space. Verified
# not to change any of the 20 CFR extracts.
BR_RE = re.compile(r"<br\s*/?>", re.I)
# A naked URL in running text is a citation too. Both thinkers do it: Setser
# rarely, Fishman in 7 of his 20 footnote citations, which the <a>-only
# reference inventory could not see at all.
BARE_URL_RE = re.compile(r'(?<![(\w])(https?://[^\s<>")\]]+)')
FIG_RE = re.compile(r"<figure[^>]*>.*?</figure>", re.S)
IMG_SRC_RE = re.compile(r'<img[^>]*src="([^"]+)"')


# ------------------------------------------------------------------ fetching ---

def fetch(url, use_cache=True, cache_dir=CACHE_DIR, ua=UA):
    """Return (page_html, was_cached), caching raw bytes so re-runs are offline.

    The cache is what makes a refactor of this module checkable: every page the
    corpus was built from is still on disk, so the output can be diffed against
    the committed extracts without touching the network.
    """
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = os.path.join(cache_dir, key + ".html")
    if use_cache and os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace"), True

    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            raw = urllib.request.urlopen(req, timeout=60).read()
            with open(path, "wb") as fh:
                fh.write(raw)
            return raw.decode("utf-8", "replace"), False
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(DELAY_SECONDS * attempt * 2)
    raise RuntimeError("fetch failed for %s: %s" % (url, last))


# -------------------------------------------------------------------- text ---

def clean(fragment):
    """Strip tags from an HTML fragment and normalize whitespace."""
    text = html.unescape(TAG_RE.sub("", BR_RE.sub(" ", fragment)))
    return re.sub(r"\s+", " ", text).strip()


def to_markdown(fragment):
    """Strip tags but keep inline <a> as Markdown links.

    Both thinkers in the corpus argue partly by hyperlink: the cited paper or
    dataset *is* the evidence, so the link has to survive into the annotation
    file rather than being flattened to its label.
    """
    def repl(match):
        href = match.group(1)
        inner = clean(match.group(2))
        return "[%s](%s)" % (inner, href) if inner else ""

    replaced = A_RE.sub(repl, BR_RE.sub(" ", fragment))
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", replaced))).strip()


def jsonld(page, script_re=None):
    """First parsable schema.org object on the page.

    CFR tags its block with `id="parsely-*"`; Substack ships a bare
    `type="application/ld+json"` and follows the article object with a
    BreadcrumbList. Scanning every block and returning the first one that has a
    `headline` or `datePublished` handles both without a per-publisher regex,
    so this is shared rather than adapter-local.
    """
    pattern = script_re or re.compile(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
    for m in pattern.finditer(page):
        try:
            obj = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list):
            obj = next((o for o in obj if isinstance(o, dict)), {})
        if isinstance(obj, dict) and (obj.get("headline") or obj.get("datePublished")):
            return obj
    return {}


def ld_authors(ld, default=None):
    """schema.org `author` is a dict, a list of dicts, or a bare string."""
    authors = ld.get("author") or []
    if isinstance(authors, (dict, str)):
        authors = [authors]
    names = []
    for a in authors:
        if isinstance(a, dict) and a.get("name"):
            names.append(a["name"])
        elif isinstance(a, str) and a.strip():
            names.append(a.strip())
    return names or list(default or [])


def references_from(fragments, include_bare=True):
    """Ordered, de-duplicated outbound citations across a sequence of HTML fragments.

    Anchors first, then naked URLs left in the text. `include_bare` exists only
    so a publisher that pastes URLs it does not mean as citations can turn it
    off; both current adapters want it on. Dropping bare URLs cost 7 of the 20
    citations in the first Substack post, all of them in footnotes.
    """
    refs, seen = [], set()
    for frag in fragments:
        for a in A_RE.finditer(frag):
            href = a.group(1)
            if href.startswith("http") and href not in seen:
                seen.add(href)
                refs.append({"label": clean(a.group(2)), "href": href})
        if not include_bare:
            continue
        for m in BARE_URL_RE.finditer(clean(A_RE.sub(" ", frag))):
            href = m.group(1).rstrip(".,;:)")
            if href not in seen:
                seen.add(href)
                refs.append({"label": "", "href": href})
    return refs


def yaml_escape(value):
    return '"%s"' % str(value).replace("\\", "\\\\").replace('"', '\\"')


# ------------------------------------------------------------------ render ---

def render(doc):
    """Markdown file: Stage 1a metadata in frontmatter, Stage 1b left as TODO.

    Publisher-neutral: everything that used to be a CFR literal here now comes
    off the doc dict. The layout is fixed on purpose - `link_passages.py` keys
    on `<!-- pN -->` and `url:`, and `trace.py` quotes the frontmatter, so this
    is an interface, not formatting.
    """
    date_iso = (doc.get("date_published") or "")[:10]
    lines = [
        "---",
        "# Stage 1a - deterministic metadata (parsed, do not hand-edit)",
        "doc_id: %s" % doc["slug"],
        "title: %s" % yaml_escape(doc["title"]),
        "authors: [%s]" % ", ".join(yaml_escape(a) for a in doc["authors"]),
        "publisher: %s" % yaml_escape(doc.get("publisher", "")),
        "series: %s" % yaml_escape(doc.get("series", "")),
        "section: %s" % yaml_escape(doc.get("section", "")),
        "doc_type: %s" % yaml_escape(doc.get("doc_type") or "AnalysisNewsArticle"),
        "date_published: %s" % (date_iso or '""'),
        "date_modified: %s" % ((doc.get("date_modified") or "")[:10] or '""'),
        "language: en",
        "word_count: %d" % doc["word_count"],
        "n_paragraphs: %d" % len(doc["paragraphs"]),
        "n_figures: %d" % len(doc["figures"]),
        "n_references: %d" % len(doc["references"]),
        "url: %s" % doc["url"],
        "retrieved_at: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "page_sha256: %s" % doc["page_sha256"],
        "owner: %s" % (doc.get("owner") or '""'),
    ]
    if doc.get("notes"):
        lines.append("extraction_note: >")
        for note in doc["notes"]:
            lines.append("  %s" % note)
    lines += [
        "",
        "# Stage 1b - inferred metadata (fill in during annotation)",
        "genre: TODO            # paper | note | speech | testimony",
        "topics: []             # fixed list, multi-label",
        "author_role: TODO      # academic | policymaker | strategist",
        "audience: TODO         # policy | market/model | narrative",
        "scope: []              # markets | geography | institutions",
        "time_horizon: TODO     # tactical | cyclical | structural",
        "input_richness: TODO   # score + confidence",
        "---",
        "",
        "# %s" % doc["title"],
        "",
        "*%s - %s - [source](%s)*"
        % (", ".join(doc["authors"]), date_iso or doc.get("date_label", ""), doc["url"]),
        "",
        "## Body",
        "",
    ]

    for i, para in enumerate(doc["paragraphs"], 1):
        lines.append("<!-- p%d -->" % i)
        lines.append(para)
        lines.append("")

    lines += ["## Figures (charts cited as evidence)", ""]
    if doc["figures"]:
        for i, fig in enumerate(doc["figures"], 1):
            lines.append("%d. **%s**  " % (i, fig["title"]))
            lines.append("   %s" % fig["src"])
    else:
        lines.append("_None found._")

    lines += ["", "## References (inline citations, in order)", ""]
    if doc["references"]:
        for i, ref in enumerate(doc["references"], 1):
            lines.append("%d. [%s](%s)" % (i, ref["label"] or ref["href"], ref["href"]))
    else:
        lines.append("_None found._")

    lines += [
        "",
        "## Argument map (Stage 2 - fill in by hand)",
        "",
        "Template: internal/reference/argument_map_template.md",
        "",
    ]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ driver ---

def warn_empty(doc, selector_hint):
    """Say the selector broke. Never write an empty file silently.

    CFR extraction is regex-based and so is Substack's; a restyle shows up as
    zero paragraphs, which would otherwise look like a successful extraction of
    an empty article and quietly zero out every passage link for that doc.
    """
    if not doc["paragraphs"]:
        print("    WARNING: no body paragraphs matched - check %s" % selector_hint)
        return True
    return False


def write_manifest(new_rows, path):
    """Merge `new_rows` into the manifest at `path` on `url`. Returns (path, n).

    MERGED, not overwritten. There is one manifest for one `internal/extracted/`
    directory and now more than one adapter writing into it, so a plain write
    meant whichever extractor ran last erased the other publisher's rows - which
    is exactly what happened the first time the Substack adapter ran, wiping the
    20 CFR rows. Keying on url makes a re-extraction update its own row and
    leave every other row alone.
    """
    existing = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as fh:
            existing = list(csv.DictReader(fh))
    fresh = {r["url"]: r for r in new_rows}
    merged = [r for r in existing if r.get("url") not in fresh] + list(new_rows)
    merged.sort(key=lambda r: (r.get("date_published") or "9999", r.get("doc_id") or ""))

    fields = list(new_rows[0].keys())
    for row in merged:                                  # tolerate an older schema
        for k in row:
            if k not in fields:
                fields.append(k)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)
    return path, len(merged)


def process(rows, parse, out_dir=OUT_DIR, use_cache=True, selector_hint="the selector",
            delay=DELAY_SECONDS, manifest_name="_manifest.csv"):
    """Fetch, parse, render and write each row. Returns (manifest, failures).

    `rows` are dicts carrying at least `url`; anything else (owner, year,
    title, date_label) is passed through to the adapter. `parse(url, page, row)`
    is the adapter.
    """
    os.makedirs(out_dir, exist_ok=True)
    manifest, failures = [], []

    for i, row in enumerate(rows, 1):
        url = row["url"]
        print("[%d/%d] %s" % (i, len(rows), url))
        try:
            page, cached = fetch(url, use_cache=use_cache)
            doc = parse(url, page, row)
            doc["page_sha256"] = hashlib.sha256(page.encode("utf-8", "replace")).hexdigest()
            doc["cached"] = cached
        except Exception as exc:                      # keep going, report at the end
            print("    FAILED: %s" % exc)
            failures.append((url, str(exc)))
            continue

        warn_empty(doc, selector_hint)

        date_iso = (doc.get("date_published") or "")[:10] or "undated"
        name = "%s_%s.md" % (date_iso, doc["slug"])
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(render(doc))

        print("    -> %s  (%d paras, %d words, %d figs, %d refs%s)"
              % (name, len(doc["paragraphs"]), doc["word_count"], len(doc["figures"]),
                 len(doc["references"]), ", cached" if doc["cached"] else ""))
        manifest.append({
            "file": name,
            "doc_id": doc["slug"],
            "owner": doc.get("owner", ""),
            "year": doc.get("year", ""),
            "date_published": date_iso,
            "title": doc["title"],
            "word_count": doc["word_count"],
            "n_paragraphs": len(doc["paragraphs"]),
            "n_figures": len(doc["figures"]),
            "n_references": len(doc["references"]),
            "url": url,
            "page_sha256": doc["page_sha256"],
        })

        if not doc["cached"]:
            time.sleep(delay)

    if manifest and manifest_name:
        mpath = write_manifest(manifest, os.path.join(out_dir, manifest_name))
        print("\nmanifest: %s (%d rows)" % (mpath[0], mpath[1]))

    if failures:
        print("\n%d failure(s):" % len(failures))
        for url, err in failures:
            print("  %s -> %s" % (url, err))

    return manifest, failures


def dedupe(rows):
    """One row per URL, first occurrence wins."""
    seen, unique = set(), []
    for row in rows:
        if row["url"] not in seen:
            seen.add(row["url"])
            unique.append(row)
    return unique
