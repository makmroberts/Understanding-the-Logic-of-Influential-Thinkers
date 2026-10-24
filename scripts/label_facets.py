#!/usr/bin/env python3
"""Assign subject facets to every argument node, against a closed vocabulary.

    python scripts/label_facets.py --dry-run          # show one prompt, no API call
    python scripts/label_facets.py --docs setser_mar_10_24
    python scripts/label_facets.py                    # label everything unlabelled
    python scripts/label_facets.py --force            # relabel llm rows too
    python scripts/label_facets.py --report           # distribution + saturation audit
    python scripts/label_facets.py --eval             # score against the CQ fixtures
    python scripts/label_facets.py --import-json labels.json    # no API key needed

Reads   scripts/facets.yaml          the closed vocabulary
        scripts/competency_questions.yaml   fixtures for --eval
        data/nodes.csv               the argument nodes
        data/edges.csv               for --eval one-hop expansion
        data/documents.csv     document context
Writes  data/node_facets.csv         one row per (node, facet, value)
        data/review_facets.md        everything the run could not map

THREE RULES THIS SCRIPT ENFORCES

1. The vocabulary is closed. Allowed values are compiled into a JSON-schema
   enum, so the model cannot return a term that is not in facets.yaml - the
   constraint is structural, not a post-hoc filter. Values are re-validated
   after parsing anyway, because defence in depth is cheap and the review
   report needs the data.

2. One call per document, with every node in it. The subject of a node is often
   carried by the article rather than by its own words: setser_aug_14_24#SC
   ("the methodology was already changed at a convenient moment in 2015") is a
   balance-of-payments claim that never says so. Labelling nodes in isolation
   loses those; labelling them in document context recovers them. This is the
   whole reason the labeller is a model and not a regex.

3. Hand beats model. A row whose source is `hand` is never overwritten, not
   even by --force. Human corrections accumulate; model output is disposable.

NO API KEY? --import-json takes the same payload the API would return, from
wherever you produced it - a model session labelling the documents by hand-off,
or a teammate who does have API access. Validation, cardinality caps, variable
inheritance and provenance are identical either way; only the transport
differs. An assistant subscription is not API access, so this is the route when
there is no key.

Costs about $1 for the current 20-document corpus. The vocabulary is sent as a
cached system prefix, so documents 2-20 read it from cache rather than paying
for it again; `--report` prints the measured cache hit rate after a run. If the
corpus grows past a few hundred documents, move the per-document calls onto the
Message Batches API (50% cheaper, same prompts) - the per-document prompt shape
here is already the unit of work a batch request would carry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml missing - pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
FACETS_YAML = ROOT / "scripts" / "facets.yaml"
CQ_YAML = ROOT / "scripts" / "competency_questions.yaml"
# --cq points the eval at a candidate question set (e.g. a derived one) so it
# can be scored against the same labels without swapping the governing file.
CQ_OVERRIDE: Path | None = None
NODES_CSV = ROOT / "data" / "nodes.csv"
EDGES_CSV = ROOT / "data" / "edges.csv"
DOCS_CSV = ROOT / "data" / "documents.csv"   # written by parse_maps.py
OUT_CSV = ROOT / "data" / "node_facets.csv"
REVIEW_MD = ROOT / "data" / "review_facets.md"
CACHE_DIR = ROOT / "internal" / ".cache_facets"   # internal/ is gitignored

FIELDS = ["doc", "node_id", "facet", "value", "role", "source", "model"]

# The facets, and which ones are per-role.
#
# `country` and `bloc` form the WHERE axis (facets.yaml assignment.groups.where)
# and split into subject/counterpart - see that section for why the distinction
# is the point. The model is asked for the AXIS and never for the facet: whether
# `asia-surplus` is a bloc and `china` a country is a property of the term,
# recorded in facets.yaml, so validate() routes each value to its facet rather
# than making the model guess.
SIMPLE_FACETS = ["variable", "instrument", "data_basis"]
WHERE_FACETS = ["country", "bloc"]
# Every binding key that names a place rather than a subject. `index_rows`
# writes four forms per where-value (`where`, `where_<role>`, `<facet>`,
# `<facet>_<role>`), and a fixture may bind any of them, so the whole family is
# listed. `shape` is here too: it constrains the binding's form, not its topic.
WHEREISH_KEYS = (
    {"where", "shape"}
    | {f for f in WHERE_FACETS}
    | {f"where_{r}" for r in ("subject", "counterpart")}
    | {f"{f}_{r}" for f in WHERE_FACETS for r in ("subject", "counterpart")}
)
WHERE_ROLES = ["subject", "counterpart"]

# Presentation-only node types never get facets: they are apparatus, not
# argument. parse_maps.py already drops the real apparatus; `question` survives
# into the graph but is the article's framing rather than a claim about a
# variable, so it is labelled on the where axis only.
SKIP_TYPES: set[str] = set()


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_facets() -> dict:
    spec = yaml.safe_load(FACETS_YAML.read_text(encoding="utf-8"))
    vocab = {}
    for f in SIMPLE_FACETS + WHERE_FACETS:
        terms = spec[f]["terms"]
        vocab[f] = {tid: (t.get("def") or "") for tid, t in terms.items()}
    caps = {f: spec["assignment"]["cardinality"][f] for f in vocab}
    # The where axis is one slot to the model and two facets in the data. This
    # map is what routes a value back to its facet, so the model never has to
    # know which kind of thing a term is.
    term_facet = {t: f for f in WHERE_FACETS for t in vocab[f]}
    where_cap = max(caps[f]["max"] for f in WHERE_FACETS)
    return {"vocab": vocab, "caps": caps, "term_facet": term_facet,
            "where_cap": where_cap,
            "where_min": 1 if spec["assignment"].get("requires_one_of") else 0,
            "saturation": spec["assignment"]["saturation_warn"]}


def load_nodes() -> tuple[list[dict], dict]:
    nodes = list(csv.DictReader(NODES_CSV.open(encoding="utf-8")))
    docs = {}
    for d in csv.DictReader(DOCS_CSV.open(encoding="utf-8")):
        docs[d["id"]] = d
    return nodes, docs


def load_existing() -> list[dict]:
    if not OUT_CSV.exists():
        return []
    return list(csv.DictReader(OUT_CSV.open(encoding="utf-8")))


# ---------------------------------------------------------------------------
# prompt construction
#
# Order matters for caching: the vocabulary is identical on every call and goes
# in `system` with a cache breakpoint; the document is volatile and goes in the
# user turn. Any byte that changes in the system block invalidates the cache for
# every later document, so nothing per-document may leak into it.
# ---------------------------------------------------------------------------

RULES = """\
You are classifying nodes from a hand-built argument map of one author's \
published work. The author, outlet and date are given per document in the user \
turn; they are not fixed across the corpus, so do not assume a subject matter \
beyond what the document and the vocabulary tell you. Each node is a single \
claim, already classified by the ROLE it plays in the argument - prior, \
mechanism, evidence, claim, caveat. That role is given to you and is not your \
concern.

