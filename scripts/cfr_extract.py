"""Extract CFR "Follow the Money" articles into annotation-ready Markdown.

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
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "scripts", "sources_followthemoney.csv")
OUT_DIR = os.path.join(ROOT, "internal", "extracted")
CACHE_DIR = os.path.join(ROOT, "internal", ".cache_html")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CapstoneResearch/1.0 (academic use)"
DELAY_SECONDS = 2.0
RETRIES = 3

# CFR renders body copy as <p class="rich-text ...">. Verified Sept 2026 against
# the 2020 and 2024 articles; see scripts/README.md if this stops matching.
P_RE = re.compile(r'<p[^>]*class="rich-text[^"]*"[^>]*>(.*?)</p>', re.S)
FIG_RE = re.compile(r"<figure[^>]*>.*?</figure>", re.S)
IMG_SRC_RE = re.compile(r'<img[^>]*src="([^"]+)"')
A_RE = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
LD_RE = re.compile(
    r'<script[^>]*id="parsely-[^"]*"[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
    re.S,
)
TAG_RE = re.compile(r"<[^>]+>")


def fetch(url, use_cache=True):
    """Return page HTML, caching raw bytes so re-runs do not re-hit CFR."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    path = os.path.join(CACHE_DIR, key + ".html")
    if use_cache and os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace"), True

    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=60).read()
            with open(path, "wb") as fh:
                fh.write(raw)
            return raw.decode("utf-8", "replace"), False
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(DELAY_SECONDS * attempt * 2)
    raise RuntimeError("fetch failed for %s: %s" % (url, last))


def clean(fragment):
    """Strip tags from an HTML fragment and normalize whitespace."""
    text = html.unescape(TAG_RE.sub("", fragment))
    return re.sub(r"\s+", " ", text).strip()


def to_markdown(fragment):
    """Strip tags but keep inline <a> as Markdown links.

    Setser argues largely by hyperlink: the cited paper *is* the evidence, so
    the link has to survive into the annotation file.
    """

    def repl(match):
        href = match.group(1)
        inner = clean(match.group(2))
        return "[%s](%s)" % (inner, href) if inner else ""

    replaced = A_RE.sub(repl, fragment)
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", replaced))).strip()


def parse_jsonld(page):
    match = LD_RE.search(page)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def figure_title(src):
    """CFR names chart files after the chart title, so the filename is the caption."""
    name = urllib.parse.unquote(src.rsplit("/", 1)[-1])
    name = re.sub(r"_\d+(?=\.)", "", name)
    name = re.sub(r"\.(png|jpe?g|gif|webp|svg)$", "", name, flags=re.I)
    return name.strip()


def yaml_escape(value):
    return '"%s"' % str(value).replace("\\", "\\\\").replace('"', '\\"')


def extract(url, row=None, use_cache=True):
    page, cached = fetch(url, use_cache=use_cache)
    ld = parse_jsonld(page)
    row = row or {}

    paragraphs = [to_markdown(m.group(1)) for m in P_RE.finditer(page)]
    paragraphs = [p for p in paragraphs if p]
    body_plain = " ".join(clean(m.group(1)) for m in P_RE.finditer(page))

    figures = []
    for fig in FIG_RE.finditer(page):
        src = IMG_SRC_RE.search(fig.group(0))
        if src and "static.cfr.org" in src.group(1):
            figures.append({"title": figure_title(src.group(1)), "src": src.group(1)})

    refs = []
    seen = set()
    for m in P_RE.finditer(page):
        for a in A_RE.finditer(m.group(1)):
            href = a.group(1)
            label = clean(a.group(2))
            if href.startswith("http") and href not in seen:
                seen.add(href)
                refs.append({"label": label, "href": href})

    authors = ld.get("author") or []
    if isinstance(authors, dict):
        authors = [authors]
    author_names = [a.get("name", "") for a in authors if isinstance(a, dict)]

    return {
        "url": url,
        "slug": url.rstrip("/").rsplit("/", 1)[-1],
        "title": ld.get("headline") or row.get("title", ""),
        "authors": author_names or ["Brad W. Setser"],
        "date_published": ld.get("datePublished", ""),
        "date_modified": ld.get("dateModified", ""),
        "section": ld.get("articleSection", ""),
        "doc_type": ld.get("@type", ""),
        "paragraphs": paragraphs,
        "figures": figures,
        "references": refs,
        "word_count": len(body_plain.split()),
        "page_sha256": hashlib.sha256(page.encode("utf-8", "replace")).hexdigest(),
        "cached": cached,
        "owner": row.get("owner", ""),
        "year": row.get("year", ""),
        "date_label": row.get("date_label", ""),
    }


