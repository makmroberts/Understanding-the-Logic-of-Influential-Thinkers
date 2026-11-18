#!/usr/bin/env python3
"""Trace any claim back to its source, and audit how traceable the corpus is.

    python scripts/trace.py setser_aug_14_24#P2       # one claim, full chain
    python scripts/trace.py --audit                   # corpus-wide report
    python scripts/trace.py --match-urls              # re-solve the URL join

Reads   data/nodes.csv, data/edges.csv, data/node_facets.csv,
        data/documents.csv, mermaid_code/*.mmd,
        scripts/sources_followthemoney.csv

THE POINT

Every line this project emits is supposed to be something the author actually
wrote, with its source. That promise is only as good as the weakest link in the
chain, and the chain has four links:

    claim  ->  node in a .mmd map  ->  article  ->  published URL

Plus two derived layers that each need their own provenance: the TYPE of a node
(how was "hidden assumption" decided?) and the SUBJECT facets (who assigned
`data_basis: customs`?).

This tool makes every link visible at once, and marks each one as READ from the
source or INFERRED by the pipeline. The distinction matters more than the
content: 201 of 340 edges carry no label in the source map and were defaulted
to `supports`, and until now the vault rendered those identically to the 139
that were actually read off the page.

Nothing here invents provenance. Where a link is missing it says so.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODES = ROOT / "data" / "nodes.csv"
EDGES = ROOT / "data" / "edges.csv"
FACETS = ROOT / "data" / "node_facets.csv"
PASSAGES = ROOT / "data" / "node_passages.csv"
DOCS = ROOT / "data" / "documents.csv"   # written by parse_maps.py
MAPS = ROOT / "mermaid_code"
REGISTRY = ROOT / "scripts" / "sources_followthemoney.csv"
URL_MAP = ROOT / "scripts" / "source_urls.yaml"

# How a node's type was decided, weakest last. The parser records this per node
# and it is real provenance - keep it visible.
TYPE_SOURCE = {
    "header": "READ - the map's own bold slot label",
    "class": "READ - the classDef assigned in the map",
    "l6_keyword": "INFERRED - keyword match on the header (schema_map.yaml)",
    "level": "INFERRED - fell back to the enclosing subgraph",
}


def load():
    nodes = list(csv.DictReader(NODES.open(encoding="utf-8")))
    edges = list(csv.DictReader(EDGES.open(encoding="utf-8")))
    # documents.csv comes from the Neo4j export and carries titles only, so a
    # missing one degrades the report rather than failing the trace.
    docs = ({r["id"]: r for r in csv.DictReader(DOCS.open(encoding="utf-8"))}
            if DOCS.exists() else {})
    facets = defaultdict(list)
    if FACETS.exists():
        for r in csv.DictReader(FACETS.open(encoding="utf-8")):
            facets[(r["doc"], r["node_id"])].append(r)
    return nodes, edges, docs, facets


def mmd_line(doc: str, nid: str) -> tuple[str, int] | None:
    """Locate a node's definition in its authored .mmd map."""
    p = MAPS / f"{doc}.mmd"
    if not p.exists():
        return None
    pat = re.compile(r"^\s*" + re.escape(nid) + r"\s*[\[\(\{]")
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if pat.match(line):
            return (str(p.relative_to(ROOT)), i)
    return None


def load_passages() -> dict:
    """(doc, node_id) -> [rows], from scripts/link_passages.py."""
    out = defaultdict(list)
    if PASSAGES.exists():
        for r in csv.DictReader(PASSAGES.open(encoding="utf-8")):
            out[(r["doc"], r["node_id"])].append(r)
    return out


def load_url_warnings() -> dict:
    """doc -> attribution warning, from the URL overlay. Empty if none."""
    if not URL_MAP.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    spec = yaml.safe_load(URL_MAP.read_text(encoding="utf-8")) or {}
    out = {}
    for k, v in (spec.get("urls") or {}).items():
        if not isinstance(v, dict):
            continue
        if v.get("warning"):
            out[k] = ("ATTRIBUTION WARNING", v["warning"])
        elif v.get("annotation_provenance"):
            out[k] = ("ANNOTATION PROVENANCE", v["annotation_provenance"])
    return out


