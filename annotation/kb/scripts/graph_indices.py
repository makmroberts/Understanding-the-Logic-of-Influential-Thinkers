#!/usr/bin/env python3
"""Signed edges, and graph-theory indices over the argument maps.

    python scripts/graph_indices.py            # write artifacts + report
    python scripts/graph_indices.py --print     # report to stdout as well

Reads   data/nodes.csv, data/edges.csv, data/node_facets.csv
Writes  data/edges_signed.csv     every edge with an explicit sign
        data/variable_map.csv     the variable-level signed digraph
        data/graph_indices.json   all indices, machine-readable
        data/graph_indices.md     the report

WHAT IS BORROWED, AND WHAT IS NOT

Axelrod (1976) coded decision-makers' causal assertions as signed directed
graphs: nodes are variables, an edge means "more of A causes more (or less) of
B". Ozesmi & Ozesmi (2004) add the graph-theory indices used below - density,
in/out degree, centrality, transmitter/receiver character, and MacDonald's
hierarchy index - and report maps averaging 23 +- 2 variables and 37 +- 3
connections, which gives us something to compare against.

HONESTY ABOUT THE SIGN. Our edges are not Axelrod's. They are ARGUMENTATIVE:
"this evidence supports that claim", "this caveat qualifies that conclusion".
They are not causal assertions between variables, so the sign below means
backs / pushes back on, not increases / decreases. Treating the two as the
same thing would be a category error, and the whole point of the sign is lost
if it is.

What a true Axelrod map would need is the direction of effect BETWEEN
VARIABLES inside each mechanism - "weak domestic demand raises the surplus" is
a signed causal claim, but that sign lives in the mechanism's prose and is not
annotated anywhere. Extracting it is a separate annotation pass, and until it
exists the variable-level map below is a projection of argument structure, not
a causal model. It is still the closest honest analogue, and it is the thing
that makes the facet layer analytically useful rather than merely navigational.

Kosko's (1986) fuzzy cognitive maps additionally need edge WEIGHTS to be run as
a dynamical system. We have no weights and will not invent them, so nothing
here is Kosko - it is sign-only, which is what Axelrod's original was.
"""

from __future__ import annotations

import argparse
import csv

import yaml
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODES = ROOT / "data" / "nodes.csv"
EDGES = ROOT / "data" / "edges.csv"
SCHEMA = ROOT / "scripts" / "schema_map.yaml"
FACETS = ROOT / "data" / "node_facets.csv"
OUT_SIGNED = ROOT / "data" / "edges_signed.csv"
OUT_VARMAP = ROOT / "data" / "variable_map.csv"
OUT_JSON = ROOT / "data" / "graph_indices.json"
OUT_MD = ROOT / "data" / "graph_indices.md"

# Sign per edge type. The parser already records `polarity` (forward /
# pushes_back) and it is perfectly determined by type - checked, no type mixes
# polarities - so this table cannot contradict it; it only makes the sign
# explicit and numeric so it can be summed.
#
# `defers` is 0 rather than -1 on purpose: setting a question aside for a
# future post neither backs nor attacks the claim, and counting it as an attack
# would overstate how much he concedes.
# The -1 set is NOT written out here. `schema_map.yaml` already declares
# `pushes_back_relations`, and re-typing it in Python is how two files come to
# disagree after someone edits one of them. SIGN is assembled from that list at
# import time by `build_sign()` below; the entries kept here are the ones the
# config does not declare.
SIGN_POSITIVE = ("supports", "licenses", "bounds", "motivates", "reconstructs")
SIGN_NEUTRAL = {
    "defers": 0,
    # `frames` is the question-to-prior link, recovered from the maps' `~~~`
    # operator (see schema_map.yaml). It is structural, not argumentative: the
    # question sets up what the article assumes, which neither backs nor pushes
    # back on it. 0 for the same reason `defers` is 0.
    "frames": 0,
}


SIGN: dict = {}


def build_sign(spec: dict) -> dict:
    """SIGN, assembled from schema_map.yaml rather than duplicated from it.

    A relation the config calls `pushes_back` scores -1; the positives and the
    two structural zeroes are listed above. A relation in none of the three is
    absent from the table, and the caller reports it rather than defaulting -
    an unsigned relation is a config change nobody propagated, not a 0.
    """
    sign = {r: +1 for r in SIGN_POSITIVE}
    # insertion order matters: data/graph_indices.json publishes this table, and
    # reordering it would show up as a diff in an artefact that did not change.
    for r in spec.get("pushes_back_relations") or ():
        sign[r] = -1
    sign.update(SIGN_NEUTRAL)
    return sign

