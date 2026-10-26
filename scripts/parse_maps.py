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
# Only the five meta-family maps carry a `%% url:` comment. The other fifteen
# URLs are reconciled in this overlay rather than by editing the maps, which
# are the authored artifact - same contract as schema_map.yaml.
SOURCE_URLS = Path(__file__).resolve().parent / "source_urls.yaml"
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
    # The banner maps separate the header from the claim with a middot, as in
    # "<b>Main claim</b> · <i>type: single</i><br/>The reported surplus...".
    # Peeling the header leaves that middot stranded at the front of the body,
    # where it becomes the first character of the note title and of every trace
    # line for the claim. It is layout, not content.
    body = re.sub(r"^[·•]\s*", "", body).strip()
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


def load_source_urls() -> dict:
    """stem -> url, from the reconciliation overlay. Confirmed entries only.

    Entries under `needs_review` are deliberately NOT returned: they were
    assigned by elimination rather than by evidence, and a URL presented as the
    source has to be one somebody checked.
    """
    if not SOURCE_URLS.exists():
        return {}
    spec = yaml.safe_load(SOURCE_URLS.read_text(encoding="utf-8")) or {}
    return {k: v["url"] for k, v in (spec.get("urls") or {}).items()
            if isinstance(v, dict) and v.get("url")}


SOURCE_URL_OVERLAY = None


def doc_meta(text: str, stem: str) -> dict:
    global SOURCE_URL_OVERLAY
    if SOURCE_URL_OVERLAY is None:
        SOURCE_URL_OVERLAY = load_source_urls()
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

    # The map's own comment wins; the overlay only fills a gap, so a map that
    # later gains a `%% url:` line silently takes precedence over this file.
    if not meta["url"]:
        meta["url"] = SOURCE_URL_OVERLAY.get(stem, "")

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
    # `~~~` is mermaid's invisible link and this corpus uses it for two things:
    # chaining subgraph containers (layout) and linking claim to claim (argument
    # structure, mostly the question to its priors and a prior to its datum).
    # They are told apart by their endpoints, which needs no judgement per edge.
    # See the layout_operators block in schema_map.yaml.
    layout_ops = set(smap.get("layout_operators")
                     or smap.get("drop_edge_operators", []))
    pushes_back = set(smap.get("pushes_back_relations", []))
    for raw_line in text.splitlines():
        line = raw_line.split("%%")[0].rstrip()
        if not line.strip() or line.lstrip().startswith(("subgraph", "classDef", "class", "linkStyle", "style")):
            continue
        m = EDGE_RE.match(line.strip())
        if not m:
            continue

        op = m.group("op") or "-.->"
        label = (m.group("sl") or m.group("dl") or "").strip()
        dashed = op in {"-.->", "---"} or m.group("dashlab") is not None
        is_layout = op in layout_ops

        if is_layout:
            # Keep only the claim-to-claim use. Either endpoint being a subgraph
            # container (or an unfilled slot) makes it layout, and layout is
            # dropped as it always was.
            srcs = [s.strip() for s in re.split(r"\s*&\s*", m.group("src").strip())]
            dsts = [s.strip() for s in re.split(r"\s*&\s*", m.group("dst").strip())]
            if not (all(s in nodes for s in srcs if s)
                    and all(s in nodes for s in dsts if s)):
                continue
            for src in srcs:
                for dst in dsts:
                    if not src or not dst:
                        continue
                    # The relation is DERIVED after every document is parsed,
                    # from the relations this annotator actually labelled - see
                    # derive_layout_relations. Nothing is typed here, because
                    # the evidence for typing it is corpus-wide.
                    edges.append({
                        "from": src, "to": dst,
                        "type": None, "raw": "",
                        "polarity": "forward",
                        "relation_source": "layout_operator",
                        "needs_review": False,
                    })
            continue

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
                    # three provenance classes, countable: the annotator wrote
                    # the relation, or it came from the arrow style, or it was
                    # recovered from a layout operator.
                    "relation_source": "label" if label else "arrow",
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