Your job is the orthogonal axis: what each claim is ABOUT, using only the \
controlled vocabulary below.

Rules:
- Use only the term ids given. Never invent a term, never return a near-miss \
spelling. If nothing fits, return an empty list.
- Prefer FEWER terms. Two precise values beat five loose ones. A term is right \
only if the claim is actually about that thing, not merely adjacent to it.
- Read each node IN THE CONTEXT of the document it belongs to. Many nodes are \
elliptical and only make sense against the article's question and the other \
nodes. For example, a caveat reading "the income line carries no detail, so \
this cannot be checked from outside" is about the balance-of-payments income \
balance even though it names neither.
- variable is the measurable magnitude the claim concerns. Variables are \
MAGNITUDES, not processes: a claim about trade being rerouted is about the \
variable `bilateral-trade-flows`, not about a process.
- where splits by role. `where_subject` is the economy or grouping whose \
variable the claim is about; `where_counterpart` is the OTHER side, and is set \
only when the claim is genuinely bilateral or a direct two-way comparison. \
Leave where_counterpart empty for claims about one economy's own global \
position. Do not mark a claim bilateral just because two places are \
mentioned - a comparison used to characterise one economy's own position is \
not bilateral. Pick the place, not its kind - whether a term is a country or a \
bloc is already recorded.
- The where axis states a minimum of 1 below and that is right for almost \
every claim. The one exception: a universal premise about behaviour anywhere \
is about no place at all. Leave the axis empty for those rather than defaulting \
to the document's main subject - an unplaced claim is reported for a human \
decision, which is the intended outcome, and a wrong place is not.
- instrument is the policy lever the claim concerns. Leave it empty for \
descriptive and measurement claims, which is most evidence.
- data_basis is the measurement regime the claim rests on - which dataset the \
number or the critique lives on. Leave empty unless the claim actually turns \
on the data source.

