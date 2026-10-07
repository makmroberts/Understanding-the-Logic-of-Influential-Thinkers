#!/usr/bin/env python3
"""Build a self-contained HTML viewer for the argument maps in mermaid_code/.

Usage:
    python scripts/build_viewer.py            # writes viewer/index.html
    python scripts/build_viewer.py --open     # ...and opens it in the browser
    python scripts/build_viewer.py --serve    # ...and serves it on localhost

Re-run after adding or editing any .mmd file. Every map is embedded in the
output file, so viewer/index.html can be opened directly or emailed around
(it pulls mermaid from a CDN at view time, so it needs an internet connection).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR = ROOT / "mermaid_code"
DEFAULT_OUT = ROOT / "viewer" / "index.html"

MERMAID_VERSION = "12.1.0"
ELK_VERSION = "1.0.1"

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
    "nov": 11, "dec": 12,
}

# ---------------------------------------------------------------- metadata ---


def strip_markup(text: str) -> str:
    """Turn a mermaid node label into plain text."""
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("#quot;", '"').replace("#39;", "'")
    text = html.unescape(text)
    text = text.replace("`", " ").replace("**", "").replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def date_from_filename(stem: str) -> tuple[str, str]:
    """Return (iso_date, display_date) parsed from the filename, if possible."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", stem)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        # setser_aug_13_19  ->  13 Aug 2019
        m = re.search(r"_([a-z]{3,4})_(\d{1,2})_(\d{2})$", stem, re.I)
        if not m:
            return "", ""
        mon = MONTHS.get(m.group(1).lower())
        if not mon:
            return "", ""
        y, mo, d = 2000 + int(m.group(3)), mon, int(m.group(2))
    try:
        dt = datetime(y, mo, d)
    except ValueError:
        return "", ""
    return dt.strftime("%Y-%m-%d"), dt.strftime("%-d %b %Y") if sys.platform != "win32" else dt.strftime("%#d %b %Y")


