"""Step 1: get the article as numbered paragraphs, using the team's extractor unchanged."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import kb_scripts, path


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

    @property
    def body_sha(self) -> str:
        """Hash of the paragraph text only. The page hash changes with every fetch (ads, tokens)."""
        text = "\n".join(f"{k}\t{v}" for k, v in sorted(self.paras.items()))
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

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
    for p in sorted((path("kb") / "internal" / "extracted").glob("*.md")):
        m = re.search(r"^url:\s*(\S+)", p.read_text(encoding="utf-8", errors="replace"), re.M)
        if m and m.group(1).strip() == url:
            return p
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
    if f is None:                                       # download with the team's extractor
        subprocess.run([sys.executable, "scripts/cfr_extract.py", "--url", url],
                       cwd=path("kb"), check=True)
        f = _extract_for(url)
        if f is None:
            raise SystemExit(f"the extractor wrote nothing for {url}")

    lp = __import__("link_passages")                    # the team's paragraph reader
    raw = f.read_text(encoding="utf-8", errors="replace")
    fm = yaml.safe_load(raw.split("---", 2)[1])
    paras = {}
    for pm in re.finditer(r"<!--\s*p(\d+)\s*-->\s*\n(.*?)(?=\n<!--|\n##|\Z)", raw, re.S):
        body = lp.strip_md(pm.group(2))
        if body:
            paras[int(pm.group(1))] = body
    if not paras:
        raise SystemExit(f"{f.name}: the extractor found no paragraphs")
    authors = list(fm.get("authors") or [])
    date = str(fm.get("date_published") or "")
    if not doc:                                         # a new article: same style as the 2025+ maps
        last = (authors[0].split()[-1] if authors else "author").lower()
        doc = f"{last}_{date}_{fm.get('doc_id')}"
    return Article(doc=doc, url=url, title=str(fm.get("title") or ""), date=date, authors=authors,
                   publisher=str(fm.get("publisher") or ""), series=str(fm.get("series") or ""),
                   paras=paras, figures=_section(raw, "Figures"),
                   references=_section(raw, "References"), file=f)
