#!/usr/bin/env python3
"""Inter-annotator agreement for the role axis, at three levels of granularity.

    python scripts/agreement.py --selftest          # verify the alpha maths
    python scripts/agreement.py --status            # what double annotations exist
    python scripts/agreement.py --pair A.mmd B.mmd  # two annotations, one article

THE CLAIM THIS EXISTS TO TEST

Everything in this repo is annotated by one person. "The method generalises to
another annotator" is therefore an assertion with no measurement behind it, and
it is the assertion the whole project rests on - if a second reader produces a
different graph from the same article, the graph is a reading rather than a
record.

The standard instrument is Krippendorff's alpha. The conventional bars: alpha >=
0.800 is reliable, 0.800 > alpha >= 0.667 supports tentative conclusions only.
Argument-annotation work uses it routinely, and also reports the unitizing
variant, because annotators disagree about where a claim starts as well as about
what it is.

WHY THREE LEVELS, AND WHY THAT IS THE POINT

The 26 role types are one annotator's vocabulary; schema_map.yaml declares two
coarser levels above them (`oper`, then Toulmin's elements). The cross-domain
argument-mining literature reports that coarse decisions transfer while
fine-grained unit classification does not, so the prediction is:

    alpha(toulmin) > alpha(oper) > alpha(type)

If that holds, it is direct evidence for keying rules on families rather than on
types - which is what this repo now does - and it tells us which level a second
annotator's work can be trusted at. If it does not hold, the family hierarchy is
not doing the work claimed for it, and that is worth knowing too.

UNITIZING IS REPORTED SEPARATELY, ALWAYS

Two annotators do not produce the same node ids, so units are matched by text
overlap. Alpha is then computed on the MATCHED units only, which makes it
conditional on unitizing agreement - an alpha of 0.9 over 40% of claims is not a
reliable annotation. Both numbers are always printed together; neither is
meaningful alone.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "scripts" / "schema_map.yaml"
PAIRS = ROOT / "scripts" / "double_annotation.yaml"

MATCH_THRESHOLD = 0.35          # token-overlap floor for calling two units the same


# --------------------------------------------------------------- alpha ------

def krippendorff_nominal(units: list[tuple[str, str]]) -> float:
    """Krippendorff's alpha for nominal data, two coders, no missing values.

    Coincidence-matrix form: alpha = 1 - Do/De, where Do is observed
    disagreement and De is the disagreement expected if both coders were
    assigning labels at the observed marginal rates.
    """
    if not units:
        return float("nan")
    o: dict[tuple[str, str], float] = defaultdict(float)
    for a, b in units:
        # m_u = 2, so each ordered pair contributes 1/(m_u - 1) = 1
        o[(a, b)] += 1.0
        o[(b, a)] += 1.0
    n_c = Counter()
    for (c, k), v in o.items():
        n_c[c] += v
    n = sum(n_c.values())
    if n <= 1:
        return float("nan")
    do = sum(v for (c, k), v in o.items() if c != k) / n
    de = sum(n_c[c] * n_c[k] for c in n_c for k in n_c if c != k) / (n - 1) / n
    if len(n_c) < 2:
        # Only one label observed across both coders. Expected disagreement is
        # zero, so alpha is 0/0 - undefined, NOT perfect. Reporting 1.0 here is
        # the classic way an agreement figure becomes meaningless: it is what a
        # single matched unit produces.
        return float("nan")
    if de == 0:
        return float("nan")
    return 1.0 - do / de


def selftest() -> int:
    cases = [
        ("perfect agreement", [("a", "a")] * 10 + [("b", "b")] * 10, 1.0),
        ("total disagreement, two labels",
         [("a", "b")] * 10 + [("b", "a")] * 10, None),
        ("one coder constant", [("a", "a")] * 10 + [("a", "b")] * 10, None),
    ]
    ok = True
    for name, units, expect in cases:
        got = krippendorff_nominal(units)
        line = f"  {name:34s} alpha = {got:+.3f}"
        if expect is not None:
            good = abs(got - expect) < 1e-9
            ok &= good
            line += f"   expected {expect:+.3f}  {'PASS' if good else 'FAIL'}"
        print(line)
    # a known property: systematic disagreement is worse than chance
    bad = krippendorff_nominal([("a", "b")] * 10 + [("b", "a")] * 10)
    good = bad < 0
    ok &= good
    print(f"  systematic disagreement is negative      {'PASS' if good else 'FAIL'}")
    return 0 if ok else 1


# ------------------------------------------------------------- map reading ---

NODE_RE = re.compile(r'^[ \t]*(\w+)\[\s*"(.*?)"\s*\]', re.M | re.S)
HDR_RE = re.compile(r"<b>(.*?)</b>", re.S)


CLASS_RE = re.compile(r"^[ \t]*class\s+([\w,\s]+?)\s+(\w+)[ \t]*$", re.M)


def read_map(path: Path, smap: dict) -> dict:
    """node id -> (role type, text). Deliberately a thin reader.

    This does not reuse parse_maps.parse_doc because that applies the URL
    overlay and the level fallbacks. For agreement we want the role each
    annotator actually declared, with nothing reconciled on their behalf.

    Two signals, in the parser's own priority order - header first, then class.
    Both are needed: the `banner` and `meta` families put the role name in the
    bold header, while the `plain` family puts the CLAIM there and declares the
    role through a `class` line. An earlier version of this reader only looked
    at headers and silently found zero units in every plain-family map, which
    would have reported perfect disagreement as an empty result.
    """
    by_header = {k.lower(): v for k, v in
                 (smap.get("node_types_by_header") or {}).items()}
    by_class = {k.lower(): v for k, v in
                (smap.get("node_types_by_class") or {}).items()}
    drop = {c.lower() for c in (smap.get("drop_classes") or [])}
    text = path.read_text(encoding="utf-8")

    cls_of: dict[str, str] = {}
    for m in CLASS_RE.finditer(text):
        cls = m.group(2).strip().lower()
        for nid in re.split(r"[,\s]+", m.group(1).strip()):
            if nid:
                cls_of[nid] = cls

    out = {}
    for m in NODE_RE.finditer(text):
        nid, label = m.group(1), m.group(2)
        cls = cls_of.get(nid, "")
        if cls in drop:
            continue
        h = HDR_RE.search(label)
        header = re.sub(r"<[^>]+>", "", h.group(1)).strip().lower() if h else ""
        header = re.split(r"\s*·\s*", header)[0].strip()
        role = by_header.get(header) or by_class.get(cls)
        if not role:
            continue
        body = re.sub(r"<[^>]+>", " ", label)
        body = re.sub(r"\s+", " ", body).strip()
        out[nid] = (role, body)
    return out


def tokens(s: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z\-']{2,}", s.lower())}


def match_units(a: dict, b: dict) -> tuple[list, list, list]:
    """Greedy best-overlap matching. Returns (pairs, unmatched_a, unmatched_b)."""
    ta = {k: tokens(v[1]) for k, v in a.items()}
    tb = {k: tokens(v[1]) for k, v in b.items()}
    scored = []
    for ka, sa in ta.items():
        for kb, sb in tb.items():
            if not sa or not sb:
                continue
            j = len(sa & sb) / len(sa | sb)
            if j >= MATCH_THRESHOLD:
                scored.append((j, ka, kb))
    scored.sort(reverse=True)
    used_a, used_b, pairs = set(), set(), []
    for j, ka, kb in scored:
        if ka in used_a or kb in used_b:
            continue
        used_a.add(ka)
        used_b.add(kb)
        pairs.append((ka, kb, j))
    return (pairs, [k for k in a if k not in used_a],
            [k for k in b if k not in used_b])


def families(smap: dict) -> dict:
    rf = smap.get("role_families") or {}
    levels = {"type": {}}
    for level in ("oper", "toulmin"):
        m = {}
        for name, members in (rf.get(level) or {}).items():
            for t in members:
                m[t] = name
        levels[level] = m
    return levels


def compare(pa: Path, pb: Path) -> None:
    smap = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    lv = families(smap)
    A, B = read_map(pa, smap), read_map(pb, smap)
    pairs, ua, ub = match_units(A, B)
    print(f"\n{pa.name}  vs  {pb.name}")
    print(f"  units: {len(A)} and {len(B)};  matched {len(pairs)}")
    denom = max(len(A), len(B)) or 1
    print(f"  UNITIZING agreement: {len(pairs)}/{denom} = {len(pairs)/denom:.0%}"
          f"   unmatched: {len(ua)} + {len(ub)}")
    if not pairs:
        print("  no matched units - alpha is undefined, and that IS the result")
        return
    print()
    print("  level      alpha    reading")
    for name in ("type", "oper", "toulmin"):
        m = lv[name]
        units = [(m.get(A[ka][0], A[ka][0]) if name != "type" else A[ka][0],
                  m.get(B[kb][0], B[kb][0]) if name != "type" else B[kb][0])
                 for ka, kb, _ in pairs]
        a = krippendorff_nominal(units)
        if a != a:                                   # NaN
            print(f"  {name:9s}   undefined   only one label observed - "
                  f"too few matched units to measure")
            continue
        bar = ("reliable" if a >= 0.80 else
               "tentative only" if a >= 0.667 else "not reliable")
        if len(pairs) < 10:
            bar += f"  (only {len(pairs)} units - treat as indicative)"
        print(f"  {name:9s}  {a:+.3f}   {bar}")
    print("\n  Alpha is computed on matched units only, so it is conditional on"
          "\n  the unitizing number above. Report both or neither.")


def status() -> None:
    spec = yaml.safe_load(PAIRS.read_text(encoding="utf-8")) if PAIRS.exists() else None
    pairs = (spec or {}).get("pairs") or []
    print("double annotations on record:", len(pairs))
    if not pairs:
        print("""
  None. So the role axis has no measured reliability, and any claim that it
  transfers to another annotator is currently an assertion.

  WHAT WOULD SETTLE IT, and it is the smallest experiment on the list:

    1. Pick two articles. One `plain`-family and one `banner`-family, because
       label density and slot conventions differ by family and a single pair
       would confound the two.
    2. A second annotator maps both from the article text alone - not from the
       existing map, and without seeing it.
    3. Save as mermaid_code/alt/<stem>.mmd and list the pair in
       scripts/double_annotation.yaml.
    4. python scripts/agreement.py --pair mermaid_code/<stem>.mmd \\
                                          mermaid_code/alt/<stem>.mmd

  It reports unitizing agreement and then alpha at all three levels, which is
  what tells us whether to trust the 26 types, only the families, or neither.
""")
        return
    for p in pairs:
        compare(ROOT / p["a"], ROOT / p["b"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--pair", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    if args.pair:
        compare(Path(args.pair[0]), Path(args.pair[1]))
        return
    status()


if __name__ == "__main__":
    main()