def edge_provenance(e: dict) -> str:
    raw = (e.get("raw") or "").strip()
    if raw:
        return f'READ - drawn as "{raw}"'
    return "INFERRED - unlabelled in the map, defaulted by schema_map.yaml"


def cmd_trace(ref: str) -> None:
    nodes, edges, docs, facets = load()
    if "#" not in ref:
        sys.exit("give a reference as <doc>#<node_id>, e.g. setser_aug_14_24#P2")
    doc, nid = ref.split("#", 1)
    match = [r for r in nodes if r["doc"] == doc and r["node_id"] == nid]
    if not match:
        sys.exit(f"no such node: {ref}")
    n = match[0]
    d = docs.get(doc, {})
    byid = {(r["doc"], r["node_id"]): r for r in nodes}

    W = 78
    out = ["", "=" * W, f"  TRACE  {ref}", "=" * W, ""]
    out.append("CLAIM")
    out.append(f"  header : {' '.join(n['header'].split())}")
    text = " ".join(n["text"].split())
    if text and text != " ".join(n["header"].split()):
        out.append(f"  text   : {text}")
    out.append("")

    out.append("WHAT KIND OF CLAIM, AND HOW THAT WAS DECIDED")
    out.append(f"  type   : {n['type']}  (level {n['level']})")
    out.append(f"  source : {TYPE_SOURCE.get(n['type_source'], n['type_source'])}")
    if n.get("implicit_only") == "1":
        out.append("  NOTE   : implicit_only - the annotator inferred this node "
                   "exists; it is not stated in the article")
    if n.get("mechanism_kind"):
        out.append(f"  kind   : {n['mechanism_kind']}")
    out.append("")

    out.append("WHERE IT CAME FROM")
    loc = mmd_line(doc, nid)
    if loc:
        out.append(f"  map    : {loc[0]}:{loc[1]}  <- the authored artifact")
    else:
        out.append(f"  map    : MISSING - no definition found in "
                   f"mermaid_code/{doc}.mmd")
    out.append(f"  article: {d.get('title', '(unknown)')}  [{n['date']}]")
    if d.get("outlet"):
        out.append(f"  outlet : {d['outlet']}")
    if d.get("url"):
        out.append(f"  url    : {d['url']}")
    else:
        out.append("  url    : MISSING - this article has no recorded URL "
                   "(see --match-urls)")
    pas = [r for r in load_passages().get((doc, nid), [])
           if r["grade"] != "none"]
    if not pas:
        out.append("  passage: none linked - no paragraph shares a literal or "
                   "enough wording with this claim")
    for r in pas:
        rel = r.get("relation", "?")
        if r["grade"] == "confirmed":
            out.append(f"  passage: {r['para']}  {rel.upper()} "
                       f"- confirmed by hand")
        elif r["grade"] == "elsewhere":
            out.append(f"  passage: none here - ELSEWHERE, a prior grounded "
                       f"in his wider work (confirmed by hand)")
        elif r["grade"] == "anchored":
            out.append(f"  passage: {r['para']}  STATES, anchored on "
                       f"[{r['anchors']}] - the shared literal is the evidence")
        else:
            out.append(f"  passage: {r['para']}  proposed {rel} "
                       f"(score {r['score']}) - unreviewed, NOT a citation")
    if pas:
        out.append(f"  extract: internal/extracted/ @ page "
                   f"{pas[0]['page_sha256']}")
    warn = load_url_warnings().get(doc)
    if warn:
        out.append("")
        out.append(f"  *** {warn[0]} ***")
        for line in " ".join(warn[1].split()).split(". "):
            if line.strip():
                out.append(f"  {line.strip().rstrip('.')}.")
    out.append("")

    fr = facets.get((doc, nid), [])
    if fr:
        out.append("SUBJECT, AND WHO ASSIGNED IT")
        by_facet = defaultdict(list)
        for r in fr:
            tag = f"{r['value']}" + (f" ({r['role']})" if r["role"] else "")
            by_facet[r["facet"]].append((tag, r["source"], r.get("model", "")))
        for f, vals in by_facet.items():
            joined = ", ".join(v for v, _, _ in vals)
            srcs = {s for _, s, _ in vals}
            models = {m for _, _, m in vals if m}
            prov = "/".join(sorted(srcs))
            if models:
                prov += " by " + "/".join(sorted(models))
            out.append(f"  {f:11}: {joined}")
            out.append(f"  {'':11}  [{prov}]")
        out.append("")

    outg = [e for e in edges if e["doc"] == doc and e["from"] == nid]
    inc = [e for e in edges if e["doc"] == doc and e["to"] == nid]
    if outg:
        out.append("LEADS TO")
        for e in outg:
            t = byid.get((doc, e["to"]), {})
            out.append(f"  --{e['type']}--> {e['to']} "
                       f"({t.get('type', '?')}) "
                       f"{' '.join(t.get('header', '').split())[:46]}")
            out.append(f"      {edge_provenance(e)}")
        out.append("")
    if inc:
        out.append("RESTS ON")
        for e in inc:
            s = byid.get((doc, e["from"]), {})
            out.append(f"  <--{e['type']}-- {e['from']} "
                       f"({s.get('type', '?')}) "
                       f"{' '.join(s.get('header', '').split())[:46]}")
            out.append(f"      {edge_provenance(e)}")
        out.append("")
    if not outg and not inc:
        out.append("NO EDGES - this node is isolated in the graph. For question "
                   "nodes this")
        out.append("is the known mermaid artifact: the question-to-priors link is "
                   "drawn with")
        out.append("the layout-only `~~~`, which carries no meaning, so no edge "
                   "was recorded.")
        out.append("")

    print("\n".join(out))


