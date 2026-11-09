"""Status of a session, for ``scripts/sweep-status.sh``: cells done and remaining, the current
cell and phase, an estimated time to finish, the flags so far and the last error."""

from __future__ import annotations

import calendar
import json
import time
from pathlib import Path

from . import estimate
from . import records as rec
from .server import pid_alive


def _epoch(utc: str | None) -> float | None:
    try:
        return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def latest_session(out_root: Path, spec_name: str, filters: dict | None = None,
                   unfinished_only: bool = True) -> str | None:  # fmt: skip
    best = None
    for sj in sorted(Path(out_root).glob("*/session.json")):
        s = _load(sj)
        if not s or s.get("spec", {}).get("name") != spec_name:
            continue
        if (s.get("filters") or {}) != (filters or {}):
            continue
        if unfinished_only and s.get("state") == "complete":
            continue
        if best is None or s["created_utc"] >= best["created_utc"]:
            best = s
    return best["session_id"] if best else None


def report(session_dir: Path) -> dict:
    d = Path(session_dir)
    sess = _load(d / "session.json") or {}
    prog = _load(d / "progress.json") or {}
    loaded = rec.Store(d / "records.jsonl").load()
    order = sess.get("cell_order", [])
    final = {c["cell"]: c for c in loaded.cells if c["final"] and c["role"] == "measured"}
    done = [n for n in order if n in final]
    remaining = [n for n in order if n not in final]
    # measured seconds per completed cell, by context (from the cell summaries)
    measured: dict[int, list[float]] = {}
    for f in (d / "cells").glob("*.json") if (d / "cells").exists() else []:
        s = _load(f) or {}
        if s.get("role") != "measured" or s.get("cell") not in final:
            continue
        secs = 0.0
        for inst in s.get("instances", []):
            a, b = _epoch(inst.get("started_utc")), _epoch(inst.get("finished_utc"))
            if a and b:
                secs += b - a
        ctx = next((int(x) for x in [_context(s)] if x), None)
        if ctx and secs:
            measured.setdefault(ctx, []).append(secs)
    reps = sess.get("repetitions", 2)
    eta = 0.0
    for n in remaining:
        ctx = _ctx_of(order, n, d)
        vals = measured.get(ctx or 0)
        eta += (
            sum(vals) / len(vals)
            if vals
            else (estimate.cell_s(ctx, reps) if ctx in estimate.DEPTHS else 300.0)
        )
    counts: dict[str, int] = {}
    for r in loaded.requests:
        if r["role"] == "warmup":
            continue
        for f in r.get("flags", []):
            counts[f] = counts.get(f, 0) + 1
    cell_flags = sorted({(c["cell"], f) for c in loaded.cells if c["final"] for f in c["flags"]})
    runs = sess.get("runs", [])
    pid = runs[-1]["pid"] if runs else None
    last_error = prog.get("last_error") or sess.get("last_error")
    return {
        "session_id": sess.get("session_id", d.name),
        "state": sess.get("state"),
        "runner_alive": bool(pid and pid_alive(pid)),
        "pid": pid,
        "cells_total": len(order),
        "cells_done": len(done),
        "cells_remaining": len(remaining),
        "current_cell": prog.get("cell"),
        "phase": prog.get("phase"),
        "repetition": prog.get("repetition"),
        "depth": prog.get("depth"),
        "eta_s": round(eta),
        "request_flags_so_far": counts,
        "cell_flags": [f"{c}:{f}" for c, f in cell_flags],
        "drift": (sess.get("drift") or {}),
        "last_error": last_error,
        "records": {
            "requests": len(loaded.requests),
            "cells": len(loaded.cells),
            "torn_lines": loaded.torn_lines,
            "incomplete_batches": loaded.incomplete_batches,
        },  # fmt: skip
        "updated_utc": prog.get("updated_utc"),
    }


def _context(summary: dict) -> int | None:
    argv = summary.get("argv", [])
    if "-c" in argv:
        return int(argv[argv.index("-c") + 1])
    return None


def _ctx_of(order: list[str], name: str, d: Path) -> int | None:
    f = (
        next(iter((d / "resolved").glob(f"{name}.toml")), None)
        if (d / "resolved").exists()
        else None
    )
    if f:
        for ln in f.read_text().splitlines():
            if ln.startswith("context ="):
                return int(ln.split("=")[1])
    return None


def fmt_duration(s: float | None) -> str:
    if s is None:
        return "?"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{sec:02d}s"


def format_report(r: dict) -> str:
    alive = "running" if r["runner_alive"] else "NOT running"
    lines = [
        f"session   {r['session_id']}   state={r['state']}   runner {alive} (pid {r['pid']})",
        f"cells     {r['cells_done']}/{r['cells_total']} done, {r['cells_remaining']} remaining",
        f"current   {r['current_cell']}   phase={r['phase']}   repetition={r['repetition']}   "
        f"depth={r['depth']}",
        f"ETA       ~{fmt_duration(r['eta_s'])} for the remaining cells "
        "(measured mean per context where available, else the live-check estimate)",
        f"flags     requests: {r['request_flags_so_far'] or 'none'}   cells: "
        f"{r['cell_flags'] or 'none'}",
        f"drift     {_drift_text(r['drift'])}",
        f"records   {r['records']}",
        f"last error  {r['last_error'] or 'none'}",
        f"updated   {r['updated_utc']}",
    ]
    return "\n".join(lines)


def _drift_text(d: dict) -> str:
    if not d:
        return "not computed yet (end canary pending)"
    return "; ".join(f"{k}: {v.get('flag') or 'no flag'}" for k, v in d.items())