def comment_fields(text: str) -> dict[str, str]:
    """Read `%% key: value | key: value` header comments."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("%%"):
            continue
        body = line[2:].strip()
        if ":" not in body:
            continue
        for chunk in body.split("|"):
            if ":" not in chunk:
                continue
            key, _, value = chunk.partition(":")
            key = key.strip().lower()
            value = value.strip()
            # a url has a colon in it; don't split it across chunks
            if key in {"url", "link"}:
                value = body.partition(":")[2].strip()
            if key and value and key not in fields:
                fields[key] = value
    return fields


def node_label(text: str, node_id: str) -> str:
    """Grab the raw label of a top-level node like  T["..."]  or  Q["..."]."""
    m = re.search(rf'^\s*{node_id}\["(.*?)"\]\s*$', text, re.M | re.S)
    return m.group(1) if m else ""


def parse_map(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    stem = path.stem
    iso_date, display_date = date_from_filename(stem)
    fields = comment_fields(text)

    title = fields.get("title", "")
    subtitle = ""
    shape = ""

    t_label = node_label(text, "T")
    q_label = node_label(text, "Q")

    if not title and t_label:
        # T["<b>Aug 2024 · #quot;China's Imaginary Trade Data#quot;</b><br/>..."]
        quoted = re.search(r"#quot;(.+?)#quot;", t_label)
        if quoted:
            title = strip_markup(quoted.group(1))
        bolds = [strip_markup(b) for b in re.findall(r"<b>(.*?)</b>", t_label)]
        shape = next((b for b in bolds if b.lower().startswith("shape")), "")
        if not display_date and bolds:
            lead = re.match(r"([A-Z][a-z]{2,3}\.?\s+\d{4})", bolds[0])
            if lead:
                display_date = lead.group(1)

    if not title and q_label:
        # older maps put the article's question in Q, with the byline in <i>
        bold = re.search(r"<b>(.*?)</b>", q_label, re.S)
        if bold:
            title = strip_markup(bold.group(1))
        ital = re.search(r"<i>(.*?)</i>", q_label, re.S)
        if ital and not display_date:
            display_date = strip_markup(ital.group(1))

    is_template_file = "template" in stem or "edge_types" in stem
    question = ""
    if q_label and not is_template_file:
        q_plain = strip_markup(q_label)
        q_plain = re.sub(r"^(Question( &amp; framing)?)\s*", "", q_plain, flags=re.I)
        question = q_plain

    if not title:
        title = stem.replace("_", " ")

    is_template = "template" in stem or "edge_types" in stem
    if is_template:
        # the templates' Q node is a placeholder, not a title
        title = stem.replace("_", " ").replace("mmd", "").strip().capitalize()
        question = ""
    levels = sorted({m for m in re.findall(r'subgraph\s+(L\d\w*)\[', text)})

    return {
        "file": path.name,
        "stem": stem,
        "group": "Schema & templates" if is_template else "Argument maps",
        "title": title,
        "shape": shape,
        "subtitle": subtitle,
        "question": question,
        "date": display_date,
        "iso": iso_date,
        "author": fields.get("author", ""),
        "outlet": fields.get("outlet", ""),
        "url": fields.get("url", ""),
        "topics": fields.get("topics", ""),
        "genre": fields.get("genre", ""),
        "levels": levels,
        "nodes": len(re.findall(r'^\s*\w+\["', text, re.M)),
        "lines": len(text.splitlines()),
        "code": text,
    }


def collect() -> list[dict]:
    if not MAPS_DIR.is_dir():
        sys.exit(f"no maps directory at {MAPS_DIR}")
    maps = [parse_map(p) for p in sorted(MAPS_DIR.glob("*.mmd"))]
    if not maps:
        sys.exit(f"no .mmd files found in {MAPS_DIR}")
    # templates first, then articles oldest -> newest (reads as a thought process)
    maps.sort(key=lambda m: (m["group"] != "Schema & templates", m["iso"] or "9999", m["file"]))
    return maps


# ------------------------------------------------------------------ output ---

TEMPLATE = r"""<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Argument maps · __AUTHOR__</title>
<style>
  :root{
    --bg:#1B1B19; --panel:#262624; --panel-2:#2C2C2A; --line:#44443F;
    --ink:#F1EFE8; --ink-dim:#B4B2A9; --ink-faint:#85837B;
    --accent:#5DCAA5; --accent-dim:#085041; --focus:#85B7EB;
  }
  *{box-sizing:border-box}
  html,body{height:100%;margin:0}
  body{
    background:var(--bg); color:var(--ink); overflow:hidden;
    font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;
  }
  button,select,input{font:inherit;color:inherit}

  .app{display:grid;grid-template-columns:320px 1fr;height:100vh}

  /* ---------------------------------------------------------- sidebar --- */
  .side{background:var(--panel);border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
  .side header{padding:14px 14px 10px;border-bottom:1px solid var(--line)}
  .side h1{margin:0;font-size:14px;letter-spacing:.02em}
  .side .sub{color:var(--ink-faint);font-size:11px;margin-top:3px}
  .search{margin:10px 14px 8px}
  .search input{
    width:100%;padding:7px 9px;background:var(--bg);border:1px solid var(--line);
    border-radius:6px;outline:none
  }
  .search input:focus{border-color:var(--focus)}
  .list{overflow:auto;padding:0 8px 24px;min-height:0;flex:1}
  .grouphead{
    padding:12px 6px 5px;font-size:10px;letter-spacing:.09em;text-transform:uppercase;
    color:var(--ink-faint)
  }
  .item{
    width:100%;text-align:left;display:block;background:none;border:1px solid transparent;
    border-radius:7px;padding:8px 9px;margin:1px 0;cursor:pointer
  }
  .item:hover{background:var(--panel-2)}
  .item.on{background:var(--accent-dim);border-color:var(--accent)}
  .item .t{font-weight:600;line-height:1.35}
  .item .m{color:var(--ink-faint);font-size:11px;margin-top:3px;font-variant-numeric:tabular-nums}
  .item.on .m{color:#BFE8D8}
  .item .badge{color:var(--ink-dim);font-size:10px}

  /* ------------------------------------------------------------ panes --- */
  .main{display:flex;flex-direction:column;min-width:0}
  .toolbar{
    display:flex;gap:8px;align-items:center;padding:9px 12px;
    border-bottom:1px solid var(--line);background:var(--panel)
  }
  .toolbar .spacer{flex:1}
  .btn{
    background:var(--panel-2);border:1px solid var(--line);border-radius:6px;
    padding:5px 10px;cursor:pointer
  }
  .btn:hover{border-color:var(--ink-faint)}
  .btn.on{background:var(--accent-dim);border-color:var(--accent);color:#DFF3EB}
  .hint{color:var(--ink-faint);font-size:11px}

  .panes{flex:1;display:grid;grid-template-columns:1fr;min-height:0}
  .panes.split{grid-template-columns:1fr 1fr}
  .pane{display:flex;flex-direction:column;min-width:0;border-left:1px solid var(--line)}
  .pane:first-child{border-left:0}
  .panes.split .pane.active .phead{box-shadow:inset 2px 0 0 var(--accent)}
  .phead{
    display:flex;gap:8px;align-items:center;padding:7px 10px;
    border-bottom:1px solid var(--line);background:var(--panel-2)
  }
  .phead select{
    background:var(--bg);border:1px solid var(--line);border-radius:6px;
    padding:4px 6px;max-width:100%;flex:1;min-width:0
  }
  .meta{
    padding:7px 12px;border-bottom:1px solid var(--line);color:var(--ink-dim);
    font-size:11px;display:flex;gap:10px;flex-wrap:wrap;align-items:baseline
  }
  .meta b{color:var(--ink);font-size:12px}
  .meta a{color:var(--focus)}
  .meta .q{color:var(--ink-faint);flex-basis:100%}

  .stage{flex:1;overflow:hidden;position:relative;cursor:grab;background:var(--bg)}
  .stage.drag{cursor:grabbing}
  .canvas{position:absolute;top:0;left:0;transform-origin:0 0;will-change:transform}
  .canvas svg{display:block;max-width:none!important;height:auto}
  .status{
    position:absolute;left:50%;top:46%;transform:translate(-50%,-50%);
    color:var(--ink-faint);text-align:center;max-width:70%
  }
  .zoom{
    position:absolute;right:10px;bottom:10px;display:flex;gap:4px;align-items:center;
    background:rgba(38,38,36,.92);border:1px solid var(--line);border-radius:7px;padding:4px
  }
  .zoom button{
    background:none;border:0;border-radius:5px;width:26px;height:24px;cursor:pointer;
    color:var(--ink-dim)
  }
  .zoom button:hover{background:var(--panel-2);color:var(--ink)}
  .zoom .pct{color:var(--ink-faint);font-size:11px;min-width:40px;text-align:center;
    font-variant-numeric:tabular-nums}
  .src{
    display:none;flex:1;overflow:auto;margin:0;padding:12px;background:#1F1F1D;
    border-top:1px solid var(--line);font:11.5px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;
    color:var(--ink-dim);white-space:pre
  }
  .pane.showsrc .src{display:block}
  .pane.showsrc .stage{flex:0 0 45%}
  .err{color:#F0A8C4;white-space:pre-wrap;text-align:left;font:12px/1.5 ui-monospace,Consolas,monospace}
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <header>
      <h1>Argument maps</h1>
      <div class="sub">__COUNT__ maps · __AUTHOR__ · built __BUILT__</div>
    </header>
    <div class="search"><input id="q" type="search" placeholder="Filter by title, date, topic…" autocomplete="off"></div>
    <div class="list" id="list"></div>
  </aside>

  <div class="main">
    <div class="toolbar">
      <button class="btn" id="cmp">Compare two</button>
      <span class="hint">L0 Question · L1 Priors · L2 Evidence · L3 Mechanisms · L4 Intermediate · L5 Conclusion · L6 Counterpoints</span>
      <span class="spacer"></span>
      <span class="hint">scroll = zoom · drag = pan · <b>0</b> fit · <b>c</b> compare</span>
    </div>
    <div class="panes" id="panes"></div>
  </div>
</div>

<script type="application/json" id="data">__MAPS_JSON__</script>
<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@__MERMAID__/dist/mermaid.esm.min.mjs';
import elkLayouts from 'https://cdn.jsdelivr.net/npm/@mermaid-js/layout-elk@__ELK__/dist/mermaid-layout-elk.esm.min.mjs';

const MAPS = JSON.parse(document.getElementById('data').textContent);
const byFile = new Map(MAPS.map(m => [m.file, m]));

mermaid.registerLayoutLoaders(elkLayouts);
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',                 // older maps have no frontmatter theme; this keeps them dark
  securityLevel: 'loose',        // local, trusted files; keeps <b>/<br/> labels intact
  maxTextSize: 500000,
  maxEdges: 2000,
  fontFamily: '-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif',
  flowchart: { htmlLabels: true, useMaxWidth: false },
});

/* ---------------------------------------------------------- rendering --- */
const svgCache = new Map();
let seq = 0;

async function renderMap(file) {
  if (svgCache.has(file)) return svgCache.get(file);
  const p = (async () => {
    const { svg } = await mermaid.render('m' + (seq++), byFile.get(file).code);
    return svg;
  })();
  svgCache.set(file, p);
  p.catch(() => svgCache.delete(file));
  return p;
}

window.argumentMaps = { maps: MAPS, render: renderMap };

/* -------------------------------------------------------------- panes --- */
class Pane {
  constructor(index) {
    this.index = index;
    this.file = null;
    this.k = 1; this.x = 0; this.y = 0;

    const el = document.createElement('div');
    el.className = 'pane';
    el.innerHTML = `
      <div class="phead">
        <select></select>
        <button class="btn src-btn" title="Show the .mmd source">source</button>
      </div>
      <div class="meta"></div>
      <div class="stage">
        <div class="canvas"></div>
        <div class="status">Pick a map from the left.</div>
        <div class="zoom">
          <button data-z="out" title="Zoom out">−</button>
          <span class="pct">100%</span>
          <button data-z="in" title="Zoom in">+</button>
          <button data-z="fit" title="Fit to window (0)">⤢</button>
        </div>
      </div>
      <pre class="src"></pre>`;
    this.el = el;
    this.sel = el.querySelector('select');
    this.metaEl = el.querySelector('.meta');
    this.stage = el.querySelector('.stage');
    this.canvas = el.querySelector('.canvas');
    this.statusEl = el.querySelector('.status');
    this.pctEl = el.querySelector('.pct');
    this.srcEl = el.querySelector('.src');

    for (const m of MAPS) {
      const o = document.createElement('option');
      o.value = m.file;
      o.textContent = (m.date ? m.date + ' — ' : '') + m.title;
      this.sel.append(o);
    }
    this.sel.onchange = () => this.load(this.sel.value);
    el.querySelector('.src-btn').onclick = (e) => {
      el.classList.toggle('showsrc');
      e.currentTarget.classList.toggle('on', el.classList.contains('showsrc'));
    };
    el.addEventListener('mousedown', () => setActive(this.index), true);
    el.querySelector('.zoom').onclick = (e) => {
      const z = e.target.dataset.z;
      if (z === 'in') this.zoomBy(1.25);
      else if (z === 'out') this.zoomBy(1 / 1.25);
      else if (z === 'fit') this.fit();
    };
    this.wirePanZoom();
  }

  async load(file) {
    if (!file) return;
    this.file = file;
    this.sel.value = file;
    const m = byFile.get(file);
    this.srcEl.textContent = m.code;
    this.renderMeta(m);
    this.canvas.innerHTML = '';
    this.statusEl.style.display = '';
    this.statusEl.className = 'status';
    this.statusEl.textContent = 'Laying out…';
    paintList();

    try {
      const svg = await renderMap(file);
      if (this.file !== file) return;                 // user moved on
      this.canvas.innerHTML = svg;
      const el = this.canvas.querySelector('svg');
      const vb = (el.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
      if (vb.length === 4) {
        el.style.width = vb[2] + 'px';
        el.style.height = vb[3] + 'px';
      }
      el.removeAttribute('width'); el.removeAttribute('height');
      this.statusEl.style.display = 'none';
      this.fit();
    } catch (err) {
      this.canvas.innerHTML = '';
      this.statusEl.style.display = '';
      this.statusEl.className = 'status err';
      this.statusEl.textContent = 'Mermaid could not render ' + file + '\n\n' + (err && err.message || err);
    }
  }

  renderMeta(m) {
    const bits = [`<b>${esc(m.title)}</b>`];
    const line = [m.date, m.outlet, m.genre, m.shape].filter(Boolean).map(esc);
    if (line.length) bits.push(`<span>${line.join(' · ')}</span>`);
    bits.push(`<span>${esc(m.file)}</span>`);
    if (m.levels.length) bits.push(`<span>${m.levels.join(' ')}</span>`);
    if (m.url) bits.push(`<a href="${esc(m.url)}" target="_blank" rel="noreferrer">article ↗</a>`);
    if (m.topics) bits.push(`<span>${esc(m.topics)}</span>`);
    if (m.question && !m.question.startsWith(m.title.slice(0, 40)))
      bits.push(`<span class="q">${esc(m.question)}</span>`);
    this.metaEl.innerHTML = bits.join('');
  }

  /* ---- zoom / pan ---- */
  apply() {
    this.canvas.style.transform = `translate(${this.x}px,${this.y}px) scale(${this.k})`;
    this.pctEl.textContent = Math.round(this.k * 100) + '%';
  }
  svgSize() {
    const el = this.canvas.querySelector('svg');
    if (!el) return null;
    return { w: parseFloat(el.style.width) || el.clientWidth, h: parseFloat(el.style.height) || el.clientHeight };
  }
  fit() {
    const s = this.svgSize(); if (!s) return;
    const r = this.stage.getBoundingClientRect();
    this.k = Math.min((r.width - 32) / s.w, (r.height - 32) / s.h);
    this.k = Math.max(0.05, Math.min(this.k, 2));
    this.x = (r.width - s.w * this.k) / 2;
    this.y = (r.height - s.h * this.k) / 2;
    this.apply();
  }
  zoomAt(factor, cx, cy) {
    const k2 = Math.max(0.05, Math.min(8, this.k * factor));
    const f = k2 / this.k;
    this.x = cx - (cx - this.x) * f;
    this.y = cy - (cy - this.y) * f;
    this.k = k2;
    this.apply();
  }
  zoomBy(factor) {
    const r = this.stage.getBoundingClientRect();
    this.zoomAt(factor, r.width / 2, r.height / 2);
  }
  wirePanZoom() {
    this.stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = this.stage.getBoundingClientRect();
      this.zoomAt(Math.pow(0.9988, e.deltaY), e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });

    let sx = 0, sy = 0, ox = 0, oy = 0, down = false;
    this.stage.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      down = true; sx = e.clientX; sy = e.clientY; ox = this.x; oy = this.y;
      this.stage.classList.add('drag');
      this.stage.setPointerCapture(e.pointerId);
    });
    this.stage.addEventListener('pointermove', (e) => {
      if (!down) return;
      this.x = ox + (e.clientX - sx); this.y = oy + (e.clientY - sy); this.apply();
    });
    const up = () => { down = false; this.stage.classList.remove('drag'); };
    this.stage.addEventListener('pointerup', up);
    this.stage.addEventListener('pointercancel', up);
    this.stage.addEventListener('dblclick', () => this.fit());
  }
}

