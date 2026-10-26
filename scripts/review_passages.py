#!/usr/bin/env python3
"""Review candidate passage links by hand, and record the decisions.

    python scripts/review_passages.py --worksheet              # all unreviewed
    python scripts/review_passages.py --worksheet --band clear --limit 40
    python scripts/review_passages.py --worksheet --type hidden_assumption
    python scripts/review_passages.py --apply                  # read it back
    python scripts/review_passages.py --status                 # progress

Reads   data/node_passages.csv, data/nodes.csv,
        internal/extracted/*.md, scripts/passage_review.yaml
Writes  internal/passage_worksheet.md    the thing you edit
        scripts/passage_review.yaml      your decisions, versioned

WHY A WORKSHEET AND NOT A PROMPT

`link_passages.py` grades a link `anchored` when the claim and the paragraph
share a distinctive literal, and `candidate` when the match is semantic only.
A candidate is explicitly NOT a citation - it is a narrowing, from thirty-odd
paragraphs to one. Confirming it is a human judgement, so this produces
something a human can work through in batches and hand back.

Decisions beat the matcher permanently, the same contract `label_facets.py`
has with its `hand` source: once you confirm p12, nothing re-derives it.

THE WORKSHEET LIVES IN internal/
It quotes article paragraphs, and extracted text stays local in this repo.
Your decisions are paragraph numbers only, so those are versioned in
scripts/passage_review.yaml and shareable.

ORDERING
Claims are ordered by how much the project needs them, not by document:
priors, hidden assumptions and mechanisms first, because those are the
reasoning machinery ask.py reconstructs; evidence last, because it already
anchors on figures. Within a role, by `margin` descending - how far the chosen
paragraph beat the runner-up - so the quick confirmations come first and the
near-ties come last, with their runner-up shown for comparison.

    band clear     margin > 0.10   one paragraph won outright
    band moderate  0.05 - 0.10
    band tie       < 0.05          read both, the matcher is guessing
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml missing - pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
NODES = ROOT / "data" / "nodes.csv"
PASSAGES = ROOT / "data" / "node_passages.csv"
URL_MAP = Path(__file__).resolve().parent / "source_urls.yaml"
REVIEW = Path(__file__).resolve().parent / "passage_review.yaml"
WORKSHEET = ROOT / "internal" / "passage_worksheet.md"

# What the project most needs a verified passage for, best first.
ROLE_ORDER = [
    "hidden_assumption", "stated_assumption", "accounting_identity",
    "revised_prior", "source_credibility", "scope_choice", "benchmark",
    "mechanism", "main_claim", "reconstruction", "recommendation",
    "intermediate_claim", "case_type", "policy_reductio",
    "opposing_view", "caveat", "other_explanation", "counterpoint",
    "deferred_question", "anomaly", "position_map", "question",
    "evidence_discrepancy", "evidence_rival", "evidence_source",
    "evidence_data",
]
RANK = {t: i for i, t in enumerate(ROLE_ORDER)}

DECISION_RE = re.compile(r"^decision:\s*(.*?)\s*$", re.M)

# What you write, and what it means. Short, because you will type it 52 times.
#
# The relation matters more than the paragraph number. Every claim comes from
# somewhere in the article; the question is HOW - does the paragraph say it,
# does the claim compress it, or does the paragraph merely need it to be true?
VOCAB = {
    "s": ("states", "the paragraph says it"),
    "a": ("abstracts", "the claim compresses or generalises the paragraph"),
    "w": ("presupposes", "the paragraph only works if the claim is true - the "
                         "claim is its unstated warrant"),
    "e": ("elsewhere", "a real prior of his, but grounded in his wider work "
                       "rather than this article's text"),
    "no": ("none", "cannot place it anywhere"),
}
ITEM_RE = re.compile(r"^### \[(?P<n>\d+)\]\s+(?P<ref>\S+)\s+->\s+(?P<para>p\d+)",
                     re.M)


# Claims where a confirmed passage actually buys something. The other ~220
# candidates can stay candidates indefinitely: they are labelled as not-
# citations, so leaving them is honest, not a debt. Review is opportunistic.
#
#   fixture  a node some competency question PROMISES to return. If an answer
#            cites a passage, this is the citation a reader will check.
#   concept  carries a concept id, so it recurs across articles.
#   sharp    the warrant types, where the matcher is least trustworthy and the
#            relation is the whole question: a hidden assumption normally
#            PRESUPPOSES its paragraph rather than stating it.
SHARP_TYPES = {"hidden_assumption", "accounting_identity", "revised_prior",
               "source_credibility"}


def priority_refs(nodes: dict) -> tuple[set, set, set]:
    cqf = Path(__file__).resolve().parent / "competency_questions.yaml"
    fixture = set()
    if cqf.exists():
        cq = yaml.safe_load(cqf.read_text(encoding="utf-8")) or {}
        for q in cq.get("questions", []):
            for ref in (q.get("example") or {}).get("must_return", []):
                fixture.add(tuple(ref.split("#")))
    concept = {k for k, v in nodes.items() if v.get("concept")}
    return fixture, concept, SHARP_TYPES


def band_of(margin: float) -> str:
    return "clear" if margin > 0.10 else "moderate" if margin >= 0.05 else "tie"


def load_review() -> dict:
    if not REVIEW.exists():
        return {}
    spec = yaml.safe_load(REVIEW.read_text(encoding="utf-8")) or {}
    return spec.get("decisions") or {}


def load_extracts() -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from link_passages import load_extracts as le
    return le()


def gather():
    nodes = {(n["doc"], n["node_id"]): n
             for n in csv.DictReader(NODES.open(encoding="utf-8"))}
    spec = yaml.safe_load(URL_MAP.read_text(encoding="utf-8")) or {}
    stem_url = {k: v["url"] for k, v in (spec.get("urls") or {}).items()
                if isinstance(v, dict) and v.get("url")}
    rows = list(csv.DictReader(PASSAGES.open(encoding="utf-8")))
    return nodes, stem_url, rows


def cmd_worksheet(args) -> None:
    nodes, stem_url, rows = gather()
    extracts = load_extracts()
    done = load_review()

    cands = [r for r in rows if r["grade"] == "candidate"]
    fixture, concept, sharp = priority_refs(nodes)
    if args.priority:
        cands = [r for r in cands
                 if (r["doc"], r["node_id"]) in fixture
                 or (r["doc"], r["node_id"]) in concept
                 or r["type"] in sharp]
    if args.type:
        cands = [r for r in cands if r["type"] in set(args.type)]
    if args.doc:
        cands = [r for r in cands if r["doc"] in set(args.doc)]
    if args.band:
        cands = [r for r in cands
                 if band_of(float(r["margin"] or 0)) in set(args.band)]
    if not args.redo:
        cands = [r for r in cands
                 if f"{r['doc']}#{r['node_id']}" not in done]
    def sort_key(r):
        k = (r["doc"], r["node_id"])
        tier = (0 if r["type"] in sharp else
                1 if k in concept else
                2 if k in fixture else 3)
        return (tier, RANK.get(r["type"], 99), -float(r["margin"] or 0))
    cands.sort(key=sort_key)
    if args.limit:
        cands = cands[:args.limit]
    if not cands:
        print("nothing to review with those filters")
        return

    L = ["# Passage review worksheet", "",
         f"{len(cands)} candidate links to check. Each one is a claim and the "
         "paragraph the",
         "matcher thinks carries it. **A candidate is not a citation** - that is "
         "what you are",
         "deciding.", "",
         "Fill the `decision:` line under each item. **The relation matters "
         "more than the",
         "paragraph number** - every claim comes from somewhere, the question "
         "is how:", "",
         "| write | relation | meaning |",
         "|---|---|---|",
         "| `s` | states | the paragraph says it |",
         "| `a` | abstracts | the claim compresses or generalises the "
         "paragraph |",
         "| `w` | presupposes | the paragraph only works if the claim is true "
         "- it is the unstated warrant. **The usual answer for a hidden "
         "assumption.** |",
         "| `e` | elsewhere | a real prior of his, but grounded in his wider "
         "work, not this article |",
         "| `no` | none | cannot place it |",
         "| `p17` | | wrong paragraph - it is p17. Add a relation: `p17 a` |",
         "| `?` | | cannot tell, leave for later |",
         "| *(blank)* | | not reviewed yet |", "",
         "Then: `python scripts/review_passages.py --apply`", "",
         "Ordered by how much a verified passage is worth here - priors, hidden "
         "assumptions",
         "and mechanisms first, evidence last - and within a role by how "
         "decisively the",
         "chosen paragraph beat the runner-up. `tie` items show the runner-up "
         "too.", "",
         "---", ""]

    for i, r in enumerate(cands, 1):
        n = nodes[(r["doc"], r["node_id"])]
        ref = f"{r['doc']}#{r['node_id']}"
        ex = extracts.get(stem_url.get(r["doc"], ""), {})
        paras = ex.get("paras", {})
        margin = float(r["margin"] or 0)
        b = band_of(margin)
        claim = " ".join(f"{n['header']} {n['text']}".split())
        why = []
        if (r["doc"], r["node_id"]) in fixture:
            why.append("CQ fixture")
        if (r["doc"], r["node_id"]) in concept:
            why.append(f"concept `{n['concept']}`")
        if n["type"] in sharp:
            why.append("warrant - expect `w`, not `no`")
        L += [f"### [{i}] {ref} -> {r['para']}",
              f"`{n['type']}` · score {r['score']} · margin {r['margin']} "
              f"· band **{b}**"
              + (f" · **{', '.join(why)}**" if why else ""), "",
              f"Proposed relation: **{r.get('relation', '?')}** "
              f"(from the role type - the matcher cannot tell `abstracts` "
              f"from `presupposes`, so correct it if wrong)", "",
              f"**Claim:** {claim}", "",
              f"**{r['para']}:** {paras.get(int(r['para'][1:]), '(missing)')}",
              ""]
        if b == "tie":
            # the matcher nearly chose something else - show it
            alt = runner_up(r, nodes, extracts, stem_url)
            if alt:
                L += [f"**Runner-up {alt[0]}:** {alt[1]}", ""]
        L += ["decision:", "", "---", ""]

    WORKSHEET.parent.mkdir(parents=True, exist_ok=True)
    WORKSHEET.write_text("\n".join(L) + "\n", encoding="utf-8")
    by_band = Counter(band_of(float(r["margin"] or 0)) for r in cands)
    by_role = Counter(r["type"] for r in cands)
    print(f"wrote {WORKSHEET.relative_to(ROOT)}  ({len(cands)} items)")
    print(f"  bands: {dict(by_band)}")
    print(f"  roles: {', '.join(f'{k} {v}' for k, v in by_role.most_common(6))}")
    print()
    print("Edit the decision: lines, then run --apply.")
    print("Tip: --priority is the 52 that matter; the rest can wait "
          "indefinitely.")


def runner_up(row, nodes, extracts, stem_url):
    """Recompute the second-best paragraph for a near-tie, for comparison."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from link_passages import toks, literals
    import math
    ex = extracts.get(stem_url.get(row["doc"], ""), {})
    paras = ex.get("paras", {})
    if not paras:
        return None
    n = nodes[(row["doc"], row["node_id"])]
    pt = {i: toks(t) for i, t in paras.items()}
    df = Counter()
    for t in pt.values():
        df.update(set(t))
    N = len(pt)
    idf = {w: math.log(1 + N / (1 + c)) for w, c in df.items()}
    ct = toks(" ".join(f"{n['header']} {n['text']}".split()))
    cvec = Counter(ct)
    cnorm = math.sqrt(sum((v * idf.get(w, 0)) ** 2
                          for w, v in cvec.items())) or 1.0
    best = []
    for i, t in pt.items():
        pvec = Counter(t)
        dot = sum(cvec[w] * pvec[w] * idf.get(w, 0) ** 2
                  for w in cvec if w in pvec)
        pnorm = math.sqrt(sum((v * idf.get(w, 0)) ** 2
                              for w, v in pvec.items())) or 1.0
        best.append((dot / (cnorm * pnorm), i))
    best.sort(reverse=True)
    chosen = int(row["para"][1:])
    for _sc, i in best:
        if i != chosen:
            return (f"p{i}", paras[i])
    return None


