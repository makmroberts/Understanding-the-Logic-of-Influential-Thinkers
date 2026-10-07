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

import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "data" / "graph.json"
SCHEMA_MAP = Path(__file__).resolve().parent / "schema_map.yaml"
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


def slot_names() -> set:
    """Headers that are schema slot labels rather than content.

    The banner/meta maps put the slot name in the bold header ("Hidden
    assumption") and the actual claim in the body; the plain maps put the claim
    itself in the header. Titling a note from the header blindly produces twenty
    notes called "Main claim", which is useless in a graph view.
    """
    smap = yaml.safe_load(SCHEMA_MAP.read_text(encoding="utf-8"))
    names = set(smap.get("node_types_by_header") or {})
    names |= {"implicit", "mechanism", "evidence", "studies & sources"}
    return names


def safe(text: str, limit: int = 70) -> str:
    text = ILLEGAL.sub("", " ".join(str(text).split())).strip(" .")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
    return text or "untitled"


def main() -> None:
    if not GRAPH.exists():
        raise SystemExit("data/graph.json missing - run scripts/parse_maps.py first")
    docs = json.loads(GRAPH.read_text(encoding="utf-8"))["documents"]

    # ---- note titles, unique across the vault -------------------------------
    slots = slot_names()
    titles: dict[tuple[str, str], str] = {}
    used: dict[str, int] = {}
    for d in docs:
        for ns in d["levels"].values():
            for n in ns:
                header, text = n["header"], " ".join((n["text"] or "").split())
                # a generic slot label makes a useless note title - prefer the claim
                label = text if (header.lower() in slots and text) else (header or text)
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

    art_title = {d["doc"]: safe(f"{d['date']} {d['meta']['title']}", 90) for d in docs}

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
            if n.get("concept"):
                fm.append(f'concept: {n["concept"]}')
            if n.get("mechanism_kind"):
                fm.append(f'mechanism_kind: {n["mechanism_kind"]}')
            if n["implicit_only"]:
                fm.append("implicit_only: true")
            fm += [f'tags: [type/{n["type"]}, level/{n["level"]}, family/{d["family"]}]',
                   "---", ""]

            body = [f"# {n['header'] or title}", ""]
            text = " ".join((n["text"] or "").split())
            if text and text != n["header"]:
                body += [f"> {text}", ""]

            if outgoing[nid]:
                body.append("## Leads to")
                for e in outgoing[nid]:
                    t = nodes[e["to"]]
                    rel = READABLE.get(e["type"] or "", e["type"] or "unresolved")
                    drawn = f' _(drawn as "{e["raw"]}")_' if e["raw"] and e["raw"] != rel else ""
                    body.append(f"- **{rel}** → [[{titles[(d['doc'], e['to'])]}]] "
                                f"`{t['type']}`{drawn}")
                body.append("")

            if incoming[nid]:
                body.append("## Rests on")
                for e in incoming[nid]:
                    s = nodes[e["from"]]
                    rel = READABLE.get(e["type"] or "", e["type"] or "unresolved")
                    body.append(f"- [[{titles[(d['doc'], e['from'])]}]] "
                                f"`{s['type']}` **{rel}** this")
                body.append("")

            body.append(f"## Source")
            body.append(f"- Article: [[{art_title[d['doc']]}]]")
            if n.get("concept"):
                body.append(f"- Concept: [[{n['concept']}]]")
            body.append(f"- Node `{d['doc']}#{nid}` · level {n['level']} · "
                        f"type resolved by `{n['type_source']}`")
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
            # a Dataview block for anyone who has the plugin; harmless without it
            body += ["```dataview",
                     "TABLE WITHOUT ID file.link AS Claim, date, article",
                     "FROM " + " OR ".join(f"#type/{t}" for t in types),
                     "SORT date ASC", "```", ""]
            for d, n in items:
                art = d["meta"]["title"]
                art = art[:44] + "..." if len(art) > 47 else art
                body.append(f"- **{d['date'][:7]}** [[{titles[(d['doc'], n['id'])]}]] "
                            f"· _{art}_")
            body.append("")
        (OUT / "views" / f"{view_name}.md").write_text(
            "\n".join(body) + "\n", encoding="utf-8")

    # ---- index --------------------------------------------------------------
    idx = ["# Argument maps", "",
           f"{sum(counts.values())} claims across {len(docs)} articles.", "",
           "Open the graph view (Ctrl/Cmd+G) and click any claim to expand it. "
           "Use the local-graph pane to follow one argument at a time.", "",
           "## Browse everything of one kind", ""]
    for name, total in view_links:
        idx.append(f"- [[{name}]] — {total}")
    idx += ["", "In the graph view, the filter box takes the same cuts:", "",
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
    idx += ["", "## Notes", "",
            "- Level 0 question notes have no outgoing links: the maps draw the "
            "question-to-priors link with mermaid's layout-only `~~~`, which carries "
            "no meaning, so no edge was recorded.",
            "- 201 of 340 edges are unlabelled in the source and default to "
            "**supports**. Where an edge states its own label it is shown in quotes.",
            "- Articles use three annotation templates (`plain`, `banner`, `meta`); "
            "the `family` tag on every note records which."]
    (OUT / "index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")

    # ---- graph colours ------------------------------------------------------
    groups = [{"query": f"path:claims/{t}", "color": {"a": 1, "rgb": int(c[1:], 16)}}
              for t, c in COLORS.items() if counts.get(t)]
    groups += [{"query": "path:articles", "color": {"a": 1, "rgb": int("C9A23D", 16)}},
               {"query": "path:concepts", "color": {"a": 1, "rgb": int("F0A8C4", 16)}}]
    # Obsidian writes your own tuning back into this file, so never clobber it
    # on a re-export - the colour groups only need writing once.
    graph_cfg = OUT / ".obsidian" / "graph.json"
    if graph_cfg.exists():
        print("  kept your existing .obsidian/graph.json (delete it to reset colours)")
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

    print(f"obsidian/  ->  {sum(counts.values())} claims, {len(docs)} articles, "
          f"{len(concepts)} concepts")
    print("  In Obsidian: Open folder as vault ->", OUT)
    print("  Then Ctrl/Cmd+G for the graph. Colour groups are preset by claim type.")


if __name__ == "__main__":
    main()