/* --------------------------------------------------------------- shell --- */
const panesEl = document.getElementById('panes');
const listEl = document.getElementById('list');
const qEl = document.getElementById('q');
const cmpBtn = document.getElementById('cmp');

const panes = [new Pane(0), new Pane(1)];
let split = false, active = 0;

function layout() {
  panesEl.innerHTML = '';
  panesEl.classList.toggle('split', split);
  panesEl.append(panes[0].el);
  if (split) panesEl.append(panes[1].el);
  cmpBtn.classList.toggle('on', split);
  setActive(split ? active : 0);
  requestAnimationFrame(() => panes.forEach(p => { if (p.el.isConnected && p.file) p.fit(); }));
}
function setActive(i) {
  active = split ? i : 0;
  panes.forEach((p, j) => p.el.classList.toggle('active', j === active));
  paintList();
}
function toggleSplit() {
  split = !split;
  layout();
  if (split && !panes[1].file) panes[1].load(panes[0].file || MAPS[0].file);
}
cmpBtn.onclick = toggleSplit;

const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function visible() {
  const q = qEl.value.trim().toLowerCase();
  if (!q) return MAPS;
  return MAPS.filter(m => [m.title, m.file, m.date, m.topics, m.outlet, m.genre, m.shape, m.question]
    .join(' ').toLowerCase().includes(q));
}