def derive_layout_relations(docs: list[dict], smap: dict, issues: list) -> None:
    """Type the recovered `~~~` edges from the annotator's own labelled edges.

    The maps' invisible operator carries real structure - the question to its
    priors, a prior to its datum - but no relation label. An earlier version of
    this file typed those from a hand-written role-pair table; this derives them
    instead, which is both less specified and more accurate: 89% leave-one-out
    against the 161 edges that DO carry a label, against 12 cells somebody chose.

    The mechanism is coarse-to-fine back-off over the role hierarchy declared in
    schema_map.yaml: the exact role pair where that cell has evidence, else the
    operational family pair, else the Toulmin element pair. Backing off from
    sparse fine-grained labels to their parents is the standard treatment for
    long-tail relations (Han et al. 2018), and it is what lets a second
    annotator map their own role types onto two small family sets rather than
    rewrite a table over 676 role pairs.

    Every derived edge records the level it was typed at and the purity of the
    cell it came from, so a weak typing is a review item and never silently
    authoritative.
    """
    cfg = smap.get("layout_edge_derivation") or {}
    chain = cfg.get("backoff") or ["type"]
    min_ex = int(cfg.get("min_examples", 1))
    flag_below = float(cfg.get("flag_below_purity", 0.0))
    fallback = cfg.get("fallback", "frames")
    fams = smap.get("role_families") or {}

    def fam(level: str, rtype: str) -> str:
        if level == "type":
            return rtype
        for name, members in (fams.get(level) or {}).items():
            if rtype in members:
                return name
        return "?"

    # nodes live under `levels`, keyed by the level they were drawn in
    role = {(d["doc"], n["id"]): n["type"]
            for d in docs for lst in d["levels"].values() for n in lst}
    tables = {lv: defaultdict(Counter) for lv in chain}
    for d in docs:
        for e in d["edges"]:
            if e.get("relation_source") != "label" or not e["type"]:
                continue
            a = role[(d["doc"], e["from"])]
            b = role[(d["doc"], e["to"])]
            for lv in chain:
                tables[lv][(fam(lv, a), fam(lv, b))][e["type"]] += 1

    pushes_back = set(smap.get("pushes_back_relations", []))
    derived = Counter()
    for d in docs:
        for e in d["edges"]:
            if e.get("relation_source") != "layout_operator" or e["type"]:
                continue
            a = role[(d["doc"], e["from"])]
            b = role[(d["doc"], e["to"])]
            etype, level, purity = fallback, "fallback", 0.0
            for lv in chain:
                cell = tables[lv].get((fam(lv, a), fam(lv, b)))
                if cell and sum(cell.values()) >= min_ex:
                    top, n = cell.most_common(1)[0]
                    etype, level, purity = top, lv, n / sum(cell.values())
                    break
            e["type"] = etype
            e["relation_level"] = level
            e["relation_purity"] = round(purity, 2)
            e["polarity"] = "pushes_back" if etype in pushes_back else "forward"
            derived[(level, etype)] += 1
            # Flag only a cell that EXISTED and was weak. A fallback is not a
            # weak cell, it is the absence of one, and it is reported once
            # below rather than as one review item per edge.
            if level != "fallback" and purity < flag_below:
                issues.append(("layout edge typed from a weak cell", d["doc"],
                               f"{a} -> {b}: {etype} "
                               f"(level {level}, purity {purity:.2f})"))
    n_fb = sum(v for (lv, _), v in derived.items() if lv == "fallback")
    if n_fb:
        issues.append(("layout edges with no evidence to derive from", "corpus",
                       f"{n_fb} edges typed `{fallback}` by declared convention. "
                       f"These role pairs carry NO labelled example anywhere, "
                       f"because the annotator used the unlabelled `~~~` "
                       f"operator for exactly this structure - so there is "
                       f"nothing to back off to. Sign 0: the structure is "
                       f"recorded without asserting support we cannot evidence."))
    for (level, etype), n in sorted(derived.items(), key=lambda kv: -kv[1]):
        print(f"  derived {n:3d} layout edges as {etype} (at {level} level)")


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

    # Per-document metadata, which the parser already reads out of each map's
    # title node. It used to exist only inside the Neo4j export, which made
    # every other consumer depend on that exporter having been run; writing it
    # here makes the parser the single source, like nodes.csv and edges.csv.
    with (DATA_DIR / "documents.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "date", "family", "title", "author", "outlet", "url",
                    "genre", "shape", "topics"])
        for d in sorted(docs, key=lambda x: x["date"]):
            m = d.get("meta") or {}
            w.writerow([d["doc"], d["date"], d["family"], m.get("title", ""),
                        m.get("author", ""), m.get("outlet", ""), m.get("url", ""),
                        m.get("genre", ""), m.get("shape", ""), m.get("topics", "")])

    with (DATA_DIR / "edges.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doc", "family", "date", "from", "to", "type", "polarity",
                    "raw", "relation_source", "relation_level",
                    "relation_purity", "needs_review"])
        for d in docs:
            for e in d["edges"]:
                w.writerow([d["doc"], d["family"], d["date"], e["from"], e["to"],
                            e["type"] or "", e["polarity"], e["raw"],
                            e.get("relation_source", "arrow"),
                            e.get("relation_level", ""),
                            e.get("relation_purity", ""),
                            int(e["needs_review"])])

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


