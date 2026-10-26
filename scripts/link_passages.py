#!/usr/bin/env python3
"""Link each claim to the paragraph of its article that carries it.

    python scripts/link_passages.py              # build links + report
    python scripts/link_passages.py --docs setser_aug_14_24
    python scripts/link_passages.py --show setser_aug_14_24#E1

Reads   data/nodes.csv, scripts/source_urls.yaml,
        internal/extracted/*.md  (paragraph-anchored article text)
Writes  data/node_passages.csv   one row per (node, paragraph) link
        data/passage_report.md   coverage, and the by-role pattern

THE PROBLEM, AND WHY THERE ARE TWO TIERS

The last link in the provenance chain was missing: claims reached their article
but not the passage inside it. The obstacle is that a node's text is the
annotator's PARAPHRASE, not a quote, so no string match finds it, and a
semantic match that is presented as a citation is worse than no citation at
all - it looks authoritative and is sometimes wrong.

So links are graded, and the grade is part of the data:

  anchored   The claim and the paragraph share a distinctive LITERAL - a figure
             ("$300bn", "1.5pp", "25 percent"), or a rare proper noun ("COFCO",
             "Fajgelbaum", "NDRC"). The shared literal is itself the evidence
             and a human can confirm it in seconds. This is provenance.

  candidate  Semantic overlap only. A reviewing aid that says "start here".
             NOT a citation, and never rendered as one.

  none       Nothing matched.

WHY `none` IS SOMETIMES THE RIGHT ANSWER

A hidden assumption is by definition not stated in the article. If one of them
anchored to a paragraph, that would be evidence it is not actually hidden and
the annotation is wrong. So linkability should vary by role in a predictable
way - evidence anchors, stated assumptions match, hidden assumptions should
not - and the report below checks that pattern. Where it breaks, the annotation
is worth a look. That makes this a validity check on the maps, not only a
citation builder.

Paragraph numbers are only meaningful against the page that was extracted, so
every row carries the `page_sha256` of that extraction. If CFR re-flows an
article, the hash changes and the citation is invalidated rather than silently
wrong.
"""

from __future__ import annotations

import argparse
import csv
import math
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
URL_MAP = Path(__file__).resolve().parent / "source_urls.yaml"
EXTRACTED = ROOT / "internal" / "extracted"
OUT_CSV = ROOT / "data" / "node_passages.csv"
OUT_MD = ROOT / "data" / "passage_report.md"
REVIEW = Path(__file__).resolve().parent / "passage_review.yaml"

FIELDS = ["doc", "node_id", "type", "para", "grade", "relation", "score",
          "margin", "anchors", "page_sha256"]

# HOW A CLAIM RELATES TO ITS PARAGRAPH
#
# An earlier version of this script graded links as quoted-or-not, which made
# `none` the only possible answer for a hidden assumption. That was wrong. A
# hidden assumption is abstracted FROM a paragraph: the annotator read it and
# inferred the unstated warrant the passage needs. That paragraph is the
# provenance for the inference even though it is not where the claim is said.
#
#   states       the paragraph says it. A restatement or a quote.
#   abstracts    the claim compresses or generalises what the paragraph says.
#                Most mechanisms, intermediate claims and conclusions.
#   presupposes  the paragraph only works if the claim is true - the claim is
#                the unstated warrant behind it. Hidden assumptions.
#   none         not grounded in this article's text at all. Still a real
#                answer: the claim may come from a chart, or be a prior he
#                carries across the corpus rather than argues here.
#
# The matcher cannot tell `abstracts` from `presupposes` - that is a reading
# judgement - so it PROPOSES one from the role type and the human confirms.
# `states` is proposed only when the link anchored on a shared literal, which
# is the one case the matcher has real evidence for.
RELATIONS = ("states", "abstracts", "presupposes", "none")
PROPOSE_PRESUPPOSES = {"hidden_assumption"}

STOP = set("""a an and the of in to for on at by or as is are be been it its do
does did still now than that their they them what why how will can could would
may might with from when where which who this those these not no but if then so
such more most one two i he she his her our your you about over under into out
also been being had has have was were more much many less least same other
another each both all any some only even just very then there here
""".split())