def cmd_audit() -> None:
    nodes, edges, docs, facets = load()
    W = 78
    N = len(nodes)
    print()
    print("=" * W)
    print("  TRACEABILITY AUDIT")
    print("=" * W)
    print()
    print("Each link in the chain, and how much of the corpus has it.")
    print()

    # link 1: claim -> .mmd
    located = sum(1 for r in nodes if mmd_line(r["doc"], r["node_id"]))
    print(f"1. claim -> authored map line")
    print(f"     {located}/{N} nodes locatable in mermaid_code/*.mmd "
          f"({located / N:.0%})")

    # link 2: node type provenance
    ts = Counter(r["type_source"] for r in nodes)
    read = sum(v for k, v in ts.items() if TYPE_SOURCE.get(k, "").startswith("READ"))
    print(f"2. claim type")
    print(f"     {read}/{N} types READ from the map ({read / N:.0%}); "
          f"{N - read} inferred")
    for k, v in ts.most_common():
        print(f"       {v:4d}  {k}: {TYPE_SOURCE.get(k, '?')}")

    # link 3: edges
    stated = sum(1 for e in edges if (e.get("raw") or "").strip())
    print(f"3. edge relation")
    print(f"     {stated}/{len(edges)} READ from a label on the edge "
          f"({stated / len(edges):.0%})")
    print(f"     {len(edges) - stated} INFERRED - unlabelled, defaulted by "
          f"schema_map.yaml")

    # link 4: article -> url
    with_url = sum(1 for d in docs.values() if d.get("url", "").strip())
    nodes_with_url = sum(1 for r in nodes
                         if docs.get(r["doc"], {}).get("url", "").strip())
    print(f"4. article -> published URL")
    print(f"     {with_url}/{len(docs)} articles have a URL; "
          f"{nodes_with_url}/{N} claims reach one ({nodes_with_url / N:.0%})")
    if with_url < len(docs):
        print(f"     *** {len(docs) - with_url} articles cannot be traced to "
              f"the published source.")
        print(f"     *** All 20 URLs exist in scripts/sources_followthemoney.csv.")
        print(f"     *** Run --match-urls to re-solve the join.")

    # link 5: passage
    pas = load_passages()
    best = {}
    for k, rs in pas.items():
        grades = {r["grade"] for r in rs}
        best[k] = ("anchored" if "anchored" in grades else
                   "candidate" if "candidate" in grades else "none")
    anch = sum(1 for v in best.values() if v == "anchored")
    cand = sum(1 for v in best.values() if v == "candidate")
    print(f"5. article -> passage")
    if not best:
        print(f"     0/{N} - run scripts/link_passages.py")
    else:
        print(f"     {anch}/{N} ANCHORED ({anch / N:.0%}) - claim and paragraph "
              f"share a distinctive")
        print(f"       literal (a figure, a rare proper noun), so the link is "
              f"checkable")
        print(f"     {cand}/{N} candidate ({cand / N:.0%}) - semantic match "
              f"only. A reviewing aid,")
        print(f"       NOT a citation, and not rendered as one.")
        print(f"     {N - anch - cand}/{N} unlinked")
        print(f"     Node text is the annotator's paraphrase, so only the "
              f"anchored tier is")
        print(f"     provenance. See data/passage_report.md for the by-role "
              f"pattern.")

    # link 6: facets
    if facets:
        fsrc = Counter(r["source"] for rs in facets.values() for r in rs)
        covered = len(facets)
        print(f"6. claim -> subject facets")
        print(f"     {covered}/{N} claims carry facets ({covered / N:.0%})")
        for k, v in fsrc.most_common():
            print(f"       {v:5d}  source={k}")
        models = Counter(r.get("model", "") for rs in facets.values() for r in rs
                         if r.get("model"))
        for m, v in models.most_common():
            print(f"       {v:5d}  model={m}")
    print()
    print("WEAKEST LINKS, in order of how cheap they are to fix")
    print("-" * W)
    print("  1. 15 of 20 articles have no URL, though the registry holds all 20.")
    print("     Cheap, but the join is NOT safe to automate - see --propose-urls.")
    print("  2. 59% of edges have an inferred relation and the vault did not say so.")
    print("     Now marked in the exported notes.")
    print("  3. No claim cites a passage. Needs annotation, not inference.")
    print()