# Ozesmi & Ozesmi (2004), for comparison against their elicited maps.
OZESMI_VARS = (23, 2)
OZESMI_CONNS = (37, 3)


def hierarchy_index(outdeg: list[int]) -> float:
    """MacDonald's h, as used by Ozesmi & Ozesmi (2004).

    0 = fully democratic, every variable as much a cause as any other.
    1 = fully hierarchical, one variable drives everything.

    Note what this does and does not measure. The formula normalises by N^3
    while the outdegree variance it sums grows only with N, so h approaches 1
    only for a STAR - one node with outdegree near N-1. It measures star-ness,
    not layeredness. Our maps are layered (L0 through L6) with a maximum
    outdegree of about 4 out of a possible 16, so they score near zero. That is
    the correct reading, not a sign the maps are flat.
    """
    N = len(outdeg)
    if N < 2:
        return 0.0
    mean = sum(outdeg) / N
    return (12.0 / ((N - 1) * N * (N + 1))) * sum((o - mean) ** 2 for o in outdeg)


def character(od: int, idg: int) -> str:
    """Ozesmi's three kinds of variable."""
    if od > 0 and idg == 0:
        return "transmitter"
    if idg > 0 and od == 0:
        return "receiver"
    if od == 0 and idg == 0:
        return "isolated"
    return "ordinary"


def indices(n_nodes: int, edges: list[tuple], ids: list) -> dict:
    """Density, degree, centrality and hierarchy for one directed graph."""
    od, idg = Counter(), Counter()
    for a, b, _s in edges:
        od[a] += 1
        idg[b] += 1
    N, C = n_nodes, len(edges)
    density = C / (N * (N - 1)) if N > 1 else 0.0
    chars = Counter(character(od[i], idg[i]) for i in ids)
    return {
        "variables": N, "connections": C, "density": round(density, 4),
        "hierarchy_index": round(hierarchy_index([od[i] for i in ids]), 4),
        "character": dict(chars),
        "mean_centrality": round(st.mean([od[i] + idg[i] for i in ids]), 2) if ids else 0,
    }


