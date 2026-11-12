"""Load the source records and the model's argument maps into the local Neo4j, as one graph.

Reads only the new pipeline's outputs, never the hand-drawn Mermaid maps:

    data/articles/<id>.json                       metadata, paragraphs, references, entities
    internal/extracted/*.md                        paragraph text (local; not committed)
    annotation/articles/<doc>/<model>/annotation.json   claims, passages, links, facets
    scripts/schema_map.yaml `role_families`        the role hierarchy (vocabulary only)

The database is a view of those files and is rebuilt on every run: **everything in it is
deleted first**, including anything `export_neo4j.py`'s legacy `load.cypher` put there.

    (:Person|:Organization)-[:AUTHORED|:PUBLISHED]->(:Article)
    (:Article)-[:HAS_PARAGRAPH]->(:Paragraph)-[:LINKS_TO]->(:Source)-[:IS_ARTICLE]->(:Article)
    (:Article)-[:HAS_CLAIM]->(:Claim)-[:CITES]->(:Paragraph)
    (:Claim)-[:SUPPORTS|:FRAMES|:QUALIFIED_BY|... {relation, sign}]->(:Claim)
    (:Claim)-[:TAGGED {facet, geo_role}]->(:Term)

A claim has two labels, `:Claim` and its role type (`:Mechanism`, `:MainClaim`, ...), and
carries the upper levels of the role hierarchy as `toulmin` and `oper`, so a rule can key
on any level. Each argumentative relation is its own relationship type, so a chain of any
length is one pattern: `MATCH p = (x:Claim)-[*1..6]->(:MainClaim) RETURN p`. Relations
point from the supporting claim to the claim it bears on, as in the annotation JSON.

Every node has a `key`, unique within its label: an article's record ID, `<article>#p3`,
`<article>#n001`, `facet/term`, a normalized URL, or a name. Claims and paragraphs are keyed
by the record ID, not the knowledge-base doc key; the doc key is kept as `kb_doc`.

Usage (Neo4j from the repo's docker-compose.yml: `docker compose up -d`):

    python scripts/exporters/neo4j_graph.py              # rebuild, then compare counts with the files
    python scripts/exporters/neo4j_graph.py --dry-run    # build the batches, send nothing
    python scripts/exporters/neo4j_graph.py --check      # counts only
    python scripts/exporters/neo4j_graph.py --no-text    # leave paragraph text out

Talks to Neo4j's HTTP API, so it needs no driver: stdlib plus PyYAML.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.metadata import body_lines, links_and_plain, split_frontmatter

ROOT = Path(__file__).resolve().parent.parent.parent
RECORDS = ROOT / "data" / "articles"
ANNOTATIONS = ROOT / "annotation" / "articles"
SETTINGS = ROOT / "annotation" / "settings.yaml"
SCHEMA_MAP = ROOT / "scripts" / "schema_map.yaml"
FACETS = ("variable", "country", "bloc", "instrument", "data_basis")
LABELS = ("Article", "Person", "Organization", "Paragraph", "Source", "Claim", "Term")
FULLTEXT = {"claim_text": ("Claim", ["text", "reason"]), "paragraph_text": ("Paragraph", ["text"])}
BATCH = 500


# ---------------------------------------------------------------- reading the files

def official_model() -> str:
    """The folder name of the official run, e.g. `claude-opus-5.5`."""
    models = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))["models"]
    return models["boxes"].split("/")[-1]


def role_levels() -> dict[str, dict[str, str]]:
    """role -> {"toulmin": ..., "oper": ...}, from schema_map.yaml `role_families`."""
    fam = yaml.safe_load(SCHEMA_MAP.read_text(encoding="utf-8"))["role_families"]
    out: dict[str, dict[str, str]] = {}
    for level, groups in fam.items():
        for group, roles in groups.items():
            for role in roles:
                out.setdefault(role, {})[level] = group
    return out


def pascal(name: str) -> str:
    """evidence_data -> EvidenceData; the label convention export_neo4j.py already uses."""
    return "".join(p.capitalize() for p in re.split(r"[_\s]+", name) if p)


def identifier(name: str, what: str) -> str:
    """A label or relationship type goes into the Cypher text itself and cannot be a
    parameter, so one read from a data file must be a plain identifier or the load stops."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
        sys.exit(f"{what} {name!r} cannot be used as a Neo4j name; fix the source file")
    return name


def paragraph_text(record: dict) -> dict[str, str]:
    """Plain text of each paragraph, links reduced to their labels. {} if the text is missing."""
    path = ROOT / record["article"]["source_text"]["path"]
    if not path.exists():
        return {}
    body = split_frontmatter(path.read_text(encoding="utf-8"))[1]
    return {pid: links_and_plain(md)[0] for pid, md in body_lines(body)[0]}


