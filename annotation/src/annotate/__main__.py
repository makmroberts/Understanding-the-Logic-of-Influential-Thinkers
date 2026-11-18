"""Command line.

  python -m annotate run --doc setser_2025-09-12_trump-shock-that-wasnt
  python -m annotate run --url https://www.cfr.org/articles/<slug>
  python -m annotate run --doc <doc> --model gpt-6-sol        # one model for all three steps
  python -m annotate run --doc <doc> --repeat 1               # ask again, for the consistency report
  python -m annotate run --doc <doc> --oracle                 # links and facets on the hand-drawn boxes
  python -m annotate kb                                       # re-add model articles to kb/ and export
  python -m annotate report                                   # articles/evaluation.md across runs
  python -m annotate profile                                  # what a hand-drawn map looks like
"""
from __future__ import annotations

import argparse
import json
import sys

from .llm import GatewayError


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(prog="annotate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="map one article")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--doc")
    g.add_argument("--url")
    r.add_argument("--model")
    r.add_argument("--repeat", type=int, default=0)
    r.add_argument("--oracle", action="store_true")
    r.add_argument("--tag", help="name of a prompt or settings variant under test; the run is an experiment")
    sub.add_parser("kb", help="put model-annotated articles into kb/data and export")
    sub.add_parser("report", help="evaluation across runs")
    sub.add_parser("profile", help="the corpus profile the completeness check uses")
    a = ap.parse_args()

    if a.cmd == "run":
        from .pipeline import StepFailed, run
        try:
            out = run(a.doc, a.url, a.model, a.repeat, a.oracle, a.tag)
        except (GatewayError, StepFailed) as e:
            sys.exit(f"stopped: {e}")
        print(f"done: {out}")
        for name in ("review.md", "evaluation.md"):
            if (out / name).exists():
                print(f"  {name}")
    elif a.cmd == "kb":
        from .kb import into_kb
        print(json.dumps(into_kb(), indent=1))
    elif a.cmd == "report":
        from .evaluate import report
        print(f"wrote {report()}")
    elif a.cmd == "profile":
        from .config import profile
        print(json.dumps(profile(), indent=1))


if __name__ == "__main__":
    main()
