"""The workflow, as a LangGraph state graph.

  fetch -> boxes -> links -> facets -> save -> kb -> evaluate
             ^  |     ^  |     ^  |
             +--+     +--+     +--+   one model call per visit; the conditional edge sends the
                                     step back to itself for a fix round or the targeted re-ask

Every node writes its output file in the run folder; the graph state only carries what the
next node needs. A checkpoint after every node (SQLite, in runs/) lets a stopped run resume
at the step that was running, and the response cache makes repeating a finished step free.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from . import boxes as B
from . import facets as F
from . import links as L
from . import record
from .article import load
from .config import hand_docs, model_slug, ontology, path, read_csv, settings
from .kb import into_kb
from .llm import Gateway


class StepFailed(RuntimeError):
    pass


class State(TypedDict, total=False):
    doc: str
    url: str
    run: str
    models: dict          # step -> model
    repeat: int
    oracle: bool          # links and facets on the hand-drawn boxes (evaluation only)
    official: bool        # the configured models, first run, not oracle: the version kept in annotation/
    boxes: dict           # per model step: msgs, fixes, reasks, next
    links: dict
    facets: dict


def run_dir(s: State) -> Path:
    """Official runs live in annotation/articles; experiments (another model, a repeat, an
    oracle run) live in paths.experiments, outside annotation/."""
    return path("articles" if s.get("official") else "experiments") / s["doc"] / s["run"]


def _article(s: State):
    return load(s["doc"], s.get("url"))


def _read(s: State, name: str):
    return json.loads((run_dir(s) / name).read_text(encoding="utf-8"))


def _write(s: State, name: str, obj) -> None:
    d = run_dir(s)
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def hand_boxes(doc: str) -> list[dict]:
    """A hand-drawn map's boxes in the shape the model steps produce (for oracle runs)."""
    out = []
    for n in read_csv(path("kb") / "data" / "nodes.csv"):
        if n["doc"] == doc:
            claim = f"{n['header']}: {n['text']}" if n["text"].strip() else n["header"]
            out.append({"id": n["node_id"], "role": n["type"], "level": n["level"],
                        "claim": " ".join(claim.split()), "excerpt": "", "excerpt_para": None,
                        "explicit": n["implicit_only"] != "1", "paragraphs": [], "reason": "",
                        "kind": n["mechanism_kind"] or "none", "claim_type": n["claim_type"] or "none"})
    return out


# --- nodes -------------------------------------------------------------------------------

def fetch(s: State) -> dict:
    a = _article(s)                                   # downloads with the team's extractor if needed
    return {"doc": a.doc, "url": a.url}


def _model_step(s: State, step: str, start, check, model_for, fix_message, reask_message, out_name):
    """One visit = one model call, then the step's checks decide: again, or done."""
    cfg = settings()
    st = dict(s.get(step) or {})
    if not st:
        st = {"msgs": start(), "fixes": 0, "reasks": 0}
    gw = Gateway(run_dir(s) / "calls.jsonl")
    text, rec = gw.ask(step=step, model=s["models"][step], messages=st["msgs"], schema=model_for(),
                       params=cfg["params"].get(step, {}), repeat=s.get("repeat", 0))
    r = check(text)
    result_key = {"boxes": "boxes", "links": "links", "facets": "rows"}[step]
    if rec.get("error"):
        r["fix"] = [rec["error"]] + r["fix"]
    if not text.strip():                               # nothing to answer: ask the same again
        if rec.get("finish") == "length":              # every token went to thinking; the same request ends the same way
            raise StepFailed(f"{step}: the model used all max_tokens before answering; raise max_tokens or "
                             f"lower reasoning_effort for this step in settings.yaml")
        if st["fixes"] >= cfg["retries"]["format"]:
            raise StepFailed(f"{step}: {rec.get('error')}; see {run_dir(s) / 'calls.jsonl'}")
        st["fixes"] += 1
        st["next"] = "again"
        return {step: st}
    st["msgs"] = st["msgs"] + [{"role": "assistant", "content": text}]
    if r["fix"] and st["fixes"] < cfg["retries"]["format"]:
        st["fixes"] += 1
        st["msgs"].append({"role": "user", "content": fix_message(r["fix"])})
        st["next"] = "again"
    elif r[result_key] is not None and r.get("gaps") and reask_message and st["reasks"] < cfg["retries"]["reask"]:
        st["reasks"] += 1
        st["msgs"].append({"role": "user", "content": reask_message(r["gaps"])})
        st["next"] = "again"
    else:
        if r[result_key] is None:
            raise StepFailed(f"{step}: no usable answer after {st['fixes']} fix rounds; "
                             f"see {run_dir(s) / 'calls.jsonl'}")
        review = r["review"] + [f"still wrong after {st['fixes']} fix rounds: {p}" for p in r["fix"]]
        _write(s, out_name, {"result": r[result_key], "review": review,
                             "gaps_left": r.get("gaps", []), "dropped": r.get("dropped", []),
                             "fix_rounds": st["fixes"], "reasks": st["reasks"]})
        st["next"] = "done"
    return {step: st}


def boxes_node(s: State) -> dict:
    if s.get("oracle"):
        _write(s, "boxes.json", {"result": hand_boxes(s["doc"]), "review": [], "gaps_left": [],
                                 "dropped": [], "fix_rounds": 0, "reasks": 0, "oracle": True})
        return {"boxes": {"next": "done"}}
    a, ont = _article(s), ontology()
    M = B.model_for(a, ont)
    return _model_step(s, "boxes", lambda: B.start(a, ont), lambda t: B.check(t, a, ont, M),
                       lambda: M, B.fix_message, B.reask_message, "boxes.json")