def cmd_apply(args) -> None:
    if not WORKSHEET.exists():
        sys.exit(f"{WORKSHEET.relative_to(ROOT)} not found - run --worksheet")
    raw = WORKSHEET.read_text(encoding="utf-8")
    blocks = raw.split("\n### ")
    decisions = load_review()
    added = changed = skipped = bad = 0
    for blk in blocks[1:]:
        m = ITEM_RE.match("### " + blk)
        if not m:
            continue
        ref, para = m.group("ref"), m.group("para")
        d = DECISION_RE.search(blk)
        val = (d.group(1).strip() if d else "")
        if not val or val == "?":
            skipped += 1
            continue
        parts = val.split()
        head = parts[0]
        rel_tok = parts[1] if len(parts) > 1 else None
        if head == "e":
            rec = {"para": "", "verdict": "elsewhere", "relation": "elsewhere"}
        elif head in VOCAB and head not in ("no", "e"):
            rec = {"para": para, "verdict": "confirmed",
                   "relation": VOCAB[head][0]}
        elif head == "no":
            rec = {"para": "", "verdict": "no_passage", "relation": "none"}
        elif re.fullmatch(r"p\d+", head):
            rel = VOCAB.get(rel_tok, ("abstracts",))[0] if rel_tok else "abstracts"
            rec = {"para": head, "verdict": "corrected", "was": para,
                   "relation": rel}
        else:
            print(f"  ?? {ref}: cannot read decision {val!r}")
            bad += 1
            continue
        if ref in decisions and decisions[ref] != rec:
            changed += 1
        elif ref not in decisions:
            added += 1
        decisions[ref] = rec

    header = [
        "# Passage links confirmed by hand. THIS BEATS THE MATCHER.",
        "#",
        "# scripts/link_passages.py grades a link `anchored` (the claim and the",
        "# paragraph share a distinctive literal - checkable) or `candidate`",
        "# (semantic match only - a narrowing, not a citation). Everything here",
        "# is a human verdict on a candidate, and link_passages.py applies it",
        "# instead of re-deriving: a `confirmed` link becomes provenance.",
        "#",
        "# Same contract as the `hand` source in data/node_facets.csv - human",
        "# decisions accumulate, matcher output is disposable.",
        "#",
        "#   confirmed    the relation to that paragraph is as recorded",
        "#   corrected    it was a different paragraph; `was` keeps the miss",
        "#   elsewhere    a real prior, grounded in his wider work rather than",
        "#                this article - the concept layer is where it belongs",
        "#   no_passage   cannot be placed at all",
        "#",
        "# relation: states | abstracts | presupposes | elsewhere | none",
        "#   A hidden assumption normally PRESUPPOSES its paragraph: the passage",
        "#   only works if the claim is true. One that STATES a literal was",
        "#   never hidden.",
        "#",
        "# Produced by: python scripts/review_passages.py --apply",
        "",
        "decisions:",
    ]
    body = []
    for ref in sorted(decisions):
        rec = decisions[ref]
        body.append(f"  {ref}:")
        body.append(f"    verdict: {rec['verdict']}")
        if rec.get("relation"):
            body.append(f"    relation: {rec['relation']}")
        if rec.get("para"):
            body.append(f"    para: {rec['para']}")
        if rec.get("was"):
            body.append(f"    was: {rec['was']}")
    REVIEW.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    v = Counter(r["verdict"] for r in decisions.values())
    print(f"wrote {REVIEW.relative_to(ROOT)}")
    print(f"  {added} new, {changed} changed, {skipped} left blank"
          + (f", {bad} unreadable" if bad else ""))
    print(f"  totals: {dict(v)}")
    print()
    print("Now: python scripts/link_passages.py   (applies your decisions)")