# Magnitude and unit words folded to a canonical form, so "$550B" in a claim
# and "550 billion" in the article are the same literal.
UNIT = {"bn": "billion", "b": "billion", "billion": "billion",
        "m": "million", "mn": "million", "million": "million",
        "tn": "trillion", "t": "trillion", "trillion": "trillion",
        "pp": "pp", "ppt": "pp", "percentagepoints": "pp",
        "%": "percent", "percent": "percent", "pct": "percent",
        "bp": "bp", "bps": "bp"}

# A claim and a paragraph sharing one of these is not evidence of anything.
BORING_NUM = {"1", "2", "3", "4", "5", "10", "2017", "2018", "2019", "2020",
              "2021", "2022", "2023", "2024", "2025", "2026"}

# Role types where a STATES relation is the anomaly. A hidden assumption that
# restates a literal from the paragraph was never hidden - it is a stated
# assumption, mis-typed. It should `presuppose` a paragraph, not state one.
EXPECT_NOT_STATED = {"hidden_assumption"}
# Role types that should anchor on a literal if the annotation is faithful.
EXPECT_ANCHOR = {"evidence_data", "evidence_discrepancy", "evidence_rival",
                 "benchmark"}


def norm_num(tok: str) -> str | None:
    """Canonicalise a figure: '$430 billion' / '~$430bn' / '430B' -> '430billion'."""
    t = tok.lower().replace(",", "").replace("~", "").replace("$", "")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([a-z%]*)$", t)
    if not m:
        return None
    num, unit = m.group(1), m.group(2)
    if num in BORING_NUM and not unit:
        return None
    return num + UNIT.get(unit, unit)


def literals(text: str) -> set:
    """Distinctive tokens: figures with units, and rare proper nouns."""
    out = set()
    # figures, with an optional trailing unit word on the next token
    for m in re.finditer(r"[~$]?\d[\d,.]*\s?(?:billion|bn|million|mn|trillion"
                         r"|tn|percent|percentage points|pp|bps?|%|[bmt](?![a-z]))?",
                         text, re.I):
        n = norm_num(m.group(0).strip())
        if n:
            out.add("#" + n)
    # acronyms and rare proper nouns
    for m in re.finditer(r"\b([A-Z][A-Za-z'’\-]{2,})\b", text):
        w = m.group(1)
        if w.isupper() and len(w) >= 3:          # COFCO, NDRC, IMF, COMAC
            out.add("!" + w.lower())
        elif w.lower() not in STOP and not w.isupper():
            out.add("!" + w.lower())
    return out


def toks(text: str) -> list:
    text = text.lower().replace("’", "'")
    return [w for w in re.findall(r"[a-z][a-z'\-]{2,}", text) if w not in STOP]


def strip_md(text: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)     # links -> label
    text = re.sub(r"[*_`]", "", text)
    return " ".join(text.split())