def links_node(s: State) -> dict:
    a, ont, bx = _article(s), ontology(), _read(s, "boxes.json")["result"]
    if not bx:
        raise StepFailed("links: there are no boxes to link")
    M = L.model_for(ont, bx)
    return _model_step(s, "links", lambda: L.start(a, ont, bx), lambda t: L.check(t, ont, bx, M),
                       lambda: M, L.fix_message, L.reask_message, "links.json")


def facets_node(s: State) -> dict:
    a, ont = _article(s), ontology()
    bx, lk = _read(s, "boxes.json")["result"], _read(s, "links.json")["result"]
    # a hand-drawn map (oracle run) can hold the parser's fallback role `counterpoint`
    nodes = F.kb_nodes(a.doc, bx, lambda r: ont.roles.get(r, {}).get("name", r))
    model = s["models"]["facets"]
    return _model_step(s, "facets", lambda: F.start(a, nodes), lambda t: F.check(t, a.doc, nodes, lk, model),
                       lambda: F.model_for(nodes), F.fix_message, None, "facets.json")


def save(s: State) -> dict:
    a = _article(s)
    bx, lk, fc = (_read(s, n) for n in ("boxes.json", "links.json", "facets.json"))
    review = {"boxes": bx["review"], "links": lk["review"], "facets": fc["review"]}
    stats = {}
    if not s.get("oracle"):
        stats, review["passages"] = record.compare_passages(bx["result"], record.second_opinion(a, bx["result"]))
    checks = [f"boxes: {len(bx['result'])}, fix rounds {bx['fix_rounds']}, re-asks {bx['reasks']}, "
              f"gaps left {bx['gaps_left'] or 'none'}",
              f"links: {len(lk['result'])}, fix rounds {lk['fix_rounds']}, re-asks {lk['reasks']}, "
              f"gaps left {lk['gaps_left'] or 'none'}, dropped {lk['dropped'] or 'none'}"]
    calls = [json.loads(x) for x in (run_dir(s) / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    calls = [c for c in calls if c.get("repeat", 0) == s.get("repeat", 0)]
    ann = record.build(a, s["run"], s["models"], settings()["params"], bx["result"], lk["result"],
                       fc["result"], stats, review, checks, calls)
    _write(s, "annotation.json", ann)
    md = record.review_md(a, s["run"], review)
    f = run_dir(s) / "review.md"
    if md:
        f.write_text(md, encoding="utf-8")
    elif f.exists():
        f.unlink()                                    # an earlier run's review no longer applies
    return {}


def kb_node(s: State) -> dict:
    if s["doc"] not in hand_docs() and s.get("official"):
        into_kb()
    return {}


def evaluate_node(s: State) -> dict:
    if s["doc"] in hand_docs():
        from .evaluate import evaluate_run
        evaluate_run(run_dir(s), s["doc"])
    return {}


def _again(step: str, nxt: str):
    return lambda s: step if s[step].get("next") == "again" else nxt


def graph(checkpointer=None):
    g = StateGraph(State)
    for name, fn in [("fetch", fetch), ("boxes", boxes_node), ("links", links_node),
                     ("facets", facets_node), ("save", save), ("kb", kb_node),
                     ("evaluate", evaluate_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "fetch")
    g.add_edge("fetch", "boxes")
    g.add_conditional_edges("boxes", _again("boxes", "links"), ["boxes", "links"])
    g.add_conditional_edges("links", _again("links", "facets"), ["links", "facets"])
    g.add_conditional_edges("facets", _again("facets", "save"), ["facets", "save"])
    g.add_edge("save", "kb")
    g.add_edge("kb", "evaluate")
    g.add_edge("evaluate", END)
    return g.compile(checkpointer=checkpointer)


def run(doc: str | None, url: str | None, model: str | None = None, repeat: int = 0,
        oracle: bool = False, tag: str | None = None) -> Path:
    """tag names a prompt or settings variant under test; a tagged run is always an experiment."""
    cfg = settings()
    models = {k: (model or cfg["models"][k]) for k in ("boxes", "links", "facets")}
    a = load(doc, url)                                # resolves the doc ID for a bare URL
    if oracle and a.doc not in hand_docs():
        raise StepFailed(f"--oracle needs a hand-drawn map, and {a.doc} has none")
    run_name = (model_slug(models["boxes"]) + (f"_{tag}" if tag else "") + ("_oracle" if oracle else "")
                + (f"_r{repeat}" if repeat else ""))
    official = models == {k: cfg["models"][k] for k in models} and not repeat and not oracle and not tag
    s: State = {"doc": a.doc, "url": a.url, "run": run_name, "models": models,
                "repeat": repeat, "oracle": oracle, "official": official,
                "boxes": {}, "links": {}, "facets": {}}   # a fresh run forgets the last one's turns
    path("runs").mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path("runs") / "checkpoints.sqlite")) as cp:
        app = graph(cp)
        conf = {"configurable": {"thread_id": f"{a.doc}/{run_name}"}, "recursion_limit": 40}
        resume = bool(app.get_state(conf).next)      # the process stopped mid-run (sleep, kill)
        if not resume and (run_dir(s) / "calls.jsonl").exists():
            (run_dir(s) / "calls.jsonl").unlink()   # the record of this run only
        try:
            app.invoke(None if resume else s, conf)
        finally:
            # A checkpoint is kept only while a run is cut off part-way (sleep, kill); a finished
            # or failed run needs none: the next run starts fresh and replays from the cache.
            cp.delete_thread(conf["configurable"]["thread_id"])
    return run_dir(s)
