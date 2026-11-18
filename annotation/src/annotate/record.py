"""Step 5: check and save. Puts the three answers together as one record (annotation.json, in
the annotation contract the team drafted), gets a second opinion on every box's paragraphs
from the team's passage linker, and writes review.md only if something needs a person."""
from __future__ import annotations

import contextlib
import csv
import io
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .article import Article
from .config import ROOT, kb_scripts, ontology, path


def second_opinion(a: Article, boxes: list[dict]) -> list[dict]:
    """Run kb/scripts/link_passages.py, unchanged, on this article's boxes only.

    Its inputs and outputs are module-level paths, so they are pointed at a scratch folder
    for the run; the team's data/ files are not touched."""
    lp = (kb_scripts(), __import__("link_passages"))[1]
    with tempfile.TemporaryDirectory(dir=path("kb") / "internal") as tmp:
        tmp = Path(tmp)
        nodes, urls = tmp / "nodes.csv", tmp / "urls.yaml"
        with nodes.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["doc", "node_id", "type", "header", "text"])
            w.writeheader()
            for b in boxes:
                w.writerow({"doc": a.doc, "node_id": b["id"], "type": b["role"],
                            "header": ontology().roles[b["role"]]["name"], "text": b["claim"]})
        urls.write_text(yaml.safe_dump({"urls": {a.doc: {"url": a.url}}}), encoding="utf-8")
        saved = (lp.NODES, lp.URL_MAP, lp.OUT_CSV, lp.OUT_MD, lp.REVIEW, sys.argv)
        lp.NODES, lp.URL_MAP, lp.OUT_CSV, lp.OUT_MD = nodes, urls, tmp / "out.csv", tmp / "out.md"
        lp.REVIEW = tmp / "no_review.yaml"     # hand verdicts are about the hand boxes, not ours
        sys.argv = ["link_passages.py", "--docs", a.doc]
        try:
            with contextlib.redirect_stdout(io.StringIO()):     # its progress report
                lp.main()
        finally:
            lp.NODES, lp.URL_MAP, lp.OUT_CSV, lp.OUT_MD, lp.REVIEW, sys.argv = saved
        with (tmp / "out.csv").open(encoding="utf-8") as fh:
            return list(csv.DictReader(fh))


def compare_passages(boxes: list[dict], rows: list[dict]) -> tuple[dict, list[str]]:
    """Agreement between the model's citations and the linker's. Only an `anchored` link
    (a distinctive figure or name the box and paragraph share) the model did not cite is
    worth a person's time; tf-idf candidates are weak by design."""
    by_box = defaultdict(list)
    for r in rows:
        if r["grade"] != "none":
            by_box[r["node_id"]].append(r)
    review, stats = [], {"anchored": 0, "anchored_cited": 0, "candidate": 0, "candidate_cited": 0}
    for b in boxes:
        cited = {f"p{k}" for k in b["paragraphs"]}
        for r in by_box.get(b["id"], []):
            g = r["grade"]
            stats[g] = stats.get(g, 0) + 1
            if r["para"] in cited:
                stats[f"{g}_cited"] = stats.get(f"{g}_cited", 0) + 1
            elif g == "anchored":
                review.append(f"`{b['id']}`: the team's passage linker anchors it to {r['para']} "
                              f"(shared: {r['anchors']}), which the box does not cite")
    return stats, review


