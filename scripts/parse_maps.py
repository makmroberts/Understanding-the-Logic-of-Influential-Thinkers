#!/usr/bin/env python3
"""Parse mermaid_code/*.mmd into one normalized argument graph.

Usage:
    python scripts/parse_maps.py                 # writes data/ + data/review.md
    python scripts/parse_maps.py --propose       # ...and suggest concept clusters

Two projections of the same parse:

    data/graph.json   nested, one object per document (doc -> levels -> nodes)
    data/nodes.csv    flat, one row per argument node   } cross-document
    data/edges.csv    flat, one row per argument edge   } queries

Normalization is driven entirely by scripts/schema_map.yaml; nothing is guessed
here. Anything the table does not cover is written to data/review.md rather
than silently dropped or mapped to a default.

The cross-document layer is scripts/concepts.yaml, which the team maintains by
hand: it maps (doc, node id) pairs onto canonical concept ids, which is what
turns 20 disconnected maps into one graph.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR = ROOT / "mermaid_code"
DATA_DIR = ROOT / "data"
SCHEMA_MAP = Path(__file__).resolve().parent / "schema_map.yaml"
CONCEPTS = Path(__file__).resolve().parent / "concepts.yaml"

TEMPLATE_STEMS = ("template", "edge_types")

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "june": 6,
          "jul": 7, "july": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
          "nov": 11, "dec": 12}


# ----------------------------------------------------------------- helpers ---

def plain(text: str) -> str:
    """Mermaid label -> plain text."""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("#quot;", '"').replace("#39;", "'")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("`", "")
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    return "\n".join(ln.strip() for ln in text.split("\n")).strip()


# "Brad Setser, CFR, Dec 2017" - the 2017-2020 maps close the Q node with this.
BYLINE_RE = re.compile(r"^[^,]{2,40},\s*[^,]{2,40},\s*[A-Z][a-z]{2,4}\.?\s*\d{4}$")

# second_flow_template.mmd annotates some nodes inline: <i>kind: economic</i> on a
# mechanism, <i>type: single</i> on a conclusion. These are schema fields wearing
# italics - left in the text they dominate any similarity measure, because every
# mechanism in the corpus then "shares" the phrase "kind: economic".
ANNOT_RE = re.compile(r"<i>\s*·?\s*(kind|type)\s*:\s*([^<|]+?)\s*(?:\|[^<]*)?</i>", re.I)


def pull_annotations(label: str) -> tuple[str, dict]:
    """Strip inline `kind:`/`type:` annotations out of a label into fields."""
    annot: dict[str, str] = {}
    for m in ANNOT_RE.finditer(label):
        value = m.group(2).strip()
        # the template itself lists every option; that is a placeholder, not a value
        if value and "|" not in m.group(0).split(value)[0]:
            annot.setdefault(m.group(1).lower(), value)
    return ANNOT_RE.sub("", label), annot


def split_header(label: str) -> tuple[str, str, str]:
    """Split a node label into (bold header, body, byline).

    The older maps put the article's question in the bold header and close the
    node with an italic byline. Left in, the byline becomes the node text and
    then the document title, so it is peeled off here.
    """
    byline = ""
    for m in re.finditer(r"<i>(.*?)</i>", label, re.S):
        if BYLINE_RE.match(plain(m.group(1))):
            byline = plain(m.group(1))
            label = label.replace(m.group(0), "")
    m = re.search(r"<b>(.*?)</b>", label, re.S) or re.search(r"\*\*(.*?)\*\*", label, re.S)
    header = plain(m.group(1)) if m else ""
    header = re.split(r"\s*·\s*", header)[0].strip()      # drop "· optional" etc.
    body = plain(label)
    if header and body.startswith(header):
        body = body[len(header):].strip()
    return header, body, byline


def doc_date(stem: str) -> str:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", stem)
    if m:
        return m.group(0)
    m = re.search(r"_([a-z]{3,4})_(\d{1,2})_(\d{2})$", stem, re.I)
    if m and m.group(1).lower() in MONTHS:
        return f"20{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return ""


def doc_family(text: str) -> str:
    """Which annotation template a map was built from.

    Three coexist and they are NOT separated by date - the `banner` template
    spans 2020-2025 while `plain` runs to Feb 2020 and `meta` starts Jul 2025.
    Any cross-corpus count has to control for this, so it is a first-class
    property rather than something to remember.

      plain   no apparatus; evidence split into granular D1..D6 nodes
      banner  T[] banner + LEG legend + ghost slots + Level 1b; E1/E2 evidence
      meta    no apparatus; %% header comments; E1/E2 with the longest text
    """
    if re.search(r"%%\s*title:", text):
        return "meta"
    if re.search(r'^\s*T\["', text, re.M):
        return "banner"
    return "plain"


def doc_meta(text: str, stem: str) -> dict:
    meta = {"title": "", "author": "", "outlet": "", "url": "", "topics": "", "genre": ""}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("%%"):
            continue
        body = line[2:].strip()
        if body.lower().startswith(("url:", "link:")):
            meta["url"] = body.partition(":")[2].strip()
            continue
        for chunk in body.split("|"):
            key, _, val = chunk.partition(":")
            key, val = key.strip().lower(), val.strip()
            if key in meta and val and not meta[key]:
                meta[key] = val

    if not meta["title"]:
        m = re.search(r'^\s*T\["(.*?)"\]', text, re.M | re.S)
        if m:
            q = re.search(r"#quot;(.+?)#quot;", m.group(1))
            if q:
                meta["title"] = plain(q.group(1))
    if not meta["title"]:
        m = re.search(r'^\s*Q\["(.*?)"\]', text, re.M | re.S)
        if m:
            header, body, _ = split_header(m.group(1))
            # the older maps hold the question in the header, the newer ones in the body
            meta["title"] = " ".join((header or body).split())
    if not meta["title"]:
        meta["title"] = stem.replace("_", " ")

    m = re.search(r'^\s*T\["(.*?)"\]', text, re.M | re.S)
    meta["shape"] = ""
    if m:
        for b in re.findall(r"<b>(.*?)</b>", m.group(1)):
            if plain(b).lower().startswith("shape"):
                meta["shape"] = plain(b)
    return meta


# ------------------------------------------------------------------ parser ---

NODE_RE = re.compile(r'^[ \t]*(\w+)\[\s*"(.*?)"\s*\]', re.M | re.S)
SUBGRAPH_RE = re.compile(r'^[ \t]*subgraph\s+(\w+)\s*\[', re.M)
END_RE = re.compile(r'^[ \t]*end[ \t]*$', re.M)
CLASS_RE = re.compile(r'^[ \t]*class\s+([\w,\s]+?)\s+(\w+)[ \t]*$', re.M)

EDGE_RE = re.compile(
    r'(?P<src>[\w&\s]+?)\s*'
    r'(?:'
    r'(?P<dashlab>-\.\s*(?P<dl>[^.\n]*?)\s*\.-)'          #  A -. label .- B
    r'|(?P<op>-->|-\.->|==>|~~~|---)\s*(?:\|(?P<sl>[^|]*)\|)?'
    r')\s*(?P<dst>[\w&\s]+?)[ \t]*$'
)


def subgraph_at(text: str, pos: int) -> str:
    """Innermost subgraph enclosing a character offset."""
    stack: list[str] = []
    for m in sorted([*SUBGRAPH_RE.finditer(text), *END_RE.finditer(text)],
                    key=lambda m: m.start()):
        if m.start() > pos:
            break
        if m.re is SUBGRAPH_RE:
            stack.append(m.group(1))
        elif stack:
            stack.pop()
    return stack[-1] if stack else ""


def parse_doc(path: Path, smap: dict, issues: list) -> dict:
    text = path.read_text(encoding="utf-8")
    stem = path.stem
    meta = doc_meta(text, stem)

    classes: dict[str, str] = {}
    for m in CLASS_RE.finditer(text):
        for nid in m.group(1).split(","):
            if nid.strip():
                classes[nid.strip()] = m.group(2)

    drop_classes = set(smap["drop_classes"])
    drop_subgraphs = set(smap.get("drop_subgraphs", []))
    drop_text = [re.compile(p, re.I) for p in smap["drop_if_text_matches"]]

    nodes: dict[str, dict] = {}
    dropped: set[str] = set()

    for m in NODE_RE.finditer(text):
        nid, label = m.group(1), m.group(2)
        if nid in {"subgraph", "end", "classDef", "class"}:
            continue
        cls = classes.get(nid, "")
        label, annot = pull_annotations(label)
        header, body, byline = split_header(label)
        level = subgraph_at(text, m.start())

        if (cls in drop_classes or level in drop_subgraphs
                or any(p.match(body or header) for p in drop_text)):
            dropped.add(nid)
            continue

        # Two conventions coexist. The schema-conforming maps put the slot name in
        # the bold header ("Mechanism A", "Data"); the older maps put the node's own
        # claim there and carry the type on the class instead. Try header, then
        # class, then level - and record which one answered, so any type can be
        # traced back to its evidence.
        hl = header.lower()
        ntype, source = smap["node_types_by_header"].get(hl), "header"
        if not ntype:
            ntype, source = smap["node_types_by_class"].get(cls), "class"
        if not ntype:
            ntype, source = smap["node_types_by_level"].get(level), "level"

        # `class mech` covers both L3 mechanisms and L4 intermediate claims;
        # the level is what separates them.
        if ntype == "mechanism" and level == "L4":
            ntype = "intermediate_claim"
        if ntype == "benchmark" and hl.startswith("scope"):
            ntype = "scope_choice"

        # Every Level 6 node carries class `dia`, so the header is the only thing
        # separating a caveat from an opposing view from a rival explanation.
        # The keywords live in schema_map.yaml; anything they miss is reported.
        if ntype == "counterpoint":
            for kw, t in (smap.get("counterpoint_by_header_contains") or {}).items():
                if kw in hl:
                    ntype, source = t, "l6_keyword"
                    break
            else:
                issues.append(("unresolved counterpoint", stem,
                               f"{nid} {header!r} - stays generic `counterpoint`"))

        if not ntype:
            issues.append(("unmapped node", stem, f"{nid} class={cls!r} "
                                                  f"header={header!r} level={level!r}"))
            ntype = "unclassified"

        nodes[nid] = {
            "id": nid,
            "type": ntype,
            "level": level,
            "header": header,
            "text": body or header,
            "byline": byline,
            "class": cls,
            "type_source": source,
            "claim_type": annot.get("type", ""),
            "mechanism_kind": (annot.get("kind", "").lower()
                               or smap["mechanism_kind_by_class"].get(cls, "")),
            "implicit_only": cls == "implicit" or "implicit" in header.lower(),
        }

    # ---- edges ----
    edges = []
    drop_ops = set(smap["drop_edge_operators"])
    for raw_line in text.splitlines():
        line = raw_line.split("%%")[0].rstrip()
        if not line.strip() or line.lstrip().startswith(("subgraph", "classDef", "class", "linkStyle", "style")):
            continue
        m = EDGE_RE.match(line.strip())
        if not m:
            continue

        op = m.group("op") or "-.->"
        if op in drop_ops:
            continue
        label = (m.group("sl") or m.group("dl") or "").strip()
        dashed = op in {"-.->", "---"} or m.group("dashlab") is not None

        if label:
            etype = smap["edge_types"].get(label.lower())
            if not etype:
                issues.append(("unmapped edge label", stem, repr(label)))
                etype = None
        else:
            etype = smap["edge_default_dashed"] if dashed else smap["edge_default_solid"]
            if etype is None:
                issues.append(("unlabelled dashed edge", stem,
                               f"{m.group('src').strip()} -> {m.group('dst').strip()}"))

        for src in re.split(r"\s*&\s*", m.group("src").strip()):
            for dst in re.split(r"\s*&\s*", m.group("dst").strip()):
                src, dst = src.strip(), dst.strip()
                if not src or not dst:
                    continue
                if src in dropped or dst in dropped:
                    continue          # an edge to an unfilled slot is not an argument edge
                if src not in nodes or dst not in nodes:
                    issues.append(("edge to unknown node", stem, f"{src} -> {dst}"))
                    continue
                edges.append({
                    "from": src, "to": dst,
                    "type": etype, "raw": label,
                    "polarity": "pushes_back" if dashed else "forward",
                    "needs_review": etype is None,
                })

    levels: dict[str, list] = defaultdict(list)
    for n in nodes.values():
        levels[n["level"] or "?"].append(n)

    return {
        "doc": stem,
        "file": path.name,
        "family": doc_family(text),
        "date": doc_date(stem),
        "meta": meta,
        "levels": {k: levels[k] for k in sorted(levels)},
        "edges": edges,
        "counts": {"nodes": len(nodes), "edges": len(edges), "dropped_nodes": len(dropped)},
    }


# ------------------------------------------------------------------ output ---

def attach_concepts(docs: list[dict]) -> int:
    """Join scripts/concepts.yaml onto parsed nodes. Returns how many matched."""
    if not CONCEPTS.exists():
        return 0
    spec = yaml.safe_load(CONCEPTS.read_text(encoding="utf-8")) or {}
    lookup: dict[tuple[str, str], str] = {}
    for cid, entry in (spec.get("concepts") or {}).items():
        for ref in (entry or {}).get("nodes", []):
            doc, _, nid = str(ref).partition("#")
            lookup[(doc.strip(), nid.strip())] = cid
    hits = 0
    for d in docs:
        for nodes in d["levels"].values():
            for n in nodes:
                cid = lookup.get((d["doc"], n["id"]))
                n["concept"] = cid or ""
                hits += bool(cid)
    return hits


def write_outputs(docs: list[dict], issues: list) -> None:
    DATA_DIR.mkdir(exist_ok=True)

    (DATA_DIR / "graph.json").write_text(
        json.dumps({"documents": docs}, ensure_ascii=False, indent=1), encoding="utf-8")

    with (DATA_DIR / "nodes.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doc", "family", "date", "node_id", "type", "level", "header", "concept",
                    "mechanism_kind", "implicit_only", "type_source",
                    "claim_type", "text"])
        for d in docs:
            for nodes in d["levels"].values():
                for n in nodes:
                    w.writerow([d["doc"], d["family"], d["date"], n["id"], n["type"], n["level"],
                                n["header"], n.get("concept", ""), n["mechanism_kind"],
                                int(n["implicit_only"]), n["type_source"],
                                n["claim_type"], n["text"]])

    with (DATA_DIR / "edges.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doc", "family", "date", "from", "to", "type", "polarity", "raw", "needs_review"])
        for d in docs:
            for e in d["edges"]:
                w.writerow([d["doc"], d["family"], d["date"], e["from"], e["to"], e["type"] or "",
                            e["polarity"], e["raw"], int(e["needs_review"])])

    # ---- review report ----
    all_nodes = [n for d in docs for ns in d["levels"].values() for n in ns]
    all_edges = [(d, e) for d in docs for e in d["edges"]]
    unlabelled = [e for _, e in all_edges if not e["raw"]]
    touched = {(d["doc"], e["from"]) for d, e in all_edges} | {(d["doc"], e["to"]) for d, e in all_edges}
    orphans = [(d, n) for d in docs for ns in d["levels"].values() for n in ns
               if (d["doc"], n["id"]) not in touched]
    src = Counter(n["type_source"] for n in all_nodes)

    lines = ["# Parse review", "",
             f"{len(docs)} documents -> {len(all_nodes)} nodes, {len(all_edges)} edges.", "",
             "## Defaults applied - these are conventions, not authored decisions", "",
             f"- **{len(unlabelled)} of {len(all_edges)} edges carry no label** in the "
             f"source and took `edge_default_solid` (`supports`). An unlabelled solid "
             f"arrow meaning support is the drawing convention across all 20 maps, but "
             f"it is still a default: only {len(all_edges) - len(unlabelled)} edges state "
             f"their type explicitly.",
             f"- Node types resolved by: " +
             ", ".join(f"{v} from {k}" for k, v in src.most_common()) +
             ". A type resolved by `level` alone is the weakest inference - "
             "see the `type_source` column in nodes.csv.", ""]

    if orphans:
        lines += [f"## Nodes in no edge ({len(orphans)})", "",
                  "Mostly Level 0 question nodes: the schema says L0 `==>|frames|` L1, but "
                  "every article map draws that link with `~~~`, which is layout-only and "
                  "carries no meaning. The question is therefore not connected to the "
                  "argument it frames. Worth a schema decision rather than a parser fix.", ""]
        for d, n in orphans:
            lines.append(f"- `{d['doc']}#{n['id']}` ({n['type']}) {n['text'][:60]!r}")
        lines.append("")

    if not issues:
        lines += ["## Flagged for review", "",
                  "Nothing - every node and edge mapped onto the schema.", ""]
    else:
        lines += ["## Flagged for review", ""]
        for kind in sorted({i[0] for i in issues}):
            group = [i for i in issues if i[0] == kind]
            lines += [f"## {kind} ({len(group)})", ""]
            for _, doc, detail in group:
                lines.append(f"- `{doc}` - {detail}")
            lines.append("")
        lines += ["Fix by adding the term to `scripts/schema_map.yaml` and re-running.", ""]

    ntypes = Counter(n["type"] for d in docs for ns in d["levels"].values() for n in ns)
    etypes = Counter(e["type"] or "UNRESOLVED" for d in docs for e in d["edges"])
    lines += ["## Normalized node types", ""]
    lines += [f"- {c:4} {t}" for t, c in ntypes.most_common()]
    lines += ["", "## Normalized edge types", ""]
    lines += [f"- {c:4} {t}" for t, c in etypes.most_common()]
    lines.append("")
    (DATA_DIR / "review.md").write_text("\n".join(lines), encoding="utf-8")


def propose_concepts(docs: list[dict]) -> None:
    """Suggest candidate cross-document concepts by shared distinctive terms.

    Deliberately crude and deliberately not applied: it writes a candidate file
    for the team to accept, rename or reject. Concept assignment is the
    analysis, not a preprocessing step.
    """
    stop = set("""the a an and or of to in for on with that this it is are was were be been
        as at by from not no than then so such but if when which who what how why more most
        less least its their his her our your они about over under into out up down off
        china chinese u.s. us american europe european""".split())

    nodes = [(d["doc"], n) for d in docs for ns in d["levels"].values() for n in ns]
    df = Counter()
    toks: dict[tuple[str, str], set[str]] = {}
    for doc, n in nodes:
        t = {w for w in re.findall(r"[a-z][a-z\-']{3,}", (n["header"] + " " + n["text"]).lower())
             if w not in stop}
        toks[(doc, n["id"])] = t
        df.update(t)

    rare = {w for w, c in df.items() if 2 <= c <= 25}
    groups: list[list] = []
    used: set[tuple[str, str]] = set()
    for i, (doc_a, a) in enumerate(nodes):
        ka = (doc_a, a["id"])
        if ka in used:
            continue
        cluster = [(doc_a, a)]
        ta = toks[ka] & rare
        if len(ta) < 3:
            continue
        for doc_b, b in nodes[i + 1:]:
            kb = (doc_b, b["id"])
            if kb in used or doc_b == doc_a or b["type"] != a["type"]:
                continue
            tb = toks[kb] & rare
            overlap = ta & tb
            if len(overlap) >= 3 and len(overlap) / max(1, min(len(ta), len(tb))) > 0.25:
                cluster.append((doc_b, b))
                used.add(kb)
        if len(cluster) > 1:
            used.add(ka)
            groups.append(cluster)

    groups.sort(key=len, reverse=True)
    out = ["# Candidate concepts - PROPOSALS ONLY, not applied.",
           "#",
           "# Each group is a set of nodes of the same type, in different documents,",
           "# sharing distinctive vocabulary. Review every one: keep and name the real",
           "# ones, delete the rest, then move them into scripts/concepts.yaml.",
           "",
           "concepts:"]
    for i, cluster in enumerate(groups[:40], 1):
        kind = cluster[0][1]["type"]
        out += [f"  candidate-{i:02d}-{kind.replace('_', '-')}:",
                f"    note: {len(cluster)} nodes, type {kind}",
                "    nodes:"]
        for doc, n in cluster:
            snippet = n["text"].replace("\n", " ")[:88]
            out.append(f"      - {doc}#{n['id']}    # {snippet}")
        out.append("")
    path = DATA_DIR / "concepts_proposed.yaml"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}  ({len(groups)} candidate groups)")


# -------------------------------------------------------------------- main ---

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--propose", action="store_true",
                    help="also write data/concepts_proposed.yaml")
    ap.add_argument("--include-templates", action="store_true",
                    help="parse the schema templates too (normally excluded)")
    args = ap.parse_args()

    smap = yaml.safe_load(SCHEMA_MAP.read_text(encoding="utf-8"))
    paths = sorted(MAPS_DIR.glob("*.mmd"))
    if not args.include_templates:
        paths = [p for p in paths if not any(s in p.stem for s in TEMPLATE_STEMS)]
    if not paths:
        sys.exit(f"no maps found in {MAPS_DIR}")

    issues: list = []
    docs = [parse_doc(p, smap, issues) for p in paths]
    docs.sort(key=lambda d: (d["date"] or "9999", d["doc"]))

    matched = attach_concepts(docs)
    write_outputs(docs, issues)

    n = sum(d["counts"]["nodes"] for d in docs)
    e = sum(d["counts"]["edges"] for d in docs)
    dropped = sum(d["counts"]["dropped_nodes"] for d in docs)
    review = sum(1 for d in docs for x in d["edges"] if x["needs_review"])

    print(f"{len(docs)} documents -> {n} nodes, {e} edges "
          f"({dropped} presentation nodes dropped)")
    print(f"  data/graph.json  data/nodes.csv  data/edges.csv  data/review.md")
    if matched:
        print(f"  {matched} nodes carry a concept id")
    else:
        print("  no concept ids yet - scripts/concepts.yaml is the cross-document layer")
    if issues or review:
        print(f"  {len(issues)} items flagged for review -> data/review.md")

    if args.propose:
        propose_concepts(docs)


if __name__ == "__main__":
    main()
