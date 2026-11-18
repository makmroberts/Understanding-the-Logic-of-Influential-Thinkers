"""Extract CFR "Follow the Money" articles into annotation-ready Markdown.

The first publisher adapter. Everything publisher-neutral - fetching, the HTML
cache, `to_markdown`, `render`, the driver - moved to `extract_lib.py` on
2026-10-19 when a second publisher arrived; what is left here is only the part
that knows how CFR builds a page. Output is byte-identical to the pre-split
version (verified against all 20 cached pages, `retrieved_at` excepted since it
is a clock reading).

Stdlib only, so it runs anywhere without a virtualenv. Output is one Markdown
file per article: YAML frontmatter carrying the deterministic (Stage 1a)
metadata, then the body with inline citations preserved, then the figure and
reference inventories that Level 2 (Evidence) annotation depends on.

Usage:
    python scripts/cfr_extract.py --owner sicheng
    python scripts/cfr_extract.py --year 2020 --year 2024
    python scripts/cfr_extract.py --all
    python scripts/cfr_extract.py --url https://www.cfr.org/articles/<slug>

See scripts/README.md for what is verified to work and what the future
large-scale skill will need to change.
"""

import argparse
import csv
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract_lib as lib

ROOT = lib.ROOT
REGISTRY = os.path.join(ROOT, "scripts", "sources_followthemoney.csv")
OUT_DIR = lib.OUT_DIR

# CFR renders body copy as <p class="rich-text ...">. Verified Sept 2026 against
# the 2020 and 2024 articles; see scripts/README.md if this stops matching.
P_RE = re.compile(r'<p[^>]*class="rich-text[^"]*"[^>]*>(.*?)</p>', re.S)

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


def parse(url, page, row=None):
    """CFR page -> the doc dict `extract_lib.render` expects."""
    row = row or {}
    ld = lib.jsonld(page, script_re=LD_RE)

    paragraphs = [p for p in (lib.to_markdown(m.group(1)) for m in P_RE.finditer(page)) if p]
    body_plain = " ".join(lib.clean(m.group(1)) for m in P_RE.finditer(page))

    figures = []
    for fig in lib.FIG_RE.finditer(page):
        src = lib.IMG_SRC_RE.search(fig.group(0))
        if src and "static.cfr.org" in src.group(1):
            figures.append({"title": figure_title(src.group(1)), "src": src.group(1)})

    return {
        "url": url,
        "slug": url.rstrip("/").rsplit("/", 1)[-1],
        "title": ld.get("headline") or row.get("title", ""),
        "authors": lib.ld_authors(ld, default=["Brad W. Setser"]),
        "publisher": "Council on Foreign Relations",
        "series": "Follow the Money",
        "section": ld.get("articleSection", ""),
        "doc_type": ld.get("@type", ""),
        "date_published": ld.get("datePublished", ""),
        "date_modified": ld.get("dateModified", ""),
        "paragraphs": paragraphs,
        "figures": figures,
        "references": lib.references_from([m.group(1) for m in P_RE.finditer(page)]),
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
        selector_hint="the `rich-text` selector (P_RE)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
