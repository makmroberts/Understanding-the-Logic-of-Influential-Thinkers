#!/usr/bin/env python3
"""Export the argument graph as an Obsidian vault.

    python scripts/export_obsidian.py

Writes an `obsidian/` folder. In Obsidian: "Open folder as vault" and point it
there - it does not touch your existing vault, and nothing has to be moved.

One note per claim, linked by the argument edges, so Obsidian's own graph view
does the work: click a claim to open it, see what it supports, what supports it
(backlinks panel), and the local graph around it.

Layout:
    claims/<type>/<claim>.md    one note per argument node, foldered by type
    articles/<date title>.md    one note per article, linking its claims
    concepts/<concept>.md       the cross-document layer
    index.md                    start here
    .obsidian/graph.json        colour groups matching the .mmd palette

Colour groups are preconfigured by folder, so hidden assumptions come up purple,
evidence blue, mechanisms green and counterpoints grey, the same as the maps.
"""

from __future__ import annotations

import csv
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "graph.json"
SCHEMA_MAP = Path(__file__).resolve().parent / "schema_map.yaml"
FACETS_YAML = Path(__file__).resolve().parent / "facets.yaml"
FACETS_CSV = ROOT / "data" / "node_facets.csv"
OUT = ROOT / "obsidian"

# Obsidian chokes on these in filenames and wikilinks.
ILLEGAL = re.compile(r'[\\/:*?"<>|#^\[\]]')

# folder -> colour, taken from the classDefs in the .mmd maps
COLORS = {
    "hidden_assumption": "#7A6FD8", "stated_assumption": "#4C44A0",
    "revised_prior": "#A3406B", "accounting_identity": "#4C44A0",
    "source_credibility": "#7A44A0", "scope_choice": "#8A6D15",
    "benchmark": "#8A6D15", "evidence_data": "#1565B5", "evidence_source": "#1565B5",
    "evidence_rival": "#1565B5", "evidence_discrepancy": "#1565B5",
    "mechanism": "#0E7A63", "intermediate_claim": "#139075",
    "case_type": "#139075", "policy_reductio": "#139075",
    "main_claim": "#2FBF9B", "reconstruction": "#2FBF9B",
    "recommendation": "#C9A23D", "question": "#D8D5CC",
    "opposing_view": "#8A8880", "caveat": "#6E6C66",
    "other_explanation": "#6E6C66", "deferred_question": "#6E6C66",
    "counterpoint": "#6E6C66", "anomaly": "#8A8880", "position_map": "#8A8880",
}

READABLE = {
    "licenses": "licenses", "supports": "supports", "bounds": "bounds",
    "motivates": "motivates", "reconstructs": "reconstructs",
    "revises": "revises", "rebuts": "rebuts", "qualified_by": "qualified by",
    "undercut_by": "undercut by", "defers": "defers",
}


# Browsable views: one note each, so "show me every assumption" is one click.
VIEWS = [
    ("Assumptions", "Everything the argument takes as given before it starts.",
     [("Hidden assumptions - the unstated warrants", ["hidden_assumption"]),
      ("Stated assumptions", ["stated_assumption"]),
      ("Revised priors - where he says he was wrong", ["revised_prior"]),
      ("Accounting identities", ["accounting_identity"]),
      ("Source credibility - priors about who made the data", ["source_credibility"]),
      ("Scope choices and benchmarks", ["scope_choice", "benchmark"])]),
    ("Evidence", "The data and sources cited.",
     [("Data", ["evidence_data"]), ("Studies and sources", ["evidence_source"]),
      ("Rival measurements and discrepancies",
       ["evidence_rival", "evidence_discrepancy"])]),
    ("Mechanisms", "The causal channels - how one thing is said to cause another.",
     [("Mechanisms", ["mechanism"])]),
    ("Conclusions", "Where the arguments land.",
     [("Main claims", ["main_claim"]),
      ("Reconstructions - replacement numbers he builds", ["reconstruction"]),
      ("Recommendations - the normative 'should'", ["recommendation"])]),
    ("Counterpoints", "What he concedes and who he argues against.",
     [("Opposing views", ["opposing_view"]), ("Caveats", ["caveat"]),
      ("Other explanations", ["other_explanation"]),
      ("Deferred questions", ["deferred_question"]),
      ("Unclassified counterpoints", ["counterpoint"])]),
    ("Questions", "What each article sets out to answer.",
     [("Questions", ["question"]), ("Anomalies and position maps",
                                    ["anomaly", "position_map"])]),
    ("Intermediate steps", "The claims between mechanism and conclusion.",
     [("Intermediate claims", ["intermediate_claim"]),
      ("Case types and policy reductios", ["case_type", "policy_reductio"])]),
]


# ---------------------------------------------------------------------------
# THE SUBJECT AXIS
#
# VIEWS above is the role axis - what a claim DOES in an argument. Everything
# below is what a claim is ABOUT, read from data/node_facets.csv (produced by
# scripts/label_facets.py against the closed vocabulary in scripts/facets.yaml).
#
# Why hub notes rather than tags alone: each facet term gets its own note under
# subjects/<facet>/, and every claim links to its terms. The hubs are therefore
# real nodes in Obsidian's graph, so claims cluster by topic as well as by role,
# and a hub's backlinks panel is literally "every claim about this". Tags give
# you filtering; hubs give you a place to stand. Both are emitted.
#
# Degrades cleanly: with no node_facets.csv the export is exactly what it was.
# ---------------------------------------------------------------------------
# Signs, mirroring scripts/graph_indices.py. Argumentative, not causal: +1
# backs, -1 pushes back, 0 neither (a deferred question, or the question-to-prior
# `frames` link, which is structural).
SIGN = {"supports": 1, "licenses": 1, "bounds": 1, "motivates": 1,
        "reconstructs": 1, "revises": -1, "rebuts": -1, "qualified_by": -1,
        "undercut_by": -1, "defers": 0, "frames": 0}

FACET_ORDER = ["variable", "country", "bloc", "instrument", "data_basis"]

# country and bloc are the WHERE axis (facets.yaml assignment.groups.where):
# two facets answering one question. They carry subject/counterpart roles, and
# every value also gets a `where/<term>` tag so the axis is queryable in
# Obsidian - `tag:#where/china` finds the claim whether china is filed as a
# country or a bloc.
WHERE_FACETS = ["country", "bloc"]

FACET_VIEW = {
    "variable":   ("By variable",
                   "The measurable magnitude each claim is about. The primary "
                   "subject facet - what makes two claims five years apart "
                   "comparable."),
    "country":    ("By country",
                   "One reporting economy, with an official code. Whose "
                   "variable the claim is about (subject), and against whom "
                   "(counterpart). A claim with a counterpart is bilateral."),
    "bloc":       ("By bloc",
                   "Several economies argued about together. Some are his own "
                   "analytic groupings rather than published aggregates, which "
                   "makes this facet a record of how he carves up the world."),
    "instrument": ("By instrument",
                   "The policy lever the claim concerns. Empty on descriptive "
                   "and measurement claims, which is most evidence."),
    "data_basis": ("By data basis",
                   "Which measurement regime the claim rests on. This is the "
                   "facet that separates rival claims about the same number."),
}

