#!/usr/bin/env python3
"""Lay each article out as an Obsidian Canvas, by argument level.

    python scripts/export_canvas.py            # -> obsidian/canvas/*.canvas

Reads   data/nodes.csv, data/edges.csv, data/documents.csv
        obsidian/claims/**/*.md   (to resolve each claim to its note path)
Writes  obsidian/canvas/<date> <title>.canvas, one per article
        obsidian/canvas/_index.md

WHY, GIVEN THE GRAPH VIEW ALREADY EXISTS

Obsidian's graph is force-directed and has no layered layout, so it cannot be
tuned into a hierarchy - at mean degree 14 it is a hairball, and the honest fix
there is a filter (`-path:subjects -path:views -file:index` takes mean degree to
4.4). But the hierarchy is real and it is in the data: every claim carries the
level the annotator drew it at, L0 for the question through L6 for the
concessions.

Canvas takes absolute coordinates, so that hierarchy can be drawn rather than
simulated. One canvas per article: the question at the top, priors below it,
then evidence, mechanisms, intermediate steps, conclusions, and the
counterpoints at the bottom. Every card is the real note, so clicking opens the
claim with its facets, provenance and passage.

WHAT THE COLOURS AND LABELS MEAN

Cards are coloured by Toulmin family, so the same palette works for any
annotation scheme mapped onto it. Edges carry the relation and its sign, and a
dashed-looking grey edge is one recovered from the maps' `~~~` operator - those
are the question-to-prior and prior-to-datum links, which have no label in the
source and are typed by convention. Seeing them as a distinct colour is the
point: the top of every argument is held together by edges nobody wrote down.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NODES = ROOT / "data" / "nodes.csv"
EDGES = ROOT / "data" / "edges.csv"
DOCS = ROOT / "data" / "documents.csv"   # written by parse_maps.py
SCHEMA = ROOT / "scripts" / "schema_map.yaml"
VAULT = ROOT / "obsidian"
OUT = VAULT / "canvas"

LEVELS = ["L0", "L1", "L1B", "L2", "L3", "L4", "L5", "L6"]
# Cards are deliberately large: a card shows the claim and its gloss, and
# a claim is a sentence, not a label. At 300x120 the body clipped and only
# the heading showed - which is also how a note titled with a slot label
# rather than its claim went unnoticed.
CARD_W, CARD_H = 520, 300
GAP_X, GAP_Y = 60, 180

# Canvas supports six preset colours ("1".."6") or a hex string. Hex keeps the
# palette aligned with the vault's own role colours.
FAMILY_COLOR = {
    "framing":    "#7A6FA8",
    "warrant":    "#8F4FBF",
    "grounds":    "#2F7FBF",
    "claim":      "#2FBF9B",
    "qualifier":  "#9A8C6A",
    "rebuttal":   "#8A8A8A",
    "backing":    "#2FA88F",
    "revision":   "#BF6F2F",
    "unassigned": "#AAAAAA",
}
SIGN = {"supports": 1, "licenses": 1, "bounds": 1, "motivates": 1,
        "reconstructs": 1, "revises": -1, "rebuts": -1, "qualified_by": -1,
        "undercut_by": -1, "defers": 0, "frames": 0}
EDGE_COLOR = {1: "4", -1: "1", 0: "6"}      # green / red / grey presets


SNIPPET = """/* Canvas cards: smaller type, so a claim fits in its card.
 *
 * A canvas file-card renders the whole note, and a claim note opens with its
 * text as an H1 - which is why cards look shouty at default sizes. This shrinks
 * type inside cards only; the notes themselves are untouched everywhere else.
 *
 * Written and enabled by scripts/export_canvas.py. Edit --canvas-card-font to
 * taste: the rest scales off it.
 */

.canvas-node-content {
  --canvas-card-font: 11px;
}

