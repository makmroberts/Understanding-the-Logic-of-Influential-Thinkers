#!/usr/bin/env python3
"""Reconstruct how the author would reason about a new question.

    python scripts/ask.py "Will Trump's tariffs reduce the trade deficit?"
    python scripts/ask.py "..." --prompt      # emit an LLM prompt instead
    python scripts/ask.py "..." --json        # machine-readable

This does NOT generate an answer. It retrieves the reasoning machinery the
author has actually used - the priors he brings, the warrants he leaves
unstated, the mechanisms he reaches for, where he lands and what he concedes -
and lays it out by level, with a citation on every line.

Two ideas drive the ranking:

1. Relevance. Plain tf-idf over node text, plus the article's title and topics.
   Nothing clever; the corpus is 358 nodes and the vocabulary is narrow.

2. Transferability. Evidence is dated specifics - "October's deficit was X" is
   not reusable. Priors, hidden assumptions and mechanisms are the machinery
   that carries across questions, so they are boosted, and boosted again when
   the author has reused them in more than one article. What he repeats is
   what he believes.

Reads data/graph.json, so it works whether or not Neo4j is running.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "graph.json"

STOP = set("""
a an and are as at be been but by can could did do does for from had has have he her his
if in into is it its may might more most no not of on or our she should so some such than
that the their them then there these they this those to was were what when where which
who why will with would you your about above after again against all also am any because
before being below between both during each few further here how i just me myself nor now
once only other out over own same same too under until up very we while whom
""".split())

# What each level contributes to a reconstructed answer, and how much weight it
# gets. Evidence is deliberately discounted: the numbers are dated, the habit of
# citing them is not.
LEVELS = [
    ("L1", "PRIORS HE WOULD BRING",            ["stated_assumption", "accounting_identity",
                                                "revised_prior", "source_credibility"], 1.35),
    ("L1", "WARRANTS HE WOULD LEAVE UNSTATED", ["hidden_assumption"],                     1.60),
    ("L1B", "HOW HE WOULD SCOPE IT",           ["scope_choice", "benchmark"],             1.20),
    ("L3", "MECHANISMS HE WOULD INVOKE",       ["mechanism"],                             1.35),
    ("L2", "EVIDENCE HE WOULD REACH FOR",      ["evidence_data", "evidence_source",
                                                "evidence_rival", "evidence_discrepancy"], 0.75),
    ("L4", "INTERMEDIATE STEPS",               ["intermediate_claim", "case_type",
                                                "policy_reductio"],                       1.00),
    ("L5", "WHERE HE WOULD LAND",              ["main_claim", "reconstruction",
                                                "recommendation"],                        1.25),
    ("L6", "WHAT HE WOULD CONCEDE",            ["caveat", "other_explanation",
                                                "deferred_question", "counterpoint"],     1.10),
    ("L6", "WHO HE WOULD ARGUE AGAINST",       ["opposing_view"],                         1.10),
]


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z\-']{2,}", text.lower()) if w not in STOP]


def load():
    if not GRAPH.exists():
        sys.exit("data/graph.json missing - run: python scripts/parse_maps.py")
    docs = json.loads(GRAPH.read_text(encoding="utf-8"))["documents"]
    nodes = []
    for d in docs:
        ctx = f"{d['meta']['title']} {d['meta'].get('topics', '')}"
        for ns in d["levels"].values():
            for n in ns:
                nodes.append({**n, "doc": d["doc"], "date": d["date"],
                              "family": d["family"], "title": d["meta"]["title"],
                              "url": d["meta"].get("url", ""),
                              "blob": f"{n['header']} {n['text']} {ctx}"})
    return docs, nodes


def score(nodes: list[dict], query: str) -> None:
    """Attach a relevance score to every node, in place."""
    docfreq = Counter()
    toks = {}
    for i, n in enumerate(nodes):
        t = set(tokens(n["blob"]))
        toks[i] = t
        docfreq.update(t)
    total = len(nodes)
    idf = {w: math.log(1 + total / (1 + c)) for w, c in docfreq.items()}

    q = tokens(query)
    if not q:
        sys.exit("empty question")
    qv = Counter(q)

    # how often an idea recurs: the concept layer first, then repeated headers
    header_runs = Counter(n["header"].lower() for n in nodes if n["header"])
    concept_runs = Counter(n["concept"] for n in nodes if n.get("concept"))

    for i, n in enumerate(nodes):
        overlap = toks[i] & qv.keys()
        raw = sum(idf.get(w, 0) for w in overlap)
        # length normalization, so a 400-char evidence dump cannot win on bulk
        n["match"] = raw / math.sqrt(len(toks[i]) + 4) if toks[i] else 0.0
        n["hits"] = sorted(overlap)
        reuse = 1.0
        if n.get("concept"):
            reuse += 0.25 * concept_runs[n["concept"]]
        elif header_runs.get(n["header"].lower(), 0) > 1:
            reuse += 0.10 * header_runs[n["header"].lower()]
        n["reuse"] = reuse


def coverage(nodes: list[dict], query: str) -> dict:
    """Does the corpus actually address this question, or is it matching noise?

    Without this the tool is dangerous: ask it about Bitcoin and it will match
    on 'dollar', return his tariff reasoning, and look authoritative. The check
    is deliberately blunt - which content words of the question appear in the
    corpus at all, and how much of the question's weight they carry.
    """
    vocab = Counter()
    for n in nodes:
        vocab.update(set(tokens(n["blob"])))
    q = list(dict.fromkeys(tokens(query)))
    if not q:
        return {"ratio": 0.0, "present": [], "missing": [], "thin": []}
    present = [w for w in q if vocab[w] >= 3]
    thin = [w for w in q if 0 < vocab[w] < 3]
    missing = [w for w in q if vocab[w] == 0]
    return {"ratio": len(present) / len(q), "present": present,
            "missing": missing, "thin": thin}


def pick(nodes, types, weight, limit, seen):
    out = []
    for n in sorted(nodes, key=lambda n: -(n["match"] * weight * n["reuse"])):
        if n["type"] not in types or n["match"] <= 0:
            continue
        key = (n["doc"], n["id"])
        if key in seen:
            continue
        body = " ".join((n["text"] or n["header"]).split())
        if body.lower() in {x["body"].lower() for x in out}:
            continue
        seen.add(key)
        out.append({"body": body, "header": n["header"], "doc": n["doc"],
                    "nid": n["id"], "date": n["date"], "title": n["title"],
                    "score": n["match"] * weight * n["reuse"], "hits": n["hits"]})
        if len(out) >= limit:
            break
    return out


def precedents(docs, nodes, k=4):
    agg = defaultdict(float)
    for n in nodes:
        agg[n["doc"]] += n["match"]
    byid = {d["doc"]: d for d in docs}
    top = sorted(agg.items(), key=lambda kv: -kv[1])[:k]
    return [(byid[doc], s) for doc, s in top if s > 0]


def shape_note(docs, nodes, top_docs) -> list[str]:
    """What the precedent arguments have structurally in common."""
    ids = {d["doc"] for d, _ in top_docs}
    out = []
    ev_targets = Counter()
    for d in docs:
        if d["doc"] not in ids:
            continue
        lvl = {n["id"]: n["level"] for ns in d["levels"].values() for n in ns}
        for e in d["edges"]:
            if lvl.get(e["from"]) == "L2" and e["polarity"] == "forward":
                ev_targets[lvl.get(e["to"], "?")] += 1
    if ev_targets:
        via = ev_targets.get("L3", 0)
        tot = sum(ev_targets.values())
        out.append(f"In these precedents {via} of {tot} evidence edges run through a "
                   f"mechanism before reaching a claim - he states the channel, "
                   f"he does not let a number speak for itself.")
    kinds = Counter(n["type"] for n in nodes
                    if n["doc"] in ids and n["level"] == "L6")
    if kinds:
        out.append("Counterpoint mix in these precedents: " +
                   ", ".join(f"{v} {k}" for k, v in kinds.most_common()) + ".")
    ctypes = [n.get("claim_type") for n in nodes
              if n["doc"] in ids and n["type"] == "main_claim" and n.get("claim_type")]
    if ctypes:
        out.append("Conclusion shape where annotated: " +
                   ", ".join(f"{v}x {k}" for k, v in Counter(ctypes).most_common()) + ".")
    return out


def build(query: str, docs, nodes, per_section: int):
    cov = coverage(nodes, query)
    score(nodes, query)
    top = precedents(docs, nodes)
    seen: set = set()
    sections = []
    for _, heading, types, weight in LEVELS:
        picked = pick(nodes, set(types), weight, per_section, seen)
        if picked:
            sections.append((heading, picked))
    return {"question": query,
            "coverage": cov,
            "precedents": [{"doc": d["doc"], "date": d["date"], "family": d["family"],
                            "title": d["meta"]["title"], "url": d["meta"].get("url", ""),
                            "score": round(s, 3)} for d, s in top],
            "sections": [{"heading": h, "items": items} for h, items in sections],
            "shape": shape_note(docs, nodes, top)}


def render(result: dict) -> str:
    w = 78
    out = ["", "=" * w, f"  HOW WOULD HE ANSWER:  {result['question']}", "=" * w, ""]

    cov = result["coverage"]
    if cov["ratio"] < 0.5:
        out += ["!" * w,
                "  LOW COVERAGE - the corpus does not really address this question.",
                f"  Matched only on: {', '.join(cov['present']) or '(nothing)'}"]
        if cov["missing"]:
            out.append(f"  Absent from all 20 maps: {', '.join(cov['missing'])}")
        out += ["  Treat what follows as loosely related prior reasoning, NOT as a",
                "  reconstruction of how he would answer this.", "!" * w, ""]
    elif cov["missing"]:
        out += [f"Note: {', '.join(cov['missing'])} appear nowhere in the corpus; "
                f"the answer below works around them.", ""]

    out.append("CLOSEST PRECEDENTS IN THE CORPUS")
    for p in result["precedents"]:
        out.append(f"  {p['date']}  [{p['family']:6}] {p['title'][:52]}")
    if not result["precedents"]:
        out.append("  (nothing matched - try different wording)")
    out.append("")
    for s in result["sections"]:
        out.append(s["heading"])
        out.append("-" * len(s["heading"]))
        for it in s["items"]:
            body = it["body"]
            if len(body) > 300:
                body = body[:297] + "..."
            lead = f"{it['header']}: " if it["header"] and not body.startswith(it["header"]) else ""
            wrapped = []
            line = "  - " + lead + body
            while len(line) > w:
                cut = line.rfind(" ", 0, w)
                wrapped.append(line[:cut])
                line = "    " + line[cut + 1:]
            wrapped.append(line)
            out += wrapped
            out.append(f"      [{it['doc']}#{it['nid']}, {it['date'][:7]}]")
        out.append("")
    if result["shape"]:
        out.append("HOW THE ARGUMENT IS USUALLY SHAPED")
        out.append("-" * 34)
        for s in result["shape"]:
            line = "  " + s
            while len(line) > w:
                cut = line.rfind(" ", 0, w)
                out.append(line[:cut])
                line = "  " + line[cut + 1:]
            out.append(line)
        out.append("")
    out.append("Every line above is something he actually wrote, with its source.")
    out.append("Nothing here is generated - this is retrieval, not prediction.")
    out.append(f"Question coverage: {result['coverage']['ratio']:.0%} of content terms "
               f"are well attested in the corpus.")
    return "\n".join(out)


def as_prompt(result: dict) -> str:
    cov = result["coverage"]
    out = ["You are reconstructing how Brad Setser - CFR economist, balance-of-payments "
           "specialist - would answer a question, using only his own prior reasoning.",
           "", f"QUESTION: {result['question']}", ""]
    if cov["ratio"] < 0.5:
        out += ["WARNING: his published work barely touches this question. It matched "
                f"only on: {', '.join(cov['present']) or '(nothing)'}. "
                f"Absent entirely: {', '.join(cov['missing']) or '(none)'}. "
                "Say plainly that this falls outside what he has written about, and "
                "answer only to the extent his general framework genuinely carries "
                "over.", ""]
    out += [
           "His reasoning machinery from the closest precedents in his published work, "
           "organized by the role each element plays in his arguments:", ""]
    for s in result["sections"]:
        out.append(f"## {s['heading']}")
        for it in s["items"]:
            out.append(f"- {it['body']}  [{it['doc']}#{it['nid']}, {it['date']}]")
        out.append("")
    if result["shape"]:
        out.append("## Structural habits in these precedents")
        out += [f"- {s}" for s in result["shape"]]
        out.append("")
    out += ["Write his likely answer in his voice. Rules:",
            "- Build only on the priors, mechanisms and evidence habits above.",
            "- Name the causal channel before citing a number; that is how he argues.",
            "- Include the caveat and the opposing view - he always concedes something.",
            "- Where his prior work does not cover the question, say so explicitly "
            "rather than inventing a position.",
            "- Cite the source tag for each borrowed element."]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="+", help="the question to reconstruct an answer to")
    ap.add_argument("-n", "--per-section", type=int, default=3,
                    help="items per section (default 3)")
    ap.add_argument("--prompt", action="store_true", help="emit an LLM prompt")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    # the maps contain -, ≈, ° and friends; the Windows console defaults to cp1252
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    docs, nodes = load()
    result = build(" ".join(args.question), docs, nodes, args.per_section)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    elif args.prompt:
        print(as_prompt(result))
    else:
        print(render(result))


if __name__ == "__main__":
    main()
