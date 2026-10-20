#!/usr/bin/env python3
"""predict-vs-actual — the deterministic half of the skill.

The AI decides what goes in each box. This script decides everything else:
which notes the predictor may see, whether the boxes follow the rules, how the
two charts are laid out, and how they are scored. Same JSON in, same charts out.

    python pva.py check                         data, template and sources.yaml agree?
    python pva.py freeze   --before DATE --title "..." --run RUN
    python pva.py validate RUN/predicted.json
    python pva.py lock     RUN
    python pva.py validate RUN/actual.json
    python pva.py render   RUN [--replicate RUN2 ...]
    python pva.py template [--out FILE.mmd]     copy of the agreed architecture into examples/template/
    python pva.py example  RUN                  copy a finished run into examples/<run name>/

RUN is one folder per test, e.g. internal/pva/2020-10-05_record-chinese.
Every path and name comes from sources.yaml next to this file.
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is needed (the team's parse_maps.py uses it too): pip install pyyaml")

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources.yaml"

FILLED = ("filled", "implicit")
DEFINITE = ("filled", "implicit", "absent", "na")
STATUSES = ("filled", "implicit", "absent", "na", "unsure", "unavailable")
VERDICTS = ("match", "close", "opposite")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
STOP = set("""a an and are as at be by for from has have how in is it its of on or that the
their this to was were what when which who why will with not than into over under about after
before more most new""".split())

MARK = {"match": "✓", "close": "≈", "opposite": "≠", "wrong": "✗", "missed": "★", "gap": "◇"}
MEANING = {
    "match": "slot and content right",
    "close": "right slot, close content",
    "opposite": "right slot, content contradicts the prediction",
    "wrong": "predicted, not in the article",
    "missed": "in the article, predicted empty",
    "gap": "in the article — the framework had no slot for it yet",
    "slot_only": "slot predicted, content not given — not scored",
}


# ================================================================ config =====

class Cfg:
    """sources.yaml, plus everything derived from it."""

    def __init__(self, root: Path):
        self.root = root
        self.s = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
        d = self.s["data"]
        self.nodes_path = root / d["nodes"]
        self.edges_path = root / d["edges"]
        self.schema_path = root / d["schema"]
        self.template_path = root / d["template"]
        self.col = d["columns"]
        self.show = d.get("show_columns") or []
        self.codebook = HERE / self.s["codebook"] if self.s.get("codebook") else None
        self.stages = self.s["stages"]
        self.repeat = self.s.get("repeat", {}) or {}
        self.names = self.s["slot_names"]
        e = self.s["edges"]
        self.forward, self.pushback = set(e["forward"]), set(e["pushback"])
        self.reverse_label = e.get("reverse_label", {}) or {}
        self.edge_types = self.forward | self.pushback
        w = self.s["writing"]
        self.max_label, self.max_note = w["max_label_words"], w["max_note_words"]
        self.max_finding = w.get("max_finding_words", 25)
        fz = self.s.get("freeze", {}) or {}
        self.max_notes = int(fz.get("max_notes", 10 ** 9))
        self.keep_recent = int(fz.get("always_keep_recent", 0))
        self.pal = self.s["palette"]

        self.slot_stage, self.stage_rank, self.slots = {}, {}, []
        for i, st in enumerate(self.stages):
            self.stage_rank[st["id"]] = i
            for sl in st["slots"]:
                if sl in self.slot_stage:
                    die(f"sources.yaml: slot {sl!r} is listed in two stages")
                self.slot_stage[sl] = st["id"]
                self.slots.append(sl)
        self.all_boxes = [b for sl in self.slots for b in self.boxes(sl)]
        self.box_rank = {b: i for i, b in enumerate(self.all_boxes)}

    def boxes(self, slot: str) -> list[str]:
        """Box ids for a slot: 'mechanism', 'mechanism_2', ..."""
        n = int(self.repeat.get(slot, 1))
        return [slot] + [f"{slot}_{i}" for i in range(2, n + 1)]

    def box_name(self, slot: str, i: int) -> str:
        base = self.names.get(slot, slot)
        return f"{base} {chr(ord('A') + i)}" if int(self.repeat.get(slot, 1)) > 1 else base

    def stage_of(self, box: str) -> str:
        return self.slot_stage[base_slot(self, box)]

    def guard(self, path: Path) -> None:
        rel = os.path.relpath(path.resolve(), self.root.resolve()).replace("\\", "/")
        for bad in self.s.get("never_write", []):
            if rel == bad or rel.startswith(bad.rstrip("/") + "/"):
                die(f"refusing to write under {bad}/ — see never_write in sources.yaml")


def die(msg: str) -> None:
    sys.exit(f"pva: {msg}")


def base_slot(cfg: Cfg, box: str) -> str:
    if box in cfg.slot_stage:
        return box
    m = re.match(r"^(.*)_(\d+)$", box)
    return m.group(1) if m and m.group(1) in cfg.slot_stage else box


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        die(f"{path} not found — fix the path in sources.yaml")
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_json(path: Path) -> dict:
    if not path.exists():
        die(f"{path} not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")


# ================================================================= check =====

def clean_label(s: str) -> str:
    s = re.sub(r"<i>.*?</i>", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&amp;", "&").replace("#quot;", '"')
    return re.sub(r"\s+", " ", s).strip().rstrip("·").strip()


def template_names(cfg: Cfg) -> tuple[dict, dict]:
    """(stage id -> label, slot -> [box headers]) as written in the agreed template."""
    t = cfg.template_path.read_text(encoding="utf-8")
    stages = {m.group(1): clean_label(m.group(2))
              for m in re.finditer(r'subgraph\s+(\w+)\s*\["(.*?)"\]', t, re.S)}
    by_header = {}
    if cfg.schema_path.exists():
        by_header = yaml.safe_load(cfg.schema_path.read_text(encoding="utf-8")).get("node_types_by_header", {})
    slots: dict[str, list] = {}
    for m in re.finditer(r'^\s*\w+\["(.*?)"\]', t, re.M | re.S):
        hb = re.search(r"<b>(.*?)</b>", m.group(1), re.S)
        if not hb:
            continue
        header = clean_label(hb.group(1))
        typ = by_header.get(header.lower())
        if typ:
            slots.setdefault(typ, []).append(header)
    return stages, slots


def cmd_check(cfg: Cfg, args) -> None:
    """Stop loudly if sources.yaml, the data and the template disagree."""
    problems, notes = [], []
    nodes, edges = read_csv(cfg.nodes_path), read_csv(cfg.edges_path)
    c = cfg.col

    for label, rows, keys in (("nodes", nodes, ["doc", "date", "node_id", "type", "level", "text"]),
                              ("edges", edges, ["doc", "date", "edge_from", "edge_to", "edge_type", "edge_raw"])):
        have = set(rows[0].keys()) if rows else set()
        for k in keys:
            if c[k] not in have:
                problems.append(f"{label}: column {c[k]!r} (columns.{k}) not found; has {sorted(have)}")
    if problems:
        report(problems, notes)
    have = set(nodes[0].keys()) if nodes else set()
    for k in cfg.show:
        if k not in have:
            notes.append(f"show_columns: {k!r} is not in the data yet — freeze will show it once it is")
    if cfg.codebook and not cfg.codebook.exists():
        notes.append(f"codebook {cfg.codebook} not found — mapping the actual chart needs it")

    for r in nodes:
        t, lv = r[c["type"]], r[c["level"]]
        ref = f"{r[c['doc']]}#{r[c['node_id']]}"
        if t not in cfg.slot_stage:
            if t == "counterpoint":
                notes.append(f"{ref}: generic 'counterpoint' — the parser could not tell which L6 slot")
            else:
                problems.append(f"data has slot {t!r} ({ref}) — add it to a stage in sources.yaml")
        elif cfg.slot_stage[t] != lv:
            problems.append(f"{ref}: {t} is at {lv} in the data but in stage {cfg.slot_stage[t]} in sources.yaml")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", r[c["date"]] or ""):
            problems.append(f"{r[c['doc']]}: date {r[c['date']]!r} is not YYYY-MM-DD")

    for sl in cfg.slots:
        if sl not in cfg.names:
            problems.append(f"slot {sl!r} has no entry in slot_names")

    if cfg.schema_path.exists():
        schema = yaml.safe_load(cfg.schema_path.read_text(encoding="utf-8"))
        canon = set((schema.get("edge_types") or {}).values())
        for t in sorted(canon - cfg.edge_types):
            problems.append(f"schema edge type {t!r} is in neither edges.forward nor edges.pushback")
        for t in sorted(cfg.edge_types - canon):
            notes.append(f"edge type {t!r} is in sources.yaml but not in schema_map.yaml")
    else:
        problems.append(f"{cfg.schema_path} not found")
    for t in sorted(cfg.pushback - set(cfg.reverse_label)):
        problems.append(f"pushback type {t!r} has no entry in edges.reverse_label")

    for e in edges:
        if e[c["edge_type"]] and e[c["edge_type"]] not in cfg.edge_types:
            problems.append(f"edge type {e[c['edge_type']]!r} in data is not in sources.yaml edges")

    # names must match the agreed template, word for word
    if cfg.template_path.exists():
        t_stages, t_slots = template_names(cfg)
        for st in cfg.stages:
            want = t_stages.get(st["id"])
            if want is None:
                problems.append(f"stage {st['id']} is not in the template")
            elif want != st["name"]:
                problems.append(f"stage {st['id']}: template says {want!r}, sources.yaml says {st['name']!r}")
        for sl in cfg.slots:
            mine = [cfg.box_name(sl, i) for i in range(len(cfg.boxes(sl)))]
            theirs = t_slots.get(sl)
            if not theirs:
                problems.append(f"slot {sl!r} has no box in the template")
            elif sorted(mine) != sorted(theirs):
                problems.append(f"slot {sl!r}: template says {theirs}, sources.yaml gives {mine}")
    else:
        problems.append(f"{cfg.template_path} not found")

    unl = sum(1 for e in edges if not e[c["edge_raw"]])
    notes.append(f"{len(nodes)} nodes, {len(edges)} edges, {len({r[c['doc']] for r in nodes})} articles")
    notes.append(f"{unl} of {len(edges)} edges carry no label in the source map and were defaulted to 'supports'")
    report(problems, notes)


def report(problems: list, notes: list) -> None:
    for n in dict.fromkeys(notes):
        print(f"  note  {n}")
    if problems:
        for p in dict.fromkeys(problems):
            print(f"  FAIL  {p}")
        die(f"{len(set(problems))} problem(s). Fix sources.yaml or the data, then re-run check.")
    print("check: sources.yaml, the data and the template agree")


# ================================================================ freeze =====

def content_words(s: str) -> set:
    return {w for w in re.findall(r"[a-z][a-z\-']+", s.lower()) if len(w) > 2 and w not in STOP}


def tok_key(w: str) -> str:
    """Compare words without case or a trailing possessive."""
    return re.sub(r"['’]s$", "", w.lower()).strip("'")


def note_extras(cfg: Cfg, r: dict) -> tuple[list, list]:
    """The show_columns of one note -> (short tags, longer 'name: value' parts)."""
    tags, longer = [], []
    for k in cfg.show:
        v = " ".join((r.get(k) or "").split())
        if not v or v.lower() in ("0", "false", "no", "none"):
            continue
        if v.lower() in ("1", "true", "yes"):
            tags.append(k.replace("_only", ""))
        elif " " not in v and len(v) <= 40:
            tags.append(f"{k.replace('_', ' ')}: {v}")
        else:
            longer.append(f"{k.replace('_', ' ')}: {v}")
    return tags, longer


def cmd_freeze(cfg: Cfg, args) -> None:
    """Everything published before the cutoff, and the slot types that existed then."""
    cut = args.before
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", cut):
        die("--before must be YYYY-MM-DD")
    run = Path(args.run)
    cfg.guard(run)
    if (run / "predicted.json").exists() and not args.force:
        die(f"{run} already holds a prediction — use a new run folder (e.g. {run.name}_r2) "
            "so an earlier test is never overwritten, or pass --force to re-freeze it")
    run.mkdir(parents=True, exist_ok=True)
    if len(str(run.resolve())) + 110 > 240:
        print(f"  warn  {run} is deep — on Windows the article file may pass 260 characters. "
              f"Use a shorter run name.")
    c = cfg.col
    docre = re.compile(args.docs) if args.docs else None
    budget = args.max_notes or cfg.max_notes

    def keep(r):
        return r[c["date"]] < cut and (not docre or docre.search(r[c["doc"]]))
    all_nodes = [r for r in read_csv(cfg.nodes_path) if keep(r)]
    all_edges = [r for r in read_csv(cfg.edges_path) if keep(r)]
    if not all_nodes:
        die(f"no notes dated before {cut}" + (f" matching --docs {args.docs!r}" if docre else ""))

    # the slot vocabulary comes from everything before the cutoff, selected or not
    allowed = sorted({r[c["type"]] for r in all_nodes if r[c["type"]] in cfg.slot_stage},
                     key=cfg.slots.index)
    unavailable = [s for s in cfg.slots if s not in allowed]

    # ---- which articles the predictor sees ----
    docs = {}
    for r in all_nodes:
        docs.setdefault(r[c["doc"]], {"date": r[c["date"]], "notes": []})["notes"].append(r)
    order = sorted(docs, key=lambda d: (docs[d]["date"], d))
    excluded = []
    if len(all_nodes) > budget:
        if not args.title:
            die(f"{len(all_nodes)} notes exceed the budget of {budget} — pass --title so the "
                f"most relevant articles can be chosen")
        tw = content_words(args.title)
        score = {d: len(tw & content_words(" ".join(n[c["text"]] for n in docs[d]["notes"]))) for d in docs}
        recent = order[-cfg.keep_recent:] if cfg.keep_recent else []
        # most words in common first; on a tie, the more recent article
        ranked = recent + [d for d in sorted(docs, key=lambda d: (score[d], docs[d]["date"], d), reverse=True)
                           if d not in recent]
        chosen, total = [], 0
        for d in ranked:
            n = len(docs[d]["notes"])
            if d in recent or total + n <= budget:
                chosen.append(d)
                total += n
        excluded = [(d, score[d]) for d in order if d not in chosen]
        order = [d for d in order if d in chosen]
    nodes = [n for d in order for n in docs[d]["notes"]]
    chosen_docs = set(order)
    edges = [e for e in all_edges if e[c["doc"]] in chosen_docs]

    # ---- citation names: DATE ID when the date is unique, doc#ID otherwise ----
    per_date: dict[str, set] = {}
    for d in order:
        per_date.setdefault(docs[d]["date"], set()).add(d)
    cites, aliases = {}, {}
    for r in nodes:
        doc, nid, date = r[c["doc"]], r[c["node_id"]], r[c["date"]]
        canon = f"{doc}#{nid}"
        shown = f"{date} {nid}" if len(per_date[date]) == 1 else canon
        cites[canon] = {"doc": doc, "date": date, "shown": shown, "type": r[c["type"]],
                        "text": " ".join(r[c["text"]].split())}
        for a in (canon, f"{date} {nid}", f"{date[:7]} {nid}"):
            aliases.setdefault(a, [])
            if canon not in aliases[a]:
                aliases[a].append(canon)

    vocab = set()
    for r in nodes:
        txt = " ".join([r[c["text"]]] + [r.get(k) or "" for k in cfg.show])
        txt = re.sub(r"(?<=[A-Za-z])\.(?=[A-Za-z])", "", txt)              # U.S. -> US
        vocab.update(tok_key(w) for w in re.findall(r"[A-Za-z][A-Za-z\-']+", txt))

    unl = sum(1 for e in edges if not e[c["edge_raw"]])
    (run / "frozen.json").write_text(json.dumps({
        "cutoff": cut, "n_articles": len(order), "n_notes": len(nodes),
        "n_articles_before_cutoff": len(docs), "excluded": excluded,
        "allowed_slots": allowed, "unavailable_slots": unavailable,
        "citations": cites, "aliases": aliases, "vocab": sorted(vocab),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    first = next(iter(cites.values()))["shown"]
    lines = [
        f"# Everything the author published before {cut}",
        "",
        f"{len(order)} articles, {len(nodes)} notes, {len(edges)} edges.",
        "",
        "Each note is one move in one article: `**NAME** [slot · tags] text`.",
        f"Cite a note by its NAME exactly as written, e.g. `{first}`.",
        "Node ids are local to one article — the date is part of the name.",
        "",
    ]
    if excluded:
        lines += [f"{len(docs)} articles came before the cutoff. To fit the budget of {budget} notes, "
                  f"these were left out (fewest words in common with the title):", ""]
        lines += [f"- {d}" for d, _ in excluded] + [""]
    lines += [
        "## Slots that existed before this date",
        "",
        "Only these may be predicted:",
        "",
        "    " + " · ".join(allowed),
        "",
        "These did not exist yet — leave them out:",
        "",
        "    " + (" · ".join(unavailable) or "(none)"),
        "",
        "## Edge types",
        "",
        "    forward:  " + " · ".join(sorted(cfg.forward)),
        "    pushback: " + " · ".join(sorted(cfg.pushback)),
        "",
        f"**Caution:** {unl} of {len(edges)} edges below are marked `supports*`. The `*` means",
        "the source map drew an arrow with no label and the parser filled in `supports`.",
        "Treat those as 'connected', not as evidence that he argues by support.",
        "",
    ]
    for d in order:
        lines += [f"## {docs[d]['date']}" + (f"  ({d})" if len(per_date[docs[d]['date']]) > 1 else ""), ""]
        for r in sorted(docs[d]["notes"], key=lambda r: r[c["node_id"]]):
            name = cites[f"{d}#{r[c['node_id']]}"]["shown"]
            tags, longer = note_extras(cfg, r)
            lines.append(f"- **{name}** [{' · '.join([r[c['type']]] + tags)}] {' '.join(r[c['text']].split())}"
                         + "".join(f" — {x}" for x in longer))
        es = [e for e in edges if e[c["doc"]] == d]
        if es:
            parts = [f"{e[c['edge_from']]} -{e[c['edge_type']]}{'' if e[c['edge_raw']] else '*'}-> {e[c['edge_to']]}"
                     for e in es]
            lines += ["", "  edges: " + " ; ".join(parts)]
        lines.append("")
    (run / "frozen.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"freeze: {len(order)} articles, {len(nodes)} notes before {cut}"
          + (f" ({len(excluded)} left out to fit {budget} notes)" if excluded else ""))
    print(f"  {len(allowed)} slot types available, {len(unavailable)} not yet: {', '.join(unavailable) or '-'}")
    print(f"  wrote {run / 'frozen.md'} (for the predictor) and frozen.json (for the validator)")


# ============================================================== validate =====

def words(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def norm(s: str) -> str:
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s or "")
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
                 ("—", "-"), ("–", "-"), ("‑", "-"), (" ", " ")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s.lower()).strip()


QUOTE_RE = re.compile(r'["“”]([^"“”]{3,}?)["“”]')
ID_RE = re.compile(r"\b(?:[PMCEDR]\d{1,2}|QF\d?|SCP|SC|BM|RC|REC|DF|ANOM|POS)\b")


def normalise(cfg: Cfg, data: dict, frozen: dict | None, warns: list | None = None) -> dict:
    """Fill in what the script can know for itself, so the AI never has to.

    - A prediction may leave out the slots that did not exist before the cutoff.
    - The old verdict 'partial' is read as 'close'.
    """
    slots = data.setdefault("slots", {})
    if data.get("kind") == "predicted" and frozen:
        for s in frozen["unavailable_slots"]:
            slots.setdefault(s, {"status": "unavailable"})
    for slot, entry in slots.items():
        for i, it in enumerate(entry.get("items") or []):
            if it.get("verdict") == "partial":
                it["verdict"] = "close"
                if warns is not None:
                    warns.append(f"{slot}#{i + 1}: verdict 'partial' read as 'close' — use close or opposite")
    return data


def long_path(p: Path) -> Path:
    """Windows refuses paths over 260 characters unless they carry the \\\\?\\ prefix."""
    s = str(p.resolve())
    return Path("\\\\?\\" + s) if os.name == "nt" and len(s) >= 250 and not s.startswith("\\\\?\\") else p


def article_file(run: Path) -> Path:
    hits = sorted(glob.glob(str(run / "article" / "*.md")))
    if not hits:
        die(f"no article in {run / 'article'} — run the extractor first (only after lock)")
    return Path(hits[0])


def article_text(path: Path) -> tuple[str, set]:
    t = long_path(path).read_text(encoding="utf-8")
    body = t.split("## Body", 1)[-1].split("## Figures", 1)[0]
    paras = set(re.findall(r"<!-- (p\d+) -->", body))
    return norm(re.sub(r"<!-- p\d+ -->", " ", body)), paras


def resolve_cite(cite: str, frozen: dict) -> tuple[str | None, int]:
    """-> (canonical doc#ID or None, number of matches)."""
    hits = frozen["aliases"].get(" ".join(cite.split()), [])
    return (hits[0] if len(hits) == 1 else None), len(hits)


def box_items(cfg: Cfg, data: dict) -> dict:
    """box id -> item dict, for every filled box."""
    out = {}
    for slot, entry in (data.get("slots") or {}).items():
        if slot not in cfg.slot_stage or entry.get("status") not in FILLED:
            continue
        ids = cfg.boxes(slot)
        for i, item in enumerate(entry.get("items") or []):
            if i < len(ids):
                out[ids[i]] = item
    return out


def edge_box(ref: str) -> str:
    """'mechanism#2' or 'mechanism_2' -> 'mechanism_2';  'mechanism#1' -> 'mechanism'."""
    m = re.match(r"^([a-z_]+?)(?:[#_](\d+))?$", ref.strip())
    if not m:
        return ref.strip()
    base, n = m.group(1), m.group(2)
    return base if not n or n == "1" else f"{base}_{n}"


def validate(cfg: Cfg, path: Path, quiet: bool = False) -> tuple[list, list]:
    data = load_json(path)
    run = path.parent
    kind = data.get("kind")
    errs, warns = [], []

    if kind not in ("predicted", "actual"):
        errs.append("'kind' must be 'predicted' or 'actual'")
    frozen = load_json(run / "frozen.json") if kind == "predicted" else None
    if frozen and "aliases" not in frozen:
        die(f"{run / 'frozen.json'} is from an older version — re-run freeze for this run")
    normalise(cfg, data, frozen, warns)

    art = data.get("article") or {}
    for k in ("title", "date"):
        if not art.get(k):
            errs.append(f"article.{k} missing")
    summ = data.get("summary") or {}
    if summ.get("claim_type") and summ["claim_type"] not in ("single", "enumerated", "typology", "unresolved"):
        errs.append(f"summary.claim_type {summ['claim_type']!r} must be single, enumerated, typology or unresolved")
    if words(summ.get("finding", "")) > cfg.max_finding:
        errs.append(f"summary.finding is {words(summ['finding'])} words (max {cfg.max_finding})")

    atext, aparas = (article_text(article_file(run)) if kind == "actual" else ("", set()))

    slots = data["slots"]
    for slot in slots:
        if slot not in cfg.slot_stage:
            errs.append(f"unknown slot {slot!r} — slots come from sources.yaml stages")
    for slot in cfg.slots:
        if slot not in slots:
            errs.append(f"slot {slot!r} missing — every slot needs a status, even if empty")

    for slot, entry in slots.items():
        if slot not in cfg.slot_stage:
            continue
        st = entry.get("status")
        items = entry.get("items") or []
        if st not in STATUSES:
            errs.append(f"{slot}: status {st!r} not one of {STATUSES}")
            continue
        if kind == "predicted":
            if slot in frozen["unavailable_slots"] and st != "unavailable":
                errs.append(f"{slot}: did not exist before {frozen['cutoff']} — leave it out")
            if slot in frozen["allowed_slots"] and st == "unavailable":
                errs.append(f"{slot}: existed before the cutoff — it cannot be 'unavailable'")
        elif st == "unavailable":
            errs.append(f"{slot}: 'unavailable' is for predictions only")

        cap = int(cfg.repeat.get(slot, 1))
        if st in FILLED:
            if not 1 <= len(items) <= cap:
                errs.append(f"{slot}: {st} needs 1..{cap} items, has {len(items)}")
        elif items:
            errs.append(f"{slot}: status {st} must have no items")
        if words(entry.get("why", "")) > cfg.max_note:
            errs.append(f"{slot}: 'why' is {words(entry['why'])} words (max {cfg.max_note})")

        for i, it in enumerate(items):
            w = f"{slot}#{i + 1}"
            label = it.get("label", "")
            if words(label) > cfg.max_label:
                errs.append(f"{w}: label is {words(label)} words (max {cfg.max_label}): {label!r}")
            if not label and kind == "actual":
                errs.append(f"{w}: actual boxes need a label")
            if ID_RE.search(label) or ID_RE.search(it.get("note", "")):
                warns.append(f"{w}: looks like an internal node id in the text — {label!r}")
            if slot == "mechanism" and it.get("kind") not in ("economic", "distortion"):
                errs.append(f"{w}: mechanism needs kind 'economic' or 'distortion'")

            if kind == "predicted":
                src = it.get("from") or []
                if not src:
                    errs.append(f"{w}: needs 'from' — cite notes, 'pattern' for a recurring habit, "
                                "or 'title' if the notes are silent")
                for s in src:
                    if s.strip().lower() in ("title", "pattern"):
                        continue
                    canon, n = resolve_cite(s, frozen)
                    if not canon:
                        errs.append(f"{w}: citation {s!r} " + (
                            "matches more than one article — cite it as doc#ID" if n > 1
                            else "is not among the frozen notes"))
                vocab = set(frozen["vocab"])
                toks = re.findall(r"[A-Za-z][A-Za-z\-']+", re.sub(r"(?<=[A-Za-z])\.(?=[A-Za-z])", "", label))
                for j, tok in enumerate(toks):
                    names = [tok_key(x) for x in tok.split("-") if x and x[0].isupper()]
                    if j and names and any(x not in vocab for x in names):
                        warns.append(f"{w}: {tok!r} appears nowhere in the frozen notes — outside knowledge?")
            else:
                paras = it.get("para") or []
                if not paras:
                    errs.append(f"{w}: needs 'para' — the paragraph(s) it comes from")
                for p in paras:
                    if p not in aparas:
                        errs.append(f"{w}: paragraph {p!r} is not in the article")
                for field in ("label", "note"):
                    for q in QUOTE_RE.findall(it.get(field, "")):
                        if norm(q) not in atext:
                            errs.append(f"{w}: quoted {q!r} is not verbatim in the article — "
                                        "drop the quote marks or fix the wording")
                v = it.get("verdict")
                if v is not None and v not in VERDICTS:
                    errs.append(f"{w}: verdict must be one of {VERDICTS}")
                if v in ("close", "opposite") and not it.get("note"):
                    errs.append(f"{w}: a '{v}' verdict needs a note saying what was predicted")
                if words(it.get("note", "")) > cfg.max_note:
                    errs.append(f"{w}: note is {words(it['note'])} words (max {cfg.max_note})")

    filled = box_items(cfg, data)
    seen = set()
    for e in data.get("edges") or []:
        a, b, t = edge_box(e.get("from", "")), edge_box(e.get("to", "")), e.get("type")
        tag = f"edge {e.get('from')} -{t}-> {e.get('to')}"
        if (a, b, t) in seen:
            warns.append(f"{tag}: duplicate")
        seen.add((a, b, t))
        if t not in cfg.edge_types:
            errs.append(f"{tag}: type not in sources.yaml edges")
        for end in (a, b):
            if end not in filled:
                errs.append(f"{tag}: {end!r} is not a filled box")
        if t in cfg.forward and a in filled and b in filled:
            if cfg.stage_rank[cfg.stage_of(b)] < cfg.stage_rank[cfg.stage_of(a)]:
                errs.append(f"{tag}: a forward edge runs backwards ({cfg.stage_of(a)} -> {cfg.stage_of(b)}). "
                            "Use a pushback type or reverse it.")

    if not quiet:
        print(f"validate {path.name} ({kind}): {len(errs)} error(s), {len(warns)} warning(s)")
        for x in warns:
            print(f"  warn  {x}")
        for x in errs:
            print(f"  FAIL  {x}")
    return errs, warns


def cmd_validate(cfg: Cfg, args) -> None:
    errs, _ = validate(cfg, Path(args.file))
    if errs:
        sys.exit(1)


# ================================================================== lock =====

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_lock(cfg: Cfg, args) -> None:
    run = Path(args.run)
    pred = run / "predicted.json"
    errs, _ = validate(cfg, pred)
    if errs:
        die("fix the prediction before locking it")
    if (run / "article").exists() and not args.force:
        die("article/ already exists — the article was fetched before the prediction was locked. "
            "That breaks the blind test. Delete article/ and re-predict, or pass --force and disclose it.")
    lock = {"file": "predicted.json", "sha256": sha(pred),
            "locked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "article_present_at_lock": (run / "article").exists()}
    (run / "predicted.lock").write_text(json.dumps(lock, indent=1), encoding="utf-8")
    print(f"lock: predicted.json sealed at {lock['locked_at_utc']} ({lock['sha256'][:12]}…)")
    if lock["article_present_at_lock"]:
        print("  WARNING: locked with --force while the article was already on disk — say so in the write-up")


def check_lock(run: Path) -> dict:
    lp = run / "predicted.lock"
    if not lp.exists():
        die(f"{lp} missing — run `pva.py lock {run}` before reading the article")
    lock = json.loads(lp.read_text(encoding="utf-8"))
    if sha(run / "predicted.json") != lock["sha256"]:
        die(f"{run / 'predicted.json'} has changed since it was locked — the prediction is no longer blind")
    return lock


# ================================================================= score =====

def score(cfg: Cfg, pred: dict, act: dict) -> dict:
    ps, as_ = pred["slots"], act["slots"]
    pf, af = box_items(cfg, pred), box_items(cfg, act)

    # ---- slots: was each one there or not ----
    easy = easy_right = hard = hard_right = 0
    for slot in cfg.slots:
        p, a = ps[slot]["status"], as_[slot]["status"]
        if p not in DEFINITE:
            continue
        if a in FILLED:              # 'always yes' gets these for free
            easy += 1
            easy_right += p in FILLED
        else:                        # only a real call gets these
            hard += 1
            hard_right += p not in FILLED

    # ---- boxes: what was in them ----
    rows, unjudged = [], []
    content = {k: 0 for k in VERDICTS}
    content["slot_only"] = 0
    for slot in cfg.slots:
        p_st, a_st = ps[slot]["status"], as_[slot]["status"]
        for i, box in enumerate(cfg.boxes(slot)):
            p_it, a_it = pf.get(box), af.get(box)
            if p_it and a_it:
                if not p_it.get("label"):
                    res = "slot_only"
                elif a_it.get("verdict") in VERDICTS:
                    res = a_it["verdict"]
                else:
                    res = "match"
                    unjudged.append(box)
                content[res] += 1
            elif p_it:
                res = "wrong"
            elif a_it:
                res = {"unavailable": "gap", "unsure": "unsure"}.get(p_st, "missed")
            else:
                res = "empty"
            rows.append({"slot": slot, "box": box, "i": i, "result": res,
                         "pred": p_it, "act": a_it, "p_status": p_st, "a_status": a_st})

    # ---- the error chain: wrong boxes joined by the article's own forward arrows ----
    res_of = {r["box"]: r["result"] for r in rows}
    wrong = {b for b, r in res_of.items() if r in ("close", "opposite")}
    aedges = [(edge_box(e["from"]), edge_box(e["to"]), e["type"]) for e in act.get("edges") or []]
    links = [(a, b, t) for a, b, t in aedges if t in cfg.forward and a in wrong and b in wrong]
    # a chain starts where the prediction said the opposite; a run of merely close boxes is not one
    reach, todo = set(), [b for b in wrong if res_of[b] == "opposite"]
    while todo:
        n = todo.pop()
        if n not in reach:
            reach.add(n)
            todo += [b for a, b, _ in links if a == n]
    chain = [(a, b, t) for a, b, t in links if a in reach]
    into = {b for _, b, _ in chain}
    roots = sorted({a for a, _, _ in chain if res_of[a] == "opposite"} - into, key=cfg.box_rank.get)
    paths = []

    def walk(node, path):
        nxt = sorted({b for a, b, _ in chain if a == node and b not in path}, key=cfg.box_rank.get)
        if not nxt:
            paths.append(path)
        for b in nxt:
            walk(b, path + [b])
    for r in roots:
        walk(r, [r])

    def eset(d):
        return {(edge_box(e["from"]), edge_box(e["to"]), e["type"]) for e in d.get("edges") or []}
    pe, ae = eset(pred), eset(act)

    return {
        "definite": easy + hard, "right": easy_right + hard_right, "baseline": easy,
        "easy": easy, "easy_right": easy_right, "hard": hard, "hard_right": hard_right,
        "content": content, "rows": rows, "unjudged": unjudged, "chain": chain, "paths": paths,
        "gaps": [r["slot"] for r in rows if r["result"] == "gap"],
        "edges_pred": len(pe), "edges_act": len(ae), "edges_same": len(pe & ae),
        "pairs_same": len({(a, b) for a, b, _ in pe} & {(a, b) for a, b, _ in ae}),
        "summary_pred": dict(pred.get("summary") or {}, mechanism_kind=mech_kind(pred)),
        "summary_act": dict(act.get("summary") or {}, mechanism_kind=mech_kind(act)),
    }


def mech_kind(data: dict) -> str:
    kinds = sorted({it.get("kind") for it in (data["slots"].get("mechanism", {}).get("items") or [])} - {None})
    return " + ".join(kinds) if kinds else "none"


# ================================================================ render =====

def esc(s: str) -> str:
    """Plain text -> safe inside a mermaid ["..."] label."""
    s = (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace("#", "#35;").replace('"', "#quot;")


def sources_line(froms: list, frozen: dict) -> str:
    out = []
    for f in froms or []:
        key = f.strip().lower()
        if key == "title":
            label = "title only"
        elif key == "pattern":
            label = "recurring habit"
        else:
            canon, _ = resolve_cite(f, frozen)
            date = frozen["citations"][canon]["date"] if canon else f
            m = re.match(r"(\d{4})-(\d{2})", date)
            label = f"{MONTHS[int(m.group(2)) - 1]} {m.group(1)}" if m else f
        if label not in out:
            out.append(label)
    return ", ".join(out[:2]) + (f" +{len(out) - 2}" if len(out) > 2 else "")


def display_edge(cfg: Cfg, a: str, b: str, t: str) -> tuple[str, str, str]:
    """Orient an edge for drawing so every arrow points down the chart."""
    if t in cfg.pushback and cfg.stage_rank[cfg.stage_of(b)] < cfg.stage_rank[cfg.stage_of(a)]:
        return b, a, cfg.reverse_label[t]
    return a, b, t.replace("_", " ")


def box_style(cfg: Cfg, box: str, filled: bool, distortion=False, border=None, width=1, dashed=False) -> str:
    p = cfg.pal
    if filled:
        fill = p["distortion_fill"] if distortion else p["stage_fill"][cfg.stage_of(box)]
        color, stroke = p["text"], border or p["stage_border"]
    else:
        fill, color, stroke = p["empty_fill"], p["empty_text"], border or p["empty_border"]
    s = f"fill:{fill},stroke:{stroke},color:{color},stroke-width:{width}px"
    return s + (",stroke-dasharray:5 4" if dashed else "")


# Labels of hidden arrows keep their text (so they take the same room in both charts) but
# must not show the dark chip mermaid draws behind every label.
HIDE_CSS = (".labelBkg:has(.pva-hide), .edgeLabel:has(.pva-hide), .edgeLabel p:has(.pva-hide) "
            "{ background-color: transparent !important; }")


def head(title: str) -> list[str]:
    return [
        "---",
        "config:",
        "  layout: elk",
        "  elk:",
        "    forceNodeModelOrder: true",
        "    considerModelOrder: NODES_AND_EDGES",
        "  theme: dark",
        "  themeVariables:",
        '    lineColor: "#D3D1C7"',
        '    clusterBkg: "#262624"',
        '    clusterBorder: "#5F5E5A"',
        '    titleColor: "#F1EFE8"',
        '    edgeLabelBackground: "#2C2C2A"',
        f"  themeCSS: \"{HIDE_CSS}\"",
        "  flowchart:",
        "    wrappingWidth: 190",
        "    nodeSpacing: 26",
        "    rankSpacing: 46",
        "---",
        f"%% {title}",
        "%% Generated by .claude/skills/predict-vs-actual/pva.py — edit the JSON, not this file.",
        "flowchart TD",
        "",
    ]


BOX_W, TITLE_W = 200, 420         # px; every box is this wide in both charts
CHARS_PER_LINE, LINE_PX, PAD_PX = 22, 24, 8   # a cautious guess: too tall is fine, too short only grows


def est_height(html: str, width: int) -> int:
    """Rough height of a label, so the same box gets the same size in both charts."""
    per = CHARS_PER_LINE * width // BOX_W
    lines = 0
    for seg in re.split(r"<br/>", html):
        text = re.sub(r"<[^>]+>", "", seg).replace("&amp;", "&").replace("#quot;", '"').replace("#35;", "#")
        lines += max(1, -(-len(text) // per))
    return lines * LINE_PX + PAD_PX


def sized(html: str, width: int, height: int) -> str:
    """Fix a label's width and minimum height. Equal sizes give the layout engine the same graph."""
    return f"<div style='width:{width}px;min-height:{height}px'>{html}</div>"


def draw(cfg: Cfg, title_lines, texts, styles, union, own, chain, comment, sizes) -> str:
    """One chart. `union` is the edge list both charts share; `own` the ones this chart shows.

    Both charts carry every edge in `union`, in the same order, so the layout engine
    sees the same graph and puts every box in the same place. Edges that belong only
    to the other chart are drawn without an arrowhead and made invisible.
    """
    out = head(comment)
    out.append(f'  T["{sized("<br/>".join(title_lines), TITLE_W, sizes["T"])}"]')
    out.append("")
    for st in cfg.stages:
        out.append(f'  subgraph {st["id"]}["{esc(st["name"])}"]')
        out.append("    direction LR")
        for b in (b for sl in st["slots"] for b in cfg.boxes(sl)):
            out.append(f'    {b}["{sized(texts[b], BOX_W, sizes[b])}"]')
        out.append("  end")
    out.append("")
    link_styles = []
    for i, (a, b, lab, kind) in enumerate(union):
        if (a, b, lab) in own:
            arrow = "-.->" if kind == "pushback" else "-->"
            out.append(f"  {a} {arrow}|{lab}| {b}")
            if (a, b, lab) in chain:
                link_styles.append(f"  linkStyle {i} stroke:{cfg.pal['chain']},stroke-width:3px,color:{cfg.pal['chain']}")
        else:
            # same label text as in the other chart, so it takes the same room; HIDE_CSS removes its chip
            out.append(f"  {a} ---|<span class='pva-hide' style='opacity:0'>{lab}</span>| {b}")
            link_styles.append(f"  linkStyle {i} stroke:transparent,stroke-width:0px,color:transparent")
    out.append("")
    out.append(f"  T ~~~ {cfg.stages[0]['id']}")
    for x, y in zip(cfg.stages, cfg.stages[1:]):
        out.append(f"  {x['id']} ~~~ {y['id']}")
    out.append("")
    out += [f"  style {b} {s}" for b, s in styles.items()]
    out.append("  style T fill:#2C2C2A,stroke:#F1EFE8,color:#F1EFE8,stroke-width:2px")
    out += link_styles
    return "\n".join(out) + "\n"


def cmd_render(cfg: Cfg, args) -> None:
    run = Path(args.run)
    cfg.guard(run)
    for f in ("predicted.json", "actual.json"):
        errs, _ = validate(cfg, run / f, quiet=True)
        if errs:
            die(f"{f} does not validate — run `pva.py validate {run / f}` to see why")
    lock = check_lock(run)
    frozen = load_json(run / "frozen.json")
    pred = normalise(cfg, load_json(run / "predicted.json"), frozen)
    act = normalise(cfg, load_json(run / "actual.json"), None)
    sc = score(cfg, pred, act)
    if sc["unjudged"]:
        die("these boxes have content on both sides but no verdict: " + ", ".join(sc["unjudged"])
            + " — finish pass two (match, close or opposite)")
    art = act["article"]
    title = esc(art["title"])
    rb = cfg.pal["result_border"]

    # ---- the shared edge skeleton ----
    def drawn(data):
        out = []
        for e in data.get("edges") or []:
            a, b, t = edge_box(e["from"]), edge_box(e["to"]), e["type"]
            da, db, lab = display_edge(cfg, a, b, t)
            out.append((da, db, lab, "pushback" if t in cfg.pushback else "forward", (a, b, t)))
        return out
    pd, ad = drawn(pred), drawn(act)
    union, seen = [], set()
    for da, db, lab, kind, _ in sorted(pd + ad, key=lambda x: (cfg.box_rank[x[0]], cfg.box_rank[x[1]], x[2])):
        if (da, db, lab) not in seen:
            seen.add((da, db, lab))
            union.append((da, db, lab, kind))
    p_own = {(x[0], x[1], x[2]) for x in pd}
    a_own = {(x[0], x[1], x[2]) for x in ad}
    chain_set = set(sc["chain"])
    chain_drawn = {(x[0], x[1], x[2]) for x in ad if x[4] in chain_set}

    # ---- A · predicted ----
    pf = box_items(cfg, pred)
    texts, styles = {}, {}
    for slot in cfg.slots:
        st = pred["slots"][slot]["status"]
        for i, box in enumerate(cfg.boxes(slot)):
            name, it = esc(cfg.box_name(slot, i)), pf.get(box)
            if it:
                body = esc(it["label"]) if it.get("label") else "<i>expected — content not given</i>"
                if st == "implicit":
                    body += " <i>(implicit)</i>"
                src = sources_line(it.get("from"), frozen)
                texts[box] = f"<b>{name}</b><br/>{body}" + (f"<br/><i>↳ {esc(src)}</i>" if src else "")
                styles[box] = box_style(cfg, box, True, distortion=it.get("kind") == "distortion")
            elif st == "unavailable":
                texts[box] = f"<b>{name}</b><br/><i>no such slot yet</i>"
                styles[box] = box_style(cfg, box, False, dashed=True)
            else:
                texts[box] = f"<b>{name}</b><br/><i>{'unsure' if st == 'unsure' else 'predicted empty'}</i>"
                styles[box] = box_style(cfg, box, False)
    a_title = [
        "<b>A · PREDICTED</b> — from the title alone",
        f"<i>#quot;{title}#quot;</i>",
        f"From {frozen['n_notes']} notes in {frozen['n_articles']} articles before {frozen['cutoff']}",
        "Lock forced — the article was already on disk" if lock.get("article_present_at_lock")
        else "Locked before the article was read",
    ]
    a_texts, a_styles = texts, styles

    # ---- B · actual ----
    texts, styles = {}, {}
    for r in sc["rows"]:
        box, slot, i, res = r["box"], r["slot"], r["i"], r["result"]
        name, a_it = esc(cfg.box_name(slot, i)), r["act"]
        if a_it:
            lines = [f"<b>{name}</b>" + (f" {MARK[res]}" if res in MARK else ""), esc(a_it["label"])]
            if res in VERDICTS and a_it.get("note"):
                lines.append(f"<i>{esc(a_it['note'])}</i>")
            elif res == "slot_only":
                lines.append("<i>slot predicted, content not given</i>")
            elif res == "gap":
                lines.append("<i>no slot for this in the framework yet</i>")
            elif res == "missed":
                lines.append("<i>predicted empty</i>")
            elif res == "unsure":
                lines.append("<i>predicted: unsure</i>")
            paras = [p[1:] for p in a_it.get("para") or []]
            if paras:
                lines.append(f"<i>para {', '.join(paras)}</i>")
            texts[box] = "<br/>".join(lines)
            width = 4 if res == "opposite" else 3 if res in ("match", "close", "missed", "gap") else 2
            styles[box] = box_style(cfg, box, True, distortion=a_it.get("kind") == "distortion",
                                    border=rb.get(res), width=width, dashed=res == "gap")
        elif res == "wrong":
            texts[box] = f"<b>{name}</b> {MARK['wrong']}<br/><i>predicted, not in the article</i>"
            styles[box] = box_style(cfg, box, False, border=rb["wrong"], width=3, dashed=True)
        else:
            texts[box] = f"<b>{name}</b>" + ("<br/><i>predicted: unsure</i>" if r["p_status"] == "unsure" else "")
            styles[box] = box_style(cfg, box, False)
    c = sc["content"]
    judged = c["match"] + c["close"] + c["opposite"]
    b_title = ["<b>B · ACTUAL</b> — after reading the article",
               f"<i>#quot;{title}#quot;</i> · {esc(art['date'])}"]
    if (act.get("summary") or {}).get("finding"):
        b_title.append(f"<b>{esc(act['summary']['finding'])}</b>")
    b_title.append(f"Slots {sc['right']} of {sc['definite']} — {sc['baseline']} come free by always saying yes; "
                   f"real calls {sc['hard_right']} of {sc['hard']}")
    b_title.append(f"Content {c['match']} of {judged} right · {c['opposite']} opposite"
                   + (" · red arrows: where the error travels" if sc["chain"] else ""))

    # ---- one size per box, the larger of the two, so both charts lay out the same ----
    sizes = {b: max(est_height(a_texts[b], BOX_W), est_height(texts[b], BOX_W)) for b in cfg.all_boxes}
    sizes["T"] = max(est_height("<br/>".join(a_title), TITLE_W), est_height("<br/>".join(b_title), TITLE_W))
    (run / "predicted.mmd").write_text(
        draw(cfg, a_title, a_texts, a_styles, union, p_own, set(),
             f"PREDICTED · {art['title']} · {art['date']}", sizes), encoding="utf-8")
    (run / "actual.mmd").write_text(
        draw(cfg, b_title, texts, styles, union, a_own, chain_drawn,
             f"ACTUAL · {art['title']} · {art['date']}", sizes), encoding="utf-8")

    # ---- one legend for both charts, so a legend cannot shift either layout ----
    used = {r["result"] for r in sc["rows"]}
    (run / "legend.mmd").write_text(legend(cfg, [k for k in MEANING if k in used], bool(sc["chain"])),
                                    encoding="utf-8")

    reps = [replicate(cfg, Path(r), pred, act, frozen, sc) for r in (args.replicate or [])]
    (run / "comparison.md").write_text(comparison(cfg, sc, pred, act, frozen, lock, reps), encoding="utf-8")

    print(f"render: wrote predicted.mmd, actual.mmd, legend.mmd, comparison.md in {run}")
    print(f"  slots {sc['right']}/{sc['definite']} (free {sc['baseline']}, real calls {sc['hard_right']}/{sc['hard']})"
          f" · content {c['match']}/{judged}, {c['opposite']} opposite"
          f" · arrows {sc['edges_same']}/{sc['edges_pred']}"
          f" · new slots: {', '.join(sc['gaps']) or 'none'}")
    for p in sc["paths"]:
        print("  error chain: " + " -> ".join(p))
    for rp in reps:
        print(f"  replication {rp['run']}: {rp['agree']}/{rp['n']} slot calls agree")


def legend(cfg: Cfg, results: list, chain: bool) -> str:
    rb, p = cfg.pal["result_border"], cfg.pal
    filled = f"fill:{p['stage_fill']['L3']},color:{p['text']}"
    empty = f"fill:{p['empty_fill']},color:{p['empty_text']}"
    out = head("LEGEND · for predicted.mmd and actual.mmd")
    a = [("<b>Filled</b> — predicted to appear", f"{filled},stroke:{p['stage_border']},stroke-width:1px"),
         ("<b>Dim</b> — predicted empty", f"{empty},stroke:{p['empty_border']},stroke-width:1px"),
         ("<b>Dashed</b> — no such slot yet", f"{empty},stroke:{p['empty_border']},stroke-width:1px,stroke-dasharray:5 4"),
         ("<b>Brown</b> — a mechanism of mismeasurement", f"fill:{p['distortion_fill']},color:{p['text']},stroke:{p['stage_border']},stroke-width:1px")]
    b = []
    for r in results:
        mk = MARK.get(r, "")
        base = empty if r == "wrong" else filled
        dash = ",stroke-dasharray:5 4" if r in ("wrong", "gap") else ""
        b.append((f"<b>{mk + ' ' if mk else ''}{esc(r.replace('_', ' '))}</b> — {esc(MEANING[r])}",
                  f"{base},stroke:{rb[r]},stroke-width:3px{dash}"))
    if chain:
        b.append(("<b>Red arrow</b> — the error travels along it",
                  f"{empty},stroke:{p['chain']},stroke-width:1px"))
    out.append('  subgraph LA["Chart A · predicted"]')
    out.append("    direction LR")
    out += [f'    A{i}["{t}"]' for i, (t, _) in enumerate(a)]
    out.append("  end")
    out.append('  subgraph LB["Chart B · actual — border shows how the prediction did"]')
    out.append("    direction LR")
    out += [f'    B{i}["{t}"]' for i, (t, _) in enumerate(b)]
    out.append("  end")
    out.append("  LA ~~~ LB")
    out += [f"  style A{i} {s}" for i, (_, s) in enumerate(a)]
    out += [f"  style B{i} {s}" for i, (_, s) in enumerate(b)]
    return "\n".join(out) + "\n"


def replicate(cfg: Cfg, run2: Path, pred: dict, act: dict, frozen: dict, sc: dict) -> dict:
    """A second, independent blind prediction of the same article: how much agrees?"""
    errs, _ = validate(cfg, run2 / "predicted.json", quiet=True)
    if errs:
        die(f"{run2 / 'predicted.json'} does not validate")
    lock = check_lock(run2)
    fz2 = load_json(run2 / "frozen.json")
    if fz2["cutoff"] != frozen["cutoff"]:
        die(f"{run2} was frozen at {fz2['cutoff']}, not {frozen['cutoff']}")
    p2 = normalise(cfg, load_json(run2 / "predicted.json"), fz2)
    allowed = frozen["allowed_slots"]
    agree = sum(pred["slots"][s]["status"] == p2["slots"][s]["status"] for s in allowed)
    s2 = score(cfg, p2, act)
    pf2 = box_items(cfg, p2)
    side = [(r["box"], r["result"], r["pred"], pf2.get(r["box"]), r["act"])
            for r in sc["rows"] if r["result"] in ("close", "opposite")]
    shown = os.path.relpath(run2.resolve(), cfg.root).replace("\\", "/")   # same text however the path was typed
    return {"run": shown, "agree": agree, "n": len(allowed), "lock": lock,
            "right": s2["right"], "definite": s2["definite"], "side": side,
            "differs": [(s, pred["slots"][s]["status"], p2["slots"][s]["status"], act["slots"][s]["status"])
                        for s in allowed if pred["slots"][s]["status"] != p2["slots"][s]["status"]]}


def comparison(cfg: Cfg, sc: dict, pred: dict, act: dict, frozen: dict, lock: dict, reps: list) -> str:
    art = act["article"]
    c = sc["content"]
    judged = c["match"] + c["close"] + c["opposite"]
    word = {"match": "✓ right", "close": "≈ close", "opposite": "≠ opposite", "slot_only": "slot only",
            "wrong": "✗ not there", "missed": "★ missed", "gap": "◇ no slot yet", "unsure": "unsure", "empty": "—"}

    def nm(box):
        s = base_slot(cfg, box)
        return cfg.box_name(s, cfg.boxes(s).index(box))
    sp, sa = sc["summary_pred"], sc["summary_act"]
    L = [f"# Predicted vs actual — {art['title']}", "",
         f"{art.get('url', '')}  ",
         f"Published {art['date']}. Predicted from {frozen['n_notes']} notes in {frozen['n_articles']} "
         f"articles before {frozen['cutoff']}, title only. Prediction locked {lock['locked_at_utc']}"
         + (" — **with the article already on disk (forced)**." if lock.get("article_present_at_lock") else "."),
         ""]
    if (act.get("summary") or {}).get("finding"):
        L += [f"> **{act['summary']['finding']}**", ""]
    L += ["## Score", "",
          "| | Result | What it means |", "|---|---|---|",
          f"| Slots | **{sc['right']} of {sc['definite']}** | right about whether each slot appears |",
          f"| — of which free | {sc['baseline']} | slots this article has, which 'always yes' also gets |",
          f"| — real calls | **{sc['hard_right']} of {sc['hard']}** | slots the article leaves empty: only a real prediction gets these |",
          f"| Content | **{c['match']} of {judged}** | of the boxes both filled, same claim |",
          f"| — opposite | {c['opposite']} | right slot, but the content contradicts the prediction |",
          f"| — close | {c['close']} | right slot, different claim, detail or kind |",
          f"| Slot only | {c['slot_only']} | slot predicted with no content — not scored |",
          f"| Arrows | {sc['edges_same']} of {sc['edges_pred']} | predicted links that also appear (same pair, any type: {sc['pairs_same']}) |",
          f"| New slots | {len(sc['gaps'])} | used by the article but not in the framework yet: "
          f"{', '.join(cfg.names[g] for g in sc['gaps']) or 'none'} |", ""]
    L += ["| | Predicted | Actual |", "|---|---|---|"]
    for k in ("claim_type", "mechanism_kind"):
        L.append(f"| {k.replace('_', ' ')} | {sp.get(k, '—')} | {sa.get(k, '—')} |")
    L.append("")

    if sc["paths"]:
        res_of = {r["box"]: r["result"] for r in sc["rows"]}
        L += ["## Where the error travels", "",
              "Starts at a box where the prediction said the opposite, and follows the article's own arrows",
              "through the boxes that are wrong partly because they rest on it. Drawn as red arrows on chart B.", ""]
        for p in sc["paths"]:
            L.append("- " + " → ".join(f"{nm(b)} {MARK[res_of[b]]}" for b in p))
        L.append("")

    if reps:
        L += ["## Replication — independent blind predictions of the same article", ""]
        for rp in reps:
            L += [f"Second run `{rp['run']}`, locked {rp['lock']['locked_at_utc']}"
                  + (" (forced)" if rp["lock"].get("article_present_at_lock") else "") + ".", "",
                  f"- **{rp['agree']} of {rp['n']}** slot calls agree with this run.",
                  f"- It scores **{rp['right']} of {rp['definite']}** slot calls against the article.", ""]
            if rp["differs"]:
                L += ["| Slot | This run | Second run | Actual |", "|---|---|---|---|"]
                L += [f"| {cfg.names[s]} | {a} | {b} | {x} |" for s, a, b, x in rp["differs"]]
                L.append("")
            if rp["side"]:
                L += ["Where this run got the content wrong, what the second run said:", "",
                      "| Box | This run | Second run | Actual |", "|---|---|---|---|"]
                for box, res, p1, p2, a in rp["side"]:
                    L.append(f"| {nm(box)} {MARK[res]} | {p1.get('label') or '—'} | "
                             f"{(p2 or {}).get('label') or '—'} | {a['label']} |")
                L.append("")

    L += ["## Box by box", "",
          "| Stage | Box | Predicted | From | Actual | Para | Result |", "|---|---|---|---|---|---|---|"]
    for r in sc["rows"]:
        st = next(s["name"] for s in cfg.stages if s["id"] == cfg.slot_stage[r["slot"]])
        p, a = r["pred"], r["act"]
        spare = r["i"] > 0                       # an unused second box of a repeated slot
        pt = (p.get("label") or "*(slot only)*") if p else ("—" if spare else f"*{r['p_status']}*")
        at = a["label"] if a else ("—" if spare else f"*{r['a_status']}*")
        if a and a.get("note") and r["result"] in VERDICTS:
            at += f" — *{a['note']}*"
        L.append(f"| {st} | {cfg.box_name(r['slot'], r['i'])} | {pt} | "
                 f"{', '.join(p.get('from') or []) if p else ''} | {at} | "
                 f"{', '.join(a.get('para') or []) if a else ''} | {word[r['result']]} |")
    L += ["", "## How to read the score", "",
          "- A **slot** call is right when the prediction and the article agree on whether that slot "
          "appears at all. Slots marked *unsure* or *no such slot yet* are not counted.",
          "- Most slots appear in nearly every article, so saying 'yes' to all of them already scores well. "
          "Those are the **free** ones. The **real calls** are the slots the article leaves empty — only "
          "a prediction that actually says 'no' can get them.",
          "- **Content** is judged box by box by the reader of the article: *right* = the same claim; "
          "*close* = the right slot but a different claim, detail or kind; *opposite* = the content "
          "contradicts the prediction.",
          "- **New slots** are not failures of the prediction. The framework had no word for them yet — "
          "that is a finding about the framework.",
          "", "## Checks passed", "",
          f"- Every citation in the prediction exists among the {frozen['n_notes']} frozen notes.",
          "- Every quoted phrase on the actual chart is verbatim in the article.",
          "- The prediction file is unchanged since it was locked.",
          "- No arrow touches an empty slot; no forward arrow runs backwards.",
          ""]
    return "\n".join(L)


# ============================================================== template =====

EXAMPLES = HERE / "examples"
RUN_FILES = ("predicted.json", "predicted.mmd", "actual.json", "actual.mmd", "legend.mmd", "comparison.md")


def cmd_template(cfg: Cfg, args) -> None:
    out = Path(args.out) if args.out else EXAMPLES / "template" / cfg.template_path.name
    cfg.guard(out)
    if not cfg.template_path.exists():
        die(f"{cfg.template_path} not found — check data.template in sources.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cfg.template_path, out)
    print(f"template: copied {cfg.template_path.name} -> {out}")


def cmd_example(cfg: Cfg, args) -> None:
    """Copy one finished run into examples/<run name>/, after checking it is sound."""
    run = Path(args.run)
    for f in ("predicted.json", "actual.json"):
        errs, _ = validate(cfg, run / f, quiet=True)
        if errs:
            die(f"{run / f} does not validate — fix it before it becomes an example")
    check_lock(run)
    missing = [f for f in RUN_FILES if not (run / f).exists()]
    if missing:
        die(f"{run} has no {', '.join(missing)} — run render first")
    for f in RUN_FILES[1::2] + ("legend.mmd",):
        if (run / f).stat().st_mtime < max((run / j).stat().st_mtime for j in ("predicted.json", "actual.json")):
            die(f"{run / f} is older than the JSON — run render again first")
    dest = EXAMPLES / run.name
    dest.mkdir(parents=True, exist_ok=True)
    for f in RUN_FILES:
        shutil.copyfile(run / f, dest / f)
    print(f"example: copied {len(RUN_FILES)} files from {run} -> {dest}")


# ================================================================== main =====

def main() -> None:
    for stream in (sys.stdout, sys.stderr):        # Windows consoles default to cp1252
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("freeze")
    p.add_argument("--before", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--title", help="the article's title — chooses which articles to keep when over budget")
    p.add_argument("--docs", help="regex on the doc column, e.g. '^setser' to keep one author")
    p.add_argument("--max-notes", type=int, help="override freeze.max_notes from sources.yaml")
    p.add_argument("--force", action="store_true", help="re-freeze a run folder that already holds a prediction")
    p = sub.add_parser("validate")
    p.add_argument("file")
    p = sub.add_parser("lock")
    p.add_argument("run")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("render")
    p.add_argument("run")
    p.add_argument("--replicate", nargs="*", default=[])
    p = sub.add_parser("template")
    p.add_argument("--out", help="default: examples/template/<template file name>")
    p = sub.add_parser("example")
    p.add_argument("run")
    args = ap.parse_args()

    cfg = Cfg(Path(args.root).resolve())
    {"check": cmd_check, "freeze": cmd_freeze, "validate": cmd_validate, "lock": cmd_lock,
     "render": cmd_render, "template": cmd_template, "example": cmd_example}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
