"""Step 4: subject facets, with the team's labeller (kb/scripts/label_facets.py) unchanged in
substance: its rules, closed vocabulary, schema, validation and repairs. Only the call goes
through the model service in settings.yaml (src/annotate/llm.py) instead of the Anthropic SDK."""
from __future__ import annotations

import json

from .article import Article
from .config import kb_scripts


def _lf():
    kb_scripts()
    return __import__("label_facets")


def kb_nodes(doc: str, boxes: list[dict], name_of) -> list[dict]:
    """Boxes in the shape label_facets reads from data/nodes.csv."""
    return [{"doc": doc, "node_id": b["id"], "type": b["role"], "level": b["level"],
             "header": name_of(b["role"]), "text": b["claim"]} for b in boxes]


def start(a: Article, nodes: list[dict]) -> list[dict]:
    lf = _lf()
    meta = {"title": a.title, "author": ", ".join(a.authors),
            "outlet": " ".join(x for x in (a.publisher, a.series) if x), "date": a.date}
    return [{"role": "system", "content": lf.vocab_block(lf.load_facets())},
            {"role": "user", "content": lf.doc_block(a.doc, meta, nodes)}]


def model_for(nodes: list[dict]) -> dict:
    lf = _lf()
    return lf.build_schema(lf.load_facets(), [n["node_id"] for n in nodes])


def check(text: str, doc: str, nodes: list[dict], links: list[dict], model: str) -> dict:
    lf = _lf()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        return {"rows": None, "fix": [f"The answer is not valid JSON: {e}"], "gaps": [], "review": []}
    facets, issues = lf.load_facets(), []
    rows = lf.validate(doc, payload, nodes, facets, model, issues)
    rows += lf.inherit_variable(rows, nodes, facets, issues)
    edges = [{"doc": doc, "from": l["from"], "to": l["to"], "type": l["relation"]} for l in links]
    rows += lf.inherit_where(rows, issues, edges)
    lf.promote_orphan_counterparts(rows, issues)
    return {"rows": rows, "fix": [], "gaps": [], "review": [i.lstrip("- ") for i in issues]}


def fix_message(problems: list[str]) -> str:
    return "Your answer has these problems:\n" + "\n".join(f"- {p}" for p in problems) + \
        "\n\nReturn the complete answer again."

