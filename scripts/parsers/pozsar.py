"""Parse Zoltan Pozsar's Credit Suisse "Global Money Notes" PDFs into the shared text format.

The first PDF parser. HTML parsers read structure the publisher marked up; a PDF
has only positioned text, so structure is recovered from layout, in fixed rules:

    paragraph   a vertical gap wider than 1.35x the font size starts a new one
    heading     bold and larger than the body size
    body text   within 0.6pt of the document's most common font size
    furniture   lines repeated on three or more pages, and the header and footer bands
    link        a URI annotation, attached to the text fragments inside its rectangle

Requires pypdf. Input PDFs are local and never committed.

Usage:
    python scripts/parsers/pozsar.py --input <pdf dir> --source-index <manifest.json>
    python scripts/parsers/pozsar.py --input <pdf dir> --check     # parse, report, write nothing
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

from pypdf import PdfReader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsers import common as lib

PUBLISHER = "Credit Suisse"
SERIES = "Global Money Notes"
HEADER_Y = 735
FOOTER_Y = 45
PARAGRAPH_GAP = 1.35       # multiple of the font size
SAME_LINE = 2.0            # points of vertical tolerance within one line
REPEATED_ON = 3
MARGIN_INDENT = 45         # body lines start at the page's text margin, or indented up to this
CHAR_WIDTH = 0.47          # average glyph width as a share of font size
MAX_SNAP = 8               # characters to search for a word boundary
MAX_RAISE = 7              # points a superscript sits above its line

MONTHS = ("January February March April May June July August September October "
          "November December").split()
DATE_RE = re.compile(r"\b(\d{1,2}) (%s) (\d{4})\b" % "|".join(MONTHS))
SERIES_RE = re.compile(r"^Global Money Notes\s*#\s*(\d+)$")
NAME_RE = re.compile(r"^[A-Z][\w.'-]*(?: [A-Z][\w.'-]*)+$")
FIGURE_RE = re.compile(r"^Figures?\s*\d+\s*[:.]")
TERMINAL_RE = re.compile(r"[.?!:;…”\"\)]$")
# A page carrying one of these is legal boilerplate, wherever it sits.
DISCLAIMER_RE = re.compile(
    r"has not been prepared in accordance with|Disclosure Appendix|ANALYST CERTIFICATION", re.I)
AUTHOR_BLOCK_RE = re.compile(r"^(CONTRIBUTORS?|Research Analysts?)\b", re.I)
LETTERS_RE = re.compile(r"[A-Za-z]{2}")
DEPARTMENT_RE = re.compile(r"\b(Research|Economics|Strategy|Analysts?|Global|Income|Solutions|Credit|Suisse|Information)\b")
# Everything after this line is boilerplate.
STOP_RE = re.compile(r"^(Additional Important Information|General disclaimer|Important disclosures)", re.I)


class Line:
    """One row of text: ordered (text, uri) tokens plus its position and font."""

    def __init__(self, y, x, size, bold, page):
        self.y, self.x, self.size, self.bold, self.page = y, x, size, bold, page
        self.tokens = []

    @property
    def text(self):
        return re.sub(r"\s+", " ", "".join(t for t, _ in self.tokens)).strip()


def page_uris(page):
    """[(x0, y0, x1, y1, uri)] for each hyperlink annotation on a page."""
    out = []
    for ref in page.get("/Annots") or []:
        annot = ref.get_object()
        action = annot.get("/A")
        action = action.get_object() if action is not None else None
        if action is None or action.get("/URI") is None or annot.get("/Rect") is None:
            continue
        x0, y0, x1, y1 = (float(v) for v in annot["/Rect"])
        out.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), str(action["/URI"]).strip()))
    return out


def snap(piece, i):
    """The word boundary nearest to character i."""
    for step in range(MAX_SNAP):
        for j in (i - step, i + step):
            if 0 <= j <= len(piece) and (
                    j in (0, len(piece)) or piece[j - 1].isspace() or piece[j].isspace()):
                return j
    return max(0, min(i, len(piece)))


def link_tokens(piece, x, y, size, uris):
    """Split a text run at its link rectangles. Returns [(text, uri)].

    pypdf reports where a run starts but not how wide its glyphs are, so link
    edges are estimated from an average character width and snapped to the nearest
    word. The URL and its location are exact; the label's edges are approximate.
    """
    if not piece.strip():
        return [(piece, None)]
    width = max(size * CHAR_WIDTH, 0.1)
    end = x + len(piece) * width
    tokens, cursor = [], 0
    for x0, y0, x1, y1, uri in sorted(uris):
        if not (y0 - 2 <= y <= y1 + 2) or x1 < x - 1 or x0 > end:
            continue
        start = 0 if x0 <= x + 1 else snap(piece, round((x0 - x) / width))
        stop = len(piece) if x1 >= end else snap(piece, round((x1 - x) / width))
        start = max(start, cursor)
        while stop > start and piece[stop - 1] in " .,;:)":
            stop -= 1
        if stop <= start:
            continue
        if start > cursor:
            tokens.append((piece[cursor:start], None))
        tokens.append((piece[start:stop], uri))
        cursor = stop
    if cursor < len(piece):
        tokens.append((piece[cursor:], None))
    return tokens


def is_superscript(line, y, size):
    return size <= line.size - 2 and 0 < y - line.y <= MAX_RAISE


def read_lines(page, page_no):
    """The page's text rows, in the order the PDF draws them."""
    uris = page_uris(page)
    fragments = []

    def visit(text, cm, tm, font, size):
        if text:
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            name = str((font or {}).get("/BaseFont", "")) if font else ""
            fragments.append((text, x, y, name, size * abs(tm[3] or 1)))

    page.extract_text(visitor_text=visit)

    lines, current = [], None
    for text, x, y, name, size in fragments:
        for piece in re.split(r"(\n)", text):
            if piece == "\n" or not piece:
                continue
            if current is not None and is_superscript(current, y, size):
                if not piece.strip().isdigit():       # keep "th", drop footnote marks
                    current.tokens.append((piece, None))
                continue
            taller = current is not None and current.text and size > current.size + 2
            if current is None or abs(current.y - y) > SAME_LINE or (piece.strip() and taller):
                current = Line(y, x, size, "Bold" in name, page_no)
                lines.append(current)
            if piece.strip() and not current.text:
                current.x, current.size, current.bold = x, size, "Bold" in name
            current.tokens.extend(link_tokens(piece, x, y, size, uris))
    return [line for line in lines if line.text]


