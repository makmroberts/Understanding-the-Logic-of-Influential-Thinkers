#!/usr/bin/env python3
"""Export the argument graph as AIF, and check it conforms.

    python scripts/export_aif.py              # -> data/aif/<doc>.json + corpus.json
    python scripts/export_aif.py --check      # conformance only, no write

Reads   data/nodes.csv, data/edges.csv, scripts/source_urls.yaml,
        scripts/schema_map.yaml (role_families)
Writes  data/aif/*.json, data/aif/conformance.md

WHY THIS EXISTS, AND WHY IT IS NOT A REWRITE

The role axis in this project is one annotator's vocabulary: 26 types over seven
levels. Keeping rules keyed to it is the over-specification risk - a second
thinker, annotator or domain would have to re-decide all of it. The standard
answer is to specialise an upper ontology rather than invent one, and the upper
ontology for argument graphs is the Argument Interchange Format (Chesnevar et
al., Knowledge Engineering Review 2006), which exists to be "an interlingua
between various reifications".

So this does NOT replace the native model. The vault stays the knowledge graph
and the .mmd maps stay the record. This emits AIF alongside them, which buys two
things:

  1. INTEROPERABILITY. 92% of our claims map onto Toulmin's six elements, which
     AIF already represents as I-nodes. A corpus that round-trips through an
     interlingua is not a private dialect.
  2. A CONFORMANCE TEST. AIF's core constraint is that an argument relation is
     REIFIED as a node: an I-node never links directly to another I-node; it
     links through an S-node (RA for inference, CA for conflict, PA for
     preference). That constraint is strict enough to catch real modelling
     errors, so --check is a test of the graph and not just of this exporter.

WHAT AIF CANNOT HOLD, WHICH IS THE INTERESTING PART

28 of 359 claims have no Toulmin slot and no home in AIF's single-argument core:

  framing    question, position_map, deferred_question - article-level
             apparatus. This is AIF+ dialogue territory, not argument structure.
  revision   revised_prior - a change of mind ACROSS articles. Neither Toulmin
             nor AIF has anywhere to put it, and it is what this project is for.

Those are exported as I-nodes carrying their family, and the conformance report
names them as the part of the model that is genuinely ours. Pretending they fit
would be worse than recording that they do not.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NODES = ROOT / "data" / "nodes.csv"
EDGES = ROOT / "data" / "edges.csv"
DOCS = ROOT / "data" / "documents.csv"             # written by parse_maps
URL_MAP = ROOT / "scripts" / "source_urls.yaml"
SCHEMA = ROOT / "scripts" / "schema_map.yaml"
OUT = ROOT / "data" / "aif"
REPORT = OUT / "conformance.md"

# Our relations onto AIF's three S-node kinds. Conflict is CA; everything that
# advances the argument is an inference (RA). `frames` and `defers` are neither:
# they are structural, so they are exported as RA nodes carrying their own
# scheme name rather than being dropped - losing them would re-create exactly
# the hole the `~~~` recovery closed.
# Which relations are conflict applications is NOT re-typed here either: it is
# exactly `pushes_back_relations` in schema_map.yaml. See build_s_kind().
S_KIND_RA = ("supports", "licenses", "bounds", "motivates", "reconstructs",
             "frames", "defers")


S_KIND: dict = {}


def build_s_kind(spec: dict) -> dict:
    """Relation -> AIF scheme node kind, from the config's own polarity list."""
    kind = {r: "RA" for r in S_KIND_RA}
    for r in spec.get("pushes_back_relations") or ():
        kind[r] = "CA"
    return kind


def families(spec: dict) -> tuple[dict, dict]:
    rf = spec.get("role_families") or {}
    out = []
    for level in ("toulmin", "oper"):
        m = {}
        for name, members in (rf.get(level) or {}).items():
            for t in members:
                m[t] = name
        out.append(m)
    return out[0], out[1]