.canvas-node-content .markdown-preview-view,
.canvas-node-content .markdown-rendered {
  font-size: var(--canvas-card-font);
  line-height: 1.35;
}

/* the claim itself - an H1 in the note, a title in the card */
.canvas-node-content .markdown-rendered h1,
.canvas-node-content .markdown-rendered h2,
.canvas-node-content .markdown-rendered h3 {
  font-size: calc(var(--canvas-card-font) * 1.15);
  line-height: 1.25;
  margin: 0 0 0.3em 0;
  font-weight: 600;
  border: none;
  padding: 0;
}

/* the gloss, which the plain-family maps put in italics under the claim */
.canvas-node-content .markdown-rendered blockquote {
  font-size: calc(var(--canvas-card-font) * 0.95);
  margin: 0.2em 0;
  padding-left: 0.6em;
  border-left-width: 2px;
}

.canvas-node-content .markdown-rendered ul,
.canvas-node-content .markdown-rendered ol {
  padding-left: 1.1em;
  margin: 0.2em 0;
}

.canvas-node-content .markdown-rendered code {
  font-size: calc(var(--canvas-card-font) * 0.9);
}

/* The properties block is 14 lines of facets and provenance. Useful in the
 * note, noise in a 300x120 card - the facets are on the hub notes and in the
 * card's own note one click away. */
.canvas-node-content .metadata-container,
.canvas-node-content .frontmatter-container,
.canvas-node-content .mod-header,
.canvas-node-content .mod-footer {
  display: none !important;
}