def load_extracts() -> dict:
    """url -> {"sha": ..., "paras": {n: text}}"""
    out = {}
    if not EXTRACTED.exists():
        return out
    for p in sorted(EXTRACTED.glob("*.md")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^url:\s*(\S+)", raw, re.M)
        h = re.search(r"^page_sha256:\s*(\S+)", raw, re.M)
        if not m:
            continue
        paras = {}
        for pm in re.finditer(r"<!--\s*p(\d+)\s*-->\s*\n(.*?)(?=\n<!--|\n##|\Z)",
                              raw, re.S):
            body = strip_md(pm.group(2))
            if body:
                paras[int(pm.group(1))] = body
        out[m.group(1).strip()] = {"sha": (h.group(1) if h else ""),
                                   "paras": paras, "file": p.name}
    return out


def load_review() -> dict:
    """ref -> verdict, from scripts/passage_review.yaml.

    A human verdict is final: `confirmed` and `corrected` become the grade
    `confirmed` (real provenance, not a candidate), and `no_passage` becomes
    `none` and stays there. Nothing re-derives a reviewed link.
    """
    if not REVIEW.exists():
        return {}
    spec = yaml.safe_load(REVIEW.read_text(encoding="utf-8")) or {}
    return spec.get("decisions") or {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", nargs="*")
    ap.add_argument("--show", metavar="DOC#NODE")
    ap.add_argument("--min-score", type=float, default=0.18,
                    help="cosine floor for a candidate (default 0.18)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    nodes = list(csv.DictReader(NODES.open(encoding="utf-8")))
    spec = yaml.safe_load(URL_MAP.read_text(encoding="utf-8")) or {}
    stem_url = {k: v["url"] for k, v in (spec.get("urls") or {}).items()
                if isinstance(v, dict) and v.get("url")}
    extracts = load_extracts()

    missing = sorted({n["doc"] for n in nodes
                      if extracts.get(stem_url.get(n["doc"], "")) is None})
    by_doc = defaultdict(list)
    for n in nodes:
        by_doc[n["doc"]].append(n)
    order = [d for d in by_doc if d not in missing]
    if args.docs:
        order = [d for d in order if d in set(args.docs)]

    rows, per_doc_stats = [], {}
    for doc in order:
        ex = extracts[stem_url[doc]]
        paras = ex["paras"]
        if not paras:
            continue
        # idf over this article's paragraphs - a word that is in every
        # paragraph tells you nothing about which one a claim came from
        pt = {i: toks(t) for i, t in paras.items()}
        df = Counter()
        for t in pt.values():
            df.update(set(t))
        N = len(pt)
        idf = {w: math.log(1 + N / (1 + c)) for w, c in df.items()}
        plit = {i: literals(t) for i, t in paras.items()}
        # A literal shared with the claim is only evidence if it is DISTINCTIVE
        # in this article. "china", "imf", "gdp" appear in most paragraphs and
        # discriminate nothing; "$300bn" or "COFCO" appear in one or two.
        lit_df = Counter(x for ls in plit.values() for x in ls)
        cap = max(1, int(0.15 * len(plit)))
        distinctive = {x for x, c in lit_df.items() if c <= cap}

        for n in by_doc[doc]:
            ctext = " ".join(f"{n['header']} {n['text']}".split())
            ct, cl = toks(ctext), literals(ctext)
            if not ct:
                continue
            cvec = Counter(ct)
            cnorm = math.sqrt(sum((v * idf.get(w, 0)) ** 2
                                  for w, v in cvec.items())) or 1.0
            scored = []
            for i, t in pt.items():
                pvec = Counter(t)
                dot = sum(cvec[w] * pvec[w] * idf.get(w, 0) ** 2
                          for w in cvec if w in pvec)
                pnorm = math.sqrt(sum((v * idf.get(w, 0)) ** 2
                                      for w, v in pvec.items())) or 1.0
                cos = dot / (cnorm * pnorm)
                shared = (cl & plit[i]) & distinctive
                nums = {x for x in shared if x.startswith("#")}
                scored.append((i, cos, shared, nums))

            # anchored: a shared figure, or two shared proper nouns
            anchored = [s for s in scored if s[3] or len(s[2]) >= 2]
            margin = 0.0
            if anchored:
                best = max(s[1] for s in anchored)
                keep = [s for s in anchored if s[1] >= best * 0.6][:3]
                grade = "anchored"
            else:
                ranked = sorted(scored, key=lambda s: -s[1])
                top = ranked[0]
                runner = ranked[1][1] if len(ranked) > 1 else 0.0
                margin = top[1] - runner
                keep = [top] if top[1] >= args.min_score else []
                grade = "candidate" if keep else "none"

            if not keep:
                rows.append({"doc": doc, "node_id": n["node_id"],
                             "type": n["type"], "para": "", "grade": "none",
                             "relation": "none", "score": "", "margin": "",
                             "anchors": "", "page_sha256": ex["sha"][:16]})
                continue
            for i, cos, shared, nums in sorted(keep, key=lambda s: -s[1]):
                rows.append({
                    "doc": doc, "node_id": n["node_id"], "type": n["type"],
                    "para": f"p{i}", "grade": grade,
                    "relation": ("states" if grade == "anchored" else
                                 "presupposes"
                                 if n["type"] in PROPOSE_PRESUPPOSES
                                 else "abstracts"),
                    "score": f"{cos:.3f}", "margin": f"{margin:.3f}",
                    "anchors": " ".join(sorted(
                        x.lstrip("#!") for x in (nums or shared))[:6]),
                    "page_sha256": ex["sha"][:16]})
        per_doc_stats[doc] = len(paras)

    if args.show:
        d, nid = args.show.split("#")
        sel = [r for r in rows if r["doc"] == d and r["node_id"] == nid]
        node = next((n for n in nodes if n["doc"] == d
                     and n["node_id"] == nid), None)
        if not node:
            sys.exit(f"no such node: {args.show}")
        ex = extracts.get(stem_url.get(d, ""), {})
        print()
        print(f"CLAIM  {args.show}  [{node['type']}]")
        print(f"  {' '.join(f'{node['header']} {node['text']}'.split())[:300]}")
        print()
        for r in sel:
            if r["grade"] == "none":
                print("  no passage linked")
                continue
            print(f"  {r['para']}  [{r['grade']}, score {r['score']}, "
                  f"anchors: {r['anchors'] or '-'}]")
            body = ex.get("paras", {}).get(int(r["para"][1:]), "")
            print(f"    {body[:400]}")
            print()
        return

    # Apply hand decisions last, so they override whatever the matcher said.
    review = load_review()
    if review:
        kept, seen = [], set()
        for r in rows:
            ref = f"{r['doc']}#{r['node_id']}"
            if ref not in review:
                kept.append(r)
                continue
            if ref in seen:
                continue                      # one row per reviewed claim
            seen.add(ref)
            rec = review[ref]
            if rec["verdict"] == "elsewhere":
                # A real prior of his, grounded in his wider work rather than
                # this article. Not a passage citation, but not a gap either -
                # the concept layer is where it belongs.
                r = {**r, "para": "", "grade": "elsewhere",
                     "relation": "elsewhere", "score": "", "margin": "",
                     "anchors": "reviewed: prior from his wider work"}
            elif rec["verdict"] == "no_passage":
                r = {**r, "para": "", "grade": "none", "relation": "none",
                     "score": "", "margin": "",
                     "anchors": "reviewed: not grounded in this text"}
            else:
                r = {**r, "para": rec.get("para", r["para"]),
                     "grade": "confirmed",
                     "relation": rec.get("relation", r["relation"]),
                     "anchors": "reviewed by hand"}
            kept.append(r)
        rows = kept

    OUT_CSV.parent.mkdir(exist_ok=True)
    rows.sort(key=lambda r: (r["doc"], r["node_id"], r["para"]))
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    # ---- report ----------------------------------------------------------
    PREC = {"confirmed": 4, "elsewhere": 3, "anchored": 2,
            "candidate": 1, "none": 0}
    per_node = {}
    for r in rows:
        k = (r["doc"], r["node_id"])
        if PREC[r["grade"]] >= PREC.get(per_node.get(k, "none"), 0):
            per_node[k] = r["grade"]
    g = Counter(per_node.values())
    total = len(per_node)

    by_type = defaultdict(Counter)
    ntype = {(n["doc"], n["node_id"]): n["type"] for n in nodes}
    for k, grade in per_node.items():
        by_type[ntype[k]][grade] += 1

    rel_by_type = defaultdict(Counter)
    for r in rows:
        if r["grade"] != "none":
            rel_by_type[r["type"]][r["relation"]] += 1

    L = ["# Passage linking", "",
         "The last link in the provenance chain: which paragraph of the article "
         "carries each",
         "claim. Generated by `scripts/link_passages.py`.", "",
         "Links are graded, and the grade is part of the data. **`anchored` "
         "means the claim and",
         "the paragraph share a distinctive literal** - a figure or a rare "
         "proper noun - so a",
         "human can confirm it at a glance. **`candidate` is semantic overlap "
         "only: a reviewing",
         "aid, not a citation.** Never render a candidate as a source.", "",
         f"- {total} claims over {len(order)} articles, "
         f"{sum(per_doc_stats.values())} paragraphs",
         f"- **confirmed by hand: {g['confirmed']} "
         f"({g['confirmed'] / total:.0%})**",
         f"- **anchored: {g['anchored']} ({g['anchored'] / total:.0%})**",
         f"- candidate: {g['candidate']} ({g['candidate'] / total:.0%})",
         f"- none: {g['none']} ({g['none'] / total:.0%})"]
    if missing:
        L.append(f"- not linkable, no extract: {len(missing)} documents "
                 f"({', '.join(missing)})")
    L += ["", "## The pattern by role, which is also a validity check", "",
          "Every claim comes from somewhere in the article; what differs is "
          "HOW. Evidence",
          "**states** a figure. A mechanism **abstracts** a passage. A hidden "
          "assumption",
          "**presupposes** one - the paragraph only works if the claim is "
          "true - which is why",
          "a hidden assumption that *states* a literal is the anomaly, not one "
          "that fails to.",
          "Deviations from the expected column are worth an annotator's time.",
          "",
          "The relations below are PROPOSED from the role type. The matcher "
          "cannot tell",
          "`abstracts` from `presupposes`; `scripts/review_passages.py` is "
          "where a human",
          "settles it.", "",
          "| role | n | states | abstracts | presupposes | none | expected |",
          "|---|---|---|---|---|---|"]
    for t, c in sorted(by_type.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        exp = ("states" if t in EXPECT_ANCHOR else
               "presupposes" if t in EXPECT_NOT_STATED else "abstracts")
        rc = rel_by_type.get(t, Counter())
        L.append(f"| `{t}` | {n} | {rc['states']} | {rc['abstracts']} "
                 f"| {rc['presupposes']} | {c['none']} | {exp} |")

    flags = []
    for t in EXPECT_NOT_STATED:
        c = rel_by_type.get(t, Counter())
        if c["states"]:
            flags.append(f"- **{c['states']} `{t}` claims STATE a literal from "
                         f"the paragraph.** One that restates the text was "
                         f"never hidden - check whether it is a stated "
                         f"assumption, mis-typed.")
        n_none = by_type.get(t, Counter())["none"]
        if n_none:
            flags.append(f"- **{n_none} `{t}` claims reach no paragraph at "
                         f"all.** Worth asking where the annotator got them: a "
                         f"warrant abstracted from nothing in the article may "
                         f"be a prior carried in from his wider work, which is "
                         f"a legitimate finding, or the matcher may simply have "
                         f"missed it.")
    for t in EXPECT_ANCHOR:
        c = by_type.get(t)
        if c and sum(c.values()) and c["none"] / sum(c.values()) > 0.25:
            flags.append(f"- **{c['none']} of {sum(c.values())} `{t}` claims "
                         f"found no passage at all.** Evidence nodes carry "
                         f"figures; if the figure is not in the article text it "
                         f"may have come from a chart, which the extractor "
                         f"captures only as a filename.")
    if flags:
        L += ["", "## Flagged by that check", ""] + flags
    L += ["", "## How to read a row", "",
          "```", "python scripts/link_passages.py --show setser_aug_14_24#E1",
          "```", "",
          "Paragraph numbers are only meaningful against the extraction they "
          "came from, so",
          "every row carries that page's `page_sha256`. If CFR re-flows an "
          "article the hash",
          "changes and the citation is invalidated rather than silently wrong.",
          "",
          "The article text lives in `internal/extracted/`, which is gitignored "
          "- so these",
          "rows are pointers into local files, by design.", ""]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"{total} claims linked over {len(order)} articles")
    print(f"  confirmed {g['confirmed']:4d}  ({g['confirmed'] / total:.0%})"
          f"   <- reviewed by hand, beats the matcher")
    if g["elsewhere"]:
        print(f"  elsewhere {g['elsewhere']:4d}  "
              f"({g['elsewhere'] / total:.0%})   <- his prior, grounded "
              f"outside this article")
    print(f"  anchored  {g['anchored']:4d}  ({g['anchored'] / total:.0%})")
    print(f"  candidate {g['candidate']:4d}  ({g['candidate'] / total:.0%})")
    print(f"  none      {g['none']:4d}  ({g['none'] / total:.0%})")
    if missing:
        print(f"  no extract for {len(missing)} docs: {', '.join(missing)}")
    print(f"wrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} rows)")
    print(f"wrote {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
