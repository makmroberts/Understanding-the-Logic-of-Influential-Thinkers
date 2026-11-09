"""Settings, the ontology and the corpus profile. Every path comes from settings.yaml."""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]          # the annotation/ folder


@lru_cache
def settings() -> dict:
    return yaml.safe_load((ROOT / "settings.yaml").read_text(encoding="utf-8"))


def path(key: str) -> Path:
    return ROOT / settings()["paths"][key]


def examples() -> list[str]:
    """The hand-drawn maps used as worked examples (never scored)."""
    return list(settings()["example_articles"])


def model_slug(model: str) -> str:
    """A model name usable as a folder name: 'anthropic/claude-sonnet-5.5' -> 'claude-sonnet-5.5'."""
    return model.split("/")[-1]


def kb_scripts() -> Path:
    """The team's scripts, importable as modules (link_passages, label_facets ...)."""
    p = path("kb") / "scripts"
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    return p


def read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(p: Path, rows: list[dict], fields: list[str]) -> None:
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


class Ontology:
    """roles, relations, level order and ID rules from config/ontology.yaml."""

    def __init__(self, spec: dict):
        self.spec = spec
        self.levels: list[str] = spec["levels"]
        self.roles: dict = spec["roles"]
        self.relations: dict = spec["relations"]
        self.linked_exempt = set(spec.get("linked_exempt") or [])
        self.rules: list[str] = spec["granularity"]["rules"]
        # attribute name -> {role: allowed values}
        self.attributes: dict[str, dict[str, list[str]]] = defaultdict(dict)
        for role, r in self.roles.items():
            for a, vals in (r.get("attributes") or {}).items():
                self.attributes[a][role] = list(vals)

    def level(self, role: str) -> str:
        return self.roles[role]["level"]

    def assign_ids(self, roles: list[str]) -> list[str]:
        """Slot IDs in the template's style: fixed IDs (K, then K2), group counters (P1, P2)."""
        order = {r: i for i, r in enumerate(self.roles)}
        ranked = sorted(range(len(roles)), key=lambda i: (order[roles[i]], i))
        used: Counter = Counter()
        ids = [""] * len(roles)
        for i in ranked:
            r = self.roles[roles[i]]
            stem = r.get("id") or r["group"]
            used[stem] += 1
            n = used[stem]
            ids[i] = f"{stem}{n}" if "group" in r else (stem if n == 1 else f"{stem}{n}")
        return ids


@lru_cache
def ontology() -> Ontology:
    return Ontology(yaml.safe_load(path("ontology").read_text(encoding="utf-8")))


def hand_docs() -> set[str]:
    """Articles that have a hand-drawn map. Their model output is for evaluation only."""
    # the same rule parse_maps.py uses to skip the templates
    return {p.stem for p in (path("kb") / "mermaid_code").glob("*.mmd")
            if not any(t in p.stem for t in ("template", "edge_types"))}


@lru_cache
def profile() -> dict:
    """What a hand-drawn map looks like, from the maps in kb/data, without the held-out ones."""
    s = settings()
    skip = set(s.get("held_out") or [])
    nodes = [n for n in read_csv(path("kb") / "data" / "nodes.csv")
             if n["doc"] in hand_docs() and n["doc"] not in skip]
    per_doc: dict[str, Counter] = defaultdict(Counter)
    for n in nodes:
        per_doc[n["doc"]][n["type"]] += 1
    sizes = [sum(c.values()) for c in per_doc.values()]
    share = Counter(t for c in per_doc.values() for t in c)
    n_docs = len(per_doc)
    expected = sorted(t for t, k in share.items()
                      if k / n_docs >= s["completeness"]["expect_share"]
                      and t in ontology().roles)
    return {"articles": n_docs, "min_boxes": min(sizes), "max_boxes": max(sizes),
            "mean_boxes": round(sum(sizes) / n_docs, 1), "expected_roles": expected,
            "role_share": {t: round(k / n_docs, 2) for t, k in share.most_common()}}
