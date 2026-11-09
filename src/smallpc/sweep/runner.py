"""Command line of the sweep runner.

    python -m smallpc.sweep check SPEC [--only context=32K] [--only batch=b2048]
    python -m smallpc.sweep run SPEC --session-id ID [--resume] [--rerun-flagged]
        [--only context=32K] [--only batch=b2048] [--allow-dirty] [--inhibit-tag TAG]
        [--machine M.toml] [--model-config MODEL.toml] [--no-inhibit-check]
    python -m smallpc.sweep status [SESSION-ID | --latest]
    python -m smallpc.sweep latest SPEC [--only ...]

Normally started through ``scripts/run-sweep.sh`` (detached, GPU lock, systemd-inhibit).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from ..config import load_sweep, repo_root
from . import estimate, status
from . import spec as sp
from .core import EXIT_ERROR, EXIT_OK, SessionAbort, default_env
from .session import Session


def check_spec(path: Path, root: Path | None = None, only: dict[str, str] | None = None) -> dict:
    """Expand and validate a spec. Raises ``SpecError`` if it is inconsistent or does not expand
    to the number of cells it declares (``expect_cells``; always checked on the whole spec, before
    ``only`` filters it). Reports the cell counts, the expansion per axis value and the time
    estimate of the (filtered) cells."""
    root = root or repo_root()
    spec = load_sweep(path)
    cells = sp.expand(spec, root)
    sp.validate_cells(cells)
    if spec.expect_cells is not None and len(cells) != spec.expect_cells:
        raise sp.SpecError(
            f"the spec expects {spec.expect_cells} cells but expands to {len(cells)}"
        )
    total = len(cells)
    cells = sp.apply_filter(cells, only or {})

    def ctx_of(c: sp.CellDef) -> str:
        return c.coords.get("context", str(c.overrides.get("context")))

    by_ctx: dict[str, int] = {}
    by_axis: dict[str, dict[str, int]] = {}
    for c in cells:
        by_ctx[ctx_of(c)] = by_ctx.get(ctx_of(c), 0) + 1
        for axis, value in c.coords.items():
            by_axis.setdefault(axis, {})
            by_axis[axis][value] = by_axis[axis].get(value, 0) + 1
    by_axis["profile"] = {}
    for c in cells:
        by_axis["profile"][c.profile] = by_axis["profile"].get(c.profile, 0) + 1
    order = sp.order_cells(cells, spec.shuffle_seed)
    canary_reps = spec.canary.repetitions if spec.canary else 0
    est = estimate.spec_s(cells, spec.repetitions, canary_repetitions=canary_reps)
    return {
        "name": spec.name,
        "cells": len(cells),
        "cells_in_spec": total,
        "filter": only or {},
        "stock_cells": sum(c.profile == "stock" for c in cells),
        "by_context": by_ctx,
        "by_axis": by_axis,
        "cells_with_tokens": [c.name for c in cells if c.tokens],
        "repetitions": spec.repetitions,
        "canary": spec.canary is not None,
        "first_in_order": [c.name for c in order[:5]],
        "estimate": {
            "basis": "WP8 live-check request times, planning overhead 60 s per cell, 3 probe "
            "steps per (context, batch) group with a @max_fit cell; updated by measured "
            "pre-flight figures in docs/runbook-stage1.md",
            "cells_h": round(est["cells_s"] / 3600, 2),
            "probing_h": round(est["probing_s"] / 3600, 2),
            "canaries_h": round(est["canaries_s"] / 3600, 2),
            "total_h": round(est["total_s"] / 3600, 2),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.sweep")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("spec", type=Path)
    c.add_argument("--only", action="append", default=[], help="axis=value (context, batch)")
    r = sub.add_parser("run")
    r.add_argument("spec", type=Path)
    r.add_argument("--session-id", required=True)
    r.add_argument("--resume", action="store_true")
    r.add_argument("--rerun-flagged", action="store_true")
    r.add_argument("--only", action="append", default=[])
    r.add_argument("--allow-dirty", action="store_true")
    r.add_argument("--inhibit-tag")
    r.add_argument("--no-inhibit-check", action="store_true", help="tests only")
    r.add_argument("--machine", type=Path)
    r.add_argument("--model-config", type=Path)
    r.add_argument("--health-timeout", type=int, default=600)
    s = sub.add_parser("status")
    s.add_argument("session", nargs="?")
    s.add_argument("--latest", action="store_true")
    s.add_argument("--json", action="store_true")
    lt = sub.add_parser("latest")
    lt.add_argument("spec", type=Path)
    lt.add_argument("--only", action="append", default=[])
    a = ap.parse_args(argv)
    root = repo_root()
    out_root = root / "data/raw"

    try:
        if a.cmd == "check":
            print(json.dumps(check_spec(a.spec, root, sp.parse_only(a.only)), indent=2))
            return EXIT_OK
        if a.cmd == "latest":
            sid = status.latest_session(out_root, load_sweep(a.spec).name, sp.parse_only(a.only))
            if sid is None:
                print("no unfinished session for this spec", file=sys.stderr)
                return EXIT_ERROR
            print(sid)
            return EXIT_OK
        if a.cmd == "status":
            sid = a.session
            if a.latest or not sid:
                dirs = sorted(out_root.glob("*/session.json"), key=lambda p: p.stat().st_mtime)
                if not dirs:
                    print("no sessions", file=sys.stderr)
                    return EXIT_ERROR
                sid = dirs[-1].parent.name
            rep = status.report(out_root / sid)
            print(json.dumps(rep, indent=2) if a.json else status.format_report(rep))
            return EXIT_OK

        # run
        only = sp.parse_only(a.only)
        spec = load_sweep(a.spec)
        sp.validate_cells(sp.expand(spec, root))
        env = default_env(root, a.machine, a.model_config, health_timeout=a.health_timeout)
        env.check_inhibit = not a.no_inhibit_check
        mode = "rerun" if a.rerun_flagged else ("resume" if a.resume else "run")
        sess = Session(env, spec, a.spec, a.session_id, filters=only,
                       allow_dirty=a.allow_dirty, inhibit_tag=a.inhibit_tag, mode=mode)  # fmt: skip
        sess.install_signals()
        if a.rerun_flagged:
            return sess.rerun_flagged()
        return sess.run(resume=a.resume)
    except (sp.SpecError, ValidationError, SessionAbort, OSError) as e:
        print(f"smallpc.sweep: {e}", file=sys.stderr)
        return getattr(
            e, "exit_code", 2 if isinstance(e, sp.SpecError | ValidationError) else EXIT_ERROR
        )


if __name__ == "__main__":
    raise SystemExit(main())