def propose_concepts(docs: list[dict], smap: dict) -> None:
    """Suggest candidate cross-document concepts, by two independent detectors.

    Deliberately crude and deliberately not applied: it writes a candidate file
    for the team to accept, rename or reject. Concept assignment is the
    analysis, not a preprocessing step.

    TWO DETECTORS, because wording and reasoning are not the same signal.

    `wording` - shared distinctive terms. The original. It finds a claim restated
    in similar words across articles.

      Measured 2026-10-19: it was also finding SLOT LABELS. The token set was
      `header + text`, and `header` is the schema slot name ("Studies and
      sources", "Data") on 92 of 92 `banner`-family nodes and 55 of 70 `meta`
      ones, against 1 of 197 `plain` ones. A slot label appears in 13-27 nodes,
      which sits inside the `2 <= c <= 25` distinctiveness window, so two
      articles "matched" for both having an evidence slot. Dropping a header
      that is a known slot label took 29 candidate groups to 15 - half were
      artifacts. The window itself turned out to be fine and is unchanged.

    `structure` - the same reasoning applied to the same magnitudes, whatever
    the wording. A prior is machinery: it binds a `variable` facet and it emits
    a relation. Two priors in different articles with the same variable
    signature and the same emitted relation are candidates to be one concept
    even with no vocabulary in common.

      This is the detector that matters if the goal is mental models rather than
      claims, because a model recurs as reasoning and not as phrasing. Measured
      on the same corpus, it finds 4 groups over 9 nodes, and its two best are
      invisible to `wording` - 1 and 0 shared distinctive tokens against a
      threshold of 3:

        jun_4_18#P3    "Countries under pressure often rely on weaker
                        currencies and exports"                        (2018)
        2025-07-07#P1  "A large real estate crisis typically pushes a
                        country to rely more on exports"               (2025)

      Scope is the `warrant.prior` and `revision` families of the `oper`
      hierarchy - the priors, deliberately not `warrant.mechanism`, which is the
      split schema_map.yaml already measures as worth keeping. Needs
      data/node_facets.csv from a labelling run; says so and skips if absent.
    """
    stop = set("""the a an and or of to in for on with that this it is are was were be been
        as at by from not no than then so such but if when which who what how why more most
        less least its their his her our your они about over under into out up down off
        china chinese u.s. us american europe european""".split())

    nodes = [(d["doc"], n) for d in docs for ns in d["levels"].values() for n in ns]

    # The slot labels the parser itself recognizes. Derived, not listed again
    # here, so a new header added to schema_map.yaml is excluded automatically.
    slot_labels = {h.lower() for h in smap["node_types_by_header"]}

    df = Counter()
    toks: dict[tuple[str, str], set[str]] = {}
    for doc, n in nodes:
        # Only use `header` where it carries the claim. On the templated maps it
        # is the schema slot name, and two articles both having a "Data" slot is
        # not evidence that they share a concept.
        source = (n["text"] if n["header"].strip().lower() in slot_labels
                  else n["header"] + " " + n["text"])
        t = {w for w in re.findall(r"[a-z][a-z\-']{3,}", source.lower())
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

    struct, struct_note = propose_structural(docs, smap)

    out = ["# Candidate concepts - PROPOSALS ONLY, not applied.",
           "#",
           "# Two detectors, listed separately because they are different evidence.",
           "#",
           "#   wording    nodes of the same type, in different documents, sharing",
           "#              distinctive vocabulary. A claim restated.",
           "#   structure  priors in different documents binding the same `variable`",
           "#              facet and emitting the same relation. The same reasoning",
           "#              applied, whatever the words. This is the one to read first",
           "#              if you are looking for a recurring mental model - its best",
           "#              candidates share almost no vocabulary, so `wording` cannot",
           "#              see them.",
           "#",
           "# Review every one: keep and name the real ones, delete the rest, then move",
           "# them into scripts/concepts.yaml by hand. Nothing here is applied.",
           "",
           "concepts:"]

    for i, cluster in enumerate(groups[:40], 1):
        kind = cluster[0][1]["type"]
        out += [f"  wording-{i:02d}-{kind.replace('_', '-')}:",
                f"    detector: wording",
                f"    note: {len(cluster)} nodes, type {kind}",
                "    nodes:"]
        for doc, n in cluster:
            snippet = n["text"].replace("\n", " ")[:88]
            out.append(f"      - {doc}#{n['id']}    # {snippet}")
        out.append("")

    if struct_note:
        out += [f"  # structure detector: {struct_note}", ""]
    for i, (sig, cluster) in enumerate(struct[:40], 1):
        variables, relations = sig
        out += [f"  structure-{i:02d}-prior:",
                f"    detector: structure",
                f"    variable: [{', '.join(sorted(variables))}]",
                f"    emits: [{', '.join(sorted(relations)) or 'nothing'}]",
                f"    note: {len(cluster)} priors over "
                f"{len({d for d, _ in cluster})} documents, same variable "
                f"signature and same emitted relation",
                "    nodes:"]
        for doc, n in cluster:
            snippet = (n["text"] or n["header"]).replace("\n", " ")[:88]
            out.append(f"      - {doc}#{n['id']}    # [{n['type']}] {snippet}")
        out.append("")

    path = DATA_DIR / "concepts_proposed.yaml"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"  {path.relative_to(ROOT)}  "
          f"({len(groups)} by wording, {len(struct)} by structure)")
    if struct_note:
        print(f"    structure detector: {struct_note}")


