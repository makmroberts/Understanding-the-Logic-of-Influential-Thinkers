#!/usr/bin/env python3
"""Walk one article all the way to a citation, and write it up.

    python scripts/worked_example.py --list
    python scripts/worked_example.py --doc setser_2025-07-07_china-stealth-surplus
    python scripts/worked_example.py --doc ... --out WORKED_EXAMPLE.md
    python scripts/worked_example.py --doc ... --full-text    # local only, see below

Reads   data/nodes.csv, data/edges.csv, data/edges_signed.csv,
        data/node_facets.csv, data/node_passages.csv, data/graph_indices.json,
        mermaid_code/*.mmd, internal/extracted/*.md,
        scripts/worked_example_notes.yaml

THE POINT

PROCESS.md says what every step decides. It never shows one article going
through all of them, and the step people actually ask about - how 29 paragraphs
of prose become 13 claims - is the one step with no script behind it.

So this generates the checkable half and splices in the hand-written half:

    panels 1, 3-7   derived from data/, so the numbers cannot go stale
    panel 2         scripts/worked_example_notes.yaml, written by a person

The split is the no-silent-re-derivation rule applied to a document. The
reading pass is a human judgement; deriving it would be the pipeline inventing
the thing the pipeline is supposed to be audited against. Where a note is
missing the script says so rather than filling the gap.

ON ARTICLE TEXT

internal/ is gitignored - extracted text stays local. So by default this emits
a short excerpt per cited paragraph plus the paragraph number and the published
URL, which is enough for a reader to open the article and check the fit. Pass
--full-text for a local copy with whole paragraphs, and do not commit that one.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
NODES = ROOT / "data" / "nodes.csv"
EDGES = ROOT / "data" / "edges.csv"
SIGNED = ROOT / "data" / "edges_signed.csv"
FACETS = ROOT / "data" / "node_facets.csv"
PASSAGES = ROOT / "data" / "node_passages.csv"
INDICES = ROOT / "data" / "graph_indices.json"
MAPS = ROOT / "mermaid_code"
EXTRACTED = ROOT / "internal" / "extracted"
NOTES = ROOT / "scripts" / "worked_example_notes.yaml"

# How much of the article to reproduce. Kept deliberately short: the document
# is committed and `internal/` is not, the published page is a click away, and
# a walkthrough that quotes the article at length stops being a walkthrough.
# The shared literals carry the verification anyway - they are the evidence.
# `--full-text` lifts this for a local copy.
EXCERPT_WORDS = 12

# How a node's role was decided. Same distinction trace.py prints, same
# wording - two tools disagreeing about provenance vocabulary is its own bug.
TYPE_SOURCE = {
    "header": "read - the map's own bold slot label",
    "class": "read - the classDef assigned in the map",
    "l6_keyword": "inferred - keyword match on the header",
    "level": "inferred - fell back to the enclosing subgraph",
}
RELATION_SOURCE = {
    "label": "read - the annotator wrote this on the arrow",
    "arrow": "declared - a bare solid arrow, taken as support",
    "layout_operator": "declared - an invisible `~~~` connector, taken as framing",
    "inferred": "inferred - backed off from the labelled links",
}
SIGN_WORD = {"1": "backs", "-1": "pushes back on", "0": "defers"}


# --------------------------------------------------------------- loading

def rows(path: Path, doc: str | None = None) -> list:
    if not path.exists():
        return []
    out = list(csv.DictReader(path.open(encoding="utf-8")))
    return [r for r in out if r.get("doc") == doc] if doc else out


def load_paras(doc_url: str) -> dict:
    """paragraph number -> text, from the local extract matching this url."""
    if not EXTRACTED.exists() or not doc_url:
        return {}
    for p in sorted(EXTRACTED.glob("*.md")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^url:\s*(\S+)", raw, re.M)
        if not m or m.group(1).strip() != doc_url:
            continue
        paras = {}
        for pm in re.finditer(r"<!--\s*p(\d+)\s*-->\s*\n(.*?)(?=\n<!--|\n##|\Z)",
                              raw, re.S):
            body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", pm.group(2))
            body = re.sub(r"[*_`]", "", body)
            body = " ".join(body.split())
            if body:
                paras[int(pm.group(1))] = body
        return paras
    return {}


def map_header(doc: str) -> dict:
    """Article metadata, best source first.

    Only 5 of 20 maps carry `%%` comments - the `banner` maps put their
    title in a `T[...]` node instead - so the comments are the first source
    and not the only one. The order is the project's rule that the authored
    artifact outranks anything inferred about it: the map's own header beats
    `documents.csv`, which beats the `source_urls.yaml` overlay.
    """
    meta = {}
    p = MAPS / f"{doc}.mmd"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("%%"):
                continue
            for part in line.strip()[2:].split("|"):
                m = re.match(r"\s*(\w+):\s*(.+)", part)
                if m:
                    meta[m.group(1).strip()] = m.group(2).strip()

    docs = ROOT / "data" / "documents.csv"
    if docs.exists():
        for r in csv.DictReader(docs.open(encoding="utf-8")):
            if r.get("id") != doc:
                continue
            for src, dst in (("title", "title"), ("date", "date"),
                             ("author", "author"), ("outlet", "outlet"),
                             ("url", "url"), ("topics", "topics")):
                if r.get(src) and not meta.get(dst):
                    meta[dst] = r[src]

    overlay = ROOT / "scripts" / "source_urls.yaml"
    if not meta.get("url") and overlay.exists():
        spec = (yaml.safe_load(overlay.read_text(encoding="utf-8")) or {})
        rec = (spec.get("urls") or {}).get(doc)
        if isinstance(rec, dict) and rec.get("url"):
            meta["url"] = rec["url"]
            meta["url_source"] = "scripts/source_urls.yaml"
    return meta


def map_body(doc: str) -> str:
    """The flowchart itself, without the theme config or the classDefs.

    The styling is thirty lines that say nothing about the argument; dropping
    it is the difference between a readable panel and a wall of hex codes.
    """
    p = MAPS / f"{doc}.mmd"
    if not p.exists():
        return ""
    text = re.sub(r"^---\n.*?\n---\n", "", p.read_text(encoding="utf-8"), flags=re.S)
    keep = [ln for ln in text.splitlines()
            if not re.match(r"\s*(classDef|class|style)\s", ln)]
    return "\n".join(keep).strip()


def claim_of(node: dict) -> str:
    """The claim sentence, honouring the template family.

    In `plain` maps the bold line is the claim and the body is the annotator's
    gloss. In `banner` and `meta` maps it is reversed. Reading one field is how
    an analysis silently ends up about notes instead of claims.
    """
    header, text = node.get("header", ""), node.get("text", "")
    return (header or text) if node.get("family") == "plain" else (text or header)


def slot_of(node: dict) -> str:
    """The other field: the role label the annotator typed into the slot."""
    header, text = node.get("header", ""), node.get("text", "")
    return (text or "") if node.get("family") == "plain" else (header or "")


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def para_num(row: dict):
    """Paragraph number of a passage row, or None.

    `link_passages.py` writes a row per claim even when nothing matched -
    grade `none`, every other column blank - so "no link" is a row, not a
    missing row, and it has to survive being sorted and counted.
    """
    raw = (row.get("para") or "").strip()
    return int(raw[1:]) if raw[1:].isdigit() else None


def plural(n, word: str) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return f"? {word}s"
    return f"{n} {word}" + ("" if n == 1 else "s")


def excerpt(text: str, words: int = EXCERPT_WORDS) -> str:
    w = (text or "").split()
    return " ".join(w[:words]) + (" ..." if len(w) > words else "")


# --------------------------------------------------------------- panels

def panel_front(doc, nodes, edges, meta, manifest, notes) -> list:
    # Both documents are the same walkthrough of different articles, so the
    # title has to name the article or they are indistinguishable in a list.
    title = meta.get("title") or doc
    o = [f"# Worked example: {title}", "",
         "*One article from prose to a citation, in seven panels.*", ""]
    intro = notes.get("intro")
    o += [intro.strip(), ""] if intro else [
        "> No `intro:` for this article in `scripts/worked_example_notes.yaml`.", ""]
    byline = " - ".join(x for x in (meta.get("author"), meta.get("outlet")) if x)
    src = meta.get("url", "")
    if src and meta.get("url_source"):
        # Where the url came from is itself provenance: only 5 of 20 maps
        # carry their own, and the rest are joined through an overlay a
        # person wrote evidence for.
        src += f"  *(via `{meta['url_source']}`)*"
    o += [
        "| | |", "|---|---|",
        f"| Article | **{meta.get('title') or doc}** |",
        f"| Author | {byline or '—'} |",
        f"| Published | {meta.get('date') or '—'} |",
        f"| Source | {src or '—'} |",
        f"| Map | `mermaid_code/{doc}.mmd` |",
        f"| Cited as | `{doc}#<node_id>` |",
        "",
        f"The article runs {manifest.get('word_count', '?')} words over "
        f"{manifest.get('n_paragraphs', '?')} paragraphs, with "
        f"{plural(manifest.get('n_figures'), 'figure')} and "
        f"{plural(manifest.get('n_references'), 'inline reference')}. The map "
        f"reduces it to **{len(nodes)} claims and {len(edges)} links**. "
        "Everything below is either generated from `data/` or marked as "
        "hand-written.",
        "",
    ]
    return o


def panel_article(paras, passages, full_text) -> list:
    o = ["---", "", "## Panel 1 - The article, as the annotator sees it", "",
         "`cfr_extract.py` numbers the paragraphs. Those numbers are the only "
         "handle anything downstream has on the prose, so a paragraph is the "
         "unit a passage link points at.", ""]
    if not paras:
        o += ["> No local extract matches this url, so paragraph text is "
              "unavailable here. Run `cfr_extract.py` first.", ""]
        return o

    by_para = defaultdict(list)
    for r in passages:
        n = para_num(r)
        if n is not None:
            by_para[n].append(r)

    # The paragraph text is not reproduced here. What a reader needs to check
    # the map is the paragraph number and the literal it shares with the
    # claim; the article itself is one click away and stays out of the repo.
    head = ("| para | words | claims linked | grade | shared literals |"
            if not full_text else
            "| para | words | claims linked | grade | text |")
    o += [head, "|---|---|---|---|---|"]
    for n in sorted(paras):
        hits = by_para.get(n, [])
        ids = ", ".join(f"`{h['node_id']}`" for h in hits) or "-"
        grades = ", ".join(sorted({h["grade"] for h in hits})) or "-"
        if full_text:
            last = esc(paras[n])
        else:
            lits = sorted({a for h in hits for a in (h["anchors"] or "").split()})
            last = " ".join(f"`{a}`" for a in lits) or "-"
        o.append(f"| p{n} | {len(paras[n].split())} | {ids} | {grades} | {last} |")
    unused = [n for n in sorted(paras) if n not in by_para]
    o += ["",
          f"**{len(paras) - len(unused)} of {len(paras)} paragraphs carry a "
          f"claim.** The other {len(unused)} "
          f"({', '.join('p' + str(n) for n in unused)}) are not lost in any "
          "sense that matters - see panel 2.", ""]
    return o


def panel_reading(nodes, passages, paras, notes, full_text) -> list:
    o = ["---", "", "## Panel 2 - The reading pass *(hand-written)*", "",
         "**This is the only panel a script does not produce.** It is written "
         "by a person in `scripts/worked_example_notes.yaml`; code may propose, "
         "never overwrite.", "",
         "It is also deliberately not a story about what the annotator was "
         "thinking. Each note gives the paragraph, the claim and the rule in "
         "`schema_map.yaml` that the role answers to, so a reader can disagree "
         "with the fit rather than take it on trust.", ""]
    pnotes = notes.get("nodes") or {}
    by_node = defaultdict(list)
    for r in passages:
        if para_num(r) is not None:
            by_node[r["node_id"]].append(r)

    for nd in nodes:
        nid = nd["node_id"]
        o += [f"### `{nid}` - {nd['type'].replace('_', ' ')}", "",
              f"> {esc(claim_of(nd))}", ""]
        links = by_node.get(nid, [])
        if links:
            for h in sorted(links, key=para_num):
                anc = f", shared literals `{h['anchors']}`" if h.get("anchors") else ""
                o.append(f"- **{h['para']}** - {h['grade']}, {h['relation']}{anc}")
                # An anchored link is already evidenced by the literal, so it
                # needs no quotation. A candidate is a claim about meaning and
                # nothing but the words shows whether it holds.
                src = paras.get(para_num(h), "")
                if src and (full_text or h["grade"] != "anchored"):
                    o.append(f"  > {esc(src if full_text else excerpt(src))}")
            o.append("")
        else:
            o += ["- *No paragraph link at all.*", ""]
        note = pnotes.get(nid)
        o += [note.strip(), ""] if note else [
            f"> WRITE ME: no note for `{nid}` in `worked_example_notes.yaml`.", ""]

    left = notes.get("left_out")
    o += ["### What the map leaves out", "",
          left.strip() if left else
          "> WRITE ME: no `left_out:` note in `worked_example_notes.yaml`.", ""]
    return o


def panel_map(doc, body) -> list:
    return ["---", "", "## Panel 3 - The map", "",
            "The authored artifact. Code never rewrites this file. The theme "
            "config and the `classDef` styling are dropped here for legibility; "
            "nothing else is changed.", "",
            "```mermaid", body, "```", ""]


def panel_parse(nodes, edges) -> list:
    # Each map stores the claim in one field and something else in the other,
    # and which is which depends on the template. Naming the second column
    # wrongly would reproduce, in the document, the exact confusion the
    # document is trying to warn about.
    fam = nodes[0].get("family", "?")
    other = "annotator's gloss" if fam == "plain" else "slot label"
    o = ["---", "", "## Panel 4 - Parse: what was read, what was declared", "",
         "`parse_maps.py` turns the map into rows. Every row records *how it "
         "was known*, and that column matters more than the content does.", "",
         "### Claims", "",
         f"| id | role | level | {other} | claim | how the role was known |",
         "|---|---|---|---|---|---|"]
    for nd in nodes:
        o.append(f"| `{nd['node_id']}` | {nd['type']} | {nd['level']} | "
                 f"{esc(slot_of(nd))} | {esc(excerpt(claim_of(nd), 18))} | "
                 f"{TYPE_SOURCE.get(nd['type_source'], nd['type_source'])} |")
    ts = Counter(n["type_source"] for n in nodes)
    where = ("the bold line and the annotator's gloss sits in the body"
             if fam == "plain" else
             "the node body and the bold line holds the role name")
    o += ["",
          "Role provenance: "
          + ", ".join(f"**{v}** {k}" for k, v in ts.most_common()) + ".",
          "",
          f"Note the fourth column. This is a `{fam}` template, so the claim "
          f"sits in {where}. The three templates disagree about this, and an "
          "analysis that reads one field without checking `family` reads notes "
          "rather than claims for most of the corpus.",
          "", "### Links", "",
          "| from | to | relation | how the relation was known |",
          "|---|---|---|---|"]
    for e in edges:
        o.append(f"| `{e['from']}` | `{e['to']}` | {e['type']} | "
                 f"{RELATION_SOURCE.get(e['relation_source'], e['relation_source'])} |")
    rs = Counter(e["relation_source"] for e in edges)
    o += ["",
          "Relation provenance: "
          + ", ".join(f"**{v}** {k}" for k, v in rs.most_common()) + ".",
          "",
          "The declared ones are a convention, not a reading. A bare arrow is "
          "taken as support because in the thirteen maps that label selectively, "
          "all 49 written labels are non-support - leaving a link bare is the "
          "annotator's shorthand for the ordinary case. `~~~` is layout, so it "
          "is signed 0 and cannot inflate a support count.", ""]
    return o


def panel_subject(nodes, facets) -> list:
    if not facets:
        return ["---", "", "## Panel 5 - The subject axis", "",
                "> No facet rows for this article. Run `label_facets.py`.", ""]
    cols = sorted({r["facet"] for r in facets})
    byn = defaultdict(lambda: defaultdict(list))
    for r in facets:
        byn[r["node_id"]][r["facet"]].append(r)
    o = ["---", "", "## Panel 5 - The subject axis", "",
         "`label_facets.py` assigns terms from the closed vocabulary in "
         "`facets.yaml`. The allowed values compile into the response schema at "
         "run time, so an off-list term is a validation failure rather than a "
         "quiet new tag.", "",
         "| claim | " + " | ".join(cols) + " |",
         "|---" * (1 + len(cols)) + "|"]
    for nd in nodes:
        cells = []
        for f in cols:
            vals = []
            for r in byn[nd["node_id"]].get(f, []):
                role = f" *({r['role']})*" if r.get("role") else ""
                vals.append(f"`{r['value']}`{role}")
            cells.append(", ".join(vals) or "-")
        o.append(f"| `{nd['node_id']}` | " + " | ".join(cells) + " |")
    src = Counter(r["source"] for r in facets)
    o += ["",
          f"{len(facets)} labels over {len(cols)} facets, "
          + ", ".join(f"**{v}** {k}" for k, v in src.most_common()) + ".", ""]

    geo = ("country", "bloc")
    subj = sorted({r["value"] for r in facets
                   if r.get("role") == "subject" and r["facet"] in geo})
    cpt = sorted({r["value"] for r in facets
                  if r.get("role") == "counterpart" and r["facet"] in geo})
    if cpt:
        o += ["`subject` against `counterpart` is what makes a claim bilateral: "
              + ", ".join(f"`{p}`" for p in subj) + " as subject, "
              + ", ".join(f"`{c}`" for c in cpt)
              + " as counterpart, direction preserved.", ""]
    return o


def panel_derived(doc, indices) -> list:
    signs = {(r["from"], r["to"]): r["sign"] for r in rows(SIGNED, doc)}
    tally = Counter(signs.values())
    o = ["---", "", "## Panel 6 - Derived: signs and indices", "",
         "No edge is signed by hand; the sign is a function of the relation. It "
         "is **argumentative, not causal** - `+1` backs, `-1` pushes back, `0` "
         "defers. It does not mean increases or decreases.", "",
         "| sign | reading | links |", "|---|---|---|"]
    for s in ("1", "0", "-1"):
        if tally.get(s):
            o.append(f"| `{s}` | {SIGN_WORD[s]} | {tally[s]} |")
    pushes = [f"`{a}` to `{b}`" for (a, b), s in signs.items() if s == "-1"]
    o += [""]
    if pushes:
        o += ["The negative links are the author arguing against his own case: "
              + ", ".join(pushes) + ".", ""]
    per = (indices.get("per_document") or {}).get(doc) or {}
    if per:
        o += ["| index | value | what it means here |", "|---|---|---|",
              f"| variables | {per.get('variables')} | claims in the map |",
              f"| connections | {per.get('connections')} | links |",
              f"| density | {per.get('density')} | share of possible links drawn |",
              f"| hierarchy index | {per.get('hierarchy_index')} | star-ness, "
              "**not** layeredness - near zero is the correct reading |",
              f"| mean centrality | {per.get('mean_centrality')} | links per claim |",
              ""]
        ch = per.get("character") or {}
        if ch:
            o += ["Node character: "
                  + ", ".join(f"**{v}** {k}" for k, v in ch.items())
                  + ". Transmitters are what the argument rests on; receivers "
                    "are where it lands.", ""]
    return o


def panel_citation(doc, nodes, passages, meta, notes) -> list:
    anchored = [r for r in passages if r["grade"] == "anchored"]
    linked = [r for r in passages if para_num(r) is not None]
    o = ["---", "", "## Panel 7 - One claim, cited", "",
         f"Of {len(linked)} passage links on this article, **{len(anchored)} "
         "are `anchored`**: the claim and the paragraph share a distinctive "
         "literal, which is provenance. The rest are `candidate` - semantic "
         f"overlap only, a narrowing from {meta.get('n_paragraphs', 'thirty')} "
         "paragraphs to one, and the vault never renders one as a source.", ""]
    unmatched = len(passages) - len(linked)
    if unmatched:
        o += [f"A further **{unmatched}** claim(s) matched no paragraph at all. "
              "That is a row in the data, graded `none`, not a gap in it.", ""]
    if anchored:
        # Cite the claim with the MOST anchored paragraphs, and show all of
        # them. Picking the single highest-scoring row would imply a claim has
        # one source, which for an aggregate evidence node is false - and the
        # reading pass two panels up says so in as many words.
        per_node = defaultdict(list)
        for r in anchored:
            per_node[r["node_id"]].append(r)
        nid, links = max(per_node.items(),
                         key=lambda kv: (len(kv[1]),
                                         max(float(r["score"]) for r in kv[1])))
        links.sort(key=lambda r: -float(r["score"]))
        nd = next((n for n in nodes if n["node_id"] == nid), {})
        o += ["| | |", "|---|---|",
              f"| Claim | `{doc}#{nid}` |",
              f"| Role | {nd.get('type', '')} |",
              f"| Text | {esc(claim_of(nd))} |",
              f"| Published at | {meta.get('url', '')} |", "",
              f"It rests on **{len(links)} paragraph(s)**, each sharing a "
              "distinctive literal with the claim:", "",
              "| paragraph | relation | score | shared literals |",
              "|---|---|---|---|"]
        for r in links:
            o.append(f"| {r['para']} | `{r['relation']}` | {r['score']} | "
                     f"`{r['anchors']}` |")
        o += ["",
              "The literals are why this is a citation and not a guess: those "
              "tokens occur in the claim, in that paragraph, and in few other "
              "paragraphs of this article. Open the URL, find the paragraph, "
              "check it.",
              "",
              "**One claim is not one paragraph.** An evidence node that "
              "gathers figures from across an article is cited by every "
              "paragraph it gathers from, and a citation line that showed only "
              "the best-scoring one would misrepresent the claim as narrower "
              "than it is.", ""]
    o += ["The full chain for any claim on this article:", "",
          "```", f"python scripts/trace.py {doc}#{nodes[0]['node_id']}", "```", ""]
    close = notes.get("closing")
    if close:
        o += ["### What this example shows, and what it does not", "",
              close.strip(), ""]
    return o


# --------------------------------------------------------------- main

def build(doc: str, full_text: bool) -> str:
    nodes = rows(NODES, doc)
    if not nodes:
        sys.exit(f"no claims for {doc!r} in data/nodes.csv - "
                 "run parse_maps.py, or see --list")
    edges = rows(EDGES, doc)
    facets = rows(FACETS, doc)
    passages = rows(PASSAGES, doc)
    indices = json.loads(INDICES.read_text(encoding="utf-8")) if INDICES.exists() else {}
    meta = map_header(doc)
    paras = load_paras(meta.get("url", ""))

    manifest = {}
    mf = EXTRACTED / "_manifest.csv"
    if mf.exists():
        for r in csv.DictReader(mf.open(encoding="utf-8")):
            if r.get("url") == meta.get("url"):
                manifest = r
    meta.setdefault("n_paragraphs", manifest.get("n_paragraphs", ""))

    allnotes = yaml.safe_load(NOTES.read_text(encoding="utf-8")) if NOTES.exists() else {}
    notes = ((allnotes or {}).get("documents") or {}).get(doc) or {}

    out = []
    out += panel_front(doc, nodes, edges, meta, manifest, notes)
    out += panel_article(paras, passages, full_text)
    out += panel_reading(nodes, passages, paras, notes, full_text)
    out += panel_map(doc, map_body(doc))
    out += panel_parse(nodes, edges)
    out += panel_subject(nodes, facets)
    out += panel_derived(doc, indices)
    out += panel_citation(doc, nodes, passages, meta, notes)
    # A reader who finds one of these should be able to find the other.
    siblings = sorted(((allnotes or {}).get("documents") or {}))
    if len(siblings) > 1:
        others = [d for d in siblings if d != doc]
        out += ["---", "", "## The other worked examples", "",
                "The same seven panels over a different article, which is the "
                "only way to tell what is the method and what is one article:",
                ""]
        for d in others:
            t = (map_header(d).get("title") or d)
            out.append(f"- **{t}** — `python scripts/worked_example.py --doc {d}`")
        out.append("")

    out += ["---", "",
            f"*Panels 1 and 3-7 are generated by `scripts/worked_example.py "
            f"--doc {doc}`. Panel 2 is hand-written in "
            "`scripts/worked_example_notes.yaml`. Regenerate after any pipeline "
            "run so the numbers cannot drift.*", ""]
    return "\n".join(out)


def listing() -> None:
    """Which articles could carry a worked example, best first."""
    n = Counter(r["doc"] for r in rows(NODES))
    allpass = rows(PASSAGES)
    a = Counter(r["doc"] for r in allpass if r["grade"] == "anchored")
    t = Counter(r["doc"] for r in allpass)
    print(f"{'doc':<42} {'claims':>6} {'anchored':>9} {'links':>6}")
    for d in sorted(n, key=lambda d: (-a[d] / max(t[d], 1), n[d])):
        print(f"{d:<42} {n[d]:>6} {a[d]:>9} {t[d]:>6}")
    print("\nRanked by the share of passage links that reach an anchor, then "
          "by size. A small map with good anchoring is the one a reader can "
          "check by hand, which is the whole point of the document.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--doc", help="document id, e.g. setser_mar_10_24")
    ap.add_argument("--out", help="write here instead of stdout")
    ap.add_argument("--full-text", action="store_true",
                    help="embed whole paragraphs (local only - internal/ is gitignored)")
    ap.add_argument("--list", action="store_true",
                    help="which articles are good candidates")
    args = ap.parse_args()

    if args.list:
        listing()
        return
    if not args.doc:
        ap.error("--doc is required (or --list)")

    text = build(args.doc, args.full_text)
    # The articles are full of curly quotes and em dashes; a Windows console
    # defaulting to cp437 turns them into question marks on the way out.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.out:
        p = ROOT / args.out
        p.write_text(text, encoding="utf-8")
        warn = "   (--full-text: do not commit this one)" if args.full_text else ""
        print(f"wrote {p.relative_to(ROOT)}  {len(text.splitlines())} lines{warn}")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
