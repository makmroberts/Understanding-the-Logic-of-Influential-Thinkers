#!/usr/bin/env python3
"""Export the parsed argument graph to Neo4j.

Usage:
    python scripts/parse_maps.py          # first - produces data/graph.json
    python scripts/export_neo4j.py        # writes data/neo4j/

Produces two ways in, because they suit different moments:

    data/neo4j/load.cypher    self-contained. Paste into Neo4j Browser or run
                              through cypher-shell. No import directory, no
                              file mounting, no APOC. This is the easy path.
    data/neo4j/*.csv          the same graph as flat files, for `LOAD CSV` or
                              neo4j-admin import if the corpus ever outgrows
                              a paste-able script.

Graph model
-----------
    (:Document {id, title, date, outlet, url, genre, shape, topics})
    (:Claim:<Type> {uid, doc, nid, type, level, header, text, ...})
    (:Concept {id, label, note})

    (:Claim)-[:IN]->(:Document)
    (:Claim)-[:SUPPORTS|LICENSES|BOUNDS|MOTIVATES|RECONSTRUCTS       // forward
             |REVISES|REBUTS|QUALIFIED_BY|UNDERCUT_BY|DEFERS         // push-back
             {raw, polarity, labelled}]->(:Claim)
    (:Claim)-[:INSTANCE_OF]->(:Concept)

Every claim carries a second label for its type (`:Claim:Mechanism`), so the
obvious Cypher works: MATCH (m:Mechanism)-[:SUPPORTS]->(k:MainClaim).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "graph.json"
CONCEPTS = Path(__file__).resolve().parent / "concepts.yaml"
OUT = ROOT / "data" / "neo4j"

# Properties that belong on the node but are not worth a column of nulls.
# Neo4j Browser captions a node with its `name` property, so every node gets a
# short one. Without it the whole graph renders as blank circles.
NODE_PROPS = ["uid", "name", "doc", "family", "nid", "type", "level", "header", "text",
              "type_source", "claim_type", "mechanism_kind", "implicit_only",
              "concept", "date"]


def label_for(type_name: str) -> str:
    """mechanism -> Mechanism; evidence_data -> EvidenceData."""
    return "".join(p.capitalize() for p in re.split(r"[_\s]+", type_name) if p)


def rel_for(edge_type: str | None) -> str:
    """qualified_by -> QUALIFIED_BY; an unresolved type -> RELATED."""
    return edge_type.upper() if edge_type else "RELATED"


def cy(value) -> str:
    """A Cypher literal. json.dumps gives valid Cypher for strings and scalars."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def cy_map(d: dict) -> str:
    return "{" + ", ".join(f"{k}: {cy(v)}" for k, v in d.items()) + "}"


def load() -> tuple[list, list, list, dict]:
    if not GRAPH.exists():
        raise SystemExit("data/graph.json missing - run scripts/parse_maps.py first")
    docs = json.loads(GRAPH.read_text(encoding="utf-8"))["documents"]

    documents, claims, edges = [], [], []
    for d in docs:
        documents.append({"id": d["doc"], "date": d["date"],
                          "name": f"{d['date'][:7]} {d['meta']['title']}"[:60],
                          "family": d["family"], **d["meta"]})
        for nodes in d["levels"].values():
            for n in nodes:
                caption = n["header"] or n["text"]
                caption = " ".join(caption.split())
                if len(caption) > 46:
                    caption = caption[:45].rsplit(" ", 1)[0] + "…"
                claims.append({
                    "uid": f"{d['doc']}#{n['id']}",
                    "name": f"{n['id']}  {caption}",
                    "doc": d["doc"], "nid": n["id"], "date": d["date"],
                    "family": d["family"],
                    "type": n["type"], "level": n["level"],
                    "header": n["header"], "text": n["text"],
                    "type_source": n["type_source"],
                    "claim_type": n.get("claim_type", ""),
                    "mechanism_kind": n.get("mechanism_kind", ""),
                    "implicit_only": bool(n["implicit_only"]),
                    "concept": n.get("concept", ""),
                })
        for e in d["edges"]:
            edges.append({
                "src": f"{d['doc']}#{e['from']}",
                "dst": f"{d['doc']}#{e['to']}",
                "type": e["type"], "raw": e["raw"],
                "polarity": e["polarity"],
                "labelled": bool(e["raw"]),
            })

    concepts = {}
    if CONCEPTS.exists():
        spec = yaml.safe_load(CONCEPTS.read_text(encoding="utf-8")) or {}
        for cid, entry in (spec.get("concepts") or {}).items():
            entry = entry or {}
            concepts[cid] = {"id": cid,
                             "name": entry.get("label", cid),
                             "label": entry.get("label", cid),
                             "note": " ".join((entry.get("note") or "").split())}
    return documents, claims, edges, concepts