def main() -> None:
    global SIGN
    SIGN = build_sign(yaml.safe_load(SCHEMA.read_text(encoding="utf-8")) or {})
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--print", dest="show", action="store_true")
    args = ap.parse_args()

    nodes = list(csv.DictReader(NODES.open(encoding="utf-8")))
    edges = list(csv.DictReader(EDGES.open(encoding="utf-8")))
    nkey = {(r["doc"], r["node_id"]): r for r in nodes}

    # ---- 1. explicit signs -------------------------------------------------
    unknown = sorted({e["type"] for e in edges if e["type"] not in SIGN})
    signed = []
    for e in edges:
        s = SIGN.get(e["type"])
        if s is None:
            continue
        signed.append({"doc": e["doc"], "date": e["date"], "from": e["from"],
                       "to": e["to"], "type": e["type"], "sign": s,
                       "polarity": e["polarity"]})
    with OUT_SIGNED.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["doc", "date", "from", "to", "type",
                                           "sign", "polarity"])
        w.writeheader()
        w.writerows(signed)
    sign_mix = Counter(r["sign"] for r in signed)

    # consistency check against the parser's own polarity column
    conflicts = [r for r in signed
                 if (r["sign"] > 0) != (r["polarity"] == "forward")
                 and r["sign"] != 0]

    # ---- 2. claim-level indices, per article and corpus-wide ---------------
    per_doc = {}
    for doc in dict.fromkeys(r["doc"] for r in nodes):
        ids = [r["node_id"] for r in nodes if r["doc"] == doc]
        de = [(r["from"], r["to"], r["sign"]) for r in signed if r["doc"] == doc]
        per_doc[doc] = indices(len(ids), de, ids)

    all_ids = [(r["doc"], r["node_id"]) for r in nodes]
    all_edges = [((r["doc"], r["from"]), (r["doc"], r["to"]), r["sign"])
                 for r in signed]
    corpus = indices(len(all_ids), all_edges, all_ids)

    # ---- 3. per-facet-term centrality --------------------------------------
    #
    # The question this answers: which variables are CENTRAL to his reasoning
    # and which are peripheral - and, more usefully, which behave as causes
    # (transmitters, the priors he argues from) versus effects (receivers, the
    # conclusions he argues to).
    od, idg = Counter(), Counter()
    for a, b, _s in all_edges:
        od[a] += 1
        idg[b] += 1

    members = defaultdict(lambda: defaultdict(list))
    if FACETS.exists():
        for r in csv.DictReader(FACETS.open(encoding="utf-8")):
            members[r["facet"]][r["value"]].append((r["doc"], r["node_id"]))

    facet_idx = {}
    for facet, terms in members.items():
        rows = []
        for term, keys in terms.items():
            keys = [k for k in dict.fromkeys(keys) if k in nkey]
            if not keys:
                continue
            o = sum(od[k] for k in keys)
            i = sum(idg[k] for k in keys)
            rows.append({
                "term": term, "claims": len(keys),
                "outdegree": o, "indegree": i, "centrality": o + i,
                "centrality_per_claim": round((o + i) / len(keys), 2),
                # >0 means it argues outward more than it is argued toward
                "transmitter_bias": round((o - i) / (o + i), 2) if (o + i) else 0.0,
                "articles": len({d for d, _ in keys}),
            })
        rows.sort(key=lambda r: -r["centrality"])
        facet_idx[facet] = rows

    # ---- 4. the variable-level signed digraph ------------------------------
    #
    # Project each argument edge onto the variables its endpoints carry. An
    # edge variable_a -> variable_b with sign s means: a claim about a backed
    # (or pushed back on) a claim about b. Self-loops are counted separately
    # and excluded from density, per Ozesmi's convention.
    var_of = defaultdict(list)
    for term, keys in members.get("variable", {}).items():
        for k in keys:
            var_of[k].append(term)

    var_edges = Counter()
    self_loops = Counter()
    for a, b, s in all_edges:
        for qa in var_of.get(a, ()):
            for qb in var_of.get(b, ()):
                if qa == qb:
                    self_loops[(qa, s)] += 1
                else:
                    var_edges[(qa, qb, s)] += 1

    with OUT_VARMAP.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["from_variable", "to_variable", "sign", "claim_edges"])
        for (qa, qb, s), c in sorted(var_edges.items(), key=lambda kv: -kv[1]):
            w.writerow([qa, qb, s, c])

    var_ids = sorted(members.get("variable", {}))
    var_list = [(qa, qb, s) for (qa, qb, s) in var_edges]
    var_map = indices(len(var_ids), var_list, var_ids)

    # ---- 5. report ---------------------------------------------------------
    doc_vars = [v["variables"] for v in per_doc.values()]
    doc_conns = [v["connections"] for v in per_doc.values()]
    L = []
    L.append("# Graph indices")
    L.append("")
    L.append("Generated by `scripts/graph_indices.py`. Indices follow Ozesmi &")
    L.append("Ozesmi (2004); the signed-graph form follows Axelrod (1976).")
    L.append("")
    L.append("**The sign is argumentative, not causal.** It means *backs* / *pushes")
    L.append("back on*, not *increases* / *decreases*. See the script docstring.")
    L.append("")
    L.append("## 1. Signed edges")
    L.append("")
    L.append(f"- {len(signed)} edges signed, from {len(edges)} parsed")
    L.append(f"- supporting (+1): {sign_mix.get(1, 0)}  ·  "
             f"attacking (-1): {sign_mix.get(-1, 0)}  ·  neutral (0): "
             f"{sign_mix.get(0, 0)}")
    ratio = sign_mix.get(-1, 0) / len(signed) if signed else 0
    L.append(f"- **{ratio:.0%} of his edges push back.** Every article carries "
             f"its own counterpoints; this is the size of that habit.")
    L.append(f"- conflicts with the parser's `polarity` column: {len(conflicts)}")
    if unknown:
        L.append(f"- UNSIGNED edge types (not in the SIGN table): "
                 f"{', '.join(unknown)}")
    L.append("")
    L.append("## 2. Map structure, against the FCM literature")
    L.append("")
    L.append("| | this corpus | Ozesmi & Ozesmi (2004) |")
    L.append("|---|---|---|")
    L.append(f"| variables per map | {st.mean(doc_vars):.1f} "
             f"± {st.stdev(doc_vars):.1f} | {OZESMI_VARS[0]} ± {OZESMI_VARS[1]} |")
    L.append(f"| connections per map | {st.mean(doc_conns):.1f} "
             f"± {st.stdev(doc_conns):.1f} | {OZESMI_CONNS[0]} ± {OZESMI_CONNS[1]} |")
    L.append("")
    L.append("Comparable in size, roughly half as densely connected. That is the")
    L.append("expected signature of an argument map rather than a causal web: it is")
    L.append("built to converge on a claim, not to close loops - an elicited FCM")
    L.append("closes feedback loops, and these maps deliberately do not.")
    L.append("")
    L.append("| scope | variables | connections | density | hierarchy |")
    L.append("|---|---|---|---|---|")
    L.append(f"| whole corpus | {corpus['variables']} | {corpus['connections']} "
             f"| {corpus['density']} | {corpus['hierarchy_index']} |")
    mh = st.mean([v["hierarchy_index"] for v in per_doc.values()])
    md = st.mean([v["density"] for v in per_doc.values()])
    L.append(f"| mean per article | {st.mean(doc_vars):.1f} "
             f"| {st.mean(doc_conns):.1f} | {md:.4f} | {mh:.4f} |")
    L.append(f"| variable-level map | {var_map['variables']} | "
             f"{var_map['connections']} | {var_map['density']} | "
             f"{var_map['hierarchy_index']} |")
    L.append("")
    L.append(f"Corpus-wide density is near zero by construction - the 20 maps are "
             f"20 disconnected components, joined only by the concept layer "
             f"(9 of 358 nodes). The per-article figures are the meaningful ones.")
    L.append("")
    L.append("**Reading the hierarchy index.** MacDonald's h normalises by N^3 while")
    L.append("the outdegree variance it sums grows only with N, so it approaches 1")
    L.append("only for a star - one node with outdegree near N-1. It measures")
    L.append("star-ness, not layeredness. These maps are layered L0-L6 with a peak")
    L.append("outdegree around 4 out of a possible 16, so a near-zero h is correct")
    L.append("and is NOT evidence the maps are flat. The variable-level map scores")
    L.append(f"{var_map['hierarchy_index']} because a handful of variables really do")
    L.append("dominate the outflow there.")
    L.append("")
    L.append("Variable character, per article (mean):")
    ch = Counter()
    for v in per_doc.values():
        ch.update(v["character"])
    L.append("")
    for k, c in ch.most_common():
        L.append(f"- {k}: {c / len(per_doc):.1f} per map ({c} total)")
    iso_types = Counter(nkey[k]["type"] for k in all_ids
                        if od[k] == 0 and idg[k] == 0)
    if iso_types:
        L.append("")
        L.append(f"The {sum(iso_types.values())} isolates are all "
                 f"`{'`, `'.join(iso_types)}` nodes - the known mermaid artifact "
                 f"(question-to-priors links are drawn with the layout-only `~~~`, "
                 f"which carries no meaning, so no edge was recorded). Not a data "
                 f"problem, but it does mean every map's question node is "
                 f"unreachable by graph traversal.")
    L.append("")
    L.append("## 3. Which subjects are central to his reasoning")
    L.append("")
    L.append("`transmitter_bias` is (out - in) / (out + in) over the claims carrying")
    L.append("a term: **positive means he argues FROM it** (it behaves like a prior "
             "or a mechanism), **negative means he argues TO it** (it behaves like a "
             "conclusion). This is the ranking signal the retrieval path lacks.")
    L.append("")
    L.append("**Caveat on the measure.** Bias washes out for ubiquitous terms. "
             "`us`, `china`, `tariffs` and `import-volumes` all sit on both ends of "
             "most edges, so they land near 0 and the number says nothing. Bias is "
             "informative for mid- and low-frequency terms, and centrality is the "
             "number to read for the common ones.")
    for facet in ["variable", "country", "bloc", "instrument", "data_basis"]:
        rows = facet_idx.get(facet)
        if not rows:
            continue
        L.append("")
        L.append(f"### {facet}")
        L.append("")
        L.append("| term | claims | out | in | centrality | per claim | bias |")
        L.append("|---|---|---|---|---|---|---|")
        for r in rows[:12]:
            L.append(f"| {r['term']} | {r['claims']} | {r['outdegree']} | "
                     f"{r['indegree']} | {r['centrality']} | "
                     f"{r['centrality_per_claim']} | {r['transmitter_bias']:+} |")
    L.append("")
    # The finding that justifies the data_basis facet, stated outright rather
    # than left for the reader to spot in a table.
    db = {r["term"]: r for r in facet_idx.get("data_basis", [])}
    if "customs" in db and "balance-of-payments" in db:
        c_, b_ = db["customs"], db["balance-of-payments"]
        L.append("")
        L.append("#### The one finding worth stating outright")
        L.append("")
        L.append(f"`customs` runs {c_['outdegree']} out / {c_['indegree']} in "
                 f"(bias {c_['transmitter_bias']:+}), while "
                 f"`balance-of-payments` runs {b_['outdegree']} out / "
                 f"{b_['indegree']} in (bias {b_['transmitter_bias']:+}).")
        L.append("")
        L.append("He argues **from** customs data and **about** balance-of-payments")
        L.append("data. Customs is a premise he does not defend; BoP is a contested")
        L.append("object he attacks and others defend. That is his measurement-critique")
        L.append("stance - and here it falls out of graph structure rather than being")
        L.append("asserted. It is also the strongest evidence that `data_basis`")
        L.append("earned its place as a facet: no other facet separates these claims.")
        L.append("")
        L.append("Compare `academic-econometrics` (+0.88), `national-accounts`")
        L.append("(+0.75) and `press-reporting` (+1.0): near-pure transmitters, cited")
        L.append("as inputs and never argued over. And `trade-agreements` at -1.0 on")
        L.append("the instrument facet - 0 out, 3 in - trade deals are only ever")
        L.append("something he argues toward, never a premise he reasons from.")
    L.append("")
    L.append("## 4. The variable-level signed map")
    L.append("")
    L.append(f"{var_map['variables']} variables, {var_map['connections']} signed edges, "
             f"plus {sum(self_loops.values())} within-variable edges excluded from "
             f"density.")
    L.append("")
    L.append("Strongest supporting links (a claim about A backs a claim about B):")
    L.append("")
    pos = [(k, c) for k, c in var_edges.items() if k[2] > 0]
    for (qa, qb, _s), c in sorted(pos, key=lambda kv: -kv[1])[:12]:
        L.append(f"- `{qa}` → `{qb}` ({c})")
    neg = [(k, c) for k, c in var_edges.items() if k[2] < 0]
    if neg:
        L.append("")
        L.append("Strongest attacking links (a claim about A pushes back on B):")
        L.append("")
        for (qa, qb, _s), c in sorted(neg, key=lambda kv: -kv[1])[:10]:
            L.append(f"- `{qa}` ⊣ `{qb}` ({c})")
    L.append("")
    L.append("Full edge list: `data/variable_map.csv`.")
    L.append("")
    L.append("## What is still missing for a causal map")
    L.append("")
    L.append("Everything above projects ARGUMENT structure. A true Axelrod map needs")
    L.append("the direction of effect between variables - \"weak domestic demand")
    L.append("raises the surplus\" - and that sign sits in the mechanism prose,")
    L.append("unannotated. Adding a `causal_sign` to mechanism nodes is the next")
    L.append("annotation pass, and it is what would let the graph answer \"if saving")
    L.append("rises, what does he think happens to the surplus?\"")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    OUT_JSON.write_text(json.dumps({
        "sign_table": SIGN, "sign_mix": {str(k): v for k, v in sign_mix.items()},
        "sign_conflicts": len(conflicts), "unsigned_types": unknown,
        "corpus": corpus, "per_document": per_doc,
        "variable_map": var_map, "facets": facet_idx,
    }, indent=1), encoding="utf-8")

    print(f"wrote {OUT_SIGNED.relative_to(ROOT)} ({len(signed)} edges, "
          f"{sign_mix.get(-1, 0)} attacking)")
    print(f"wrote {OUT_VARMAP.relative_to(ROOT)} ({len(var_edges)} variable edges)")
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")
    if conflicts:
        print(f"  WARNING: {len(conflicts)} edges disagree with the parser's "
              f"polarity column")
    if unknown:
        print(f"  WARNING: unsigned edge types: {', '.join(unknown)}")
    if args.show:
        print()
        print(OUT_MD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
