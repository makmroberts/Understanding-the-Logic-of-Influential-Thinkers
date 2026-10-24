#!/usr/bin/env python3
"""Open every mapped URL and check it is the article the map claims it is.

    python scripts/verify_urls.py                 # verify, write the report
    python scripts/verify_urls.py --no-cache      # refetch

Reads   scripts/source_urls.yaml, data/documents.csv
Writes  data/url_verification.md

The URL join in scripts/source_urls.yaml was solved as a 1-1 assignment over
titles and dates. That is an inference about which page a map describes, and an
inference is not provenance until somebody checks it. This fetches each page
and compares what CFR actually publishes - headline and datePublished, from the
page's own JSON-LD - against what the overlay asserts.

Reuses cfr_extract.py's fetch and JSON-LD parsing, so it shares the same cache
in internal/.cache_html/ and does not re-hit CFR on a re-run.

Entries under `needs_review:` are fetched too, and are the whole point: one
map's URL was assigned by elimination with no supporting evidence, and opening
the page is the only way to settle it.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml

try:
    from cfr_extract import fetch, parse_jsonld
except ImportError as exc:
    sys.exit(f"could not import cfr_extract: {exc}")

ROOT = Path(__file__).resolve().parent.parent
URL_MAP = ROOT / "scripts" / "source_urls.yaml"
DOCS = ROOT / "data" / "documents.csv"   # written by parse_maps.py
OUT = ROOT / "data" / "url_verification.md"

STOP = set("""a an and the of in to for on at by or as is are be been it its do
does did still now than that their they them what why how will can could would
may might with from when where which who this those these not no but if then so
such more most one two i he she his her our your you""".split())


def toks(text: str) -> set:
    text = text.lower().replace("u.s.", "us").replace("-", " ")
    return {w for w in re.findall(r"[a-z0-9']+", text)
            if w not in STOP and len(w) > 1}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    spec = yaml.safe_load(URL_MAP.read_text(encoding="utf-8")) or {}
    docs = {r["id"]: r for r in csv.DictReader(DOCS.open(encoding="utf-8"))}

    targets = []
    for stem, entry in (spec.get("urls") or {}).items():
        targets.append((stem, entry["url"], "confirmed"))
    for stem, entry in (spec.get("needs_review") or {}).items():
        u = entry.get("candidate_url") or entry.get("url")
        if u:
            targets.append((stem, u, "needs_review"))

    rows = []
    for stem, url, status in targets:
        d = docs.get(stem, {})
        map_date = d.get("date", "")
        map_title = d.get("title", "")
        try:
            page, cached = fetch(url, use_cache=not args.no_cache)
            http = "200"
        except Exception as exc:                      # noqa: BLE001
            rows.append({"stem": stem, "url": url, "status": status,
                         "http": f"FAILED ({exc})", "headline": "", "pub": "",
                         "map_date": map_date, "verdict": "UNREACHABLE"})
            print(f"  {stem:42} FETCH FAILED")
            continue

        ld = parse_jsonld(page) or {}
        headline = (ld.get("headline") or ld.get("title") or "").strip()
        pub = (ld.get("datePublished") or "").strip()[:10]

        # does the page's own date agree with the map's filename date?
        if pub and map_date:
            date_ok = pub == map_date
            near = abs(int(pub[:4]) - int(map_date[:4])) == 0 and \
                abs(int(pub[5:7]) - int(map_date[5:7])) <= 1
        else:
            date_ok = near = False

        sim = 0.0
        if headline and map_title:
            a, b = toks(map_title), toks(headline)
            sim = len(a & b) / max(1, min(len(a), len(b)))

        if not headline:
            verdict = "NO METADATA on page"
        elif date_ok:
            verdict = "CONFIRMED - date exact"
        elif near:
            verdict = "CONFIRMED - date within a month"
        elif sim >= 0.5:
            verdict = "TITLE MATCHES but date differs"
        else:
            verdict = "MISMATCH - check by hand"

        rows.append({"stem": stem, "url": url, "status": status, "http": http,
                     "headline": headline, "pub": pub, "map_date": map_date,
                     "sim": sim, "verdict": verdict})
        tag = "cached" if cached else "fetched"
        print(f"  {stem:42} {pub or '????-??-??'}  {verdict}  ({tag})")

    ok = sum(1 for r in rows if r["verdict"].startswith("CONFIRMED"))
    bad = [r for r in rows if not r["verdict"].startswith("CONFIRMED")]

    L = ["# URL verification", "",
         "Every mapped URL opened, and what CFR actually publishes there "
         "compared against",
         "what `scripts/source_urls.yaml` asserts. Headline and date come from "
         "each page's",
         "own JSON-LD. Generated by `scripts/verify_urls.py`.", "",
         f"**{ok} of {len(rows)} confirmed by the published date.**", "",
         "| map | map date | published | page headline | verdict |",
         "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["map_date"]):
        h = (r["headline"] or "-")[:52]
        L.append(f"| `{r['stem']}` | {r['map_date']} | {r['pub'] or '-'} "
                 f"| {h} | {r['verdict']} |")
    if bad:
        L += ["", "## Not confirmed", ""]
        for r in bad:
            L += [f"### `{r['stem']}` — {r['verdict']}", "",
                  f"- overlay status: **{r['status']}**",
                  f"- url: {r['url']}",
                  f"- map date: {r['map_date']}  ·  page date: "
                  f"{r['pub'] or '(none found)'}",
                  f"- page headline: {r['headline'] or '(none found)'}",
                  f"- map title: {docs.get(r['stem'], {}).get('title', '')}", ""]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print()
    print(f"{ok}/{len(rows)} confirmed by published date")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
