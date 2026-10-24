#!/usr/bin/env python3
"""Restore the graph view's colours and forces. Run with Obsidian CLOSED.

    python scripts/graph_prefs.py              # colours + forces
    python scripts/graph_prefs.py --colors     # colours only, leave forces alone
    python scripts/graph_prefs.py --force      # write even if Obsidian is running

WHY THIS EXISTS

Obsidian owns `.obsidian/graph.json`. It holds the file in memory and writes its
own state back on quit, on a graph-settings change, and on its own schedule - so
anything written there while the vault is open is reverted, colour groups
included. `export_obsidian.py` restores the colours on every run and loses the
race just as often.

So this is the one thing to run after quitting Obsidian, and it refuses to write
while Obsidian is running rather than silently losing again.

WHAT THE FORCE PRESET IS FOR

The defaults are tuned for a dense note vault. The argument-only view
(`-path:subjects -path:views -path:canvas -path:articles -file:index`) is the
opposite: 365 notes, 467 links, mean degree 2.6, in 21 separate components. At
`centerStrength` 0.52 those components pile into the middle; at `linkStrength`
1.0 each tree contracts into a ball. The preset pulls the centre force down and
lets the chains stretch.

It also turns arrows ON, because on an argument graph the direction is the
content - which claim backs which.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_obsidian import COLORS, FACET_COLORS, FACET_ORDER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "obsidian"
GRAPH = VAULT / ".obsidian" / "graph.json"

PRESET = {
    "centerStrength": 0.1,      # 21 components should sit apart, not pile up
    "repelStrength": 16,        # push the separated trees away from each other
    "linkStrength": 0.55,       # let chains stretch instead of contracting
    "linkDistance": 260,
    "showArrow": True,          # direction is the content
    "textFadeMultiplier": 0.3,  # claim text without zooming all the way in
    "nodeSizeMultiplier": 1.1,
    "lineSizeMultiplier": 0.9,
}


def obsidian_running() -> bool:
    """True if Obsidian holds the file. Best effort; never blocks on its own."""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Obsidian.exe"],
                             capture_output=True, text=True, timeout=10).stdout
        return "Obsidian.exe" in out
    except Exception:
        return False


def color_groups() -> list:
    """One group per claim-role folder and per facet folder that exists.

    Built from the vault as it is, so a removed facet cannot leave a group
    pointing at nothing - which is what happened when `sector` and `actor` were
    dropped.
    """
    groups = []
    claims = VAULT / "claims"
    for role, hexcol in COLORS.items():
        if (claims / role).is_dir():
            groups.append({"query": f"path:claims/{role}",
                           "color": {"a": 1, "rgb": int(hexcol.lstrip("#"), 16)}})
    subjects = VAULT / "subjects"
    for facet in FACET_ORDER:
        if (subjects / facet).is_dir():
            groups.append({"query": f"path:subjects/{facet}",
                           "color": {"a": 1,
                                     "rgb": int(FACET_COLORS[facet], 16)}})
    for folder, hexcol in (("concepts", "#E8A0BF"), ("articles", "#C9A23D")):
        if (VAULT / folder).is_dir():
            groups.append({"query": f"path:{folder}",
                           "color": {"a": 1, "rgb": int(hexcol.lstrip("#"), 16)}})
    return groups


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--colors", action="store_true",
                    help="restore colour groups only, leave forces as they are")
    ap.add_argument("--force", action="store_true",
                    help="write even though Obsidian is running (it will lose)")
    args = ap.parse_args()

    if obsidian_running() and not args.force:
        sys.exit(
            "Obsidian is running, so anything written here is reverted when it\n"
            "next saves its graph state - colour groups included.\n\n"
            "  1. quit Obsidian (fully: it writes graph.json on exit)\n"
            "  2. python scripts/graph_prefs.py\n"
            "  3. reopen the vault\n\n"
            "Use --force to write anyway.")

    data = json.loads(GRAPH.read_text(encoding="utf-8")) if GRAPH.exists() else {}
    before = len(data.get("colorGroups") or [])
    groups = color_groups()
    data["colorGroups"] = groups
    changed = []
    if not args.colors:
        for k, v in PRESET.items():
            if data.get(k) != v:
                changed.append(f"{k}: {data.get(k)} -> {v}")
            data[k] = v
    GRAPH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print(f"colour groups: {before} -> {len(groups)}")
    for c in changed:
        print(f"  {c}")
    print("\nNow reopen the vault. If the colours vanish again, Obsidian was "
          "open when this ran.")


if __name__ == "__main__":
    main()
