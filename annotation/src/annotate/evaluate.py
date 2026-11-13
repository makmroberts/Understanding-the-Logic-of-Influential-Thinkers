"""Step 7: compare a model map with the hand-drawn map of the same article.

ONE fixed box matcher, used for every score here:
  a model box and a hand box can pair only if they are on the same level, and either cite a
  common paragraph or are the only box of that role on both sides (one question, one main
  claim). Pairs are taken best first, each box at most once; same role counts most, then the
  share of the hand box's paragraphs the model box also cites. Hand boxes' paragraphs are the
  team's passage links (kb/data/node_passages.csv).
  Each pair records how it was made. "paragraph": the two boxes cite the same passage, so
  they very likely say the same thing. "slot": only the role matched, so they fill the same
  slot of the template but may say different things - read the claims side by side.
  (Word overlap between the claims was tried and rejected: paraphrases of the same claim
  scored as low as unrelated claims.)

Scores per step: boxes (found, same role, role presence), links (on matched boxes), facets
(on matched boxes). `report` adds the comparison across models and repeat runs, keeping
held-out articles and the worked example apart.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from .config import ontology, path, read_csv, settings


# --- metrics, copied from .claude/skills/predict-vs-actual/pva.py -------------------------

def wilson(k: int, n: int) -> tuple[float, float]:
    """95% Wilson interval for k of n; unlike p ± 1.96·se it stays sensible for small n."""
    z2 = 1.96 ** 2
    p = k / n
    mid = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = 1.96 * (p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5 / (1 + z2 / n)
    return max(0.0, mid - half), min(1.0, mid + half)


def frac(k: int, n: int) -> str:
    if not n:
        return "-"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k / n:.2f} ({lo:.2f}-{hi:.2f})"


def f1(tp: int, n_pred: int, n_true: int) -> float | None:
    return 2 * tp / (n_pred + n_true) if (n_pred + n_true) else None


def kalpha(units: list) -> float | None:
    """Krippendorff's alpha, nominal. Each unit lists the value every coder gave it."""
    units = [[v for v in u if v is not None] for u in units]
    units = [u for u in units if len(u) > 1]
    cats = sorted({v for u in units for v in u})
    at = {c: i for i, c in enumerate(cats)}
    rng = range(len(cats))
    o = [[0.0 for _ in rng] for _ in rng]
    for u in units:
        for i, a in enumerate(u):
            for j, b in enumerate(u):
                if i != j:
                    o[at[a]][at[b]] += 1 / (len(u) - 1)
    n_c = [sum(row) for row in o]
    n = sum(n_c)
    d_o = sum(o[c][k] for c in rng for k in rng if c != k)
    d_e = sum(n_c[c] * n_c[k] for c in rng for k in rng if c != k) / (n - 1) if n > 1 else 0
    return 1 - d_o / d_e if d_e else None


# --- the hand-drawn map ------------------------------------------------------------------

def hand_map(doc: str) -> dict:
    data = path("kb") / "data"
    paras = defaultdict(set)
    for r in read_csv(data / "node_passages.csv"):
        if r["doc"] == doc and r["grade"] != "none" and r["para"].startswith("p"):
            paras[r["node_id"]].add(int(r["para"][1:]))
    boxes = [{"id": n["node_id"], "role": n["type"], "level": n["level"],
              "claim": " ".join(f"{n['header']} {n['text']}".split()),
              "paragraphs": sorted(paras[n["node_id"]])}
             for n in read_csv(data / "nodes.csv") if n["doc"] == doc]
    links = [{"from": e["from"], "to": e["to"], "relation": e["type"]}
             for e in read_csv(data / "edges.csv") if e["doc"] == doc]
    facets = defaultdict(lambda: defaultdict(set))
    for r in read_csv(data / "node_facets.csv"):
        if r["doc"] == doc:
            facets[r["node_id"]][r["facet"]].add(r["value"])
    return {"boxes": boxes, "links": links, "facets": facets}


# --- the matcher -------------------------------------------------------------------------

