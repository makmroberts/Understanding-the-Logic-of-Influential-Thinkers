"""Step 1: get the article as numbered paragraphs, from the repo's parsers and metadata records.

The text comes from the parser for its source (`scripts/parsers/`), which writes the shared
text format to `paths.extracted`. The article's metadata comes from its record in
`paths.records`, written by `scripts/extractors/metadata.py`. Neither is reimplemented here.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import kb_scripts, path, settings


@dataclass
class Article:
    doc: str
    url: str
    title: str
    date: str
    authors: list[str]
    publisher: str
    series: str
    paras: dict[int, str]                       # paragraph number -> text, links reduced to labels
    figures: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    file: Path | None = None
    record: dict = field(default_factory=dict)  # the article's metadata record, as written

    def numbered(self) -> str:
        out = [f"[p{k}] {v}" for k, v in sorted(self.paras.items())]
        if self.figures:
            out += ["", "Charts in the article (titles only):"] + [f"- {f}" for f in self.figures]
        if self.references:
            out += ["", "Works the article links to:"] + [f"- {r}" for r in self.references]
        return "\n".join(out)


def _urls() -> dict[str, str]:
    spec = yaml.safe_load((kb_scripts() / "source_urls.yaml").read_text(encoding="utf-8")) or {}
    return {k: v["url"] for k, v in (spec.get("urls") or {}).items()
            if isinstance(v, dict) and v.get("url")}


def _extract_for(url: str) -> Path | None:
    for p in sorted(path("extracted").glob("*.md")):
        m = re.search(r"^url:\s*(\S+)", p.read_text(encoding="utf-8", errors="replace"), re.M)
        if m and m.group(1).strip() == url:
            return p
    return None


def _record_for(url: str) -> dict | None:
    for p in sorted(path("records").glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec["article"].get("url") == url:
            return rec
    return None


def _section(raw: str, title: str) -> list[str]:
    m = re.search(rf"^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", raw, re.M | re.S)
    if not m:
        return []
    items = re.findall(r"^\d+\.\s+(.*)$", m.group(1), re.M)
    return [re.sub(r"\*\*|\[|\]\([^)]*\)", "", i).strip() for i in items]


def load(doc: str | None = None, url: str | None = None) -> Article:
    """By doc ID (an article listed in kb/scripts/source_urls.yaml) or by URL (any article)."""
    urls = _urls()
    if doc and not url:
        for f in sorted((path("articles") / doc).glob("*/annotation.json")):
            url = json.loads(f.read_text(encoding="utf-8"))["article"]["url"]   # mapped before
        url = urls.get(doc, url)
        if not url:
            raise SystemExit(f"{doc}: no URL in kb/scripts/source_urls.yaml - pass --url instead")
    if not doc:
        doc = next((d for d, u in urls.items() if u == url), None)
    f = _extract_for(url)
    if f is None:                                       # download with the repo's parser
        subprocess.run([sys.executable, settings()["parser"], "--url", url],
                       cwd=path("repo"), check=True)
        f = _extract_for(url)
        if f is None:
            raise SystemExit(f"the parser wrote nothing for {url}")
    record = _record_for(url)
    if record is None:                                  # first time: write its metadata record
        subprocess.run([sys.executable, "scripts/extractors/metadata.py", "--file", str(f)],
                       cwd=path("repo"), check=True)
        record = _record_for(url)
        if record is None:
            raise SystemExit(f"the metadata extractor wrote no record for {url}")

    lp = __import__("link_passages")                    # the team's paragraph reader
    raw = f.read_text(encoding="utf-8", errors="replace")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    paras = {}
    for pm in re.finditer(r"<!--\s*p(\d+)\s*-->\s*\n(.*?)(?=\n<!--|\n##|\Z)", raw, re.S):
        body = lp.strip_md(pm.group(2))
        if body:
            paras[int(pm.group(1))] = body
    if not paras:
        raise SystemExit(f"{f.name}: the parser found no paragraphs")
    meta = record["article"]
    if meta["source_text"]["paragraph_count"] != len(re.findall(r"^<!--\s*p\d+\s*-->", raw, re.M)):
        raise SystemExit(f"{f.name}: the text and its metadata record disagree on paragraph "
                         "count - re-run scripts/extractors/metadata.py")
    authors = list(meta.get("authors") or [])
    date = str(meta.get("published_date") or "")
    if not doc:                                         # a new article: same style as the 2025+ maps
        last = (authors[0].split()[-1] if authors else "author").lower()
        doc = f"{last}_{date}_{fm.get('doc_id')}"
    return Article(doc=doc, url=url, title=str(meta.get("title") or ""), date=date,
                   authors=authors, publisher=str(meta.get("publisher") or ""),
                   series=str(meta.get("series") or ""),
                   paras=paras, figures=_section(raw, "Figures"),
                   references=_section(raw, "References"), file=f, record=record)