FACET_COLORS = {"variable": "2F7FBF", "country": "BF6F2F", "bloc": "BF8F4F",
                "instrument": "8F4FBF", "data_basis": "2FA88F"}


def load_facet_vocab() -> dict:
    """facet -> {term: one-line definition}. Empty if facets.yaml is missing."""
    if not FACETS_YAML.exists():
        return {}
    spec = yaml.safe_load(FACETS_YAML.read_text(encoding="utf-8"))
    return {f: {t: (v.get("def") or "") for t, v in spec[f]["terms"].items()}
            for f in FACET_ORDER if f in spec}


def load_saturation_warn(default: float = 0.40) -> float:
    """The one threshold, read from facets.yaml rather than copied here."""
    if not FACETS_YAML.exists():
        return default
    spec = yaml.safe_load(FACETS_YAML.read_text(encoding="utf-8")) or {}
    try:
        return float(spec["assignment"]["saturation_warn"])
    except (KeyError, TypeError, ValueError):
        return default


def load_facet_align() -> dict:
    """facet -> {term: {framework: code}} - the LOT reuse alignments."""
    if not FACETS_YAML.exists():
        return {}
    spec = yaml.safe_load(FACETS_YAML.read_text(encoding="utf-8"))
    return {f: {t: (v.get("align") or {})
                for t, v in spec[f]["terms"].items() if v.get("align")}
            for f in FACET_ORDER if f in spec}


def load_passages() -> dict:
    """(doc, node_id) -> [rows] from scripts/link_passages.py.

    Rendered with the grade attached and never collapsed into one "source"
    line: an `anchored` link names the literal that makes it checkable, a
    `candidate` link is a reading aid and says so.
    """
    p = ROOT / "data" / "node_passages.csv"
    if not p.exists():
        return {}
    out = defaultdict(list)
    for r in csv.DictReader(p.open(encoding="utf-8")):
        if r["grade"] != "none":
            out[(r["doc"], r["node_id"])].append(r)
    return out


def load_url_warnings() -> dict:
    """doc -> attribution warning from scripts/source_urls.yaml.

    A claim whose article does not actually contain it is the worst kind of
    traceability failure: the citation looks fine. Surface it on the note.
    """
    p = Path(__file__).resolve().parent / "source_urls.yaml"
    if not p.exists():
        return {}
    spec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out = {}
    for k, v in (spec.get("urls") or {}).items():
        if not isinstance(v, dict):
            continue
        if v.get("warning"):
            out[k] = ("warning", "Attribution is wrong for this claim",
                      v["warning"])
        elif v.get("annotation_provenance"):
            out[k] = ("info", "This map was re-annotated",
                      v["annotation_provenance"])
    return out


def load_graph_indices() -> dict:
    """facet -> {term: index row}, from scripts/graph_indices.py. Optional."""
    p = ROOT / "data" / "graph_indices.json"
    if not p.exists():
        return {}
    blob = json.loads(p.read_text(encoding="utf-8"))
    return {f: {r["term"]: r for r in rows}
            for f, rows in (blob.get("facets") or {}).items()}


def load_node_facets() -> dict:
    """(doc, node_id) -> {facet: [(value, role), ...]}."""
    if not FACETS_CSV.exists():
        return {}
    out: dict = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader(FACETS_CSV.open(encoding="utf-8")):
        out[(r["doc"], r["node_id"])][r["facet"]].append((r["value"], r["role"]))
    return out


def hub_titles(vocab: dict, used_terms: dict) -> dict:
    """(facet, term) -> note title, disambiguated if a term spans two facets."""
    seen = Counter(t for f in FACET_ORDER for t in used_terms.get(f, ()))
    return {(f, t): (t if seen[t] == 1 else f"{t} ({f})")
            for f in FACET_ORDER for t in used_terms.get(f, ())}


def slot_names() -> set:
    """Headers that are schema slot labels rather than content.

    The banner/meta maps put the slot name in the bold header ("Hidden
    assumption") and the actual claim in the body; the plain maps put the claim
    itself in the header. Titling a note from the header blindly produces twenty
    notes called "Main claim", which is useless in a graph view.
    """
    smap = yaml.safe_load(SCHEMA_MAP.read_text(encoding="utf-8"))
    names = {s.lower() for s in (smap.get("node_types_by_header") or {})}
    names |= {"implicit", "mechanism", "evidence", "studies & sources"}
    return names


def slot_nouns() -> set:
    """The head nouns of the slot labels, for catching near-misses.

    Exact matching is not enough. Some plain-family headers name the ROLE with a
    modifier rather than naming the claim: "Comparative claim", "Coverage
    caveat", "Descriptive caveat". Titled from the header, those notes say what
    kind of thing the claim is and nothing about what it says.

    A header is treated as a slot label when it is three words or fewer and its
    LAST word is one of these nouns. That keeps real handles - "Elasticity
    math", "Front-running", "2014-15 precedent", "Case for stability" - because
    their head noun is not a role word.
    """
    return {n.split()[-1] for n in slot_names() if n.split()} | {"claim", "caveat"}


def is_slot_label(header: str, slots: set, nouns: set) -> bool:
    h = (header or "").strip().lower()
    if not h:
        return False
    if h in slots:
        return True
    words = h.split()
    return len(words) <= 3 and words[-1] in nouns


# Words a truncated title must not end on. Cutting at a fixed length leaves
# titles like "...fell to $1" or "...booked as", which read as broken rather
# than shortened; dropping the dangling tail is the difference between a short
# title and a damaged one.
DANGLING = set("""a an and as at but by for from in into is of on or the to
with than that this those these its his her their our over under after before
just still even about between while when where which who whose not no if then
so such more most each both any some only very per via plus versus""".split())


def safe(text: str, limit: int = 120) -> str:
    """Filesystem-safe note title, shortened on a word boundary.

    120 leaves plenty of room: the deepest folder here is
    obsidian/claims/intermediate_claim/, so title + ".md" + an absolute clone
    prefix stays under the 260-character Windows path limit with ~40 to spare.
    It cuts the share of titles that get shortened at all from 33% to 14%.
    """
    text = ILLEGAL.sub("", " ".join(str(text).split())).strip(" .")
    if len(text) > limit:
        words = text[:limit].split(" ")[:-1]          # drop the part-word
        # then drop any trailing connector, and any trailing bare figure that
        # lost its unit to the cut ("fell to $1" from "$1.2 trillion")
        while words and (words[-1].lower().strip(".,;:—-") in DANGLING
                         or re.fullmatch(r"[$~]?[\d.,]+", words[-1])):
            words.pop()
        text = " ".join(words)
    return text.strip(" ,;:—-") or "untitled"


