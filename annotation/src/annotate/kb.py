"""Step 6: into the knowledge base. Flattens annotation.json into the team's tables, in the
same columns the hand-drawn maps produce, then runs the team's index and export scripts.

Idempotent: every model-annotated article (family `llm`) is removed and written again from
its annotation.json, so this can run any time. Run it again after parse_maps.py or
link_passages.py, which rebuild their tables from the hand-drawn maps only.
Articles that have a hand-drawn map never enter: the hand-drawn map is the record for them.
"""
from __future__ import annotations

import json
import subprocess
import sys

from .config import hand_docs, model_slug, ontology, path, read_csv, settings, write_csv

FAMILY = "llm"
EXPORTS = ["graph_indices.py", "export_obsidian.py", "export_canvas.py", "export_obsidian.py"]


def default_run() -> str:
    return model_slug(settings()["models"]["boxes"])


def annotations(hand: bool = False) -> list[dict]:
    """The KB run of every article without a hand-drawn map (with one, when hand=True)."""
    out = []
    for d in sorted(p for p in path("articles").iterdir() if p.is_dir()):
        f = d / default_run() / "annotation.json"
        if (d.name in hand_docs()) == hand and f.exists():
            out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def _outlet(art: dict) -> str:
    short = "".join(w[0] for w in art["publisher"].split() if w[:1].isupper())
    return " ".join(x for x in (short, art["series"]) if x)


def rows_for(ann: dict) -> dict[str, list[dict]]:
    ont, art = ontology(), ann["article"]
    doc, date = art["id"], art["published_date"]
    legacy = {n["id"]: n["legacy_id"] for n in ann["nodes"]}
    pushes_back = {r for r, v in ont.relations.items() if v["sign"] < 0}
    facet_model = next(r["model"] for r in ann["annotation"]["runs"] if r["stage"] == "facets")
    t = {"documents": [{"id": doc, "date": date, "family": FAMILY, "title": art["title"],
                        "author": ", ".join(art["authors"]), "outlet": _outlet(art),
                        "url": art["url"], "genre": "", "shape": "", "topics": ""}],
         "nodes": [], "edges": [], "node_facets": [], "node_passages": []}
    for n in ann["nodes"]:
        c, at = n["content"], n["attributes"]
        t["nodes"].append({"doc": doc, "family": FAMILY, "date": date, "node_id": n["legacy_id"],
                           "type": n["role"], "level": n["level"],
                           "header": ont.roles[n["role"]]["name"], "concept": "",
                           "mechanism_kind": at.get("kind", ""),
                           "implicit_only": "0" if c["explicit"] else "1",
                           "type_source": FAMILY, "claim_type": at.get("claim_type", ""),
                           "text": c["text"]})
        for f, terms in n["facets"].items():
            for x in terms:
                t["node_facets"].append({"doc": doc, "node_id": n["legacy_id"], "facet": f,
                                         "value": x["term"], "role": x.get("geo_role", ""),
                                         "source": x["assignment_source"],
                                         "model": facet_model
                                         if x["assignment_source"] == "llm" else ""})
        if not n["source"]["passages"]:              # the linker's convention for "no passage"
            t["node_passages"].append({"doc": doc, "node_id": n["legacy_id"], "type": n["role"],
                                       "para": "", "grade": "none", "relation": "none", "score": "",
                                       "margin": "", "anchors": "",
                                       "page_sha256": art["source_text"]["content_hash"]})
        for p in n["source"]["passages"]:
            t["node_passages"].append({"doc": doc, "node_id": n["legacy_id"], "type": n["role"],
                                       "para": p["paragraph_id"], "grade": FAMILY,
                                       "relation": p["relation"], "score": "", "margin": "",
                                       "anchors": "excerpt" if p["anchor_grade"] == "excerpt" else "",
                                       "page_sha256": art["source_text"]["content_hash"]})
    for e in ann["edges"]:
        t["edges"].append({"doc": doc, "family": FAMILY, "date": date, "from": legacy[e["from"]],
                           "to": legacy[e["to"]], "type": e["relation"],
                           "polarity": "pushes_back" if e["relation"] in pushes_back else "forward",
                           "raw": "", "relation_source": FAMILY, "relation_level": "",
                           "relation_purity": "", "needs_review": "1" if e["review"]["reasons"] else "0"})
    return t