def match(model: list[dict], hand: list[dict]) -> dict[str, tuple[str, str]]:
    """model box ID -> (hand box ID, "paragraph" | "slot")."""
    mc, hc = Counter(b["role"] for b in model), Counter(b["role"] for b in hand)
    cands = []
    for m in model:
        for h in hand:
            if m["level"] != h["level"]:
                continue
            shared = set(m["paragraphs"]) & set(h["paragraphs"])
            same = m["role"] == h["role"]
            unique = same and mc[m["role"]] == 1 and hc[h["role"]] == 1
            if not (shared or unique):
                continue
            cover = len(shared) / len(h["paragraphs"]) if h["paragraphs"] else 0.0
            cands.append((2 * same + unique + cover, m["id"], h["id"],
                          "paragraph" if shared else "slot"))
    out, used = {}, set()
    for _, m, h, how in sorted(cands, key=lambda c: (-c[0], c[1], c[2])):
        if m not in out and h not in used:
            out[m] = (h, how)
            used.add(h)
    return out


# --- scores ------------------------------------------------------------------------------

def score(model: dict, hand: dict, oracle: bool = False) -> dict:
    """oracle: the model was given the hand-drawn boxes, so each box pairs with itself."""
    mb, hb = model["boxes"], hand["boxes"]
    if oracle:
        ids = {b["id"] for b in hb}
        how = {b["id"]: (b["id"], "given") for b in mb if b["id"] in ids}
    else:
        how = match(mb, hb)
    pairs = {m: h for m, (h, _) in how.items()}
    by_para = sum(1 for _, x in how.values() if x == "paragraph")
    role_m = {b["id"]: b["role"] for b in mb}
    role_h = {b["id"]: b["role"] for b in hb}
    same_role = sum(role_m[m] == role_h[h] for m, h in pairs.items())
    pm, ph = set(role_m.values()), set(role_h.values())
    # links: a hand link counts as found when the model links the two matched boxes
    hl = {(l["from"], l["to"]): l["relation"] for l in hand["links"]}
    inv = {h: m for m, h in pairs.items()}
    ml = {(l["from"], l["to"]): l["relation"] for l in model["links"]}
    hl_c = {k: v for k, v in hl.items() if k[0] in inv and k[1] in inv}
    ml_c = {k: v for k, v in ml.items() if k[0] in pairs and k[1] in pairs}
    found = [k for k in hl_c if (inv[k[0]], inv[k[1]]) in ml]
    same_rel = [k for k in found if ml[(inv[k[0]], inv[k[1]])] == hl_c[k]]
    right = [k for k in ml_c if (pairs[k[0]], pairs[k[1]]) in hl]
    # facets on matched boxes, mean Jaccard per facet; only where the hand box has facets
    fj = defaultdict(list)
    for m, h in pairs.items():
        if not hand["facets"].get(h):
            continue
        for f in set(model["facets"].get(m, {})) | set(hand["facets"].get(h, {})):
            a, b = model["facets"].get(m, {}).get(f, set()), hand["facets"].get(h, {}).get(f, set())
            if a or b:
                fj[f].append(len(a & b) / len(a | b))
    return {
        "boxes": {"model": len(mb), "hand": len(hb), "matched": len(pairs), "by_paragraph": by_para,
                  "same_role": same_role,
                  "recall": (len(pairs), len(hb)), "precision": (len(pairs), len(mb)),
                  "roles_present_f1": f1(len(pm & ph), len(pm), len(ph))},
        "links": {"model": len(ml), "hand": len(hl), "hand_between_matched": len(hl_c),
                  "found": len(found), "same_relation": len(same_rel),
                  "model_between_matched": len(ml_c), "in_hand": len(right)},
        "facets": {f: round(sum(v) / len(v), 2) for f, v in sorted(fj.items())},
        "pairs": how,
    }