STOP = set("""a an and the of in to for on at by or as is are be been it its do does
did still now than that their they them what why how will can could would may
might with from when where which who this those these not no but if then so
such more most one two i he she his her our your you""".split())

MON = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
     "nov", "dec"])}


def _toks(text: str) -> set:
    text = text.lower().replace("u.s.", "us").replace("-", " ")
    return {w for w in re.findall(r"[a-z0-9']+", text)
            if w not in STOP and len(w) > 1}


def _ym(label: str):
    m = re.match(r"([A-Za-z]+)\s*(\d{4})", label.strip())
    return (int(m.group(2)), MON.get(m.group(1)[:3].lower())) if m else None


def cmd_match_urls() -> None:
    """Solve map <-> registry as ONE 1-1 assignment, and show the evidence.

    Matching each map independently fails: the registry's dates are
    month-granular and wrong in three places, and plain-family map titles are
    the annotator's question rather than the headline. But the relation IS 1-1
    over 20 maps and 20 registry rows, so the global constraint carries the
    cases where no single signal does.

    Title similarity is weighted 3x against date agreement 1x, because a
    headline shares vocabulary with the question even when paraphrased, whereas
    a wrong date is simply wrong.
    """
    try:
        import numpy as np
        from scipy.optimize import linear_sum_assignment
    except ImportError:
        sys.exit("needs scipy and numpy for the assignment solve - "
                 "pip install scipy")

    _, _, docs, _ = load()
    reg = list(csv.DictReader(REGISTRY.open(encoding="utf-8")))
    dl = list(docs.values())

    # Pin only maps that state their own URL, read from the .mmd itself rather
    # than from documents.csv - otherwise the overlay this command produced
    # would be fed back in as input and the solve could not be reproduced.
    def stated_url(stem: str) -> str:
        p = MAPS / f"{stem}.mmd"
        if not p.exists():
            return ""
        m = re.search(r"^\s*%%\s*(?:url|link)\s*:\s*(\S+)",
                      p.read_text(encoding="utf-8"), re.M | re.I)
        return m.group(1).strip() if m else ""

    pinned, used = {}, set()
    for d in dl:
        u = stated_url(d["id"])
        if not u:
            continue
        for k, r in enumerate(reg):
            if r["url"].strip() == u and k not in used:
                pinned[d["id"]] = r
                used.add(k)
                break
    open_docs = [d for d in dl if d["id"] not in pinned]
    open_reg = [r for k, r in enumerate(reg) if k not in used]

    print()
    print(f"pinned by the map's own %% url: comment : {len(pinned)}")
    print(f"to assign                              : {len(open_docs)} maps "
          f"x {len(open_reg)} registry rows")
    if len(open_docs) != len(open_reg):
        print(f"  NOT 1-1 - {len(open_docs)} maps against {len(open_reg)} rows. "
              f"The assignment below is partial.")
    n = max(len(open_docs), len(open_reg))
    ts = np.zeros((n, n))
    ds = np.zeros((n, n))
    for i, d in enumerate(open_docs):
        dt = _toks(d["title"])
        dy, dm = int(d["date"][:4]), int(d["date"][5:7])
        for j, r in enumerate(open_reg):
            rt = _toks(r["title"]) | _toks(r["slug"])
            ts[i, j] = len(dt & rt) / max(1, min(len(dt), len(_toks(r["title"]))))
            k = _ym(r["date_label"])
            if k and k[1]:
                months = abs((dy - k[0]) * 12 + (dm - k[1]))
                ds[i, j] = 1.0 if months == 0 else max(0.0, 1.0 - months / 6.0)
    score = 3.0 * ts + 1.0 * ds
    ri, ci = linear_sum_assignment(-score)

    print()
    print(f"{'map':22} {'map date':11} {'registry':10} {'title':>6} {'date':>5} "
          f"{'margin':>7}  verdict")
    print("-" * 104)
    weak = []
    for i, j in zip(ri, ci):
        if i >= len(open_docs) or j >= len(open_reg):
            continue
        d, r = open_docs[i], open_reg[j]
        t, dd = ts[i, j], ds[i, j]
        alts = [score[i, k] for k in range(n) if k != j]
        margin = score[i, j] - max(alts) if alts else 0.0
        if t >= 0.5:
            v = "strong - title"
        elif dd == 1.0 and t > 0:
            v = "strong - date + subject"
        elif dd == 1.0:
            v = "date only"
        else:
            v = "ELIMINATION ONLY"
            weak.append((d, r))
        print(f"{d['id'][:21]:22} {d['date']:11} {r['date_label']:10} "
              f"{t:6.2f} {dd:5.2f} {margin:7.2f}  {v}")
        print(f"{'':22} -> {r['title'][:76]}")
    print()
    print(f"{len(open_docs) - len(weak)} of {len(open_docs)} carried by direct "
          f"evidence; {len(weak)} by elimination alone.")
    if weak:
        print()
        print("Assigned by elimination - do NOT treat these as sources until "
              "someone opens the page:")
        for d, r in weak:
            print(f"  {d['id']}  ->  {r['url']}")
    print()
    print(f"The confirmed result is maintained by hand in "
          f"{URL_MAP.relative_to(ROOT).as_posix()},")
    print("which parse_maps.py reads as an overlay. Entries under "
          "`needs_review:` there")
    print("are deliberately not published into the graph.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ref", nargs="?", help="<doc>#<node_id>")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--match-urls", dest="match", action="store_true",
                    help="re-solve the map<->registry 1-1 assignment, with evidence")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if args.audit:
        return cmd_audit()
    if args.match:
        return cmd_match_urls()
    if not args.ref:
        ap.error("give a <doc>#<node_id>, or --audit, or --match-urls")
    cmd_trace(args.ref)


if __name__ == "__main__":
    main()