def cmd_status(args) -> None:
    nodes, _, rows = gather()
    done = load_review()
    # A reviewed claim is no longer a candidate - link_passages.py has already
    # promoted or dropped it - so count the two pools separately rather than
    # implying the reviewed ones are still waiting.
    cands = [r for r in rows if r["grade"] == "candidate"]
    left = Counter(band_of(float(r["margin"] or 0)) for r in cands)
    total = len(cands) + len(done)
    print()
    print(f"{len(done)} of {total} candidate links reviewed "
          f"({len(done) / max(1, total):.0%}); {len(cands)} left")
    if done:
        print("  verdicts:", dict(Counter(r["verdict"]
                                          for r in done.values())))
    print()
    print(f"{'band':10} {'left':>6}")
    for b in ("clear", "moderate", "tie"):
        print(f"{b:10} {left[b]:6d}")
    anchored = len({(r["doc"], r["node_id"]) for r in rows
                    if r["grade"] == "anchored"})
    conf = sum(1 for r in done.values() if r["verdict"] in
               ("confirmed", "corrected"))
    print()
    print(f"passage provenance: {anchored} anchored + {conf} hand-confirmed "
          f"= {anchored + conf} of {len(nodes)} claims")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worksheet", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--band", nargs="*", choices=["clear", "moderate", "tie"])
    ap.add_argument("--type", nargs="*")
    ap.add_argument("--doc", nargs="*")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--priority", action="store_true",
                    help="only claims where a confirmed passage buys something:"
                         " CQ fixtures, concept nodes, and the warrant types")
    ap.add_argument("--redo", action="store_true",
                    help="include items already decided")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if args.apply:
        return cmd_apply(args)
    if args.status:
        return cmd_status(args)
    if args.worksheet:
        return cmd_worksheet(args)
    ap.error("give --worksheet, --apply or --status")


if __name__ == "__main__":
    main()