function paintList() {
  const open = new Set(panes.filter(p => p.el.isConnected).map(p => p.file));
  listEl.innerHTML = '';
  let group = null;
  for (const m of visible()) {
    if (m.group !== group) {
      group = m.group;
      const h = document.createElement('div');
      h.className = 'grouphead';
      h.textContent = group;
      listEl.append(h);
    }
    const b = document.createElement('button');
    b.className = 'item' + (open.has(m.file) ? ' on' : '');
    const which = split && open.has(m.file)
      ? ' <span class="badge">[' + (panes[0].file === m.file ? 'A' : '') + (panes[1].file === m.file ? 'B' : '') + ']</span>'
      : '';
    b.innerHTML = `<div class="t">${esc(m.title)}${which}</div>
      <div class="m">${[m.date, m.file].filter(Boolean).map(esc).join(' · ')}</div>`;
    b.onclick = () => panes[active].load(m.file);
    listEl.append(b);
  }
}

qEl.oninput = paintList;

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') {
    if (e.key === 'Escape') { qEl.value = ''; paintList(); qEl.blur(); }
    return;
  }
  const p = panes[active];
  if (e.key === '0') p.fit();
  else if (e.key === '+' || e.key === '=') p.zoomBy(1.25);
  else if (e.key === '-') p.zoomBy(1 / 1.25);
  else if (e.key === 'c') toggleSplit();
  else if (e.key === '/') { e.preventDefault(); qEl.focus(); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const list = visible();
    const i = list.findIndex(m => m.file === p.file);
    const next = list[Math.min(list.length - 1, Math.max(0, i + (e.key === 'ArrowDown' ? 1 : -1)))];
    if (next) p.load(next.file);
  }
});