def body_size(pages):
    sizes = Counter()
    for lines in pages:
        for line in lines:
            sizes[round(line.size, 1)] += len(line.text)
    return sizes.most_common(1)[0][0] if sizes else 0


def text_margin(pages, size):
    """The x position where the most body-sized text starts."""
    starts = Counter()
    for lines in pages:
        for line in lines:
            if abs(line.size - size) <= 0.6:
                starts[round(line.x)] += len(line.text)
    return starts.most_common(1)[0][0] if starts else 0


def furniture(pages):
    """Texts on three or more pages are running headers or footers."""
    seen = Counter()
    for lines in pages:
        seen.update({re.sub(r"\d+$", "", line.text).strip() for line in lines})
    return {text for text, n in seen.items() if n >= REPEATED_ON and text}


def header_fields(first_page, size):
    """(title, issue, date, authors, index of the last title line)."""
    main = first_page
    date = next((m for m in (DATE_RE.search(line.text) for line in first_page) if m), None)
    iso = "%s-%02d-%02d" % (date.group(3), MONTHS.index(date.group(2)) + 1, int(date.group(1))) if date else ""

    issue, title_lines, last = "", [], -1
    for i, line in enumerate(main):
        if line.size < size + 1.5 or not line.bold:
            if title_lines and line.size <= size + 0.6:
                break
            continue
        series = SERIES_RE.match(line.text)
        if series:
            issue = series.group(1)
        else:
            title_lines.append(line.text)
        last = i

    authors, in_block = [], False
    for line in first_page:
        if AUTHOR_BLOCK_RE.match(line.text):
            in_block = True
        elif (in_block and line.bold and NAME_RE.match(line.text)
              and not DEPARTMENT_RE.search(line.text) and line.text not in authors):
            authors.append(line.text)
    return " ".join(title_lines), issue, iso, authors, main, last