/* edge labels, which carry the sign and the relation */
.canvas-edge-label {
  font-size: 10px;
}
"""


def write_snippet() -> str:
    """Ship the card CSS with the vault and switch it on.

    Self-healing, the same contract as the graph colour groups: Obsidian owns
    these files and will rewrite them, so the exporter asserts its snippet and
    merges rather than replacing whatever else is in appearance.json.
    """
    cfg = VAULT / ".obsidian"
    snips = cfg / "snippets"
    snips.mkdir(parents=True, exist_ok=True)
    (snips / "canvas-cards.css").write_text(SNIPPET, encoding="utf-8")

    ap = cfg / "appearance.json"
    data = {}
    if ap.exists():
        try:
            data = json.loads(ap.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            data = {}
    enabled = data.get("enabledCssSnippets") or []
    if "canvas-cards" not in enabled:
        enabled.append("canvas-cards")
        data["enabledCssSnippets"] = enabled
        ap.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return "written and enabled"
    data["enabledCssSnippets"] = enabled
    ap.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return "already enabled"


def note_index() -> dict:
    """(doc, node_id) -> vault-relative path of its claim note.

    Read out of the exported notes rather than recomputed, so this cannot drift
    from export_obsidian.py's filename rules.
    """
    out = {}
    for p in (VAULT / "claims").rglob("*.md"):
        head = p.read_text(encoding="utf-8")[:600]
        doc = re.search(r"^doc:\s*(\S+)", head, re.M)
        nid = re.search(r"^node_id:\s*(\S+)", head, re.M)
        if doc and nid:
            out[(doc.group(1), nid.group(1))] = p.relative_to(VAULT).as_posix()
    return out


def main() -> None:
    spec = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    fam = {t: f for f, m in spec["role_families"]["toulmin"].items() for t in m}
    nodes = list(csv.DictReader(NODES.open(encoding="utf-8")))
    edges = list(csv.DictReader(EDGES.open(encoding="utf-8")))
    meta = {d["id"]: d for d in csv.DictReader(DOCS.open(encoding="utf-8"))}
    paths = note_index()

    by_doc = defaultdict(list)
    for n in nodes:
        by_doc[n["doc"]].append(n)

    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    missing = 0
    for doc, ns in sorted(by_doc.items(), key=lambda kv: meta.get(kv[0], {}).get("date", "")):
        rows = defaultdict(list)
        for n in ns:
            rows[n["level"] or "?"].append(n)

        cnodes, pos = [], {}
        y = 0
        for lv in LEVELS:
            row = sorted(rows.get(lv, []), key=lambda n: n["node_id"])
            if not row:
                continue
            width = len(row) * CARD_W + (len(row) - 1) * GAP_X
            x0 = -width // 2
            for i, n in enumerate(row):
                key = (n["doc"], n["node_id"])
                rel = paths.get(key)
                if not rel:
                    missing += 1
                    continue
                x = x0 + i * (CARD_W + GAP_X)
                pos[key] = (x, y)
                cnodes.append({
                    "id": f"{n['doc']}-{n['node_id']}",
                    "type": "file", "file": rel,
                    "x": x, "y": y, "width": CARD_W, "height": CARD_H,
                    "color": FAMILY_COLOR.get(fam.get(n["type"]), "#AAAAAA"),
                })
            y += CARD_H + GAP_Y

        cedges = []
        for e in edges:
            if e["doc"] != doc:
                continue
            a, b = (doc, e["from"]), (doc, e["to"])
            if a not in pos or b not in pos:
                continue
            s = SIGN.get(e["type"], 0)
            # a recovered layout edge gets the neutral colour and says so
            lab = e["type"]
            if e.get("relation_source") == "layout_operator":
                lab = f"{e['type']} ~"
            cedges.append({
                "id": f"{e['from']}-{e['to']}",
                "fromNode": f"{doc}-{e['from']}", "fromSide": "bottom",
                "toNode": f"{doc}-{e['to']}", "toSide": "top",
                "label": f"{'+1' if s > 0 else '-1' if s < 0 else '0'} {lab}",
                "color": EDGE_COLOR[s],
            })

        m = meta.get(doc, {})
        # Shares the article note's prefix so the two sort together, and ends
        # with " (map)" so they are TELLABLE APART. An earlier version matched
        # the article note's name exactly, which made every article appear
        # twice in the explorer and the quick switcher - same display name, one
        # .md and one .canvas.
        title = re.sub(r'[\\/:*?"<>|#^\[\]]', "", (m.get("title") or doc))
        stem = " ".join(f"{m.get('date', '')} {title}".split())[:108].strip()
        name = f"{stem} (map)"
        (OUT / f"{name}.canvas").write_text(
            json.dumps({"nodes": cnodes, "edges": cedges}, indent=1),
            encoding="utf-8")
        made.append((name, len(cnodes), len(cedges)))

    idx = ["---", "type: index", "tags: [canvas]", "---", "",
           "# Canvases, one per article", "",
           "Obsidian's graph view is force-directed, so it cannot draw a "
           "hierarchy. These can: each canvas places the article's claims at "
           "the level the annotator drew them, question at the top through "
           "concessions at the bottom. Every card is the claim's own note.", "",
           "Cards are coloured by Toulmin family. Edge labels carry the sign "
           "(**+1** backs, **-1** pushes back, **0** neither) and the "
           "relation; a relation suffixed `~` was recovered from the map's "
           "invisible `~~~` operator and typed by convention, which is most of "
           "the question-to-prior and prior-to-evidence structure.", "",
           "| canvas | cards | links |", "|---|---|---|"]
    for name, nn, ne in made:
        idx.append(f"| [[{name}.canvas\\|{name}]] | {nn} | {ne} |")
    idx += ["", "Back to [[index]]."]
    (OUT / "_index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")

    state = write_snippet()
    print(f"obsidian/canvas/  ->  {len(made)} canvases")
    print(f"  card CSS snippet: {state} "
          f"(.obsidian/snippets/canvas-cards.css)")
    print(f"  {sum(n for _, n, _ in made)} cards, {sum(e for _, _, e in made)} links")
    if missing:
        print(f"  WARNING: {missing} claims had no note to point at")
    print("  In Obsidian: open obsidian/canvas/_index.md and click a canvas.")


if __name__ == "__main__":
    main()