# Folders this export OWNS and therefore prunes. Anything else in the vault -
# .obsidian/, canvas/ (written by export_canvas.py), a note someone made by
# hand at the root - is left alone.
OWNED = ("claims", "articles", "concepts", "subjects", "views")


def prune(run_start: float) -> int:
    """Delete notes in owned folders that this run did not write.

    The vault is a pure function of the
    data and disposable. It was not: the export only ever added and overwrote,
    so every rename left its old file behind. 375 claim notes were on disk
    against 359 written, and the stale ones were indistinguishable from real
    ones in search, in the graph and in a canvas.

    Every note is rewritten on every run, so mtime is the test: anything older
    than this run is a leftover. Empty folders go too, which is what removed the
    `subjects/geo/` tree by hand earlier today.
    """
    removed = 0
    for folder in OWNED:
        base = OUT / folder
        if not base.exists():
            continue
        for f in base.rglob("*.md"):
            if f.stat().st_mtime < run_start - 1:
                f.unlink()
                removed += 1
        for d in sorted(base.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    return removed


def vault_graph_stats() -> dict:
    """The graph numbers the index quotes, measured from what was just written.

    index.md advertises three filters and the link cost of the saturated hubs.
    Those were hardcoded, and they silently went stale the moment a facet was
    removed. This reads the vault back and recomputes them, so the recipes a
    reader follows are the ones that were true at export time.

    Counts .md notes and the links between them. Obsidian also draws .canvas
    files and their cards; that is why one of the recipes exists.
    """
    notes = {q.stem: q for q in OUT.rglob("*.md")}

    def folder(stem: str) -> str:
        rel = notes[stem].parent.relative_to(OUT).as_posix()
        return rel or "root"

    edges, deg = set(), Counter()
    for stem, q in notes.items():
        for m in re.findall(r"\[\[([^\]|#]+)", q.read_text(encoding="utf-8")):
            tgt = m.strip().rstrip("\\")
            if tgt.endswith(".canvas") or tgt not in notes or tgt == stem:
                continue
            e = tuple(sorted((stem, tgt)))
            if e not in edges:
                edges.add(e)
                deg[stem] += 1
                deg[tgt] += 1

    def cut(drop_roots: set, drop_index: bool = True) -> dict:
        keep = {s for s in notes
                if folder(s).split("/")[0] not in drop_roots
                and not (drop_index and folder(s) == "root")}
        es = [e for e in edges if e[0] in keep and e[1] in keep]
        d = Counter()
        for a, b in es:
            d[a] += 1
            d[b] += 1
        return {"n": len(keep), "e": len(es),
                "deg": 2 * len(es) / max(1, len(keep)),
                "busiest": (d.most_common(1)[0][1] if d else 0)}

    # the saturated hubs, found by their tag rather than by name
    sat = [s for s in notes if folder(s).startswith("subjects")
           and "subject/saturated" in notes[s].read_text(encoding="utf-8")]
    hubs = sum(1 for s in notes if folder(s).startswith("subjects"))
    return {
        "all": {"n": len(notes), "e": len(edges),
                "deg": 2 * len(edges) / max(1, len(notes))},
        "trees": cut({"subjects", "views", "canvas"}),
        "argument": cut({"subjects", "views", "canvas", "articles"}),
        "sat_names": sorted(sat),
        "sat_ends": sum(deg[s] for s in sat),
        "sat_other": hubs - len(sat),
    }


def main() -> None:
    run_start = time.time()
    if not GRAPH.exists():
        raise SystemExit("data/graph.json missing - run scripts/parse_maps.py first")
    docs = json.loads(GRAPH.read_text(encoding="utf-8"))["documents"]

    # ---- the subject axis ---------------------------------------------------
    nfacets = load_node_facets()
    fvocab = load_facet_vocab()
    gidx = load_graph_indices()
    falign = load_facet_align()
    sat_warn = load_saturation_warn()
    url_warn = load_url_warnings()
    passages = load_passages()
    # which terms are actually used, so the vault never shows an empty hub
    used_terms: dict[str, set] = defaultdict(set)
    for fmap in nfacets.values():
        for f, pairs in fmap.items():
            for v, _ in pairs:
                used_terms[f].add(v)
    hubs = hub_titles(fvocab, used_terms) if nfacets else {}

    def facets_of(doc: str, nid: str, facet: str) -> list:
        """[(value, role)] for one node and facet, vocabulary order preserved."""
        return nfacets.get((doc, nid), {}).get(facet, [])

    # ---- note titles, unique across the vault -------------------------------
    #
    # A filename has to be short; a claim often is not. At a 78-character limit
    # a third of the titles were cut mid-thought, which is what you see in the
    # file list and the graph. Two things fix it: a longer limit, and an
    # `aliases:` entry carrying the whole claim wherever the title still had to
    # be shortened - Obsidian resolves search, the quick-switcher and wikilinks
    # through aliases, so nothing is lost by the trim. The note's own heading
    # has always carried the claim in full.
    slots = slot_names()
    nouns = slot_nouns()
    titles: dict[tuple[str, str], str] = {}
    full_labels: dict[tuple[str, str], str] = {}
    used: dict[str, int] = {}
    for d in docs:
        for ns in d["levels"].values():
            for n in ns:
                header, text = n["header"], " ".join((n["text"] or "").split())
                # a generic slot label makes a useless note title - prefer the claim
                label = (text if (is_slot_label(header, slots, nouns) and text)
                         else (header or text))
                full_labels[(d["doc"], n["id"])] = " ".join(
                    ILLEGAL.sub("", str(label)).split()).strip(" .")
                base = safe(label)
                key = base.lower()
                if key in used:
                    used[key] += 1
                    base = f"{base} ({d['date'][:7]})"
                    if base.lower() in used:
                        base = f"{base} {n['id']}"
                else:
                    used[key] = 1
                used.setdefault(base.lower(), 1)
                titles[(d["doc"], n["id"])] = base

    art_title = {d["doc"]: safe(f"{d['date']} {d['meta']['title']}", 120) for d in docs}

    # ---- concepts -----------------------------------------------------------
    concepts: dict[str, list] = defaultdict(list)
    for d in docs:
        for ns in d["levels"].values():
            for n in ns:
                if n.get("concept"):
                    concepts[n["concept"]].append((d, n))

    for p in ("claims", "articles", "concepts"):
        (OUT / p).mkdir(parents=True, exist_ok=True)
    (OUT / ".obsidian").mkdir(parents=True, exist_ok=True)

    # ---- one note per claim -------------------------------------------------
    counts: dict[str, int] = defaultdict(int)
    for d in docs:
        nodes = {n["id"]: n for ns in d["levels"].values() for n in ns}
        outgoing: dict[str, list] = defaultdict(list)
        incoming: dict[str, list] = defaultdict(list)
        for e in d["edges"]:
            if e["from"] in nodes and e["to"] in nodes:
                outgoing[e["from"]].append(e)
                incoming[e["to"]].append(e)

        for nid, n in nodes.items():
            title = titles[(d["doc"], nid)]
            folder = OUT / "claims" / n["type"]
            folder.mkdir(parents=True, exist_ok=True)
            counts[n["type"]] += 1

            fm = ["---",
                  f'type: {n["type"]}',
                  f'level: {n["level"]}',
                  f'date: {d["date"]}',
                  f'article: "{d["meta"]["title"]}"',
                  f'doc: {d["doc"]}',
                  f'node_id: {nid}',
                  f'family: {d["family"]}']
            full = full_labels[(d["doc"], nid)]
            if full and full != title:
                # Obsidian resolves search, the quick-switcher and wikilinks
                # through aliases, so the shortened filename costs nothing.
                esc = full.replace("\\", "\\\\").replace('"', '\\"')
                fm.append(f'aliases: ["{esc}"]')
            # How this claim's relations were known. One note can carry edges
            # from different classes, so the distinct set is what goes here -
            # the body shows each link's sign, this says what to trust it as.
            rsrc = sorted({e.get("relation_source") or "arrow"
                           for e in outgoing[nid] + incoming[nid]})
            if rsrc:
                fm.append(f'relation_sources: [{", ".join(rsrc)}]')
            if n.get("concept"):
                fm.append(f'concept: {n["concept"]}')
            if n.get("mechanism_kind"):
                fm.append(f'mechanism_kind: {n["mechanism_kind"]}')
            if n["implicit_only"]:
                fm.append("implicit_only: true")
            # the subject axis, as frontmatter fields and as tags
            ntags = [f'type/{n["type"]}', f'level/{n["level"]}',
                     f'family/{d["family"]}']
            bilateral = False
            for f in FACET_ORDER:
                pairs = facets_of(d["doc"], nid, f)
                if not pairs:
                    continue
                if f in WHERE_FACETS:
                    subj = [v for v, r in pairs if r != "counterpart"]
                    cpart = [v for v, r in pairs if r == "counterpart"]
                    bilateral = bilateral or bool(cpart)
                    if subj:
                        fm.append(f'{f}_subject: [{", ".join(subj)}]')
                        ntags += [f"{f}/{v}" for v in subj]
                        ntags += [f"where/{v}" for v in subj]
                    if cpart:
                        fm.append(f'{f}_counterpart: [{", ".join(cpart)}]')
                        ntags += [f"{f}/{v}" for v in cpart]
                        ntags += [f"where/{v}" for v in cpart]
                else:
                    vals = [v for v, _ in pairs]
                    fm.append(f'{f}: [{", ".join(vals)}]')
                    ntags += [f"{f}/{v}" for v in vals]
            if bilateral:
                fm.append("bilateral: true")
                ntags.append("shape/bilateral")

            fm += [f'tags: [{", ".join(ntags)}]', "---", ""]

            # The note's own heading carries the CLAIM, in full. The filename
            # has to be short and filesystem-safe, so `title` is truncated -
            # but the heading has no such limit, and a note headed "Hidden
            # assumption" with the actual claim demoted to a blockquote reads
            # as though the slot label were the content. 135 notes looked that
            # way. Where the header is a schema slot label, the body text IS
            # the claim and becomes the heading; the slot label is already in
            # `type:` and in the folder name, so nothing is lost.
            text = " ".join((n["text"] or "").split())
            head = " ".join((n["header"] or "").split())
            # Same test as the title, and it has to be: the FILENAME was fixed
            # for near-miss slot labels ("Comparative claim", "Scale caveat")
            # while this heading was not, so a note was named after its claim
            # and headed with its label. Canvas cards render the heading, which
            # is where that showed up as a card reading "Comparative claim".
            if is_slot_label(head, slots, nouns) and text:
                body = [f"# {text}", ""]
                # An exact slot label is already in `type:` and the folder name,
                # so nothing is lost by dropping it. A near-miss carries a word
                # of the annotator's own - the "Scale" in "Scale caveat" - so it
                # is kept as a one-line handle rather than discarded.
                if head.lower() not in slots:
                    body += [f"_{head}_", ""]
            else:
                body = [f"# {head or text or title}", ""]
                if text and text != head:
                    body += [f"> {text}", ""]

            # The relation carries a SIGN and a PROVENANCE CLASS. The sign goes
            # in the body because it is what the reader needs; the class goes in
            # frontmatter because it is what an auditor needs. An earlier version
            # printed "(relation inferred)" inline on 183 edges x 2 directions,
            # which read as an admission of guesswork - and understated what we
            # know, since in the 13 maps that label only exceptions an unlabelled
            # link means support by the annotator's own convention (49 of 49).
            #
            #   label            the annotator wrote the relation
            #   arrow            from the arrow style, by convention
            #   layout_operator  recovered from the map's `~~~` links
            def edge_note(e: dict, rel: str) -> str:
                raw = (e.get("raw") or "").strip()
                if raw and raw != rel:
                    return f' _(drawn as "{raw}")_'
                return ""

            def sign_of(e: dict) -> str:
                s = SIGN.get(e.get("type") or "", None)
                return {1: "+1", -1: "-1", 0: "0"}.get(s, "?")

            if outgoing[nid]:
                body.append("## Leads to")
                for e in outgoing[nid]:
                    t = nodes[e["to"]]
                    rel = READABLE.get(e["type"] or "", e["type"] or "unresolved")
                    body.append(f"- **{sign_of(e)} {rel}** → "
                                f"[[{titles[(d['doc'], e['to'])]}]] "
                                f"`{t['type']}`{edge_note(e, rel)}")
                body.append("")

            if incoming[nid]:
                body.append("## Rests on")
                for e in incoming[nid]:
                    s = nodes[e["from"]]
                    rel = READABLE.get(e["type"] or "", e["type"] or "unresolved")
                    body.append(f"- [[{titles[(d['doc'], e['from'])]}]] "
                                f"`{s['type']}` **{sign_of(e)} {rel}** this"
                                f"{edge_note(e, rel)}")
                body.append("")

            # Links to the subject hubs. These are what make the hub backlink
            # panel into "every claim about this", and what clusters the graph
            # by topic instead of only by argument role.
            if nfacets:
                subj_lines = []
                for f in FACET_ORDER:
                    pairs = facets_of(d["doc"], nid, f)
                    if not pairs:
                        continue
                    bits = []
                    for v, r in pairs:
                        link = f"[[{hubs[(f, v)]}]]"
                        bits.append(f"{link} _(counterpart)_" if r == "counterpart"
                                    else link)
                    subj_lines.append(f"- **{f}**: " + ", ".join(bits))
                if subj_lines:
                    body += ["## Subject", ""] + subj_lines + [""]

            body.append(f"## Source")
            body.append(f"- Article: [[{art_title[d['doc']]}]]")
            if n.get("concept"):
                body.append(f"- Concept: [[{n['concept']}]]")
            body.append(f"- Authored map: `mermaid_code/{d['doc']}.mmd`")
            pas = passages.get((d["doc"], nid), [])
            REL = {
                "states": "the paragraph says it",
                "abstracts": "the claim compresses the paragraph",
                "presupposes": "the paragraph only works if this is true — "
                               "this is its unstated warrant",
                "elsewhere": "a prior of his, grounded in his wider work "
                             "rather than this article",
            }
            for r in pas:
                rel = REL.get(r["relation"], r["relation"])
                if r["grade"] == "confirmed":
                    body.append(f"- Passage: **{r['para']}** — "
                                f"**{r['relation']}**: {rel}. _Confirmed by "
                                f"hand._")
                elif r["grade"] == "elsewhere":
                    body.append(f"- Passage: none in this article — "
                                f"**elsewhere**: {rel}. _Confirmed by hand._")
                elif r["grade"] == "anchored":
                    body.append(f"- Passage: **{r['para']}** — **states**, "
                                f"anchored on `{r['anchors']}`, a literal the "
                                f"claim and the paragraph share")
                else:
                    body.append(f"- Passage: {r['para']} — _proposed "
                                f"`{r['relation']}`, score {r['score']}; "
                                f"unreviewed, not a citation_")
            if not pas:
                body.append("- Passage: none linked")
            if d["meta"].get("url"):
                body.append(f"- Published: {d['meta']['url']}")
            else:
                body.append("- Published: **no URL recorded for this article** — "
                            "it cannot be traced to the source page")
            inferred_type = n["type_source"] in ("l6_keyword", "level")
            body.append(f"- Node `{d['doc']}#{nid}` · level {n['level']} · "
                        f"type resolved by `{n['type_source']}`"
                        + (" — **inferred**, not read from the map"
                           if inferred_type else ""))
            if n["implicit_only"]:
                body.append("- **implicit_only** — the annotator inferred this "
                            "claim; it is not stated in the article")
            body.append(f"- Full chain: `python scripts/trace.py "
                        f"{d['doc']}#{nid}`")
            if d["doc"] in url_warn:
                # NB do not name these `title` or `text` - both are live
                # locals in this loop, and the note filename comes from
                # `title`.
                cal_kind, cal_title, cal_body = url_warn[d["doc"]]
                body += ["", f"> [!{cal_kind}] {cal_title}",
                         "> " + " ".join(cal_body.split())]
            if n.get("byline"):
                body.append(f"- {n['byline']}")

            (folder / f"{title}.md").write_text("\n".join(fm + body) + "\n",
                                                encoding="utf-8")

    # ---- one note per article ----------------------------------------------
    for d in docs:
        m = d["meta"]
        fm = ["---", "type: article", f'date: {d["date"]}',
              f'family: {d["family"]}', f'doc: {d["doc"]}']
        if m.get("outlet"):
            fm.append(f'outlet: "{m["outlet"]}"')
        if m.get("genre"):
            fm.append(f'genre: "{m["genre"]}"')
        fm += [f'tags: [article, family/{d["family"]}]', "---", ""]

        body = [f"# {m['title']}", ""]
        meta_line = " · ".join(x for x in [d["date"], m.get("outlet", ""),
                                           m.get("genre", ""), m.get("shape", "")] if x)
        body += [meta_line, ""]
        if m.get("url"):
            body += [f"[Read the article]({m['url']})", ""]
        if m.get("topics"):
            body += [f"**Topics:** {m['topics']}", ""]

        for level in sorted(d["levels"]):
            ns = d["levels"][level]
            if not ns:
                continue
            body.append(f"## {level}")
            for n in ns:
                body.append(f"- [[{titles[(d['doc'], n['id'])]}]] `{n['type']}`")
            body.append("")
        (OUT / "articles" / f"{art_title[d['doc']]}.md").write_text(
            "\n".join(body) + "\n", encoding="utf-8")

    # ---- one note per concept ----------------------------------------------
    for cid, members in concepts.items():
        body = [f"---", "type: concept", "tags: [concept]", "---", "",
                f"# {cid}", "",
                f"Argued in {len({d['doc'] for d, _ in members})} articles.", ""]
        for d, n in sorted(members, key=lambda x: x[0]["date"]):
            body.append(f"- {d['date']} — [[{titles[(d['doc'], n['id'])]}]] "
                        f"`{n['type']}` · [[{art_title[d['doc']]}]]")
        (OUT / "concepts" / f"{safe(cid, 80)}.md").write_text(
            "\n".join(body) + "\n", encoding="utf-8")

    # ---- subject hubs: one note per facet term ------------------------------
    #
    # Each hub lists its claims grouped by argument role, so "the assumptions he
    # has made about bilateral trade" is one note, not a search. The
    # co-occurrence block above the list is the genuinely new affordance: it
    # says what else he brings up when he argues about this, which is the first
    # thing you want when answering a question on a topic.
    node_of: dict = {}
    for d in docs:
        for ns in d["levels"].values():
            for n in ns:
                node_of[(d["doc"], n["id"])] = (d, n)

    facet_members: dict = defaultdict(lambda: defaultdict(list))
    for (doc, nid), fmap in nfacets.items():
        if (doc, nid) not in node_of:
            continue
        for f, pairs in fmap.items():
            for v, r in pairs:
                facet_members[f][v].append((doc, nid, r))

    if nfacets:
        for f in FACET_ORDER:
            if not facet_members.get(f):
                continue
            (OUT / "subjects" / f).mkdir(parents=True, exist_ok=True)
            for term, members in facet_members[f].items():
                keys = [(doc, nid) for doc, nid, _ in members]
                arts = {doc for doc, _ in keys}
                title = hubs[(f, term)]
                # A saturated hub is also the densest node in the graph view:
                # `us` and `china` carry 476 of the vault's 3,315 link-ends
                # between them. Tagging them makes `-tag:#subject/saturated` a
                # one-token filter that keeps the other 74 hubs - a folder move
                # would do the same but break nothing usefully and churn paths.
                sat = len(keys) / max(1, sum(counts.values())) > sat_warn
                tags = ["subject", f"subject/{f}", f"{f}/{term}"]
                if sat:
                    tags.append("subject/saturated")
                fm = ["---", "type: subject", f"facet: {f}", f"term: {term}",
                      f"claims: {len(keys)}",
                      f"saturated: {str(sat).lower()}",
                      f'tags: [{", ".join(tags)}]', "---", ""]
                body = [f"# {term}", ""]
                definition = fvocab.get(f, {}).get(term, "")
                if definition:
                    body += [f"> {definition}", ""]
                # The published concept this term reuses, so a reader can join
                # the claim to a standard series. Proposed, not yet checked
                # line by line against the published lists - see facets.yaml.
                # Checked against the published lists on 2026-10-15 (UNSD
                # SITC rev.4 and its HS correspondence, UN M49). The manual
                # frameworks are component names taken as known, not re-read -
                # so the note says which standing each alignment has.
                VERIFIED = {"sitc", "hs", "m49", "iso3166"}
                al = falign.get(f, {}).get(term, {})
                if al:
                    bits = ", ".join(f"**{k}** `{v}`" for k, v in al.items()
                                     if k != "none")
                    note = al.get("none")
                    if bits:
                        # NB not `keys` - that name is the hub's claim list
                        # further down, and shadowing it breaks co-occurrence.
                        frameworks = {k for k in al if k != "none"}
                        tag = ("_verified against the published list_"
                               if frameworks and frameworks <= VERIFIED
                               else "_component name, not yet re-checked_")
                        body += [f"Aligned to {bits} — {tag}", ""]
                    elif note:
                        body += [f"No published vocabulary to reuse: {note}.",
                                 ""]
                view_name = FACET_VIEW[f][0]
                body += [f"{len(keys)} claims across {len(arts)} articles · "
                         f"facet `{f}` · [[{view_name}]] · [[index]]", ""]

                # A term on most of the corpus does not narrow anything, which
                # is what assignment.saturation_warn in facets.yaml is for.
                # label_facets.py --report already flags it; say it here too,
                # because this note is where someone decides to use the term.
                n_claims = sum(counts.values())
                share = len(keys) / max(1, n_claims)
                if share > sat_warn:
                    body += [f"> **Saturated.** This term is on {share:.0%} of "
                             f"all {n_claims} claims, past the "
                             f"{sat_warn:.0%} threshold in "
                             f"`facets.yaml`. On its own it barely narrows "
                             f"anything; cross it with another facet. It also "
                             f"makes this note one of the densest in the "
                             f"graph.", ""]

                # Ozesmi-style position in the argument graph, from
                # scripts/graph_indices.py. Says whether he argues FROM this
                # or TO it, which is not visible from the claim list alone.
                g = gidx.get(f, {}).get(term)
                if g:
                    bias = g["transmitter_bias"]
                    if abs(bias) < 0.08:
                        reading = ("sits in the middle of arguments - as much "
                                   "argued toward as argued from")
                    elif bias > 0:
                        reading = ("he argues **from** this more than toward it: "
                                   "it behaves like a prior or a mechanism")
                    else:
                        reading = ("he argues **toward** this more than from it: "
                                   "it behaves like a conclusion")
                    body += [f"**Position in the argument graph** — centrality "
                             f"{g['centrality']} ({g['centrality_per_claim']} per "
                             f"claim), {g['outdegree']} out / {g['indegree']} in, "
                             f"bias {bias:+}.", "",
                             reading[0].upper() + reading[1:] + ".", ""]

                # what else travels with this term
                co = []
                for other in FACET_ORDER:
                    if other == f:
                        continue
                    c = Counter(v for doc, nid in keys
                                for v, _ in facets_of(doc, nid, other))
                    if c:
                        co.append(f"- **{other}**: " + ", ".join(
                            f"[[{hubs[(other, v)]}]] ({k})"
                            for v, k in c.most_common(5)))
                if co:
                    body += ["## Argued together with", ""] + co + [""]

                if f in WHERE_FACETS:
                    roles = Counter(r or "subject" for _, _, r in members)
                    if roles.get("counterpart"):
                        body += [f"Appears as subject in "
                                 f"{roles.get('subject', 0)} claims and as "
                                 f"counterpart in {roles['counterpart']} "
                                 f"(i.e. bilateral claims) · [[Bilateral]]", ""]

                by_role: dict = defaultdict(list)
                for doc, nid, _ in members:
                    d, nd = node_of[(doc, nid)]
                    by_role[nd["type"]].append((d, nd))
                # No Dataview block here. The static lists below carry the
                # same claims, so a Dataview table would print every claim
                # twice for anyone who has the plugin and a raw code block
                # for everyone who does not. The queries live in index.md.
                body += ["## Claims by role", ""]
                for rtype in sorted(by_role, key=lambda t: -len(by_role[t])):
                    items = sorted(by_role[rtype], key=lambda x: x[0]["date"])
                    body += [f"### {rtype} ({len(items)})", ""]
                    for d, nd in items:
                        art = d["meta"]["title"]
                        art = art[:44] + "..." if len(art) > 47 else art
                        body.append(f"- **{d['date'][:7]}** "
                                    f"[[{titles[(d['doc'], nd['id'])]}]] · _{art}_")
                    body.append("")
                (OUT / "subjects" / f / f"{safe(title, 80)}.md").write_text(
                    "\n".join(fm + body) + "\n", encoding="utf-8")

    # ---- browsable views ----------------------------------------------------
    (OUT / "views").mkdir(parents=True, exist_ok=True)
    by_type: dict[str, list] = defaultdict(list)
    for d in docs:
        for ns in d["levels"].values():
            for n in ns:
                by_type[n["type"]].append((d, n))

    view_links = []
    for view_name, blurb, groups in VIEWS:
        total = sum(len(by_type[t]) for _, types in groups for t in types)
        if not total:
            continue
        view_links.append((view_name, total))
        body = ["---", "type: view", "tags: [view]", "---", "",
                f"# {view_name}", "", blurb, "",
                f"{total} across {len(docs)} articles. "
                f"Back to [[index]].", ""]
        for heading, types in groups:
            items = [x for t in types for x in by_type[t]]
            if not items:
                continue
            items.sort(key=lambda x: x[0]["date"])
            body += [f"## {heading} ({len(items)})", ""]
            # No Dataview block - see the note in the subject-hub writer.
            for d, n in items:
                art = d["meta"]["title"]
                art = art[:44] + "..." if len(art) > 47 else art
                body.append(f"- **{d['date'][:7]}** [[{titles[(d['doc'], n['id'])]}]] "
                            f"· _{art}_")
            body.append("")
        (OUT / "views" / f"{view_name}.md").write_text(
            "\n".join(body) + "\n", encoding="utf-8")

    # ---- subject views: one index per facet, plus the bilateral cut ---------
    subject_links = []
    if nfacets:
        for f in FACET_ORDER:
            if not facet_members.get(f):
                continue
            view_name, blurb = FACET_VIEW[f]
            terms = sorted(facet_members[f].items(), key=lambda kv: -len(kv[1]))
            total = len({k for _, m in terms for k in
                         [(doc, nid) for doc, nid, _ in m]})
            subject_links.append((view_name, len(terms), total))
            body = ["---", "type: view", f'tags: [view, subject/{f}]', "---", "",
                    f"# {view_name}", "", blurb, "",
                    f"{len(terms)} terms in use, covering {total} of "
                    f"{sum(counts.values())} claims. Back to [[index]].", "",
                    f"Graph filter: `tag:#{f}/<term>`. Vocabulary and the "
                    f"reasoning behind it: `scripts/facets.yaml`.", "",
                    "| term | claims | articles | what it means |",
                    "|---|---|---|---|"]
            for term, members in terms:
                keys = {(doc, nid) for doc, nid, _ in members}
                arts = len({doc for doc, _ in keys})
                definition = fvocab.get(f, {}).get(term, "")
                definition = definition[:84] + "..." if len(definition) > 87 else definition
                body.append(f"| [[{hubs[(f, term)]}]] | {len(keys)} | {arts} | "
                            f"{definition} |")
            unused = sorted(set(fvocab.get(f, {})) - set(facet_members[f]))
            if unused:
                body += ["", f"Vocabulary terms with no claims yet "
                             f"({len(unused)}): " + ", ".join(f"`{t}`" for t in unused),
                         "", "A term that stays empty as the corpus grows is a "
                             "term to drop - see the governance note in "
                             "`scripts/competency_questions.yaml`."]
            (OUT / "views" / f"{view_name}.md").write_text(
                "\n".join(body) + "\n", encoding="utf-8")

        # The bilateral cut. This is the reviewer's own example, and it is not a
        # topic: it is a shape, "this claim has a counterpart". A flat tag list
        # cannot express it, which is why the where axis carries roles.
        pairs: dict = defaultdict(list)
        for (doc, nid), fmap in nfacets.items():
            if (doc, nid) not in node_of:
                continue
            where = [p for f in WHERE_FACETS for p in fmap.get(f, [])]
            subj = [v for v, r in where if r != "counterpart"]
            cpart = [v for v, r in where if r == "counterpart"]
            for a in subj:
                for b in cpart:
                    pairs[(a, b)].append((doc, nid))
        if pairs:
            nbil = len({k for v in pairs.values() for k in v})
            body = ["---", "type: view", "tags: [view, shape/bilateral]", "---", "",
                    "# Bilateral", "",
                    "Claims about trade between a specific pair, as opposed to "
                    "either side's global position.", "",
                    f"{nbil} of {sum(counts.values())} claims are bilateral. "
                    f"Back to [[index]].", "",
                    "This is a shape, not a topic: a claim is bilateral when it "
                    "carries a counterpart on the where axis. Graph filter: "
                    "`tag:#shape/bilateral`.", "",
                    "> He argues repeatedly that bilateral data misleads about "
                    "global position - so the distinction this view draws is one "
                    "of his own claims, not a filing convenience.", ""]
            for (a, b), keys in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
                body += [f"## {a} → {b} ({len(keys)})", ""]
                rows = sorted((node_of[k] for k in keys), key=lambda x: x[0]["date"])
                for d, nd in rows:
                    body.append(f"- **{d['date'][:7]}** "
                                f"[[{titles[(d['doc'], nd['id'])]}]] "
                                f"`{nd['type']}`")
                body.append("")
            (OUT / "views" / "Bilateral.md").write_text(
                "\n".join(body) + "\n", encoding="utf-8")
            subject_links.append(("Bilateral", len(pairs), nbil))

    # ---- index --------------------------------------------------------------
    idx = ["# Argument maps", "",
           f"{sum(counts.values())} claims across {len(docs)} articles.", "",
           "Open the graph view (Ctrl/Cmd+G) and click any claim to expand it. "
           "Use the local-graph pane to follow one argument at a time.", "",
           "Every claim is filed on two independent axes. **Role** is what a "
           "claim does in an argument; **subject** is what it is about. Neither "
           "is a sub-category of the other, which is why there are two sets of "
           "views rather than one tree.", "",
           "## Browse by role — what a claim does", ""]
    for name, total in view_links:
        idx.append(f"- [[{name}]] — {total}")
    if subject_links:
        idx += ["", "## Browse by subject — what a claim is about", ""]
        for name, nterms, total in subject_links:
            if name == "Bilateral":
                idx.append(f"- [[Bilateral]] — {total} claims across "
                           f"{nterms} country pairs")
            else:
                idx.append(f"- [[{name}]] — {nterms} terms, {total} claims")
        idx += ["", "Cross the two axes to answer a question on one topic "
                    "without reading the whole corpus. In the graph filter box:", "",
                "- `tag:#variable/current-account tag:#type/hidden_assumption` "
                "— the unstated warrants behind his current-account arguments",
                "- `tag:#shape/bilateral tag:#type/stated_assumption` "
                "— what he assumes when the claim is bilateral",
                "- `tag:#data_basis/balance-of-payments` "
                "— every claim resting on BoP data, including the critiques of it",
                "- `tag:#where/china tag:#instrument/tariffs` "
                "— China under tariffs", "",
                "**[[Cells]]** holds these as ready Dataview tables, one per "
                "cell, with its row count — and uses `country_subject` rather "
                "than `#where/`, which carries the counterpart role too. That "
                "note is hand-written and this export does not touch it."]
    idx += ["", "The role cuts still work the same way:", "",
            "- `tag:#type/hidden_assumption` — just the unstated warrants",
            "- `path:claims/mechanism` — just the causal channels",
            "- `tag:#level/L1` — everything at the assumptions level",
            "- `tag:#family/meta` — only the 2025+ template", "",
            "## By type", ""]
    for t, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        idx.append(f"- `{t}` — {c}")
    idx += ["", "## Articles", ""]
    for d in docs:
        idx.append(f"- {d['date']} [[{art_title[d['doc']]}]] `{d['family']}`")
    if concepts:
        idx += ["", "## Concepts (what links articles together)", ""]
        for cid, members in sorted(concepts.items()):
            idx.append(f"- [[{safe(cid, 80)}]] — {len({d['doc'] for d, _ in members})} articles")
    # Every hub and view note lists its claims statically, so the vault needs
    # no plugin. These are here for anyone who has Dataview and wants a
    # sortable table instead - one place, so no note prints its claims twice.
    idx += ["", "## Dataview queries (optional plugin)", "",
            "The hub and view notes list their claims directly, so none of "
            "this is required. With the Dataview plugin installed, these "
            "return the same sets as sortable tables — and [[Cells]] has a "
            "larger set, kept by hand:", "",
            "````", "```dataview",
            "TABLE WITHOUT ID file.link AS Claim, type, date, article",
            "FROM #variable/bilateral-trade-flows", "SORT date ASC", "```",
            "", "```dataview",
            "TABLE WITHOUT ID file.link AS Claim, article",
            "FROM #shape/bilateral AND (#type/stated_assumption OR "
            "#type/hidden_assumption)", "SORT date ASC", "```",
            "", "```dataview",
            "TABLE WITHOUT ID file.link AS Claim, type, variable",
            "FROM #where/china AND #instrument/tariffs", "SORT date ASC", "```",
            "````", ""]
    gs = vault_graph_stats()
    idx += ["", "## Notes", "",
            "- **For an ordered, hierarchical view, use [[_index|the canvases]]** "
            "— one per article, laid out by argument level. Obsidian's graph is "
            "force-directed and cannot draw a hierarchy; a canvas can.",
            f"- In the graph view, the useful filters, measured on this vault "
            f"at export time ({gs['all']['n']} notes, {gs['all']['e']} links "
            f"between them, mean degree {gs['all']['deg']:.1f}):",
            f"    - `-path:subjects -path:views -file:index` → "
            f"{gs['trees']['n']} notes, {gs['trees']['e']} links, mean degree "
            f"**{gs['trees']['deg']:.1f}** — the per-article argument trees, "
            f"joined only where a concept spans articles",
            f"    - `-path:subjects -path:views -path:canvas -path:articles "
            f"-file:index` → **the argument only**: {gs['argument']['n']} "
            f"notes, {gs['argument']['e']} links, mean degree "
            f"{gs['argument']['deg']:.1f}, busiest node {gs['argument']['busiest']}. "
            f"Dropping the article notes matters more than it sounds — "
            f"removing them takes {gs['trees']['e'] - gs['argument']['e']} of "
            f"the {gs['trees']['e']} links with them, nearly all of it "
            f"membership rather than reasoning, and each article note is a "
            f"star at the centre of its cluster that the force layout bends "
            f"everything around. Turn on Display → Arrows here: the "
            f"direction is the content.",
            f"    - `-path:canvas` → the canvases are files too and every card "
            f"on one counts as a link, so they add {sum(counts.values())} "
            f"link-ends to the graph view. They are for reading, not for the "
            f"force layout.",
            f"    - `-tag:#subject/saturated` → drops just "
            + ", ".join(f"`{s}`" for s in gs["sat_names"]) +
            f", which carry {gs['sat_ends']} of the {gs['all']['e']} link-ends "
            f"between them, and keeps the other {gs['sat_other']} hubs",
            "- Every link shows its sign: **+1** backs, **-1** pushes back, "
            "**0** neither. The sign is argumentative, not causal - it means "
            "*backs* and *pushes back on*, never *increases* and *decreases*.",
            "- Each link records how its relation was known, in frontmatter: "
            "`label` (the annotator wrote it), `arrow` (from the arrow style, by "
            "convention) or `layout_operator` (recovered from the map's `~~~` "
            "links, which carry the question-to-priors and prior-to-evidence "
            "structure).",
            "- Articles use three annotation templates (`plain`, `banner`, `meta`); "
            "the `family` tag on every note records which."]
    (OUT / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")

    # ---- graph colours ------------------------------------------------------
    groups = [{"query": f"path:claims/{t}", "color": {"a": 1, "rgb": int(c[1:], 16)}}
              for t, c in COLORS.items() if counts.get(t)]
    groups += [{"query": "path:articles", "color": {"a": 1, "rgb": int("C9A23D", 16)}},
               {"query": "path:concepts", "color": {"a": 1, "rgb": int("F0A8C4", 16)}}]
    # One colour per facet, so the subject hubs read as a separate layer from
    # the claims they gather rather than disappearing into the claim palette.
    groups += [{"query": f"path:subjects/{f}",
                "color": {"a": 1, "rgb": int(FACET_COLORS[f], 16)}}
               for f in FACET_ORDER if facet_members.get(f)]
    # Obsidian writes your own tuning back into this file, so never clobber it
    # on a re-export - the colour groups only need writing once.
    graph_cfg = OUT / ".obsidian" / "graph.json"
    if graph_cfg.exists():
        # Obsidian writes its own view state back over this file, and in doing
        # so it can drop colorGroups entirely - which leaves every node the
        # same grey and looks like the export broke. Refill the groups when
        # they are missing or empty, and keep every other key the person
        # tuned (zoom, link distance, filter, forces).
        try:
            live = json.loads(graph_cfg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            live = None
        if isinstance(live, dict) and not live.get("colorGroups"):
            live["colorGroups"] = groups
            graph_cfg.write_text(json.dumps(live, indent=2), encoding="utf-8")
            print(f"  restored {len(groups)} colour groups in "
                  f".obsidian/graph.json (Obsidian had emptied them); "
                  f"your other graph settings were kept")
            if str(live.get("search", "")).strip():
                print(f"  NOTE a graph filter is still set: "
                      f"{live['search'].strip()!r} - clear the search box to "
                      f"see the whole graph")
        else:
            print("  kept your existing .obsidian/graph.json "
                  "(delete it to reset colours)")
    else:
        graph_cfg.write_text(json.dumps({
            "collapse-filter": True, "search": "", "showTags": False,
            "showAttachments": False, "hideUnresolved": False, "showOrphans": True,
            "collapse-color-groups": False, "colorGroups": groups,
            "collapse-display": True, "showArrow": True, "textFadeMultiplier": -0.8,
            "nodeSizeMultiplier": 1.3, "lineSizeMultiplier": 1,
            "collapse-forces": True, "centerStrength": 0.4, "repelStrength": 12,
            "linkStrength": 0.8, "linkDistance": 180, "scale": 0.6, "close": False,
        }, indent=2), encoding="utf-8")

    stale = prune(run_start)
    nhubs = sum(len(v) for v in facet_members.values())
    print(f"obsidian/  ->  {sum(counts.values())} claims, {len(docs)} articles, "
          f"{len(concepts)} concepts, {nhubs} subject hubs")
    if stale:
        print(f"  pruned {stale} stale note(s) this run no longer writes "
              f"- renames used to leave the old file behind")
    if not nfacets:
        print("  NO SUBJECT AXIS - data/node_facets.csv missing. "
              "Run: python scripts/label_facets.py")
    else:
        unlabelled = sum(1 for d in docs for ns in d["levels"].values()
                         for n in ns if (d["doc"], n["id"]) not in nfacets)
        if unlabelled:
            print(f"  {unlabelled} claims carry no subject facets yet "
                  f"(label_facets.py has not covered them)")
    print("  In Obsidian: Open folder as vault ->", OUT)
    print("  Then Ctrl/Cmd+G for the graph. Claims are coloured by role, "
          "subject hubs by facet.")


if __name__ == "__main__":
    main()