def write_cypher(documents, claims, edges, concepts) -> Path:
    out = ["// Argument graph - generated by scripts/export_neo4j.py",
           "// Safe to re-run: everything is MERGEd on a stable key.", "",
           "CREATE CONSTRAINT claim_uid IF NOT EXISTS",
           "  FOR (c:Claim) REQUIRE c.uid IS UNIQUE;",
           "CREATE CONSTRAINT document_id IF NOT EXISTS",
           "  FOR (d:Document) REQUIRE d.id IS UNIQUE;",
           "CREATE CONSTRAINT concept_id IF NOT EXISTS",
           "  FOR (c:Concept) REQUIRE c.id IS UNIQUE;", ""]

    out += ["// ---- documents ----",
            "UNWIND [" + ",\n  ".join(cy_map(d) for d in documents) + "] AS d",
            "MERGE (n:Document {id: d.id}) SET n += d;", ""]

    if concepts:
        out += ["// ---- concepts ----",
                "UNWIND [" + ",\n  ".join(cy_map(c) for c in concepts.values()) + "] AS c",
                "MERGE (n:Concept {id: c.id}) SET n += c;", ""]

    out.append("// ---- claims, one block per type so each gets its own label ----")
    by_type: dict[str, list] = {}
    for c in claims:
        by_type.setdefault(c["type"], []).append(c)
    for type_name, group in sorted(by_type.items()):
        out += [f"// {len(group)} x {type_name}",
                "UNWIND [" + ",\n  ".join(cy_map(c) for c in group) + "] AS c",
                f"MERGE (n:Claim:{label_for(type_name)} {{uid: c.uid}}) SET n += c;", ""]

    out += ["// ---- claim -> document ----",
            "MATCH (c:Claim), (d:Document) WHERE c.doc = d.id MERGE (c)-[:IN]->(d);", ""]

    if concepts:
        out += ["// ---- claim -> concept ----",
                "MATCH (c:Claim), (k:Concept) WHERE c.concept = k.id",
                "MERGE (c)-[:INSTANCE_OF]->(k);", ""]

    out.append("// ---- argument edges, one block per relationship type ----")
    by_rel: dict[str, list] = {}
    for e in edges:
        by_rel.setdefault(rel_for(e["type"]), []).append(e)
    for rel, group in sorted(by_rel.items()):
        rows = [cy_map({"src": e["src"], "dst": e["dst"], "raw": e["raw"],
                        "polarity": e["polarity"], "labelled": e["labelled"]})
                for e in group]
        out += [f"// {len(group)} x {rel}",
                "UNWIND [" + ",\n  ".join(rows) + "] AS e",
                "MATCH (a:Claim {uid: e.src}), (b:Claim {uid: e.dst})",
                f"MERGE (a)-[r:{rel}]->(b)",
                "SET r.raw = e.raw, r.polarity = e.polarity, r.labelled = e.labelled;", ""]

    path = OUT / "load.cypher"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def write_csvs(documents, claims, edges, concepts) -> None:
    def dump(name: str, rows: list, cols: list) -> None:
        with (OUT / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    dump("documents.csv", documents,
         ["id", "date", "family", "title", "author", "outlet", "url", "genre", "shape", "topics"])
    dump("claims.csv", claims, NODE_PROPS + ["nid"])
    dump("edges.csv", [{**e, "rel": rel_for(e["type"])} for e in edges],
         ["src", "dst", "rel", "type", "raw", "polarity", "labelled"])
    if concepts:
        dump("concepts.csv", list(concepts.values()), ["id", "label", "note"])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    documents, claims, edges, concepts = load()
    path = write_cypher(documents, claims, edges, concepts)
    write_csvs(documents, claims, edges, concepts)

    kb = path.stat().st_size / 1024
    print(f"{len(documents)} documents, {len(claims)} claims, {len(edges)} edges, "
          f"{len(concepts)} concepts")
    print(f"  data/neo4j/load.cypher   ({kb:.0f} KB, paste into Neo4j Browser)")
    print(f"  data/neo4j/*.csv         (for LOAD CSV / neo4j-admin import)")
    labels = sorted({label_for(c["type"]) for c in claims})
    rels = sorted({rel_for(e["type"]) for e in edges})
    print(f"  labels: {', '.join(labels)}")
    print(f"  rels:   {', '.join(rels)}")


if __name__ == "__main__":
    main()
