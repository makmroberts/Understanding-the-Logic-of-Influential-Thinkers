"""Text -> article metadata record. Deterministic, and blind to where the text came from.

The pipeline has two separate jobs:

    parser (parsers/cfr.py, ...)     knows one site's HTML, writes text
    metadata extractor (this file)   knows only the text it is handed

Nothing here reads HTML, names a publisher, or calls a model. The same input
file always produces the same output, so a re-run that changes nothing writes
nothing different.

Reads   internal/extracted/*.md   or any file passed with --file
Writes  data/articles/<id>.json   metadata, hashes and citation locations only

Article text stays in internal/. The record holds no paragraph text, only each
paragraph's hash and the labels of the links the author wrote.

Where each field comes from, in order:

    frontmatter    a `key: value` block at the top of the file
    heading_rule   an H1 title, then a byline in the header lines above the body
    none           the field stays null and a flag says so. Nothing is guessed.

Which rule filled a field is recorded in `metadata_extension.field_sources`.

Usage:
    python scripts/extractors/metadata.py                write every record
    python scripts/extractors/metadata.py --check        audit only, write nothing
    python scripts/extractors/metadata.py --file a.txt   one file, any plain text
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers.common import BARE_URL_RE

SCHEMA_VERSION = "source-record-0.1"

ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_DIR = ROOT / "internal" / "extracted"
OUTPUT_DIR = ROOT / "data" / "articles"

ANCHOR_RE = re.compile(r"^<!--\s*p(\d+)\s*-->\s*$")
# One level of nesting on each side: labels can hold "[1]" and URLs "(2020)".
LINK_RE = re.compile(
    r"\[((?:[^\[\]]|\[[^\]]*\])*)\]"
    r"\(((?:[^()\s]|\([^()\s]*\))+)\)")
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
LONG_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),\s+(\d{4})\b")
MONTHS = ("January February March April May June July August September October "
          "November December").split()
BY_RE = re.compile(r"^\W*by\s+(.+?)\W*$", re.I)
JOINT_RE = re.compile(r"^(?:this is )?a joint (?:post|piece|article|note) by (.+?)\.?$", re.I)
FOOTNOTE_RE = re.compile(r"^(?:\[fn|\*+\s*\S)")
# The line a source extractor writes under the title: *A, B - date - [source](url)*
BYLINE_RE = re.compile(r"^\*(.+?) - (\d{4}-\d{2}-\d{2})? ?- \[source\]\((\S+?)\)\*$")
HEADER_LINES = 12
BODY_HEADING = "## Body"


# --------------------------------------------------------------------- urls ---

def normalize(url):
    """Comparison key for a URL. Query, fragment, trailing slash and the `www.`
    prefix are not part of what was cited."""
    url = url.split("?")[0].split("#")[0].rstrip("/").strip()
    url = re.sub(r"^http://", "https://", url, flags=re.I)
    return re.sub(r"^https://www\.", "https://", url, flags=re.I).lower()


def host_of(url):
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


# ------------------------------------------------------------------ parsing ---

def split_frontmatter(raw):
    """(dict of top-level keys, the text after the block). {} if there is none."""
    if not raw.startswith("---\n"):
        return {}, raw
    end = raw.find("\n---\n", 4)
    if end < 0:
        return {}, raw
    meta = {}
    for line in raw[4:end].split("\n"):
        m = re.match(r"^([a-z_0-9]+):\s*(.*?)\s*$", line)
        if m:
            meta[m.group(1)] = m.group(2)
    return meta, raw[end + 5:]


def scalar(value):
    """A frontmatter value as a string, or None when it is empty."""
    if value is None:
        return None
    value = value.strip()
    if value.startswith('"'):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = value.strip('"')
    return value or None


def string_list(value):
    """`["A", "B"]` -> list. Empty or malformed -> []."""
    try:
        parsed = json.loads(value) if value else []
    except json.JSONDecodeError:
        return []
    return [str(v).strip() for v in parsed if str(v).strip()] if isinstance(parsed, list) else []


def body_lines(text):
    """The numbered paragraphs, as [(id, markdown)], and the header above them.

    With `<!-- pN -->` anchors the numbers are read and kept, because passage
    links already cite them. Without anchors each blank-line block is one
    paragraph, numbered in order, after the header lines claimed by the title.
    """
    lines = text.split("\n")
    anchors = [i for i, line in enumerate(lines) if ANCHOR_RE.match(line)]
    if anchors:
        paragraphs = []
        for pos, start in enumerate(anchors):
            stop = anchors[pos + 1] if pos + 1 < len(anchors) else len(lines)
            block = []
            for line in lines[start + 1:stop]:
                if line.startswith("## "):
                    break
                block.append(line)
            pid = "p%s" % ANCHOR_RE.match(lines[start]).group(1)
            paragraphs.append((pid, " ".join(x.strip() for x in block if x.strip())))
        return paragraphs, lines[:anchors[0]]

    blocks, current, header = [], [], []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    while blocks and is_header_block(blocks[0]):
        header += blocks.pop(0)
    return [("p%d" % i, " ".join(b)) for i, b in enumerate(blocks, 1)], header


def is_header_block(block):
    first = block[0]
    return (first.startswith("# ") or first == BODY_HEADING.strip()
            or bool(BYLINE_RE.match(first)) or bool(BY_RE.match(first))
            or bool(re.fullmatch(r"\W*(%s|%s)\W*" % (ISO_DATE_RE.pattern, LONG_DATE_RE.pattern), first)))


def links_and_plain(markdown):
    """(plain text, links). Offsets index the plain text, so an excerpt can be checked."""
    pieces, links, cursor, offset = [], [], 0, 0
    for m in LINK_RE.finditer(markdown):
        before = markdown[cursor:m.start()]
        pieces.append(before)
        offset += len(before)
        label, href = m.group(1), m.group(2)
        pieces.append(label)
        if href.startswith(("http://", "https://")):
            links.append({"char_start": offset, "char_end": offset + len(label),
                          "label": label, "href": href, "kind": "hyperlink"})
        offset += len(label)
        cursor = m.end()
    pieces.append(markdown[cursor:])
    plain = "".join(pieces)

    masked = list(plain)
    for link in links:                 # a label that is itself a URL is one citation
        masked[link["char_start"]:link["char_end"]] = " " * (link["char_end"] - link["char_start"])
    for m in BARE_URL_RE.finditer("".join(masked)):
        href = m.group(1).rstrip(".,;:)")
        links.append({"char_start": m.start(1), "char_end": m.start(1) + len(href),
                      "label": "", "href": href, "kind": "bare_url"})
    links.sort(key=lambda link: link["char_start"])
    return plain, links


def figure_inventory(text):
    """[{title, src, after_paragraph}] from the Figures section, when the text has one.

    `after_paragraph` is a paragraph id, "start" if the figure precedes the body,
    or null if the source extractor did not say where it sits.
    """
    m = re.search(r"^## Figures[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return []
    entries = re.findall(
        r"^\d+\.\s+\*\*(.*?)\*\*[ \t]*\n[ \t]+(\S+)[ \t]*$(?:\n[ \t]+after_paragraph:[ \t]*(\S+))?",
        m.group(1), re.M)
    return [{"title": title, "src": src, "after_paragraph": after or None}
            for title, src, after in entries]


# ------------------------------------------------------------------- header ---

def read_header(header):
    """Title, authors, date and URL from the lines above the body."""
    found = {"title": None, "authors": [], "published_date": None, "url": None}
    lines = [line.strip() for line in header if line.strip()][:HEADER_LINES]
    for line in lines:
        if found["title"] is None and line.startswith("# "):
            found["title"] = line[2:].strip() or None
            continue
        byline = BYLINE_RE.match(line)
        if byline:
            found["authors"] = found["authors"] or split_names(byline.group(1))
            found["published_date"] = found["published_date"] or byline.group(2)
            found["url"] = found["url"] or byline.group(3)
            continue
        by = BY_RE.match(line)
        if by and not found["authors"]:
            found["authors"] = split_names(by.group(1))
        if found["published_date"] is None:
            found["published_date"] = first_date(line)
    return found


def split_names(text):
    return [n.strip() for n in re.split(r",|\band\b|&", text) if n.strip()]


def joint_authors(first_paragraph):
    """Names from an opening line like "This is a joint post by A, B of Org, and C."."""
    found = JOINT_RE.match(first_paragraph.strip())
    if not found:
        return []
    return [re.sub(r"\s+of\s+.*$", "", name) for name in split_names(found.group(1))]


def first_date(line):
    m = ISO_DATE_RE.search(line)
    if m:
        return m.group(0)
    m = LONG_DATE_RE.search(line)
    if m:
        return "%s-%02d-%02d" % (m.group(3), MONTHS.index(m.group(1)) + 1, int(m.group(2)))
    return None


# ------------------------------------------------------------------- hashes ---

def normalized(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def sha256(text):
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------- record ---

def choose(fields, sources, name, frontmatter_value, header_value):
    """Frontmatter first, then the header rule, else null. Records which one won."""
    if frontmatter_value:
        fields[name], sources[name] = frontmatter_value, "frontmatter"
    elif header_value:
        fields[name], sources[name] = header_value, "heading_rule"
    else:
        fields[name], sources[name] = ([] if name == "authors" else None), "none"


def build_record(path, raw):
    """One file's record. `revisions` and in-corpus targets are added afterwards."""
    meta, text = split_frontmatter(raw)
    paragraphs, header = body_lines(text)
    head = read_header(header)

    fields, sources = {}, {}
    choose(fields, sources, "title", scalar(meta.get("title")), head["title"])
    choose(fields, sources, "authors", string_list(meta.get("authors")), head["authors"])
    choose(fields, sources, "published_date", scalar(meta.get("date_published")), head["published_date"])
    choose(fields, sources, "url", scalar(meta.get("url")), head["url"])
    choose(fields, sources, "publisher", scalar(meta.get("publisher")), None)
    choose(fields, sources, "series", scalar(meta.get("series")), None)

    # A byline can omit co-authors the article itself names. Add them, never replace.
    if paragraphs:
        known = {name.split()[-1].lower() for name in fields["authors"]}
        extra = [n for n in joint_authors(links_and_plain(paragraphs[0][1])[0])
                 if n.split()[-1].lower() not in known]
        if extra:
            fields["authors"] = fields["authors"] + extra
            sources["authors"] += "+joint_post_rule"

    para_rows, references, plain_all, link_keys = [], [], [], []
    for pid, markdown in paragraphs:
        plain, links = links_and_plain(markdown)
        clean = normalized(plain)
        plain_all.append(clean)
        para_rows.append({"id": pid, "sha256": sha256(clean), "n_chars": len(plain)})
        placement = "footnote" if FOOTNOTE_RE.match(plain.lstrip()) else "body"
        for link in links:
            key = normalize(link["href"])
            link_keys.append("%s\t%s\t%s" % (pid, link["label"], link["href"]))
            references.append({
                "id": "r%03d" % (len(references) + 1),
                "paragraph_id": pid,
                "char_start": link["char_start"],
                "char_end": link["char_end"],
                "label": link["label"],
                "href": link["href"],
                "kind": link["kind"],
                "placement": placement,
                "source_key": key,
                "host": host_of(key),
                "target_article_id": None,
            })

    url = fields["url"]
    article_id = scalar(meta.get("doc_id")) or re.sub(r"^\d{4}-\d{2}-\d{2}_", "", path.stem)
    try:
        shown_path = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        shown_path = path.name

    flags = ["missing_%s" % name for name in ("title", "authors", "published_date", "url")
             if not fields[name]]
    if not para_rows:
        flags.append("no_paragraphs")
    if "n_paragraphs" in meta and meta["n_paragraphs"] != str(len(para_rows)):
        flags.append("paragraph_count_mismatch")
    # Only a file that declares its reference count can say links were preserved.
    # Plain text with no links is "unknown", never "this article cites nothing".
    references_status = "preserved" if "n_references" in meta else "unknown"
    if "n_references" in meta and int(meta["n_references"]) != len({r["href"] for r in references}):
        flags.append("reference_count_mismatch")

    return {
        "schema_version": SCHEMA_VERSION,
        "article": {
            "id": article_id,
            "title": fields["title"],
            "authors": fields["authors"],
            "published_date": fields["published_date"],
            "url": url,
            "publisher": fields["publisher"],
            "series": fields["series"],
            "source_text": {
                "path": shown_path,
                "paragraph_count": len(para_rows),
                "content_hash": sha256("\n".join(plain_all)),
                "revision": 1,
            },
            "references": references,
            "metadata_extension": {
                "field_sources": sources,
                "references_status": references_status,
                "links_hash": sha256("\n".join(link_keys)),
                "subtitle": scalar(meta.get("subtitle")),
                "published_at": scalar(meta.get("published_at")),
                "programs": string_list(meta.get("programs")),
                "source_tags": string_list(meta.get("source_tags")),
                "license": scalar(meta.get("license")),
                "section": scalar(meta.get("section")),
                "doc_type": scalar(meta.get("doc_type")),
                "language": scalar(meta.get("language")),
                "word_count": int(meta["word_count"]) if meta.get("word_count", "").isdigit() else None,
                "date_modified": scalar(meta.get("date_modified")),
                "retrieved_at": scalar(meta.get("retrieved_at")),
                "page_sha256": scalar(meta.get("page_sha256")),
                "figures": figure_inventory(text),
            },
        },
        "paragraphs": para_rows,
        "revisions": [],
        "extensions": {
            "entities": entity_roles(fields),
            "cited_sources": cited_sources(references),
        },
        "validation": {"flags": flags},
    }