def short(text: str, limit: int = 48) -> str:
    """The start of a claim, cut at a word, for a node caption."""
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def clean(props: dict) -> dict:
    """Drop nulls and empty lists: Neo4j stores neither."""
    return {k: v for k, v in props.items() if v is not None and v != []}


def build(with_text: bool = True) -> tuple[dict[str, list[dict]], dict[str, list[dict]], list[str]]:
    """(nodes by label, edges by type, warnings). Edges carry `from`/`to` keys and their labels."""
    nodes: dict[str, dict[str, dict]] = {label: {} for label in LABELS}
    edges: dict[str, list[dict]] = {}
    warnings: list[str] = []
    levels = role_levels()

    def node(label: str, key: str, /, **props) -> None:
        nodes[label].setdefault(key, clean({"key": key, **props}))

    def edge(kind: str, a: tuple[str, str], b: tuple[str, str], /, **props) -> None:
        edges.setdefault(kind, []).append({"from_label": a[0], "from": a[1],
                                           "to_label": b[0], "to": b[1], "props": clean(props)})

    records, same = {}, set()
    for path in sorted(RECORDS.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        records[rec["article"]["id"]] = rec

    for aid, rec in records.items():
        a, ext = rec["article"], rec["article"].get("metadata_extension", {})
        node("Article", aid, title=a.get("title"), url=a.get("url"),
             published_date=a.get("published_date"), publisher=a.get("publisher"),
             series=a.get("series") or None, subtitle=ext.get("subtitle"),
             language=ext.get("language"), word_count=ext.get("word_count"),
             revision=a["source_text"].get("revision"),
             content_hash=a["source_text"].get("content_hash"),
             paragraph_count=a["source_text"].get("paragraph_count"))
        for ent in rec.get("extensions", {}).get("entities", []):
            label = {"person": "Person", "organization": "Organization"}.get(ent["type"])
            if not label:
                warnings.append(f"{aid}: entity type {ent['type']!r} not loaded")
                continue
            node(label, ent["name"], name=ent["name"], entity_id=ent.get("entity_id"))
            kind = {"author": "AUTHORED", "publisher": "PUBLISHED"}.get(ent["role"], "MENTIONED_IN")
            edge(kind, (label, ent["name"]), ("Article", aid), role=ent["role"])

        text = paragraph_text(rec) if with_text else {}
        if with_text and not text:
            warnings.append(f"{aid}: no text at {a['source_text']['path']}; paragraphs loaded without it")
        for i, p in enumerate(rec["paragraphs"], 1):
            pkey = f"{aid}#{p['id']}"
            node("Paragraph", pkey, article=aid, paragraph_id=p["id"], position=i,
                 sha256=p["sha256"], n_chars=p["n_chars"], text=text.get(p["id"]))
            edge("HAS_PARAGRAPH", ("Article", aid), ("Paragraph", pkey))

        for r in a.get("references", []):
            node("Source", r["source_key"], host=r.get("host"))
            edge("LINKS_TO", ("Paragraph", f"{aid}#{r['paragraph_id']}"), ("Source", r["source_key"]),
                 ref_id=r["id"], label=r.get("label"), href=r.get("href"), kind=r.get("kind"),
                 placement=r.get("placement"), char_start=r.get("char_start"),
                 char_end=r.get("char_end"))
            target = r.get("target_article_id")
            if target and target in records and (r["source_key"], target) not in same:
                same.add((r["source_key"], target))        # one edge per source, however often cited
                edge("IS_ARTICLE", ("Source", r["source_key"]), ("Article", target))

    model = official_model()
    for path in sorted(ANNOTATIONS.glob(f"*/{model}/annotation.json")):
        ann = json.loads(path.read_text(encoding="utf-8"))
        doc = ann["article"]["id"]
        aid = ann["article"].get("metadata_extension", {}).get("source_record")
        if aid not in records:
            warnings.append(f"{doc}: no metadata record {aid!r}; annotation skipped")
            continue
        nodes["Article"][aid]["kb_doc"] = doc
        paras = {p["id"]: p["sha256"] for p in records[aid]["paragraphs"]}
        status = ann["annotation"]["status"]
        for n in ann["nodes"]:
            ckey = f"{aid}#{n['id']}"
            c = n["content"]
            if n["role"] not in levels:
                warnings.append(f"{doc}#{n['id']}: role {n['role']!r} has no family in schema_map.yaml")
            node("Claim", ckey, article=aid, kb_doc=doc, node_id=n["id"],
                 legacy_id=n.get("legacy_id"), role=n["role"], level=n.get("level"),
                 toulmin=levels.get(n["role"], {}).get("toulmin"),
                 oper=levels.get(n["role"], {}).get("oper"),
                 text=c["text"], label=c.get("label"), explicit=c.get("explicit"),
                 reason=c.get("reason"), method=n["provenance"]["method"],
                 run_id=n["provenance"]["run_id"], review_status=n["review"]["status"],
                 review_reasons=n["review"]["reasons"], annotation_status=status,
                 **{f"attr_{k}": v for k, v in n.get("attributes", {}).items()})
            edge("HAS_CLAIM", ("Article", aid), ("Claim", ckey))
            for ps in n["source"]["passages"]:
                if ps["paragraph_id"] not in paras:
                    warnings.append(f"{doc}#{n['id']}: cites {ps['paragraph_id']}, not in the record")
                    continue
                # Neo4j stores no list of maps, so a span list becomes two parallel lists,
                # plus the citation written out: <article>#p22[0:71]
                spans = ps.get("source_spans") or []
                if ps.get("source_excerpt") and not spans:
                    warnings.append(f"{doc}#{n['id']}: excerpt in {ps['paragraph_id']} has no span")
                # the paragraph as it was annotated, against the paragraph as the record has it now
                pinned = ps.get("paragraph_sha256")
                changed = bool(pinned) and pinned != paras[ps["paragraph_id"]]
                if changed:
                    warnings.append(f"{doc}#{n['id']}: {ps['paragraph_id']} changed since it was "
                                    "annotated; the citation needs review")
                edge("CITES", ("Claim", ckey), ("Paragraph", f"{aid}#{ps['paragraph_id']}"),
                     relation=ps["relation"], link_method=ps["link_method"],
                     anchor_grade=ps["anchor_grade"], review_status=ps["review_status"],
                     source_excerpt=ps.get("source_excerpt"),
                     paragraph_sha256=pinned, source_changed=changed,
                     span_starts=[s["char_start"] for s in spans],
                     span_ends=[s["char_end"] for s in spans],
                     citation=(f"{aid}#{ps['paragraph_id']}"
                               + "".join(f"[{s['char_start']}:{s['char_end']}]" for s in spans)))
            for facet in FACETS:
                for t in n["facets"].get(facet, []):
                    tkey = f"{facet}/{t['term']}"
                    node("Term", tkey, facet=facet, term=t["term"])
                    edge("TAGGED", ("Claim", ckey), ("Term", tkey), facet=facet,
                         geo_role=t.get("geo_role"), assignment_source=t["assignment_source"],
                         run_id=t["run_id"])
        for e in ann["edges"]:
            edge(identifier(e["relation"].upper(), f"{doc}: relation"), ("Claim", f"{aid}#{e['from']}"), ("Claim", f"{aid}#{e['to']}"),
                 edge_id=e["id"], relation=e["relation"], sign=e["sign"],
                 method=e["provenance"]["method"], run_id=e["provenance"]["run_id"],
                 review_status=e["review"]["status"], review_reasons=e["review"]["reasons"])

    # `name` is what Neo4j Browser shows on a node; without it, it falls back to the first
    # property alphabetically, which put "needs_review" on every claim.
    for n in nodes["Claim"].values():
        n["name"] = f"{n.get('legacy_id') or n['node_id']}: {short(n['text'])}"
    for label, field in (("Article", "title"), ("Paragraph", "paragraph_id"),
                         ("Source", "host"), ("Term", "key")):
        for n in nodes[label].values():
            n.setdefault("name", n.get(field) or n["key"])

    for kind, rows in edges.items():          # an edge to a key nobody wrote would silently vanish
        for r in rows:
            for side in ("from", "to"):
                label = r[f"{side}_label"]
                if r[side] not in nodes[label]:
                    warnings.append(f"{kind}: {label} {r[side]!r} does not exist")
    return {k: list(v.values()) for k, v in nodes.items()}, edges, warnings


# ---------------------------------------------------------------- talking to Neo4j

class Neo4j:
    """Neo4j's HTTP transaction endpoint: one auto-committed request per call."""

    def __init__(self, url: str, user: str, password: str, database: str = "neo4j"):
        self.endpoint = f"{url.rstrip('/')}/db/{database}/tx/commit"
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Content-Type": "application/json", "Accept": "application/json",
                        "Authorization": f"Basic {token}"}

    def run(self, statement: str, **params) -> list[list]:
        body = {"statements": [{"statement": statement, "parameters": params}]}
        req = urllib.request.Request(self.endpoint, data=json.dumps(body).encode("utf-8"),
                                     headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                out = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            sys.exit(f"Neo4j -> {e.code}: {e.read().decode('utf-8', 'replace')[:1000]}")
        except urllib.error.URLError as e:
            sys.exit(f"Neo4j not reachable at {self.endpoint} ({e.reason}). Start it: docker compose up -d")
        if out.get("errors"):
            sys.exit(f"Neo4j error: {out['errors'][0].get('message')}\n  statement: {statement[:300]}")
        return [row["row"] for row in out["results"][0]["data"]]


def batches(rows: list, n: int = BATCH):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def load(db: Neo4j | None, nodes: dict, edges: dict) -> list[str]:
    """Send everything; with db=None only build the statements. Returns one line per kind."""
    log = []
    if db:
        db.run("MATCH (n) DETACH DELETE n")
        for label in LABELS:
            db.run(f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS "
                   f"FOR (n:{label}) REQUIRE n.key IS UNIQUE")
        for name, (label, props) in FULLTEXT.items():
            # dropped and re-created so a config change takes effect; the default analyzer
            # does not stem, so "exports" would miss "export"
            on = ", ".join(f"n.{p}" for p in props)
            db.run(f"DROP INDEX {name} IF EXISTS")
            db.run(f"CREATE FULLTEXT INDEX {name} FOR (n:{label}) ON EACH [{on}] "
                   "OPTIONS {indexConfig: {`fulltext.analyzer`: 'english'}}")
    for label in LABELS:
        rows = nodes[label]
        groups: dict[str, list[dict]] = {}
        for r in rows:                               # a claim also gets its role type as a label
            extra = f":{identifier(pascal(r['role']), 'role')}" if label == "Claim" else ""
            groups.setdefault(extra, []).append(r)
        for extra, grp in groups.items():
            for chunk in batches(grp):
                if db:
                    db.run(f"UNWIND $rows AS r CREATE (n:{label}{extra}) SET n = r", rows=chunk)
        log.append(f"{label:<13} {len(rows):>6} nodes")
    for kind, rows in sorted(edges.items()):
        by_ends: dict[tuple[str, str], list[dict]] = {}
        for r in rows:
            by_ends.setdefault((r["from_label"], r["to_label"]), []).append(r)
        for (a, b), grp in by_ends.items():
            stmt = (f"UNWIND $rows AS r MATCH (a:{a} {{key: r.f}}) MATCH (b:{b} {{key: r.t}}) "
                    f"CREATE (a)-[e:{kind}]->(b) SET e = r.p")
            for chunk in batches(grp):
                if db:
                    db.run(stmt, rows=[{"f": r["from"], "t": r["to"], "p": r["props"]} for r in chunk])
            log.append(f"{kind:<14} {len(grp):>6} edges  {a} -> {b}")
    return log


def check(db: Neo4j, nodes: dict, edges: dict) -> list[str]:
    """Counts in the database against the files. Empty list means they match."""
    problems = []
    got = dict(map(tuple, db.run("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*)")))
    want = {label: len(rows) for label, rows in nodes.items()}
    want.update(Counter(pascal(r["role"]) for r in nodes["Claim"]))
    for label in sorted(set(got) | set(want)):
        if got.get(label, 0) != want.get(label, 0):
            problems.append(f":{label}: {got.get(label, 0)} in the database, {want.get(label, 0)} in the files")
    got = dict(map(tuple, db.run("MATCH ()-[e]->() RETURN type(e), count(*)")))
    for kind in sorted(set(got) | set(edges)):
        if got.get(kind, 0) != len(edges.get(kind, [])):
            problems.append(f"[:{kind}]: {got.get(kind, 0)} in the database, "
                            f"{len(edges.get(kind, []))} in the files")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=os.environ.get("NEO4J_HTTP_URL", "http://localhost:7474"))
    ap.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    ap.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", "argumentmaps"),
                    help="default: the local credential in docker-compose.yml")
    ap.add_argument("--dry-run", action="store_true", help="build the batches, send nothing")
    ap.add_argument("--check", action="store_true", help="only compare database counts with the files")
    ap.add_argument("--no-text", action="store_true", help="leave paragraph text out")
    ap.add_argument("--wipe-remote", action="store_true",
                    help="allow a load, which deletes everything first, on a database that is not local")
    args = ap.parse_args()

    nodes, edges, warnings = build(with_text=not args.no_text)
    for w in warnings:
        print("WARNING:", w)
    db = None if args.dry_run else Neo4j(args.url, args.user, args.password)
    local = urllib.parse.urlparse(args.url).hostname in ("localhost", "127.0.0.1", "::1")
    if db and not args.check and not local and not args.wipe_remote:
        sys.exit(f"{args.url} is not this machine, and a load deletes everything in the "
                 "database first. Pass --wipe-remote if that is intended.")
    if args.check:
        problems = check(db, nodes, edges)
        print("\n".join(problems) if problems else "database matches the files")
        sys.exit(1 if problems else 0)
    for line in load(db, nodes, edges):
        print(line)
    if db:
        problems = check(db, nodes, edges)
        print("\n".join(problems) if problems else "loaded; database matches the files")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