def build_paragraphs(pages, size, repeated, first_main, title_end):
    """Group kept lines into paragraphs. Returns (paragraphs, figures, dropped lines)."""
    margin = text_margin(pages, size)
    paragraphs, figures, dropped = [], [], 0
    current, prev = None, None

    def close():
        nonlocal current
        if current:
            paragraphs.append(current)
        current = None

    for page_index, lines in enumerate(pages):
        if page_index and any(DISCLAIMER_RE.search(line.text) for line in lines):
            close()
            prev = None
            continue
        body = first_main[title_end + 1:] if page_index == 0 else lines
        for line in body:
            text = line.text
            if STOP_RE.match(text):
                close()
                return paragraphs, figures, dropped
            if (line.y > HEADER_Y or line.y < FOOTER_Y
                    or re.sub(r"\d+$", "", text).strip() in repeated
                    or DISCLAIMER_RE.search(text) or text == "Important Information"):
                continue
            if FIGURE_RE.match(text):
                close()
                figures.append({"title": text, "src": "page-%d" % (page_index + 1),
                                "after": len(paragraphs)})
                prev = None
                continue
            heading = line.bold and line.size >= size + 1
            at_margin = margin - 3 <= line.x <= margin + MARGIN_INDENT
            if not heading and (abs(line.size - size) > 0.6 or not at_margin
                                or not LETTERS_RE.search(text)):
                dropped += 1
                continue

            same_page = prev is not None and prev.page == line.page
            starts_new = (
                current is None or heading or prev_heading(prev, size)
                or (same_page and (prev.y - line.y > line.size * PARAGRAPH_GAP or abs(line.x - prev.x) > 8))
                or (not same_page and (TERMINAL_RE.search(prev.text) or not text[:1].islower()))
            )
            if starts_new:
                close()
                current = list(line.tokens)
            else:
                join_line(current, line.tokens)
            prev = line
    close()
    return paragraphs, figures, dropped


def prev_heading(prev, size):
    return prev.bold and prev.size >= size + 1


def join_line(tokens, new):
    """Append a line. A trailing hyphen joins directly; otherwise add a single space."""
    tail = "".join(t for t, _ in tokens).rstrip()
    first_uri = next((u for t, u in new if t.strip()), None)
    last_uri = next((u for t, u in reversed(tokens) if t.strip()), None)
    if tail.endswith("-"):
        while tokens and not tokens[-1][0].strip():
            tokens.pop()
        tokens[-1] = (re.sub(r"\s+-$", "-", tokens[-1][0].rstrip()), tokens[-1][1])
    else:
        tokens.append((" ", first_uri if first_uri and first_uri == last_uri else None))
    tokens.extend(new)


def to_markdown(tokens):
    """Tokens -> one Markdown paragraph, with each run of the same URI as a link."""
    runs = []
    for i, (text, uri) in enumerate(tokens):
        if not text.strip() and runs and runs[-1][1]:       # a space inside one link
            following = next((u for t, u in tokens[i + 1:] if t.strip()), None)
            uri = runs[-1][1] if following == runs[-1][1] else None
        if runs and runs[-1][1] == uri:
            runs[-1][0] += text
        else:
            runs.append([text, uri])
    out = []
    for text, uri in runs:
        if uri and text.strip():
            lead = " " if text[:1].isspace() else ""
            trail = " " if text[-1:].isspace() else ""
            out.append("%s[%s](%s)%s" % (lead, re.sub(r"\s+", " ", text).strip(), uri, trail))
        else:
            out.append(text)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def references(paragraphs):
    """Ordered, de-duplicated citations from the finished Markdown."""
    refs, seen = [], set()
    md = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
    for para in paragraphs:
        for label, href in md.findall(para):
            if href not in seen:
                seen.add(href)
                refs.append({"label": label, "href": href})
        for m in lib.BARE_URL_RE.finditer(md.sub(" ", para)):
            href = m.group(1).rstrip(".,;:)")
            if href not in seen:
                seen.add(href)
                refs.append({"label": "", "href": href})
    return refs