def propose_structural(docs: list[dict], smap: dict) -> tuple[list, str]:
    """Priors that recur as REASONING: same `variable` facet, same relation emitted.

    Returns (groups, note). The note is non-empty when the detector could not
    run, and is reported rather than swallowed - a silent zero would read as
    "no recurring priors", which is a different claim entirely.
    """
    facets_csv = DATA_DIR / "node_facets.csv"
    if not facets_csv.exists():
        return [], ("skipped - needs data/node_facets.csv; "
                    "run scripts/label_facets.py first")

    oper = smap["role_families"]["oper"]
    # the priors, and a prior the author later changed. NOT warrant.mechanism:
    # schema_map.yaml measures that split as worth keeping, so honour it here.
    prior_types = set(oper.get("warrant.prior") or []) | set(oper.get("revision") or [])

    variables: dict[tuple[str, str], set] = defaultdict(set)
    with facets_csv.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["facet"] == "variable":
                variables[(r["doc"], r["node_id"])].add(r["value"])

    emits: dict[tuple[str, str], set] = defaultdict(set)
    for d in docs:
        for e in d["edges"]:
            if e["type"]:
                emits[(d["doc"], e["from"])].add(e["type"])

    sigs: dict[tuple, list] = defaultdict(list)
    labelled = 0
    for d in docs:
        for ns in d["levels"].values():
            for n in ns:
                if n["type"] not in prior_types:
                    continue
                key = (d["doc"], n["id"])
                var = variables.get(key)
                if not var:
                    continue
                labelled += 1
                sigs[(frozenset(var), frozenset(emits.get(key, ())))].append((d["doc"], n))

    out = [(sig, cl) for sig, cl in sigs.items() if len({doc for doc, _ in cl}) > 1]
    out.sort(key=lambda kv: -len(kv[1]))
    note = ""
    if not labelled:
        note = ("ran, but no prior carries a `variable` facet - "
                "label_facets.py has not covered these documents")
    elif not out:
        note = f"ran over {labelled} labelled priors; no signature spans two documents"
    return out, note


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
    derive_layout_relations(docs, smap, issues)
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
        propose_concepts(docs, smap)


if __name__ == "__main__":
    main()