def model_map(run: Path) -> dict:
    ann = json.loads((run / "annotation.json").read_text(encoding="utf-8"))
    legacy = {n["id"]: n["legacy_id"] for n in ann["nodes"]}
    boxes = [{"id": n["legacy_id"], "role": n["role"], "level": n["level"],
              "claim": n["content"]["text"],
              "paragraphs": sorted(int(p["paragraph_id"][1:]) for p in n["source"]["passages"])}
             for n in ann["nodes"]]
    links = [{"from": legacy[e["from"]], "to": legacy[e["to"]], "relation": e["relation"]}
             for e in ann["edges"]]
    facets = defaultdict(lambda: defaultdict(set))
    for n in ann["nodes"]:
        for f, terms in n["facets"].items():
            for t in terms:
                facets[n["legacy_id"]][f].add(t["term"])
    calls = [json.loads(x) for x in (run / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    cost = sum({c["key"]: c.get("cost_usd") or 0 for c in calls}.values())   # each request once
    return {"boxes": boxes, "links": links, "facets": facets, "cost": round(cost, 4),
            "review": len(ann["validation"]["review_items"]),
            "excerpts": sum(any(p["anchor_grade"] == "excerpt" for p in n["source"]["passages"])
                            for n in ann["nodes"])}


def evaluate_run(run: Path, doc: str) -> dict:
    """Writes evaluation.md in the run folder, for a person; returns the scores for `report`."""
    m, h = model_map(run), hand_map(doc)
    oracle = json.loads((run / "boxes.json").read_text(encoding="utf-8")).get("oracle", False)
    s = score(m, h, oracle)
    b, l = s["boxes"], s["links"]
    hb = {x["id"]: x for x in h["boxes"]}
    mb = {x["id"]: x for x in m["boxes"]}
    lines = [f"# Evaluation: {doc} / {run.name}", "",
             "Compared with the hand-drawn map. Scores with 95% Wilson intervals.",
             "Oracle run: the model was given the hand-drawn boxes, so only links and facets "
             "are scored." if oracle else "", "",
             "## Boxes", "",
             f"- model {b['model']}, hand {b['hand']}",
             f"- hand boxes found: {frac(*b['recall'])}",
             f"  - of which by a shared paragraph: {b['by_paragraph']}; by role only (same slot): "
             f"{b['matched'] - b['by_paragraph']}",
             f"- model boxes that match a hand box: {frac(*b['precision'])}",
             f"- matched with the same role: {frac(b['same_role'], b['matched'])}",
             f"- roles present, F1: {b['roles_present_f1']:.2f}" if b["roles_present_f1"] is not None else "",
             f"- boxes with an excerpt checked word for word: {frac(m['excerpts'], b['model'])}", "",
             "## Links", "",
             f"- hand links between matched boxes that the model also draws: {frac(l['found'], l['hand_between_matched'])}",
             f"- of those, the same relation: {frac(l['same_relation'], l['found'])}",
             f"- model links between matched boxes that the hand map also has: {frac(l['in_hand'], l['model_between_matched'])}", "",
             "## Facets (mean Jaccard on matched boxes)", ""]
    lines += [f"- {f}: {v}" for f, v in s["facets"].items()] or ["- the hand-drawn map has no facets to compare with"]
    lines += ["", f"Cost of this run: ${m['cost']}. Review items: {m['review']}.", "",
              "## Matched boxes", "", "| model | hand | by | model claim | hand claim |",
              "|---|---|---|---|---|"]
    for mid, (hid, how) in s["pairs"].items():
        lines.append(f"| {mid} {mb[mid]['role']} | {hid} {hb[hid]['role']} | {how} | "
                     f"{mb[mid]['claim'][:90]} | {hb[hid]['claim'][:90]} |")
    lines += ["", "Unmatched model boxes: " + (", ".join(f"{k} ({mb[k]['role']})" for k in mb if k not in s["pairs"]) or "none"),
              "", "Unmatched hand boxes: " + (", ".join(f"{k} ({hb[k]['role']})" for k in hb
                                                         if k not in {h for h, _ in s["pairs"].values()}) or "none")]
    (run / "evaluation.md").write_text("\n".join(x for x in lines if x is not None) + "\n", encoding="utf-8")
    out = {**{k: v for k, v in s.items() if k != "pairs"}, "pairs": s["pairs"], "cost": m["cost"],
           "review": m["review"], "excerpts": m["excerpts"], "oracle": oracle}
    return out


# --- across runs -------------------------------------------------------------------------

def report() -> Path:
    """evaluation.md in paths.experiments: every run, official and experimental, re-scored with
    the current code and hand-drawn maps, by model; then agreement between runs."""
    from .config import hand_docs
    cfg = settings()
    held, example = set(cfg.get("held_out") or []), set(cfg["example_articles"])
    runs = sorted(f.parent for where in ("articles", "experiments")
                  for f in path(where).glob("*/*/annotation.json")
                  if f.parent.parent.name in hand_docs())
    rows, by_doc = [], defaultdict(dict)
    for d in runs:
        doc, run = d.parent.name, d.name
        e = evaluate_run(d, doc)
        group = "example (not scored)" if doc in example else "held-out" if doc in held else "tuning"
        rows.append((group, run, doc, e))
        if not e["oracle"]:
            by_doc[doc][run] = d
    out = ["# Evaluation across runs", "",
           "Each run is scored against the hand-drawn map with the one box matcher (see "
           "`src/annotate/evaluate.py`). Held-out articles were never used while writing the "
           "prompts.", ""]
    for group in ("tuning", "held-out", "example (not scored)"):
        sel = [r for r in rows if r[0] == group and not r[3]["oracle"]]
        if not sel:
            continue
        out += [f"## {group}", "",
                "| run | article | boxes m/h | found (by paragraph) | same role | roles F1 | links found | same rel | facets | cost $ |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        tot = defaultdict(Counter)
        for _, run, doc, e in sorted(sel, key=lambda r: (r[1], r[2])):
            b, l = e["boxes"], e["links"]
            fct = ", ".join(f"{k[:4]} {v}" for k, v in e["facets"].items())
            out.append(f"| {run} | {doc} | {b['model']}/{b['hand']} | {b['matched']}/{b['hand']} ({b['by_paragraph']}) | "
                       f"{b['same_role']}/{b['matched']} | {b['roles_present_f1']:.2f} | "
                       f"{l['found']}/{l['hand_between_matched']} | {l['same_relation']}/{l['found']} | "
                       f"{fct} | {e['cost']} |")
            t = tot[run]
            t["para"] += b["by_paragraph"]
            t["matched"] += b["matched"]; t["hand"] += b["hand"]; t["model"] += b["model"]
            t["same"] += b["same_role"]; t["lf"] += l["found"]; t["lh"] += l["hand_between_matched"]
            t["lr"] += l["same_relation"]; t["n"] += 1; t["cost"] += e["cost"]
        out += ["", "Totals by run:", ""]
        for run, t in sorted(tot.items()):
            out.append(f"- {run} ({t['n']} articles): hand boxes found {frac(t['matched'], t['hand'])}, "
                       f"by a shared paragraph {frac(t['para'], t['hand'])}; "
                       f"same role {frac(t['same'], t['matched'])}; hand links found {frac(t['lf'], t['lh'])}; "
                       f"same relation {frac(t['lr'], t['lf'])}; cost ${t['cost']:.3f}, "
                       f"${t['cost'] / t['n']:.3f} per article")
        out.append("")
    orc = [r for r in rows if r[3]["oracle"]]
    if orc:
        out += ["## Links and facets on the hand-drawn boxes (oracle runs)", "",
                "The model is given the hand-drawn boxes, so these steps are scored on their own.", "",
                "| run | article | links found | same relation | model links in hand map | facets | cost $ |",
                "|---|---|---|---|---|---|---|"]
        for _, run, doc, e in sorted(orc, key=lambda r: (r[1], r[2])):
            l = e["links"]
            fct = ", ".join(f"{k[:4]} {v}" for k, v in e["facets"].items()) or "no hand facets"
            out.append(f"| {run} | {doc} | {frac(l['found'], l['hand_between_matched'])} | "
                       f"{l['same_relation']}/{l['found']} | {l['in_hand']}/{l['model']} | {fct} | {e['cost']} |")
        out.append("")
    # agreement: the same matcher between every two runs of one article
    agree = []
    for doc, rs in sorted(by_doc.items()):
        names = sorted(rs)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                ma, mb = model_map(rs[a]), model_map(rs[b])
                p = match(ma["boxes"], mb["boxes"])
                ra = {x["id"]: x["role"] for x in ma["boxes"]}
                rb = {x["id"]: x["role"] for x in mb["boxes"]}
                units = [["yes" if r in ra.values() else "no", "yes" if r in rb.values() else "no"]
                         for r in ontology().roles]
                agree.append((doc, a, b, f1(len(p), len(ma["boxes"]), len(mb["boxes"])),
                              sum(ra[x] == rb[y] for x, (y, _) in p.items()), len(p), kalpha(units)))
    if agree:
        out += ["## Agreement between runs of the same article", "",
                "Same matcher, run against run. A repeat run (`_r1`) asks the same model again; "
                "two model names compare models.", "",
                "| article | run A | run B | boxes matched F1 | same role | role presence α |",
                "|---|---|---|---|---|---|"]
        for doc, a, b, fb, same, n, al in agree:
            out.append(f"| {doc} | {a} | {b} | {fb:.2f} | {same}/{n} | "
                       f"{'-' if al is None else f'{al:.2f}'} |")
    path("experiments").mkdir(parents=True, exist_ok=True)
    f = path("experiments") / "evaluation.md"
    f.write_text("\n".join(out) + "\n", encoding="utf-8")
    return f