def _git_version() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "config"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return out + ("+uncommitted" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return ""


def build(a: Article, run: str, models: dict, params: dict, boxes: list[dict], links: list[dict],
          facet_rows: list[dict], passage_stats: dict, review: dict[str, list[str]],
          checks: list[str], calls: list[dict]) -> dict:
    ont = ontology()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    nid = {b["id"]: f"n{i:03d}" for i, b in enumerate(boxes, 1)}
    flagged = defaultdict(list)
    for step, items in review.items():
        for it in items:
            # a facet issue starts with `doc#ID` and concerns that box only
            first = it.split("`")[1] if it.startswith("`") else ""
            for b in boxes:
                hit = (first.endswith(f"#{b['id']}") if step == "facets"
                       else f"`{b['id']}`" in it)
                if hit:
                    flagged[b["id"]].append(f"{step}: {it}")
    facets = defaultdict(lambda: defaultdict(list))
    for r in facet_rows:
        t = {"term": r["value"], "assignment_source": r["source"], "run_id": f"{run}_facets"}
        if r["role"]:
            t["geo_role"] = r["role"]
        facets[r["node_id"]][r["facet"]].append(t)
    nodes = []
    for b in boxes:
        passages = [{"paragraph_id": f"p{k}", "relation": passage_relation(b, k),
                     "link_method": "llm_citation",
                     "anchor_grade": "excerpt" if k == b["excerpt_para"] else "cited",
                     "review_status": "pending",
                     "source_excerpt": b["excerpt"] if k == b["excerpt_para"] else None}
                    for k in b["paragraphs"]]
        attrs = {a_: b[a_] for a_ in ont.attributes if b.get(a_, "none") != "none"}
        nodes.append({
            "id": nid[b["id"]], "legacy_id": b["id"], "role": b["role"], "level": b["level"],
            "content": {"text": b["claim"], "label": None, "explicit": b["explicit"],
                        "reason": b["reason"]},
            "source": {"passages": passages},
            "facets": {f: facets[b["id"]].get(f, [])
                       for f in ("variable", "country", "bloc", "instrument", "data_basis")},
            "attributes": attrs,
            "provenance": {"method": "llm", "run_id": f"{run}_boxes"},
            "review": {"status": "pending", "reasons": flagged.get(b["id"], [])},
        })
    edges = [{"id": f"e{i:03d}", "from": nid[l["from"]], "to": nid[l["to"]],
              "relation": l["relation"], "sign": l["sign"],
              "provenance": {"method": "llm", "run_id": f"{run}_links"},
              "review": {"status": "pending",
                         "reasons": [x for x in review.get("links", [])
                                     if f"`{l['from']}`" in x and f"`{l['to']}`" in x]}}
             for i, l in enumerate(links, 1)]
    runs = []
    for stage in ("boxes", "links", "facets"):
        cs = [c for c in calls if c["step"] == stage]
        runs.append({"run_id": f"{run}_{stage}", "stage": stage, "method": "llm",
                     "model": models[stage], "parameters": params.get(stage, {}),
                     "timestamp": cs[-1]["time"] if cs else None, "calls": len({c["key"] for c in cs}),
                     "cost_usd": round(sum({c["key"]: c.get("cost_usd") or 0  # each request once
                                            for c in cs}.values()), 5)})
    q = next((b["claim"] for b in boxes if b["role"] == "question"), None)
    k = next((b["claim"] for b in boxes if b["role"] == "main_claim"), None)
    items = [f"{s}: {x}" for s, xs in review.items() for x in xs]
    fy = yaml.safe_load((kb_scripts() / "facets.yaml").read_text(encoding="utf-8"))
    return {
        "schema_version": "0.1-draft",
        "article": {"id": a.doc, "title": a.title, "authors": a.authors,
                    "published_date": a.date, "url": a.url, "publisher": a.publisher,
                    "series": a.series,
                    "source_text": {"path": a.file.relative_to(ROOT).as_posix() if a.file else None,
                                    "paragraph_count": len(a.paras), "content_hash": a.body_sha},
                    "references": a.references, "metadata_extension": {}},
        "annotation": {"annotated_at": now,
                       "ontology": {"id": ont.spec["id"], "version": ont.spec["version"]},
                       "facets_version": fy.get("version"), "pipeline_version": _git_version(),
                       "status": "needs_review" if items else "draft", "runs": runs},
        "summary": {"central_question": q, "main_thesis": k, "argument_summary": None},
        "nodes": nodes,
        "edges": edges,
        "validation": {"status": "needs_review" if items else "passed",
                       "checks": checks + [f"passage linker agreement: {passage_stats}"],
                       "review_items": items},
        "extensions": {},
    }


def passage_relation(b: dict, k: int) -> str:
    """The same three relations the team's linker uses."""
    if b["role"] == "hidden_assumption":
        return "presupposes"
    return "states" if k == b["excerpt_para"] else "abstracts"


def review_md(a: Article, run: str, review: dict[str, list[str]]) -> str | None:
    if not any(review.values()):
        return None
    out = [f"# Review: {a.title}", "", f"`{a.doc}`, run `{run}`. Each line needs a person's look;",
           "nothing here was changed automatically.", ""]
    for step, items in review.items():
        if items:
            out += [f"## {step} ({len(items)})", ""] + [f"- {x}" for x in items] + [""]
    return "\n".join(out)