def render(doc):
    """Markdown file: Stage 1a metadata in frontmatter, Stage 1b left as TODO."""
    date_iso = (doc["date_published"] or "")[:10]
    lines = [
        "---",
        "# Stage 1a - deterministic metadata (parsed, do not hand-edit)",
        "doc_id: %s" % doc["slug"],
        "title: %s" % yaml_escape(doc["title"]),
        "authors: [%s]" % ", ".join(yaml_escape(a) for a in doc["authors"]),
        "publisher: %s" % yaml_escape("Council on Foreign Relations"),
        "series: %s" % yaml_escape("Follow the Money"),
        "section: %s" % yaml_escape(doc["section"]),
        "doc_type: %s" % yaml_escape(doc["doc_type"] or "AnalysisNewsArticle"),
        "date_published: %s" % (date_iso or '""'),
        "date_modified: %s" % ((doc["date_modified"] or "")[:10] or '""'),
        "language: en",
        "word_count: %d" % doc["word_count"],
        "n_paragraphs: %d" % len(doc["paragraphs"]),
        "n_figures: %d" % len(doc["figures"]),
        "n_references: %d" % len(doc["references"]),
        "url: %s" % doc["url"],
        "retrieved_at: %s" % datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "page_sha256: %s" % doc["page_sha256"],
        "owner: %s" % (doc["owner"] or '""'),
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
        % (", ".join(doc["authors"]), date_iso or doc["date_label"], doc["url"]),
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

    seen = set()
    unique = []
    for row in selected:
        if row["url"] not in seen:
            seen.add(row["url"])
            unique.append(row)

    if not unique:
        ap.error("nothing selected - pass --owner, --year, --url or --all")

    os.makedirs(args.out, exist_ok=True)
    manifest = []
    failures = []

    for i, row in enumerate(unique, 1):
        url = row["url"]
        print("[%d/%d] %s" % (i, len(unique), url))
        try:
            doc = extract(url, row=row, use_cache=not args.no_cache)
        except Exception as exc:  # keep going, report at the end
            print("    FAILED: %s" % exc)
            failures.append((url, str(exc)))
            continue

        if not doc["paragraphs"]:
            print("    WARNING: no body paragraphs matched - check the selector")

        date_iso = (doc["date_published"] or "")[:10] or "undated"
        name = "%s_%s.md" % (date_iso, doc["slug"])
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as fh:
            fh.write(render(doc))

        print(
            "    -> %s  (%d paras, %d words, %d figs, %d refs%s)"
            % (
                name,
                len(doc["paragraphs"]),
                doc["word_count"],
                len(doc["figures"]),
                len(doc["references"]),
                ", cached" if doc["cached"] else "",
            )
        )
        manifest.append(
            {
                "file": name,
                "doc_id": doc["slug"],
                "owner": doc["owner"],
                "year": doc["year"],
                "date_published": date_iso,
                "title": doc["title"],
                "word_count": doc["word_count"],
                "n_paragraphs": len(doc["paragraphs"]),
                "n_figures": len(doc["figures"]),
                "n_references": len(doc["references"]),
                "url": url,
                "page_sha256": doc["page_sha256"],
            }
        )

        if not doc["cached"]:
            time.sleep(DELAY_SECONDS)

    if manifest:
        mpath = os.path.join(args.out, "_manifest.csv")
        with open(mpath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(manifest[0].keys()))
            writer.writeheader()
            writer.writerows(manifest)
        print("\nmanifest: %s (%d rows)" % (mpath, len(manifest)))

    if failures:
        print("\n%d failure(s):" % len(failures))
        for url, err in failures:
            print("  %s -> %s" % (url, err))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