addEventListener('resize', () => panes.forEach(p => { if (p.el.isConnected && p.file) p.fit(); }));

layout();
paintList();
panes[0].load((MAPS.find(m => m.group !== 'Schema & templates') || MAPS[0]).file);
</script>
</body>
</html>
"""


def build(out: Path) -> list[dict]:
    maps = collect()
    authors = {m["author"] for m in maps if m["author"]}
    author = ", ".join(sorted(authors)) or "Brad W. Setser"
    articles = [m for m in maps if m["group"] != "Schema & templates"]

    page = (TEMPLATE
            .replace("__MAPS_JSON__", json.dumps(maps, ensure_ascii=False)
                     .replace("</", "<\\/"))
            .replace("__MERMAID__", MERMAID_VERSION)
            .replace("__ELK__", ELK_VERSION)
            .replace("__COUNT__", str(len(articles)))
            .replace("__AUTHOR__", html.escape(author))
            .replace("__BUILT__", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return maps


def serve(out: Path, port: int) -> None:
    """Serve the viewer over http, for anyone whose browser blocks file:// pages."""
    import functools
    import http.server

    handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                directory=str(out.parent))
    url = f"http://127.0.0.1:{port}/{out.name}"
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"serving {url}  (ctrl-c to stop)")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output HTML path")
    ap.add_argument("--open", action="store_true", help="open the viewer when done")
    ap.add_argument("--serve", type=int, nargs="?", const=8765, metavar="PORT",
                    help="serve the viewer on localhost and open it (ctrl-c to stop)")
    args = ap.parse_args()

    maps = build(args.out)
    size = args.out.stat().st_size / 1024
    print(f"{args.out.relative_to(ROOT)}  ({size:.0f} KB, {len(maps)} maps)")
    for m in maps:
        print(f"  {m['date'] or '-':>12}  {m['file']:<48} {m['title'][:60]}")
    if args.serve:
        serve(args.out, args.serve)
    elif args.open:
        webbrowser.open(args.out.resolve().as_uri())


if __name__ == "__main__":
    main()