def build() -> tuple[dict, list]:
    spec = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    global S_KIND
    S_KIND = build_s_kind(spec)
    toulmin, oper = families(spec)
    nodes = list(csv.DictReader(NODES.open(encoding="utf-8")))
    edges = list(csv.DictReader(EDGES.open(encoding="utf-8")))
    meta = load_doc_meta(nodes)

    per_doc: dict[str, dict] = defaultdict(lambda: {"nodes": [], "edges": []})
    issues: list[str] = []
    counter = 0

    def nid() -> str:
        nonlocal counter
        counter += 1
        return str(counter)

    inode = {}
    for n in nodes:
        key = (n["doc"], n["node_id"])
        i = nid()
        inode[key] = i
        per_doc[n["doc"]]["nodes"].append({
            "nodeID": i,
            "text": n["text"].replace("\n", " ").strip(),
            "type": "I",
            # extensions: the native role, and the two family levels it
            # specialises. An AIF consumer ignores these; a second annotator
            # maps their own types onto them.
            "role": n["type"],
            "toulmin": toulmin.get(n["type"], "unassigned"),
            "oper": oper.get(n["type"], "unassigned"),
            "localID": f'{n["doc"]}#{n["node_id"]}',
        })

    for e in edges:
        a, b = (e["doc"], e["from"]), (e["doc"], e["to"])
        if a not in inode or b not in inode:
            issues.append(f"edge to a node not in nodes.csv: {a} -> {b}")
            continue
        rel = e["type"] or "unresolved"
        kind = S_KIND.get(rel)
        if kind is None:
            issues.append(f"relation `{rel}` has no AIF S-node kind")
            kind = "RA"
        s = nid()
        per_doc[e["doc"]]["nodes"].append({
            "nodeID": s, "text": rel, "type": kind, "scheme": rel,
            "relation_source": e.get("relation_source", ""),
            "relation_level": e.get("relation_level", ""),
            "relation_purity": e.get("relation_purity", ""),
        })
        # the reification: I -> S -> I, never I -> I
        per_doc[e["doc"]]["edges"].append({"edgeID": nid(),
                                           "fromID": inode[a], "toID": s})
        per_doc[e["doc"]]["edges"].append({"edgeID": nid(),
                                           "fromID": s, "toID": inode[b]})

    for doc, g in per_doc.items():
        m = meta.get(doc, {})
        g["locutions"] = []
        g["source"] = {"doc": doc, "title": m.get("title", ""),
                       "date": m.get("date", ""), "url": m.get("url", "")}
    return per_doc, issues


def load_doc_meta(nodes: list) -> dict:
    """Per-document title, date and url, without depending on another exporter.

    This used to read data/neo4j/documents.csv, which made the AIF export fail
    outright whenever the Neo4j export had not been run or had been cleaned
    away - one exporter depending on another's artefact. The date is already on
    every node and the url is in source_urls.yaml, so both are read from the
    sources. documents.csv is still preferred when it happens to exist, because
    it also carries the article title.
    """
    meta: dict = {}
    if DOCS.exists():
        meta = {d["id"]: d for d in csv.DictReader(DOCS.open(encoding="utf-8"))}
    urls = {}
    if URL_MAP.exists():
        spec = yaml.safe_load(URL_MAP.read_text(encoding="utf-8")) or {}
        for doc, entry in (spec.get("urls") or {}).items():
            urls[doc] = (entry or {}).get("url", "") if isinstance(entry, dict) else ""
    for n in nodes:
        d = meta.setdefault(n["doc"], {})
        d.setdefault("date", n.get("date", ""))
        d.setdefault("title", "")
        if not d.get("url"):
            d["url"] = urls.get(n["doc"], "")
    return meta


def check_hierarchy(spec: dict) -> list:
    """Every `oper` family must roll up into exactly one Toulmin family.

    The levels are a specialisation hierarchy, so a family that spans two
    parents is not a refinement of either. This caught `case_type`, which sat
    under `claim.step` at the operational level and `unassigned` at the Toulmin
    level - and the inconsistency only surfaced as one fixture node becoming
    unreachable when a question was dropped.
    """
    rf = spec.get("role_families") or {}
    tou = {t: f for f, m in (rf.get("toulmin") or {}).items() for t in m}
    out = []
    for ofam, members in (rf.get("oper") or {}).items():
        parents = {tou.get(t, "?") for t in members}
        if len(parents) != 1:
            out.append(f"oper family `{ofam}` rolls up into {sorted(parents)} - "
                       f"a specialisation must have exactly one parent")
    missing = sorted(set(tou) - {t for m in (rf.get("oper") or {}).values() for t in m})
    if missing:
        out.append(f"types absent from the oper level: {missing}")
    return out


