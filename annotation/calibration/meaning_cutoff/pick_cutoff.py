"""Find the meaning check's cut-off (settings.yaml `meaning.threshold`) from labelled pairs.

Run from annotation/ (needs `pip install -e ".[meaning]"`):
    python calibration/meaning_cutoff/pick_cutoff.py                   # AI raters' majority labels
    python calibration/meaning_cutoff/pick_cutoff.py hand_labels.csv   # once a person has filled it in

Each pair is scored with the scorer the evaluation itself uses (annotate.evaluate.similarity).
Every cut from 0.00 to 1.00 is tried, and the best is the one that separates "same" from
"different" best: the average of the share of "same" pairs at or above the cut and the share
of "different" pairs below it. Pairs labelled "unsure" are left out.
"""
import csv
import json
import sys
from pathlib import Path

from annotate.config import settings
from annotate.evaluate import similarity

HERE = Path(__file__).parent


def read_labels(name: str) -> tuple[dict, str]:
    path = Path(name) if Path(name).exists() else HERE / name
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    col = "label" if "label" in rows[0] else "majority"
    labels = {r["pair_id"]: r[col].strip().lower() for r in rows}
    bad = [k for k, v in labels.items() if v not in ("same", "different", "unsure")]
    if bad:
        more = f" and {len(bad) - 5} more" if len(bad) > 5 else ""
        sys.exit(f"{path.name}: write same, different or unsure in the {col} column "
                 f"({len(bad)} pairs still empty or unclear: {', '.join(bad[:5])}{more})")
    return labels, f"{path.name}, column {col}"


def share(scores: list[float], cut: float) -> float:
    return sum(s >= cut for s in scores) / len(scores) if scores else 0.0


pairs = json.load(open(HERE / "pairs.json", encoding="utf-8"))
labels, source = read_labels(sys.argv[1] if len(sys.argv) > 1 else "ai_labels.csv")

lab = pairs["labelled_pairs"]
scored = similarity([(p["hand_step"], p["model_step"]) for p in lab])
if scored is None:
    sys.exit('the scorer is not available: run `pip install -e ".[meaning]"` and check settings.yaml `meaning`')
score = dict(zip((p["pair_id"] for p in lab), scored))
same = [score[k] for k, v in labels.items() if v == "same"]
diff = [score[k] for k, v in labels.items() if v == "different"]
unsure = sum(v == "unsure" for v in labels.values())
if not same or not diff:
    sys.exit("need at least one pair labelled same and one labelled different")
other = similarity([(p["step_1"], p["step_2"]) for p in pairs["same_map_different_steps"]])
opposite = similarity([(p["main_claim"], p["opposing_view"]) for p in pairs["main_claim_vs_opposing_view"]])

cuts = [round(i / 100, 2) for i in range(101)]
fit = {c: (share(same, c) + 1 - share(diff, c)) / 2 for c in cuts}
best = max(fit.values())
tied = [c for c in cuts if fit[c] == best]
current = settings()["meaning"]["threshold"]

print(f"labels: {source}: same {len(same)}, different {len(diff)}, unsure {unsure} (left out)")
print(f"best cut: {tied[0]:.2f}" + (f" to {tied[-1]:.2f}" if len(tied) > 1 else "")
      + f" (separates same from different {best:.0%} of the time)")
print(f"current setting: {current:.2f}, " + ("inside the best range" if current in tied else
                                            f"OUTSIDE the best range: consider changing settings.yaml `meaning.threshold`"))
for cut in sorted({current, tied[0]}):
    print(f"\nat {cut:.2f}, counted as the same meaning:")
    print(f"  pairs labelled same                       {sum(s >= cut for s in same):3d}/{len(same):<3d} = {share(same, cut):.0%}")
    print(f"  pairs labelled different                  {sum(s >= cut for s in diff):3d}/{len(diff):<3d} = {share(diff, cut):.0%}")
    print(f"  two different steps of one hand map       {sum(s >= cut for s in other):3d}/{len(other):<3d} = {share(other, cut):.0%}")
    print(f"  main claim vs opposing view (same map)    {sum(s >= cut for s in opposite):3d}/{len(opposite):<3d} = {share(opposite, cut):.0%}")