def graph_entry(ann: dict, t: dict) -> dict:
    """The document as parse_maps.py writes it into data/graph.json."""
    levels = {lv: [] for lv in ontology().levels}
    for n in t["nodes"]:
        levels[n["level"]].append({"id": n["node_id"], "type": n["type"], "level": n["level"],
                                   "header": n["header"], "text": n["text"], "byline": "",
                                   "class": "", "type_source": FAMILY, "claim_type": n["claim_type"],
                                   "mechanism_kind": n["mechanism_kind"],
                                   "implicit_only": n["implicit_only"] == "1", "concept": ""})
    d = t["documents"][0]
    return {"doc": d["id"], "file": f"articles/{d['id']}/{default_run()}/annotation.json",
            "family": FAMILY, "date": d["date"],
            "meta": {k: d[k] for k in ("title", "author", "outlet", "url", "topics", "genre", "shape")},
            "levels": {k: v for k, v in levels.items() if v},
            "edges": [{"from": e["from"], "to": e["to"], "type": e["type"], "raw": "",
                       "polarity": e["polarity"], "relation_source": FAMILY,
                       "needs_review": e["needs_review"] == "1"} for e in t["edges"]],
            "counts": {"nodes": len(t["nodes"]), "edges": len(t["edges"]), "dropped_nodes": 0}}


def into_kb(export: bool = True) -> dict:
    data = path("kb") / "data"
    anns = annotations()
    tables = {name: read_csv(data / f"{name}.csv")
              for name in ("documents", "nodes", "edges", "node_facets", "node_passages")}
    fields = {name: list(rows[0].keys()) for name, rows in tables.items() if rows}
    model_docs = {r["id"] for r in tables["documents"] if r["family"] == FAMILY}
    model_docs |= {a["article"]["id"] for a in anns}
    key = {"documents": "id"}
    for name, rows in tables.items():
        tables[name] = [r for r in rows if r[key.get(name, "doc")] not in model_docs]
    # An article added here and later drawn by hand: parse_maps.py has replaced its nodes and
    # links, but the facet and passage rows written here would stay and pass for hand data.
    for ann in annotations(hand=True):
        mine = rows_for(ann)
        for name in ("node_facets", "node_passages"):
            ours = {tuple(sorted(r.items())) for r in mine[name]}
            tables[name] = [r for r in tables[name] if tuple(sorted(r.items())) not in ours
                            and not (r["doc"] == ann["article"]["id"] and r.get("grade") == FAMILY)]
    graph = json.loads((data / "graph.json").read_text(encoding="utf-8"))
    graph["documents"] = [d for d in graph["documents"] if d["doc"] not in model_docs]
    for ann in anns:
        t = rows_for(ann)
        for name in tables:
            tables[name] += t[name]
        graph["documents"].append(graph_entry(ann, t))
    for name, rows in tables.items():
        if rows or name in fields:
            write_csv(data / f"{name}.csv", rows, fields.get(name) or list(rows[0].keys()))
    (data / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    if export:
        # export_canvas rewrites every article's map but never deletes one, so a removed
        # article would leave its old map behind; start from an empty canvas folder
        for f in (path("kb") / "obsidian" / "canvas").glob("*.canvas"):
            f.unlink()
        for s in EXPORTS:
            subprocess.run([sys.executable, f"scripts/{s}"], cwd=path("kb"), check=True,
                           stdout=subprocess.DEVNULL)
    return {"articles": [a["article"]["id"] for a in anns],
            "nodes": sum(len(a["nodes"]) for a in anns), "edges": sum(len(a["edges"]) for a in anns)}
