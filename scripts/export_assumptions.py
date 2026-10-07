#!/usr/bin/env python3
"""Dump every assumption-level node, full text, nothing truncated.

    python scripts/export_assumptions.py

Writes:
    data/assumptions.csv    one row per assumption, opens in Excel
    data/assumptions.json   same, with what each assumption feeds nested

Level 1 and 1b only - stated and hidden assumptions, revised priors,
accounting identities, source-credibility priors, scope choices, benchmarks.
Each row carries what the assumption points at, since an assumption is only
interesting in terms of what it lets the author conclude.

For every node rather than just assumptions, use data/nodes.csv.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "graph.json"
DATA = ROOT / "data"

ORDER = ["hidden_assumption", "stated_assumption", "revised_prior",
         "accounting_identity", "source_credibility", "scope_choice", "benchmark"]


def main() -> None:
    if not GRAPH.exists():
        raise SystemExit("data/graph.json missing - run scripts/parse_maps.py first")
    docs = json.loads(GRAPH.read_text(encoding="utf-8"))["documents"]

    rows = []
    for d in docs:
        nodes = {n["id"]: n for ns in d["levels"].values() for n in ns}
        for n in nodes.values():
            if not n["level"].startswith("L1"):
                continue
            targets = []
            for e in d["edges"]:
                if e["from"] != n["id"]:
                    continue
                t = nodes.get(e["to"])
                if not t:
                    continue
                targets.append({
                    "edge": e["type"] or "unresolved",
                    "edge_as_drawn": e["raw"],
                    "target_id": t["id"],
                    "target_type": t["type"],
                    "target_level": t["level"],
                    "target_text": " ".join((t["text"] or t["header"]).split()),
                })
            rows.append({
                "date": d["date"],
                "year": d["date"][:4],
                "family": d["family"],
                "doc": d["doc"],
                "article": d["meta"]["title"],
                "url": d["meta"].get("url", ""),
                "node_id": n["id"],
                "type": n["type"],
                "header": n["header"],
                "text": " ".join((n["text"] or "").split()),
                # header and body joined, for reading the assumption in one cell
                "full": " ".join(
                    f'{n["header"]} - {n["text"]}'.strip(" -").split()),
                "concept": n.get("concept", ""),
                "implicit_only": int(n["implicit_only"]),
                "type_source": n["type_source"],
                "n_targets": len(targets),
                "targets": targets,
            })

    rows.sort(key=lambda r: (ORDER.index(r["type"]) if r["type"] in ORDER else 99,
                             r["date"], r["doc"]))

    cols = ["date", "year", "family", "type", "header", "text", "full", "concept",
            "doc", "node_id", "article", "url", "implicit_only", "type_source",
            "n_targets", "leads_to"]
    with (DATA / "assumptions.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "leads_to": " | ".join(
                f'{t["edge"]} -> {t["target_id"]} ({t["target_type"]}): {t["target_text"]}'
                for t in r["targets"])})

    (DATA / "assumptions.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    print(f"{len(rows)} assumptions -> data/assumptions.csv, data/assumptions.json")
    for t in ORDER:
        if by_type.get(t):
            print(f"  {by_type[t]:3}  {t}")
    orphan = sum(1 for r in rows if r["n_targets"] == 0)
    if orphan:
        print(f"  {orphan} of {len(rows)} lead nowhere "
              f"(drawn with layout-only links, so no argument edge was recorded)")


if __name__ == "__main__":
    main()