Return one entry for every node id you are given, in the same order."""


def vocab_block(facets: dict) -> str:
    out = [RULES, "", "=" * 70, "CONTROLLED VOCABULARY", "=" * 70]
    caps = facets["caps"]
    def section(f: str) -> None:
        cap = caps[f]
        out.append(f"\n## {f}  (min {cap['min']}, max {cap['max']} per node)")
        for tid, d in facets["vocab"][f].items():
            out.append(f"  {tid}: {d}")

    section("variable")
    # The where axis is shown as ONE vocabulary, because it is one slot in the
    # answer. Each line still says which facet the term belongs to, so the
    # country/bloc distinction stays visible to a reader of the prompt.
    out.append(f"\n## where  (min {facets['where_min']}, "
               f"max {facets['where_cap']} per node, across subject and "
               f"counterpart)")
    for f in WHERE_FACETS:
        for tid, d in facets["vocab"][f].items():
            out.append(f"  {tid}: [{f}] {d}")
    for f in ["instrument", "data_basis"]:
        section(f)
    return "\n".join(out)


def doc_block(doc_id: str, meta: dict, nodes: list[dict]) -> str:
    # Author and outlet live HERE, not in RULES. The corpus had one author when
    # this script was written and the system prompt named him, which meant a
    # second author's claims would have been labelled while the model was told
    # it was reading the first. The user turn is volatile anyway, so carrying it
    # per document costs nothing against the cached system prefix.
    #
    # Only 5 of 20 maps carry a `%% author:` comment, so these are OMITTED when
    # unknown rather than sent as an empty field. An empty `author:` line is
    # worse than no line: it reads as a fact about the document.
    out = [f"DOCUMENT: {doc_id}",
           f"title: {meta.get('title', '')}"]
    for key in ("author", "outlet"):
        if (meta.get(key) or "").strip():
            out.append(f"{key}: {meta[key].strip()}")
    out.append(f"date: {meta.get('date', '')}")
    if meta.get("topics"):
        out.append(f"topics (author-assigned): {meta['topics']}")
    out += ["", f"NODES TO CLASSIFY ({len(nodes)}):", ""]
    for n in nodes:
        head = " ".join(n["header"].split())
        text = " ".join(n["text"].split())
        body = head if text == head else f"{head} || {text}"
        out.append(f"[{n['node_id']}] ({n['type']}, {n['level']}) {body}")
    return "\n".join(out)


def build_schema(facets: dict, node_ids: list[str]) -> dict:
    """A JSON schema whose enums ARE the vocabulary.

    This is what makes "the labeller may not invent a term" structural. Built
    from facets.yaml at runtime, so the schema can never drift from the file.
    """
    caps = facets["caps"]

    # NO `maxItems`. Structured outputs reject it - "For 'array' type, property
    # 'maxItems' is not supported" (400, verified 2026-10-19 on the first API
    # call this script ever completed; every label before that arrived through
    # --import-json, so the schema had never been checked against the API).
    #
    # Nothing is lost. The ENUM is what makes "the labeller may not invent a
    # term" structural, and that is still here. The caps were only ever advisory
    # in the schema: validate() trims every facet to `caps[f]["max"]` and
    # records the trim as an issue, and it enforces the where axis's real TOTAL
    # across both roles, which no per-array maxItems could express anyway. The
    # prompt also states each cap in prose, so the model is still told.
    def arr(facet: str) -> dict:
        return {"type": "array",
                "items": {"type": "string",
                          "enum": sorted(facets["vocab"][facet])}}

    props = {"node_id": {"type": "string", "enum": node_ids}}
    for f in SIMPLE_FACETS:
        props[f] = arr(f)
    # The where axis is one slot with a merged enum over country and bloc, so
    # the model picks a place and never a facet. The max is a TOTAL across both
    # roles (see facets.yaml), which validate() enforces, routing each value to
    # its facet.
    where_enum = sorted(t for f in WHERE_FACETS for t in facets["vocab"][f])
    props["where_subject"] = {"type": "array",
                              "items": {"type": "string", "enum": where_enum}}
    props["where_counterpart"] = {"type": "array",
                                  "items": {"type": "string",
                                            "enum": where_enum}}

    node = {"type": "object", "additionalProperties": False,
            "properties": props, "required": list(props)}
    return {"type": "object", "additionalProperties": False,
            "required": ["nodes"],
            "properties": {"nodes": {"type": "array", "items": node}}}


# ---------------------------------------------------------------------------
# the API call
# ---------------------------------------------------------------------------

def get_client():
    try:
        import anthropic
    except ImportError as e:
        sys.exit(f"anthropic SDK not importable ({e}).\n"
                 "  pip install -U anthropic\n"
                 "An old SDK can be installed but broken - 0.34.x predates "
                 "structured outputs and needs httpx/anyio it may not have.")
    # An org-level key (`sk-ant-usr-...`) is authenticated but belongs to no
    # workspace, and the Messages API then refuses the request asking for an
    # `anthropic-workspace-id` header. Supply it via ANTHROPIC_WORKSPACE_ID, or
    # use a key the Console scoped to a workspace, in which case leave it unset.
    headers = {}
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if workspace:
        headers["anthropic-workspace-id"] = workspace
    try:
        # Otherwise zero-arg: picks up ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
        # or an `ant auth login` profile, in that order of precedence.
        return anthropic.Anthropic(default_headers=headers or None), anthropic
    except Exception as e:
        sys.exit(f"could not construct client: {e}\n"
                 "  check `ant auth status`, or export ANTHROPIC_API_KEY")


def cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def call_model(client, anthropic_mod, model: str, effort: str, system: str,
               user: str, schema: dict, use_cache: bool) -> tuple[dict, dict]:
    """One document. Returns (parsed payload, usage dict)."""
    key = cache_key(model, effort, system, user, json.dumps(schema, sort_keys=True))
    cached = CACHE_DIR / f"{key}.json"
    if use_cache and cached.exists():
        return json.loads(cached.read_text(encoding="utf-8")), {"cached": True}

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"effort": effort,
                           "format": {"type": "json_schema", "schema": schema}},
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
    except TypeError as e:
        sys.exit(f"SDK rejected a current parameter ({e}).\n"
                 "  pip install -U anthropic   # needs output_config support")
    except Exception as e:
        for name in ("NotFoundError", "RateLimitError", "APIStatusError",
                     "APIConnectionError"):
            cls = getattr(anthropic_mod, name, None)
            if cls and isinstance(e, cls):
                sys.exit(f"{name}: {e}")
        raise

    if getattr(resp, "stop_reason", None) == "refusal":
        sys.exit(f"request refused: {getattr(resp, 'stop_details', None)}")

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        sys.exit(f"model returned unparseable JSON ({e}): {text[:300]}")

    u = resp.usage
    usage = {"cached": False,
             "in": getattr(u, "input_tokens", 0),
             "out": getattr(u, "output_tokens", 0),
             "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
             "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload, usage


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def validate(doc: str, payload: dict, nodes: list[dict], facets: dict,
             model: str, issues: list[str]) -> list[dict]:
    """Payload -> CSV rows, dropping anything the vocabulary does not contain."""
    byid = {n["node_id"]: n for n in nodes}
    seen, rows = set(), []
    caps = facets["caps"]

    for entry in payload.get("nodes", []):
        nid = entry.get("node_id")
        if nid not in byid:
            issues.append(f"- `{doc}` model returned unknown node id `{nid}`")
            continue
        if nid in seen:
            issues.append(f"- `{doc}#{nid}` returned twice; kept the first")
            continue
        seen.add(nid)

        def clean(facet: str, vals, role: str = "") -> list[str]:
            out = []
            for v in vals or []:
                if v not in facets["vocab"][facet]:
                    issues.append(
                        f"- `{doc}#{nid}` {facet}: `{v}` is not in the vocabulary")
                    continue
                if v not in out:
                    out.append(v)
            cap = caps[facet]["max"]
            if len(out) > cap:
                issues.append(f"- `{doc}#{nid}` {facet}: {len(out)} values over "
                              f"cap {cap}; kept the first {cap}")
                out = out[:cap]
            return out

        for f in SIMPLE_FACETS:
            for v in clean(f, entry.get(f)):
                rows.append({"doc": doc, "node_id": nid, "facet": f,
                             "value": v, "role": "", "source": "llm",
                             "model": model})

        # The where axis: validate against the merged vocabulary, then route
        # each value to country or bloc from facets.yaml.
        def clean_where(vals, role: str) -> list[str]:
            out: list[str] = []
            for v in vals or []:
                v = str(v).strip()
                if v and v not in term_facet:
                    issues.append(f"- `{doc}#{nid}` where_{role}: `{v}` "
                                  f"is not in the vocabulary")
                elif v and v not in out:
                    out.append(v)
            return out

        term_facet = facets["term_facet"]
        subj = clean_where(entry.get("where_subject"), "subject")
        cpart = clean_where(entry.get("where_counterpart"), "counterpart")
        cpart = [c for c in cpart if c not in subj]   # a pair needs two sides
        total, gcap = len(subj) + len(cpart), facets["where_cap"]
        if total > gcap:
            issues.append(f"- `{doc}#{nid}` where: {total} values over total "
                          f"cap {gcap}; trimmed subject")
            subj = subj[:max(1, gcap - len(cpart))]
        if not subj:
            issues.append(f"- `{doc}#{nid}` where_subject empty - every claim "
                          f"needs a country or a bloc "
                          f"(assignment.requires_one_of) - needs review")
        for role, vals in (("subject", subj), ("counterpart", cpart)):
            for v in vals:
                rows.append({"doc": doc, "node_id": nid,
                             "facet": term_facet[v], "value": v, "role": role,
                             "source": "llm", "model": model})

    for nid in byid:
        if nid not in seen:
            issues.append(f"- `{doc}#{nid}` was not returned by the model")
    return rows


def inherit_variable(rows: list[dict], nodes: list[dict], facets: dict,
                     issues: list[str]) -> list[dict]:
    """A node with no variable borrows its document's most common ones.

    facets.yaml sets variable min 1: a claim about nothing measurable is
    usually a question or an elliptical caveat. Rather than leave those
    unreachable, they inherit the document's dominant variables, marked
    `inherited` so the guess is visible and revocable.
    """
    have = {(r["doc"], r["node_id"]) for r in rows if r["facet"] == "variable"}
    per_doc = defaultdict(Counter)
    for r in rows:
        if r["facet"] == "variable":
            per_doc[r["doc"]][r["value"]] += 1

    added = []
    for n in nodes:
        key = (n["doc"], n["node_id"])
        if key in have or n["type"] in SKIP_TYPES:
            continue
        top = [v for v, _ in per_doc[n["doc"]].most_common(2)]
        if not top:
            issues.append(f"- `{n['doc']}#{n['node_id']}` no variable and the "
                          f"document has none to inherit")
            continue
        for v in top:
            added.append({"doc": n["doc"], "node_id": n["node_id"],
                          "facet": "variable", "value": v, "role": "",
                          "source": "inherited", "model": ""})
        issues.append(f"- `{n['doc']}#{n['node_id']}` inherited variable "
                      f"{top} from the document - check this one")
    return added


def inherit_where(rows: list[dict], issues: list[str]) -> list[dict]:
    """A claim with no where-axis value takes it from the claim it attaches to.

    Rule and rationale in facets.yaml assignment.where_inheritance. Only
    attachment relations propagate - a qualifier, undercut, rebuttal or
    deferral is about the thing it attacks - and only onto a claim that has no
    where value of its own, so nothing is overwritten.

    Rows are marked `source: inherited`, which facets.yaml declares and which
    nothing had used until this rule existed: the value is derived, visible as
    derived, and a human verdict replaces it without argument.
    """
    spec = yaml.safe_load(FACETS_YAML.read_text(encoding="utf-8"))
    cfg = (spec["assignment"].get("where_inheritance") or {})
    along = set(cfg.get("along") or [])
    if not along:
        return []

    where_of = defaultdict(list)
    for r in rows:
        if r["facet"] in WHERE_FACETS:
            where_of[(r["doc"], r["node_id"])].append(r)
    have = set(where_of)

    added = []
    for e in csv.DictReader(EDGES_CSV.open(encoding="utf-8")):
        if e["type"] not in along:
            continue
        donor, taker = (e["doc"], e["from"]), (e["doc"], e["to"])
        if taker in have or donor not in have:
            continue
        for src in where_of[donor]:
            added.append({"doc": taker[0], "node_id": taker[1],
                          "facet": src["facet"], "value": src["value"],
                          "role": src["role"], "source": "inherited",
                          "model": ""})
        have.add(taker)
        issues.append(f"- `{taker[0]}#{taker[1]}` inherited its where-axis value "
                      f"from `{donor[1]}` along `{e['type']}` "
                      f"({[r['value'] for r in where_of[donor]]}) - check this one")
    return added


def promote_orphan_counterparts(rows: list[dict], issues: list[str]) -> int:
    """A counterpart with no subject becomes the subject.

    Rule and rationale in facets.yaml assignment.orphan_counterpart. Rewrites
    the role in place rather than adding a row - the assignment itself was never
    in question, only which side of the pair it sits on - and marks the row
    `inherited` so the repair is visible and revocable.
    """
    where_of = defaultdict(list)
    for r in rows:
        if r["facet"] in WHERE_FACETS:
            where_of[(r["doc"], r["node_id"])].append(r)
    fixed = 0
    for key, rs in where_of.items():
        if any(r["role"] == "subject" for r in rs):
            continue
        orphans = [r for r in rs if r["role"] == "counterpart"]
        if not orphans:
            continue
        for r in orphans:
            r["role"] = "subject"
            r["source"] = "inherited"
            r["model"] = ""
            fixed += 1
        issues.append(f"- `{key[0]}#{key[1]}` had a counterpart "
                      f"({[r['value'] for r in orphans]}) and no subject; "
                      f"promoted to subject - check this one")
    return fixed


def write_csv(rows: list[dict]) -> None:
    rows.sort(key=lambda r: (r["doc"], r["node_id"], r["facet"], r["role"],
                             r["value"]))
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def write_review(issues: list[str], stats: dict) -> None:
    out = ["# Facet labelling review", "",
           "Everything the last run could not map cleanly. Same contract as",
           "`data/review.md`: the labeller reports rather than guesses.", ""]
    for k, v in stats.items():
        out.append(f"- {k}: {v}")
    out += ["", f"## Issues ({len(issues)})", ""]
    out += issues or ["(none)"]
    REVIEW_MD.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# --report
# ---------------------------------------------------------------------------

def cmd_report(facets: dict) -> None:
    rows = load_existing()
    if not rows:
        sys.exit(f"{OUT_CSV.name} not found - run the labeller first")
    nodes, _ = load_nodes()
    # Saturation must be measured against the nodes actually LABELLED,
    # not the whole corpus: on a partial run the corpus denominator
    # makes every term look rare and the threshold can never fire.
    labelled = {(r["doc"], r["node_id"]) for r in rows}
    n_total, n_lab = len(nodes), len(labelled)
    docs_lab = len({d for d, _ in labelled})
    print(f"{len(rows)} assignments over {n_lab} labelled nodes "
          f"in {docs_lab} document(s); corpus has {n_total} nodes")
    if n_lab < n_total:
        print(f"PARTIAL RUN - {n_total - n_lab} nodes unlabelled; "
              f"percentages are of the {n_lab} labelled\n")
    else:
        print()

    print("source:", dict(Counter(r["source"] for r in rows)))

    # assignment.requires_one_of, checked against what is already on disk. A
    # declared rule with no check is decoration, and this one catches a real
    # case: a claim whose only where-value was `imf`, which the country/bloc/
    # actor split moved off the where axis entirely.
    where_of = defaultdict(set)
    for r in rows:
        where_of[(r["doc"], r["node_id"])].add(r["facet"])
    role_of = defaultdict(set)
    for r in rows:
        if r["facet"] in WHERE_FACETS:
            role_of[(r["doc"], r["node_id"])].add(r["role"])
    bad_roles = [k for k, roles in role_of.items()
                 if "counterpart" in roles and "subject" not in roles]
    if bad_roles:
        print()
        print(f"!! {len(bad_roles)} claim(s) carry a counterpart with no "
              f"subject - a pair needs two sides:")
        for doc, nid in sorted(bad_roles):
            print(f"   {doc}#{nid}")
        print("   Repair with: python scripts/label_facets.py --inherit-where")
    orphans = [k for k, fs in where_of.items() if not (fs & set(WHERE_FACETS))]
    if orphans:
        print()
        print(f"!! {len(orphans)} claim(s) on no country and no bloc, "
              f"against assignment.requires_one_of:")
        for doc, nid in sorted(orphans):
            print(f"   {doc}#{nid}")
        print("   These need a human decision, not a default.")
    print()
    sat = facets["saturation"]
    for f in ["variable", "country", "bloc", "instrument", "data_basis"]:
        fr = [r for r in rows if r["facet"] == f]
        covered = len({(r["doc"], r["node_id"]) for r in fr})
        print(f"=== {f}: {covered}/{n_lab} labelled nodes "
              f"({covered / n_lab:.0%}), {len(fr)} assignments ===")
        c = Counter(r["value"] for r in fr)
        for v, k in c.most_common(6):
            flag = "  << over saturation threshold" if k / n_lab > sat else ""
            print(f"   {k:4d}  {v}{flag}")
        dead = [t for t in facets["vocab"][f] if t not in c]
        if dead:
            print(f"   unused terms ({len(dead)}): {', '.join(sorted(dead))}")
        print()


# ---------------------------------------------------------------------------
# --eval
#
# Scores the labelling against the hand-verified fixtures in
# competency_questions.yaml. Reported twice: strict intersection, and with the
# one-hop expansion that rules.one_hop_expansion requires. The gap between the
# two numbers IS the argument for that rule.
# ---------------------------------------------------------------------------

def load_edges() -> dict:
    adj = defaultdict(set)
    if not EDGES_CSV.exists():
        return adj
    keep = {"supports", "licenses", "bounds", "reconstructs"}
    for e in csv.DictReader(EDGES_CSV.open(encoding="utf-8")):
        if e["type"] in keep:
            adj[(e["doc"], e["to"])].add((e["doc"], e["from"]))
            adj[(e["doc"], e["from"])].add((e["doc"], e["to"]))
    return adj


def index_rows(rows: list[dict]) -> dict:
    idx = defaultdict(lambda: defaultdict(set))
    for r in rows:
        key = (r["doc"], r["node_id"])
        idx[key][r["facet"]].add(r["value"])
        if r["facet"] in WHERE_FACETS and r["role"]:
            # A fixture may bind the AXIS (`where_subject`) or one facet of it
            # (`country_subject`), and both are legitimate: the first asks
            # "about whom", the second additionally asserts what kind of thing
            # the answer is. Index all four forms so either binding resolves.
            idx[key][f"where_{r['role']}"].add(r["value"])
            idx[key][f"{r['facet']}_{r['role']}"].add(r["value"])
            idx[key]["where"].add(r["value"])
    return idx


def shares_bound_value(binding: dict, facets_of: dict) -> bool:
    """The gate on `rules.one_hop_expansion`: is this neighbour about the thing?

    A neighbour is re-admitted only if it carries at least one of the binding's
    values on a non-`where` facet. `where` is excluded on purpose - `country:
    china` is satisfied by almost every node in a China article, so gating on
    it would narrow nothing.

    Measured 2026-10-21 over the 55 fixture refs: this changes no question's
    recall (strict 49, expanded 51, both rules) and takes `must_not_return`
    violations from 1 to 0. The node it removes, fishman_2026-10-03#M6, shared
    no bound value with its binding and was reached by graph adjacency alone.
    Both nodes expansion legitimately recovers survive it, because both satisfy
    part of their binding - see the rule's `why` in competency_questions.yaml.

    A binding with no non-`where` value gates nothing and every role-eligible
    neighbour is re-admitted, which is the old behaviour.
    """
    wanted = {v for k, v in binding.items()
              if k not in WHEREISH_KEYS and v != "any"}
    if not wanted:
        return True
    return bool(wanted & set().union(*facets_of.values()) if facets_of else False)


def matches(binding: dict, facets_of: dict) -> bool:
    for k, want in binding.items():
        if k == "shape":
            if want == "bilateral" and not facets_of.get("where_counterpart"):
                return False
            continue
        if want == "any":
            continue
        if want not in facets_of.get(k, set()):
            return False
    return True


def cmd_inherit_where() -> None:
    rows = load_existing()
    if not rows:
        sys.exit(f"{OUT_CSV.name} not found - run the labeller first")
    issues: list[str] = []
    promoted = promote_orphan_counterparts(rows, issues)
    added = inherit_where(rows, issues)
    if promoted:
        write_csv(rows)
        print(f"promoted {promoted} orphaned counterpart(s) to subject")
    if not added and not promoted:
        print("nothing to inherit - every claim already has a country or a bloc")
        return
    write_csv(rows + added)
    print(f"added {len(added)} inherited where-axis row(s) to {OUT_CSV.name}")
    for i in issues:
        print("  " + i.lstrip("- "))


def cmd_eval() -> None:
    rows = load_existing()
    if not rows:
        sys.exit(f"{OUT_CSV.name} not found - run the labeller first")
    src = CQ_OVERRIDE or CQ_YAML
    cqs = yaml.safe_load(src.read_text(encoding="utf-8"))
    print(f"fixtures from {src.name}")
    print()
    nodes, _ = load_nodes()
    ntype = {(n["doc"], n["node_id"]): n["type"] for n in nodes}
    idx = index_rows(rows)
    adj = load_edges()

    tot_hit = tot_exp = tot_req = viol = tot_avail = 0
    print("CQ fixture scores   (strict / with one-hop expansion)")
    print("`avail` counts fixture nodes that are labelled at all - a "
          "fixture in a document you have\n"
          "not labelled yet cannot be retrieved, and is not a labelling "
          "error.\n")
    # v1 carries one `example:` per question; the derived v2 can carry several
    # `examples:`, because one derived question may absorb more than one of the
    # hand-written ones.
    fixtures = []
    for q in cqs["questions"]:
        exs = q.get("examples") or ([q["example"]] if q.get("example") else [])
        for ex in exs:
            fixtures.append((q, ex))
    for q, ex in fixtures:
        binding = {k: v for k, v in (ex.get("binding") or {}).items()}
        must = [tuple(r.split("#")) for r in ex.get("must_return", [])]
        never = [tuple(r.split("#")) for r in ex.get("must_not_return", [])]
        if not must:
            continue
        roles = set(q.get("role_types") or [])
        allow_all = "all" in roles

        selected = {k for k in idx
                    if matches(binding, idx[k])
                    and (allow_all or ntype.get(k) in roles)}
        expanded = set(selected)
        for k in selected:
            for n in adj.get(k, ()):
                if not (allow_all or ntype.get(n) in roles):
                    continue
                if not shares_bound_value(binding, idx[n]):
                    continue
                expanded.add(n)

        avail = [m for m in must if m in idx]
        hit = sum(1 for m in must if m in selected)
        hit_x = sum(1 for m in must if m in expanded)
        bad = [n for n in never if n in expanded]
        tot_hit += hit; tot_exp += hit_x; tot_req += len(must)
        tot_avail += len(avail); viol += len(bad)

        print(f"  {q['id']}  recall {hit}/{len(avail)} / {hit_x}/{len(avail)}"
              f"  (fixture has {len(must)}, {len(avail)} labelled)"
              f"   selected {len(selected)} -> {len(expanded)}")
        for m in must:
            if m not in expanded:
                tag = "MISS" if m in idx else "unlabelled"
                print(f"        {tag:10}  {m[0]}#{m[1]}  [{ntype.get(m, '?')}]")
        for b in bad:
            print(f"        LEAK  {b[0]}#{b[1]} should have been excluded")

    if tot_avail:
        print(f"\nrecall on labelled fixtures: strict {tot_hit}/"
              f"{tot_avail} ({tot_hit / tot_avail:.0%}), expanded "
              f"{tot_exp}/{tot_avail} ({tot_exp / tot_avail:.0%})")
    print(f"whole fixture set: {tot_exp}/{tot_req} "
          f"({tot_exp / tot_req:.0%}) - the remainder is unlabelled, not wrong")
    print(f"must_not_return violations: {viol}")
    if tot_exp > tot_hit:
        print(f"\nOne-hop expansion recovered {tot_exp - tot_hit} node(s) that "
              f"facet intersection alone dropped.\nThat is the measured case "
              f"for rules.one_hop_expansion.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="claude-opus-5")
    ap.add_argument("--effort", default="high",
                    choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--docs", nargs="*", help="only these document ids")
    ap.add_argument("--limit-docs", type=int, help="first N documents only")
    ap.add_argument("--force", action="store_true",
                    help="relabel llm rows (hand rows are still kept)")
    ap.add_argument("--no-cache", action="store_true", help="ignore the disk cache")
    ap.add_argument("--import-json", metavar="FILE",
                    help="ingest labels produced outside the API instead of "
                         "calling the model. FILE maps document id -> the same "
                         "{'nodes': [...]} payload the API returns.")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the first prompt and exit without calling")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--inherit-where", action="store_true",
                    help="apply assignment.where_inheritance to the rows "
                         "already in node_facets.csv")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--cq", metavar="PATH",
                    help="score --eval against the fixtures in PATH instead of "
                         "the governing competency_questions.yaml, so a "
                         "candidate question set can be compared on the same "
                         "labels without swapping files")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    facets = load_facets()
    if args.report:
        return cmd_report(facets)
    if args.cq:
        global CQ_OVERRIDE
        CQ_OVERRIDE = Path(args.cq)
    if args.inherit_where:
        cmd_inherit_where()
        return
    if args.eval:
        return cmd_eval()

    nodes, docmeta = load_nodes()
    by_doc = defaultdict(list)
    for n in nodes:
        if n["type"] not in SKIP_TYPES:
            by_doc[n["doc"]].append(n)

    order = [d for d in dict.fromkeys(n["doc"] for n in nodes) if d in by_doc]
    if args.docs:
        unknown = set(args.docs) - set(order)
        if unknown:
            sys.exit(f"unknown document id(s): {', '.join(sorted(unknown))}")
        order = [d for d in order if d in set(args.docs)]
    if args.limit_docs:
        order = order[:args.limit_docs]

    # Hand rows are sacred; llm/inherited rows for a doc we are relabelling go.
    existing = load_existing()
    hand = [r for r in existing if r["source"] == "hand"]
    hand_keys = {(r["doc"], r["node_id"]) for r in hand}
    targets = set(order)
    kept = [r for r in existing
            if r["source"] != "hand" and r["doc"] not in targets]
    if not args.force:
        already = {r["doc"] for r in existing if r["source"] != "hand"}
        skip = targets & already
        if skip:
            print(f"already labelled, skipping {len(skip)} doc(s) "
                  f"(use --force to redo): {', '.join(sorted(skip))}")
            order = [d for d in order if d not in skip]
            kept = [r for r in existing if r["source"] != "hand"]

    if not order:
        print("nothing to do")
        return

    system = vocab_block(facets)
    print(f"vocabulary: {sum(len(v) for v in facets['vocab'].values())} terms, "
          f"{len(system)} chars of system prefix")
    print(f"documents to label: {len(order)}")

    if args.dry_run:
        d = order[0]
        user = doc_block(d, docmeta.get(d, {}), by_doc[d])
        schema = build_schema(facets, [n["node_id"] for n in by_doc[d]])
        print("\n" + "=" * 70 + "\nSYSTEM (cached prefix)\n" + "=" * 70)
        print(system[:2000] + "\n[...truncated]")
        print("\n" + "=" * 70 + f"\nUSER - {d}\n" + "=" * 70)
        print(user)
        print("\n" + "=" * 70 + "\nSCHEMA enum sizes\n" + "=" * 70)
        # The cap is reported from facets.yaml, NOT from the schema: structured
        # outputs reject `maxItems`, so the schema no longer carries it and
        # validate() is what enforces the cap. Reading it off the schema here is
        # what broke --dry-run when maxItems was removed.
        caps = {"variable": facets["caps"]["variable"]["max"],
                "where_subject": facets["where_cap"],
                "where_counterpart": facets["where_cap"],
                "instrument": facets["caps"]["instrument"]["max"],
                "data_basis": facets["caps"]["data_basis"]["max"]}
        for f in ["variable", "where_subject", "where_counterpart",
                  "instrument", "data_basis"]:
            props = schema["properties"]["nodes"]["items"]["properties"]
            print(f"  {f}: {len(props[f]['items']['enum'])} allowed values, "
                  f"cap {caps[f]} (enforced by validate(), not by the schema)")
        est = (len(system) + len(user)) // 4
        print(f"\n~{est} input tokens for this document "
              f"(~{len(system) // 4} of it cacheable)")
        return

    imported = None
    if args.import_json:
        imported = json.loads(Path(args.import_json).read_text(encoding="utf-8"))
        missing = [d for d in order if d not in imported]
        if missing:
            print(f"not in {args.import_json}, skipping: {', '.join(missing)}")
            order = [d for d in order if d in imported]
        if not order:
            sys.exit("nothing in the import file matches the requested documents")
        client = anthropic_mod = None
    else:
        client, anthropic_mod = get_client()

    rows, issues = list(kept), []
    usage_tot = Counter()
    for i, d in enumerate(order, 1):
        dn = by_doc[d]
        if imported is not None:
            payload, usage = imported[d], {"cached": False}
        else:
            user = doc_block(d, docmeta.get(d, {}), dn)
            schema = build_schema(facets, [n["node_id"] for n in dn])
            payload, usage = call_model(client, anthropic_mod, args.model,
                                        args.effort, system, user, schema,
                                        use_cache=not args.no_cache)
        got = validate(d, payload, dn, facets, args.model, issues)
        # never shadow a hand label
        got = [r for r in got if (r["doc"], r["node_id"]) not in hand_keys]
        rows += got
        for k, v in usage.items():
            if isinstance(v, int):
                usage_tot[k] += v
        tag = "imported" if imported is not None else (
            "cache" if usage.get("cached") else (
            f"in {usage.get('in', 0)} (+{usage.get('cache_read', 0)} cached) "
            f"out {usage.get('out', 0)}"))
        print(f"  [{i}/{len(order)}] {d}: {len(dn)} nodes -> "
              f"{len(got)} assignments   {tag}")

    rows += inherit_variable(rows, [n for n in nodes if n["doc"] in targets],
                             facets, issues)
    rows += hand
    write_csv(rows)

    stats = {"documents labelled": len(order),
             "assignments written": len(rows),
             "hand rows preserved": len(hand),
             "input tokens": usage_tot["in"],
             "cache reads": usage_tot["cache_read"],
             "output tokens": usage_tot["out"]}
    write_review(issues, stats)

    print(f"\nwrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} rows)")
    print(f"wrote {REVIEW_MD.relative_to(ROOT)} ({len(issues)} issues)")
    if usage_tot["in"]:
        print(f"tokens: {usage_tot['in']} in, {usage_tot['cache_read']} "
              f"cache reads, {usage_tot['out']} out")
        if usage_tot["cache_read"] == 0 and len(order) > 1:
            print("WARNING: zero cache reads across several documents - "
                  "something is invalidating the system prefix")
    print("\nnext:  python scripts/label_facets.py --report"
          "\n       python scripts/label_facets.py --eval")


if __name__ == "__main__":
    main()