def slug_of(title, issue, stem):
    base = re.sub(r"[^a-z0-9]+", "-", (title or stem).lower()).strip("-")[:70].strip("-")
    return ("gmn-%s-%s" % (issue, base)) if issue else "gmn-%s" % base


def parse(path, source_url="", fetched_at=""):
    """PDF path -> the doc dict `common.render` expects."""
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    reader = PdfReader(path)
    pages = [read_lines(page, i) for i, page in enumerate(reader.pages)]
    size = body_size(pages)
    repeated = furniture(pages)
    title, issue, date, authors, main, last = header_fields(pages[0], size)
    token_paras, figures, dropped = build_paragraphs(pages, size, repeated, main, last)
    paragraphs = [p for p in (to_markdown(t) for t in token_paras) if p]
    plain = " ".join(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", p) for p in paragraphs)
    stem = os.path.splitext(os.path.basename(path))[0]
    return {
        "url": source_url,
        "slug": slug_of(title, issue, stem),
        "title": title,
        "authors": authors,
        "publisher": PUBLISHER,
        "series": SERIES if issue else "",
        "section": "Global Money Notes #%s" % issue if issue else "",
        "doc_type": "PDF",
        "date_published": date,
        "date_modified": "",
        "paragraphs": paragraphs,
        "figures": figures,
        "references": references(paragraphs),
        "word_count": len(plain.split()),
        "page_sha256": digest,
        "retrieved_at": fetched_at or datetime.fromtimestamp(
            os.path.getmtime(path), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner": "",
        "notes": ["Parsed from PDF layout: paragraphs come from line spacing, so a break "
                  "can be wrong where a figure or page interrupts a paragraph.",
                  "Link locations are exact, but label edges are estimated from character width.",
                  "%d lines outside the body text were dropped (chart labels, footnotes, sources)." % dropped],
    }


def main():
    ap = argparse.ArgumentParser(description="Parse Global Money Notes PDFs.")
    ap.add_argument("--input", required=True, help="directory of PDFs")
    ap.add_argument("--source-index", help="manifest.json with note, source and fetched_at")
    ap.add_argument("--out", default=lib.OUT_DIR)
    ap.add_argument("--check", action="store_true", help="parse and report, write nothing")
    args = ap.parse_args()

    index = {}
    if args.source_index:
        with open(args.source_index, encoding="utf-8") as fh:
            index = {int(r["note"]): r for r in json.load(fh)}

    bad = 0
    names = sorted(n for n in os.listdir(args.input) if n.lower().endswith(".pdf"))
    if not args.check:
        os.makedirs(args.out, exist_ok=True)
    rows = []
    for name in names:
        number = int(re.sub(r"\D", "", name) or 0)
        entry = index.get(number, {})
        doc = parse(os.path.join(args.input, name), entry.get("source", ""),
                    (entry.get("fetched_at") or "")[:19] + "Z" if entry.get("fetched_at") else "")
        if lib.warn_empty(doc, "the layout rules in parsers/pozsar.py"):
            bad += 1
        print("%-8s %s  %s | %s | %d paras, %d figs, %d refs | %s"
              % (name, doc["date_published"] or "NODATE", doc["slug"][:44], ", ".join(doc["authors"]) or "NOAUTHOR",
                 len(doc["paragraphs"]), len(doc["figures"]), len(doc["references"]), doc["title"][:44] or "NOTITLE"))
        if args.check:
            continue
        date_iso = doc["date_published"] or "undated"
        filename = "%s_%s.md" % (date_iso, doc["slug"])
        with open(os.path.join(args.out, filename), "w", encoding="utf-8") as fh:
            fh.write(lib.render(doc))
        rows.append({"file": filename, "doc_id": doc["slug"], "owner": "", "year": "",
                     "date_published": date_iso, "title": doc["title"],
                     "word_count": doc["word_count"], "n_paragraphs": len(doc["paragraphs"]),
                     "n_figures": len(doc["figures"]), "n_references": len(doc["references"]),
                     "url": doc["url"], "page_sha256": doc["page_sha256"]})
    if rows:
        print("manifest: %s (%d rows)" % lib.write_manifest(rows, os.path.join(args.out, "_manifest.csv")))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
