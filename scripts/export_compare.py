#!/usr/bin/env python3
"""Hand-drawn map vs the model's map, side by side, one canvas per scored article.

    python scripts/export_compare.py            # -> obsidian/compare/*.canvas

Reads   data/nodes.csv, data/edges.csv, data/documents.csv   (the hand-drawn maps)
        obsidian/claims/**/*.md                (for the "open note" link on hand cards)
        annotation/articles/<doc>/<model>/annotation.json   (the official model run)
        annotation/src/annotate/evaluate.py    (the box matcher, imported, not copied)
Writes  obsidian/compare/<date> <title> (hand vs model).canvas
        obsidian/compare/_index.md

Nothing under annotation/ is written. Run export_obsidian.py first, so the hand
cards' "open note" links resolve.

WHAT IS ON A CANVAS

The hand map is on the left and the model's map on the right, both laid out by level
(question at the top, concessions at the bottom), so a step and its counterpart sit
on the same row. Cards are coloured by Toulmin family on both sides.

Both sides use the same card, built from the fields both processes produce:

    P1 · stated_assumption · ¶ 4, 7
    <claim>
    Gloss: ...   (hand: the annotator's note)    Why: ...   (model: the rule relied on)

The ¶ numbers are the paragraphs the matcher pairs on. The third line differs on
purpose: a gloss and a "why" are different kinds of note, so each keeps its label,
and it is left out when a step has none.

Cyan U-shaped edges under each row join the pairs the annotation pipeline's matcher
finds, the same pairs as that run's evaluation.md. Matched cards sit nearest the
middle, in mirrored order, so the U's nest instead of crossing; unmatched cards sit
on the outside. The label says how the pair was made. "paragraph": the two steps cite
a common paragraph. "slot": only the role matched, so read the two side by side. The
card above the two maps lists the unmatched steps.

Edges inside each map carry the relation and its sign, as in export_canvas.py.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "annotation" / "src"))

from export_canvas import (CARD_H, CARD_W, EDGE_COLOR, FAMILY_COLOR, GAP_X,  # noqa: E402
                           GAP_Y, LEVELS, SIGN, note_index, write_snippet)
from export_obsidian import is_slot_label, slot_names, slot_nouns  # noqa: E402
from annotate.evaluate import hand_map, match, model_map  # noqa: E402

NODES = ROOT / "data" / "nodes.csv"
EDGES = ROOT / "data" / "edges.csv"
DOCS = ROOT / "data" / "documents.csv"
SCHEMA = ROOT / "scripts" / "schema_map.yaml"
RUNS = ROOT / "annotation" / "articles"
VAULT = ROOT / "obsidian"
OUT = VAULT / "compare"

SIDE_GAP = 600          # between the two maps
PAIR_COLOR = "5"        # cyan preset: the matcher's pairs
HEADER_H = 260


def official_run(doc: str) -> Path | None:
    """The one official run of an article, or None. More than one is ambiguous."""
    runs = [p.parent for p in (RUNS / doc).glob("*/annotation.json")]
    return runs[0] if len(runs) == 1 else None


def flat(s: str | None) -> str:
    return " ".join((s or "").split())


def card_text(c: dict) -> str:
    """The shared card format: id · role · paragraphs, claim, then gloss or why."""
    head = f"**{c['id']}** · `{c['role']}`"
    if c["paragraphs"]:
        head += " · ¶ " + ", ".join(str(p) for p in c["paragraphs"])
    out = [head, "", c["claim"]]
    if c.get("note"):
        out += ["", f"*{c['note_label']}:* {c['note']}"]
    if c.get("link"):
        out += ["", c["link"]]
    return "\n".join(out)


def layout(cards: list[dict], rank: dict, side: str, y0: int) -> dict:
    """Card id -> (x, y). One row per level, the same rows on both sides.

    Matched cards sit nearest the middle in mirrored order (pair 0 innermost on both
    sides), so the U-shaped pair edges nest; unmatched cards go on the outside.
    """
    rows = defaultdict(list)
    for c in cards:
        rows[c["level"]].append(c)
    inner = SIDE_GAP // 2
    pos, y = {}, y0
    for lv in LEVELS + sorted(set(rows) - set(LEVELS)):
        row = sorted(rows.get(lv, []),
                     key=lambda c: (c["id"] not in rank, rank.get(c["id"], 0), c["id"]))
        for i, c in enumerate(row):              # i = 0 is the card nearest the middle
            off = inner + i * (CARD_W + GAP_X)
            pos[c["id"]] = (-off - CARD_W if side == "hand" else off, y)
        y += CARD_H + GAP_Y      # empty levels still take a row, so both sides line up
    return pos


def main() -> None:
    spec = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    fam = {t: f for f, m in spec["role_families"]["toulmin"].items() for t in m}
    color = lambda role: FAMILY_COLOR.get(fam.get(role), "#AAAAAA")
    nodes = list(csv.DictReader(NODES.open(encoding="utf-8")))
    edges = list(csv.DictReader(EDGES.open(encoding="utf-8")))
    meta = {d["id"]: d for d in csv.DictReader(DOCS.open(encoding="utf-8"))}
    paths = note_index()
    slots, nouns = slot_names(), slot_nouns()

    hand_nodes = defaultdict(list)
    for n in nodes:
        hand_nodes[n["doc"]].append(n)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.canvas"):            # this folder is generated; drop renamed leftovers
        old.unlink()
    made, warnings = [], []
    for doc in sorted(hand_nodes, key=lambda d: meta.get(d, {}).get("date", "")):
        run = official_run(doc)
        if run is None:
            continue
        ann = json.loads((run / "annotation.json").read_text(encoding="utf-8"))
        m, h = model_map(run), hand_map(doc)

        # The matcher reads annotation/kb/data. Check it sees the same hand map as this vault.
        root_ids = {n["node_id"] for n in hand_nodes[doc]}
        if root_ids != {b["id"] for b in h["boxes"]}:
            warnings.append(f"{doc}: hand node IDs differ between data/ and annotation/kb/data; "
                            "pairs may not line up")
        pairs = match(m["boxes"], h["boxes"])          # model id -> (hand id, how)
        order = sorted(pairs.items(), key=lambda kv: kv[1][0])
        mrank = {mid: i for i, (mid, _) in enumerate(order)}
        hrank = {hid: i for i, (_, (hid, _)) in enumerate(order)}

        hpar = {b["id"]: b["paragraphs"] for b in h["boxes"]}
        mpar = {b["id"]: b["paragraphs"] for b in m["boxes"]}

        hand_cards = []
        for n in hand_nodes[doc]:
            header, text = flat(n["header"]), flat(n["text"])
            # same rule as export_obsidian.py: a slot label is not the claim
            claim = text if (is_slot_label(header, slots, nouns) and text) else (header or text)
            note = text if text and text != claim else (header if header and header != claim else "")
            rel = paths.get((doc, n["node_id"]))
            hand_cards.append({"id": n["node_id"], "level": n["level"] or "?", "role": n["type"],
                               "claim": claim, "note": note, "note_label": "Gloss",
                               "paragraphs": hpar.get(n["node_id"], []),
                               "link": f"[[{rel[:-3]}|open note]]" if rel else ""})
        model_cards = [{"id": n["legacy_id"], "level": n.get("level") or "?", "role": n["role"],
                        "claim": flat(n["content"]["text"]), "note": flat(n["content"].get("reason")),
                        "note_label": "Why", "paragraphs": mpar.get(n["legacy_id"], [])}
                       for n in ann["nodes"]]

        y0 = HEADER_H + GAP_Y
        hpos = layout(hand_cards, hrank, "hand", y0)
        mpos = layout(model_cards, mrank, "model", y0)

        cnodes, cedges = [], []
        for side, cards, pos in (("hand", hand_cards, hpos), ("model", model_cards, mpos)):
            for c in cards:
                x, y = pos[c["id"]]
                cnodes.append({"id": f"{side}-{c['id']}", "type": "text", "text": card_text(c),
                               "x": x, "y": y, "width": CARD_W, "height": CARD_H,
                               "color": color(c["role"])})

        def signed(rel: str, s: int, suffix: str = "") -> str:
            return f"{'+1' if s > 0 else '-1' if s < 0 else '0'} {rel}{suffix}"

        for e in edges:                                # inside the hand map
            if e["doc"] == doc:
                s = SIGN.get(e["type"], 0)
                cedges.append({"id": f"h-{e['from']}-{e['to']}",
                               "fromNode": f"hand-{e['from']}", "fromSide": "bottom",
                               "toNode": f"hand-{e['to']}", "toSide": "top", "color": EDGE_COLOR[s],
                               "label": signed(e["type"], s, " ~" if e.get("relation_source")
                                               == "layout_operator" else "")})
        legacy = {n["id"]: n["legacy_id"] for n in ann["nodes"]}
        for e in ann["edges"]:                         # inside the model map
            s = e.get("sign", SIGN.get(e["relation"], 0))
            cedges.append({"id": f"m-{e['id']}",
                           "fromNode": f"model-{legacy[e['from']]}", "fromSide": "bottom",
                           "toNode": f"model-{legacy[e['to']]}", "toSide": "top",
                           "color": EDGE_COLOR.get(s, "6"), "label": signed(e["relation"], s)})
        for mid, (hid, how) in order:                  # the matcher's pairs, nested U's
            cedges.append({"id": f"p-{hid}-{mid}", "fromNode": f"hand-{hid}", "fromSide": "bottom",
                           "toNode": f"model-{mid}", "toSide": "bottom", "color": PAIR_COLOR,
                           "label": how})

        known = {c["id"] for c in cnodes}
        dangling = [e["id"] for e in cedges if e["fromNode"] not in known or e["toNode"] not in known]
        if dangling:
            warnings.append(f"{doc}: {len(dangling)} edges point at a missing card; dropped")
            cedges = [e for e in cedges if e["id"] not in dangling]

        un_h = sorted(c["id"] for c in hand_cards if c["id"] not in hrank)
        un_m = sorted(c["id"] for c in model_cards if c["id"] not in mrank)
        by_par = sum(how == "paragraph" for _, (_, how) in order)
        mt = meta.get(doc, {})
        title = re.sub(r'[\\/:*?"<>|#^\[\]]', "", mt.get("title") or doc)
        header = [f"## {mt.get('date', '')} {title}", "",
                  f"**Left:** hand-drawn map ({len(hand_cards)} steps). "
                  f"**Right:** model run `{run.parent.name}/{run.name}` ({len(model_cards)} steps).", "",
                  f"Matched {len(pairs)} of {len(hand_cards)} hand steps "
                  f"({by_par} by a shared paragraph, {len(pairs) - by_par} by role only).", "",
                  f"Hand steps not matched: {', '.join(un_h) or 'none'}", "",
                  f"Model steps not matched: {', '.join(un_m) or 'none'}"]
        xs = [n["x"] for n in cnodes]
        left, right = min(xs), max(xs) + CARD_W
        cnodes.insert(0, {"id": "header", "type": "text", "text": "\n".join(header),
                          "x": left, "y": 0, "width": right - left, "height": HEADER_H})

        stem = " ".join(f"{mt.get('date', '')} {title}".split())
        if len(stem) > 100:                            # cut at a word, not mid-word
            stem = stem[:100].rsplit(" ", 1)[0]
        name = f"{stem} (hand vs model)"
        (OUT / f"{name}.canvas").write_text(json.dumps({"nodes": cnodes, "edges": cedges}, indent=1),
                                            encoding="utf-8")
        made.append((name, len(hand_cards), len(model_cards), len(pairs), by_par))

    idx = ["---", "type: index", "tags: [canvas, compare]", "---", "",
           "# Hand-drawn vs model maps", "",
           "One canvas per article that has both a hand-drawn map and an official model run. "
           "The hand map is on the left and the model's map on the right, laid out by level, "
           "with the same card on both sides: ID, role, cited paragraphs (¶), the claim, and "
           "the hand map's gloss or the model's \"why\".", "",
           "Cyan edges are the pairs found by the annotation pipeline's box matcher "
           "(`annotation/src/annotate/evaluate.py`), the same pairs as that run's `evaluation.md`. "
           "`paragraph` means the two steps cite a common paragraph; `slot` means only the role "
           "matched. Unmatched cards sit on the outside of each row.", "",
           "The hand map is one person's reading, not a gold standard.", "",
           "| canvas | hand steps | model steps | matched | by paragraph |", "|---|---|---|---|---|"]
    for name, nh, nm, np_, bp in made:
        idx.append(f"| [[{name}.canvas\\|{name}]] | {nh} | {nm} | {np_} | {bp} |")
    idx += ["", "Back to [[index]]."]
    (OUT / "_index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")

    state = write_snippet()
    print(f"obsidian/compare/  ->  {len(made)} canvases")
    for name, nh, nm, np_, bp in made:
        print(f"  {np_:>2}/{nh:<2} hand steps matched ({bp} by paragraph), {nm} model steps  {name}")
    print(f"  card CSS snippet: {state}")
    for w in warnings:
        print(f"  WARNING: {w}")


if __name__ == "__main__":
    main()