def entity_roles(fields):
    """Named parties known from structure alone. Mentions in prose are not matched yet."""
    out = [{"entity_id": None, "type": "person", "name": n, "role": "author"}
           for n in fields["authors"]]
    if fields["publisher"]:
        out.append({"entity_id": None, "type": "organization",
                    "name": fields["publisher"], "role": "publisher"})
    return out


def cited_sources(references):
    """One row per distinct source, pointing back at each place it is cited."""
    grouped = {}
    for ref in references:
        row = grouped.setdefault(ref["source_key"], {
            "source_key": ref["source_key"], "host": ref["host"], "reference_ids": []})
        row["reference_ids"].append(ref["id"])
    return list(grouped.values())


# ---------------------------------------------------------------- versioning ---

def changed_paragraphs(old, new):
    before = {p["id"]: p["sha256"] for p in old}
    after = {p["id"]: p["sha256"] for p in new}
    return sorted((pid for pid in set(before) | set(after) if before.get(pid) != after.get(pid)),
                  key=lambda pid: int(pid[1:]))


def apply_revision(record, previous):
    """Carry the revision history forward. Only a change to text or links is a revision."""
    source, extension = record["article"]["source_text"], record["article"]["metadata_extension"]
    entry = {"content_hash": source["content_hash"], "links_hash": extension["links_hash"],
             "paragraph_count": source["paragraph_count"], "retrieved_at": extension["retrieved_at"]}
    if previous is None:
        record["revisions"] = [dict(entry, revision=1, changed_paragraphs=[])]
        return
    old_source = previous["article"]["source_text"]
    old_extension = previous["article"]["metadata_extension"]
    if (old_source["content_hash"], old_extension["links_hash"]) == (source["content_hash"], extension["links_hash"]):
        source["revision"] = old_source["revision"]
        record["revisions"] = previous["revisions"]
        extension["retrieved_at"] = old_extension["retrieved_at"]
        extension["page_sha256"] = old_extension["page_sha256"]
        if "source_changed_review_passages" in previous["validation"]["flags"]:
            record["validation"]["flags"].append("source_changed_review_passages")
        return
    source["revision"] = old_source["revision"] + 1
    changed = changed_paragraphs(previous["paragraphs"], record["paragraphs"])
    record["revisions"] = previous["revisions"] + [
        dict(entry, revision=source["revision"], changed_paragraphs=changed)]
    record["validation"]["flags"].append("source_changed_review_passages")


