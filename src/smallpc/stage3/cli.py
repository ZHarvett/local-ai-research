"""``python -m smallpc.stage3 headline | gate | repro``."""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..stage2 import eligibility
from . import gate as gt
from . import headline as hl
from . import repro as rp

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2


def _headline(a: argparse.Namespace) -> int:
    try:
        sanity = json.loads(a.sanity.read_text())
        res = hl.headline(a.sessions, sanity, str(a.sanity))
    except eligibility.Refused as e:
        print(f"smallpc.stage3: refused: {e}", file=sys.stderr)
        return EXIT_USAGE
    except (ValueError, OSError, KeyError) as e:
        print(f"smallpc.stage3: {e}", file=sys.stderr)
        return EXIT_ERROR
    j, m = hl.write_outputs(res, a.out)
    print(f"wrote {j} and {m}")
    for ctx, e in res["contexts"].items():
        h = e["headline"]
        print(
            f"{ctx}: headline {h['choice'] or 'none'}" + (f" ({h['label']})" if h["label"] else "")
        )
    if res["disagreeing_contexts"]:
        print("clean and all-units versions DISAGREE in: " + ", ".join(res["disagreeing_contexts"]))
    for h in res["human_decision_needed"]:
        print(f"HUMAN DECISION NEEDED: {h}")
    return EXIT_OK


def _gate(a: argparse.Namespace) -> int:
    try:
        g = gt.gate(a.session, a.spec)
    except (ValueError, OSError, KeyError) as e:
        print(f"smallpc.stage3: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(g, indent=1) if a.json else gt.format_gate(g))
    return EXIT_OK if g["pass"] else EXIT_ERROR


def _repro(a: argparse.Namespace) -> int:
    try:
        out = rp.build(a.original, a.rerun, a.cells.split(","))
    except (ValueError, OSError, KeyError) as e:
        print(f"smallpc.stage3: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(rp.render(out))
    return EXIT_OK if out["pass"] else EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.stage3", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("headline", help="the Stage 3 headline tables (plan 5.4)")
    h.add_argument("--sessions", nargs="+", required=True, type=Path)
    h.add_argument(
        "--sanity", required=True, type=Path, help="sanity run on the tuned config files"
    )
    h.add_argument("--out", required=True, type=Path, help="writes <out>.json and <out>.md")
    g = sub.add_parser("gate", help="may the next Stage 3 or 4 session start?")
    g.add_argument("--session", required=True, type=Path)
    g.add_argument(
        "--spec", type=Path, help="spec to classify stock and tuned cells (default: cell profile)"
    )
    g.add_argument("--json", action="store_true")
    r = sub.add_parser("repro", help="the S2 check, with the all-units fallback")
    r.add_argument("--original", nargs="+", required=True, type=Path)
    r.add_argument("--rerun", nargs="+", required=True, type=Path)
    r.add_argument("--cells", required=True, help="e.g. stock-64K,tuned-64K")
    a = ap.parse_args(argv)
    return {"headline": _headline, "gate": _gate, "repro": _repro}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
