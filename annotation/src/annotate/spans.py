"""The article's text as its metadata record reads it, and where an excerpt sits inside it.
No model involved.

`read_text` reads an extracted article with the functions of the repository's metadata
extractor (`scripts/extractors/metadata.py`), so paragraph IDs, plain text and hashes are
the record's own. `locate` places an excerpt in a paragraph as character offsets over that
plain text, the same text the record's `references[].char_start/char_end` index. A citation
is then `<article>#p22[0:71]`, checkable against the record and its paragraph hash.

An excerpt is matched with curly quotes and dashes made plain and whitespace collapsed.
The match is found in that normalized text and mapped back, character by character, to the
original. An ellipsis in the excerpt splits it into parts, each its own span, found in order.

    python -m annotate.spans        # self-test of the matching, no files read
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
from pathlib import Path

from .config import path

# One character for one character, so an index into the translated text is an index into
# the original.
_PLAIN = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"',
                        "–": "-", "—": "-", " ": " "})
_ELLIPSIS = re.compile(r"\.\.\.|…")
MIN_PART = 3        # a shorter piece of an excerpt ("a", "of") would match anywhere


def straighten(text: str) -> str:
    """Quotes and dashes made plain, whitespace collapsed: how two copies of a sentence are
    compared when one was retyped by a model."""
    return " ".join(text.translate(_PLAIN).split())


@lru_cache(maxsize=1)
def _metadata():
    """The repository's metadata extractor, imported without changing import priority.

    The extractor puts `scripts/` first on `sys.path` when it loads. `scripts/` also holds
    older copies of the modules this package takes from `kb/scripts/` (`link_passages`,
    `label_facets`), so left there it would shadow them. It is moved to the end instead."""
    scripts = str(path("repo") / "scripts")
    before = list(sys.path)
    sys.path.insert(0, scripts)
    try:
        from extractors import metadata
    finally:
        sys.path[:] = before + ([] if scripts in before else [scripts])
    return metadata


def read_text(file: Path) -> tuple[dict[str, str], dict[str, str], str]:
    """(`p22` -> plain text, `p22` -> paragraph hash, content hash), computed as the metadata
    extractor computes them, so the hashes can be compared with the record's to tell whether
    this text is the one the record describes."""
    m = _metadata()
    body = m.split_frontmatter(Path(file).read_text(encoding="utf-8"))[1]
    plain, hashes, joined = {}, {}, []
    for pid, markdown in m.body_lines(body)[0]:
        text = m.links_and_plain(markdown)[0]
        clean = m.normalized(text)
        plain[pid], hashes[pid] = text, m.sha256(clean)
        joined.append(clean)
    return plain, hashes, m.sha256("\n".join(joined))


def _collapsed(text: str) -> tuple[str, list[int]]:
    """`straighten(text)`, and for each of its characters the index it came from."""
    out, where, pending = [], [], None
    for i, ch in enumerate(text.translate(_PLAIN)):
        if ch.isspace():
            if out:                          # leading whitespace is dropped
                pending = i                  # a run of whitespace becomes one space
            continue
        if pending is not None:
            out.append(" ")
            where.append(pending)
            pending = None
        out.append(ch)
        where.append(i)
    return "".join(out), where


def _spaceless(text: str) -> tuple[str, list[int]]:
    """The same with no whitespace at all."""
    kept = [(ch, i) for i, ch in enumerate(text.translate(_PLAIN)) if not ch.isspace()]
    return "".join(ch for ch, _ in kept), [i for _, i in kept]


def locate(excerpt: str, text: str, loose: bool = False) -> list[dict] | None:
    """[{char_start, char_end}] for each part of the excerpt, in order; None if a part is
    missing or the excerpt has no part of `MIN_PART` characters. Step 2 uses this to check
    that an excerpt is word for word, so finding it and placing it are one operation.

    `loose` retries with all whitespace removed. Only saved runs need it: two were
    annotated on parser output from before source revision 2, which dropped the space
    before a link ("all ofBrazil's"), and the model copied that faithfully. The span still
    points at the article's own characters. A new run is held to the exact words."""
    parts = [p for p in (straighten(x) for x in _ELLIPSIS.split(excerpt)) if len(p) >= MIN_PART]
    if not parts:
        return None
    readings = [(_collapsed(text), parts)]
    if loose:
        readings.append((_spaceless(text), [p.replace(" ", "") for p in parts]))
    for (norm, where), wanted in readings:
        spans, cursor = [], 0
        for part in wanted:
            at = norm.find(part, cursor)
            if at < 0:
                break
            cursor = at + len(part)
            spans.append({"char_start": where[at], "char_end": where[cursor - 1] + 1})
        else:
            return spans
    return None


def check(spans: list[dict], excerpt: str, text: str) -> bool:
    """The spans, read back from the text, give the excerpt's characters, whitespace aside.
    Run on every span before it is saved, whoever computed it."""
    def squash(s: str) -> str:
        return "".join(_ELLIPSIS.sub("", s.translate(_PLAIN)).split())
    parts = [p for p in _ELLIPSIS.split(excerpt) if len(straighten(p)) >= MIN_PART]
    got = "".join(text[s["char_start"]:s["char_end"]] for s in spans)
    return bool(spans) and squash(got) == squash("".join(parts))


def _selftest() -> None:
    text = "  He said “the  gap” is not offset — at all.  Rather, it grew."
    cases = [
        ('"the gap" is not offset', False, ["“the  gap” is not offset"]),   # quotes, spacing
        ("is not offset - at all", False, ["is not offset — at all"]),            # dash, nbsp
        ("He said ... Rather, it grew.", False, ["He said", "Rather, it grew."]),           # ellipsis
        ("Rather, it grew. … He said", False, None),                                   # parts out of order
        ("isnot offset", False, None),                                                      # glued: strict fails
        ("isnot offset", True, ["is not offset"]),                                     # glued: loose places it
        ("not in the text", False, None),
        ("… a …", False, None),                                                   # nothing long enough
    ]
    for excerpt, loose, want in cases:
        spans = locate(excerpt, text, loose=loose)
        got = spans and [text[s["char_start"]:s["char_end"]] for s in spans]
        assert got == want, (excerpt, loose, got, want)
        assert spans is None or check(spans, excerpt, text), (excerpt, spans)
    assert not check([{"char_start": 0, "char_end": 5}], "the gap", text)
    print(f"spans self-test: {len(cases)} cases ok")


if __name__ == "__main__":
    _selftest()