def check(per_doc: dict) -> tuple[list, dict]:
    """AIF's core constraints. These catch modelling errors, not just bugs."""
    problems: list[str] = []
    stats = Counter()
    for doc, g in per_doc.items():
        by_id = {n["nodeID"]: n for n in g["nodes"]}
        if len(by_id) != len(g["nodes"]):
            problems.append(f"{doc}: duplicate nodeID")
        indeg, outdeg = Counter(), Counter()
        for e in g["edges"]:
            f, t = by_id.get(e["fromID"]), by_id.get(e["toID"])
            if f is None or t is None:
                problems.append(f"{doc}: edge references a missing node")
                continue
            if f["type"] == "I" and t["type"] == "I":
                problems.append(f"{doc}: I-node linked directly to an I-node - "
                                f"an argument relation must be reified")
            if f["type"] != "I" and t["type"] != "I":
                problems.append(f"{doc}: S-node linked directly to an S-node")
            outdeg[e["fromID"]] += 1
            indeg[e["toID"]] += 1
        for n in g["nodes"]:
            stats[n["type"]] += 1
            if n["type"] != "I" and not (indeg[n["nodeID"]] and outdeg[n["nodeID"]]):
                problems.append(f"{doc}: {n['type']}-node `{n.get('scheme')}` "
                                f"is not between two I-nodes")
        stats["edges"] += len(g["edges"])
    return problems, stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="conformance only, write nothing")
    args = ap.parse_args()

    per_doc, issues = build()
    problems, stats = check(per_doc)
    problems += check_hierarchy(yaml.safe_load(
        SCHEMA.read_text(encoding="utf-8")))

    nodes = list(csv.DictReader(NODES.open(encoding="utf-8")))
    spec = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    toulmin, _ = families(spec)
    fam = Counter(toulmin.get(n["type"], "unassigned") for n in nodes)
    outside = {"framing", "revision", "unassigned"}
    n_out = sum(v for k, v in fam.items() if k in outside)

    lines = ["# AIF conformance", "",
             f"- I-nodes: {stats['I']}",
             f"- RA-nodes (inference): {stats['RA']}",
             f"- CA-nodes (conflict): {stats['CA']}",
             f"- edges: {stats['edges']} (every argument relation reified as "
             f"I -> S -> I)", "",
             "## Core constraints", ""]
    lines.append("- no I-node links directly to another I-node: "
                 + ("PASS" if not any("directly to an I-node" in p
                                      for p in problems) else "FAIL"))
    lines.append("- every S-node sits between two I-nodes: "
                 + ("PASS" if not any("not between two" in p
                                      for p in problems) else "FAIL"))
    lines.append("- role hierarchy rolls up (each oper family has one Toulmin "
                 "parent): " + ("PASS" if not any("rolls up into" in p
                                                  for p in problems) else "FAIL"))
    lines.append("- every relation has an AIF S-node kind: "
                 + ("PASS" if not any("no AIF S-node kind" in i
                                      for i in issues) else "FAIL"))
    lines += ["", "## Toulmin coverage", "",
              "| element | claims |", "|---|---|"]
    for k, v in fam.most_common():
        lines.append(f"| {k} | {v} |")
    lines += ["",
              f"**{len(nodes) - n_out} of {len(nodes)} claims "
              f"({(len(nodes)-n_out)/len(nodes):.0%}) occupy a Toulmin element.** "
              f"The remaining {n_out} are `framing` (article-level apparatus - "
              f"AIF+ dialogue territory), `revision` (a change of mind across "
              f"articles, which neither Toulmin nor AIF can hold) and "
              f"`unassigned`. That residue is the part of this model that is "
              f"genuinely ours, and it is recorded rather than forced into a "
              f"slot it does not fit.", ""]
    if problems or issues:
        lines += ["## Problems", ""]
        for p in sorted(set(problems))[:40]:
            lines.append(f"- {p}")
        for i in sorted(set(issues))[:20]:
            lines.append(f"- {i}")
        lines.append("")

    if not args.check:
        OUT.mkdir(parents=True, exist_ok=True)
        for doc, g in per_doc.items():
            (OUT / f"{doc}.json").write_text(
                json.dumps(g, indent=1, ensure_ascii=False), encoding="utf-8")
        merged = {"nodes": [n for g in per_doc.values() for n in g["nodes"]],
                  "edges": [e for g in per_doc.values() for e in g["edges"]],
                  "locutions": []}
        (OUT / "corpus.json").write_text(
            json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")
        REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {len(per_doc)} AIF documents + corpus.json to data/aif/")

    print(f"  I {stats['I']}  RA {stats['RA']}  CA {stats['CA']}  "
          f"edges {stats['edges']}")
    print(f"  Toulmin-expressible: {len(nodes) - n_out}/{len(nodes)} "
          f"({(len(nodes)-n_out)/len(nodes):.0%})")
    if problems or issues:
        print(f"  {len(set(problems))} conformance problems, "
              f"{len(set(issues))} mapping issues - see {REPORT.name}")
    else:
        print("  conformance: PASS")


if __name__ == "__main__":
    main()