def link_corpus(records):
    """Mark citations that point at another article in the same batch."""
    by_url = {normalize(r["article"]["url"]): r["article"]["id"] for r in records if r["article"]["url"]}
    for record in records:
        for ref in record["article"]["references"]:
            ref["target_article_id"] = by_url.get(ref["source_key"])


def serialize(record):
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------- main ---

def main():
    ap = argparse.ArgumentParser(description="Deterministic text -> metadata record.")
    ap.add_argument("--file", action="append", default=[], help="one text file; repeatable")
    ap.add_argument("--input", default=str(INPUT_DIR), help="directory of *.md files")
    ap.add_argument("--out", default=str(OUTPUT_DIR))
    ap.add_argument("--check", action="store_true", help="audit only, write nothing")
    args = ap.parse_args()

    paths = [Path(f) for f in args.file] or sorted(Path(args.input).glob("*.md"))
    if not paths:
        ap.error("no input files")

    out_dir = Path(args.out)
    records = [build_record(p, p.read_text(encoding="utf-8", errors="replace")) for p in paths]
    link_corpus(records)

    if not args.check:
        out_dir.mkdir(parents=True, exist_ok=True)
    unchanged = written = 0
    for record in records:
        target = out_dir / (record["article"]["id"] + ".json")
        previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else None
        apply_revision(record, previous)
        text = serialize(record)
        if target.exists() and target.read_text(encoding="utf-8") == text:
            unchanged += 1
        elif not args.check:
            with target.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            written += 1

    n_refs = sum(len(r["article"]["references"]) for r in records)
    n_corpus = sum(1 for r in records for ref in r["article"]["references"] if ref["target_article_id"])
    n_paras = sum(r["article"]["source_text"]["paragraph_count"] for r in records)
    flagged = [(r["article"]["id"], r["validation"]["flags"]) for r in records if r["validation"]["flags"]]
    print("%d articles, %d paragraphs, %d citations (%d inside this batch)"
          % (len(records), n_paras, n_refs, n_corpus))
    print("%d written, %d unchanged%s" % (written, unchanged, "  [--check: nothing written]" if args.check else ""))
    print("%d flagged" % len(flagged))
    for article_id, flags in flagged:
        print("  %s: %s" % (article_id, ", ".join(flags)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
