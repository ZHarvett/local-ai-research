"""The gate between Stage 2 sessions: may the next session start?

``python -m smallpc.stage2 gate --stage 2f|2a|2a2|2b|2c|2d --session <dir>``

The Stage 1 gate (a: runner exited 0 and the state is complete; b: every cell has a final record;
c: no accounting, warm_prefill or cache_miss flag; d: no thermal or drift flag; e: no did_not_fit
with reason startup_failure, startup_timeout, crash_mid_cell or oom_runtime; f: at most 20% of the
measured windows paging-flagged), with two changes for Stage 2:

* criterion f does not apply to 2f, because paging is what 2f measures: the gate reports the
  number of flagged windows per cell, and the next step is the decision tool, not a stop;
* from 2a onward criterion f applies with the chosen ``--cache-ram``: more than 20% flagged
  windows means stop and report, because the 2f choice did not hold.

A failed criterion means stop: the next session does not start until a human has looked.
Flagged repetitions are counted from attempt 1 (before any ``--rerun-flagged``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .. import analysis
from ..config import repo_root

BAD_FLAGS = ("accounting", "warm_prefill", "cache_miss")
BAD_DNF_REASONS = ("startup_failure", "startup_timeout", "crash_mid_cell", "oom_runtime")
PAGING_LIMIT_PCT = 20  # "no more than 20%"
NEXT = {
    "2f": "run `python -m smallpc.stage2 decide --stage 2f` (do not run --rerun-flagged first)",
    "2a": "run `decide --stage 2a`, then generate the 2a2 spec",
    "2a2": "run `decide --stage 2a2`, then generate the 2b, 2c and 2d specs from its winner",
    "2b": "run `decide --stage 2b`",
    "2c": "run `decide --stage 2c`",
    "2d": "run `decide --stage 2d`",
}


def _job_status(session_id: str, logs_root: Path) -> dict | None:
    """The newest detached job of this session (``sweep-<id>-*``, ``resume-<id>-*``)."""
    jobs = logs_root / "jobs"
    if not jobs.is_dir():
        return None
    found = sorted(
        d for p in ("sweep", "resume") for d in jobs.glob(f"{p}-{session_id}-*") if d.is_dir()
    )
    if not found:
        return None
    f = found[-1] / "status.json"
    return json.loads(f.read_text()) if f.exists() else None


def _attempt1_windows(sess: analysis.LoadedSession) -> list[dict]:
    out = []
    for (cell, _h), summ in sess.summaries.items():
        if summ.get("role") != "measured":
            continue
        for ins in summ.get("instances", []):
            for w in ins.get("windows", []):
                if w.get("attempt") == 1:
                    out.append(
                        {"cell": cell, "repetition": w["repetition"], "flags": w.get("flags") or []}
                    )
    return out


def gate(stage: str, session_dir: Path, *, logs_root: Path | None = None) -> dict:
    if stage not in NEXT:
        raise ValueError(f"unknown stage {stage!r}")
    sess = analysis.load_session(session_dir)
    logs = logs_root or Path(os.environ.get("SMALLPC_LOG_ROOT", repo_root() / "data/logs"))
    final_units = [u for u in analysis.build_units([sess]) if not u["superseded"]]
    crit: list[dict] = []

    def add(cid: str, text: str, ok: bool | None, detail: str, applies: bool = True) -> None:
        crit.append({"id": cid, "text": text, "applies": applies, "pass": ok, "detail": detail})

    # a: runner exit 0, state complete
    job = _job_status(sess.id, Path(logs))
    state = sess.meta.get("state")
    job_ok = job is None or job.get("exit_code") == 0
    job_text = (
        "not found (state only)"
        if job is None
        else f"exit code {job.get('exit_code')}, state {job.get('state')!r}"
    )
    add(
        "a",
        "the runner exited with 0 and the state is complete",
        state == "complete" and job_ok,
        f"state {state!r}; job {job_text}",
    )
    # b: every cell has a final record
    order = sess.meta.get("cell_order") or []
    final = {c["cell"]: c for c in sess.cells if c.get("final") and c["role"] == "measured"}
    missing = [n for n in order if n not in final]
    done = f"{len(order) - len(missing)} of {len(order)} cells final"
    add(
        "b",
        "every cell has a final record",
        not missing,
        done + (f"; missing {missing}" if missing else ""),
    )
    # c: no accounting / warm_prefill / cache_miss
    bad = sorted(
        {(u["cell"], u["repetition"], f) for u in final_units for f in u["flags"] if f in BAD_FLAGS}
    )
    add(
        "c",
        "no accounting, warm_prefill or cache_miss flag",
        not bad,
        "none" if not bad else "; ".join(f"{c} r{r} {f}" for c, r, f in bad),
    )
    # d: no thermal or drift flag
    thermal = sorted({(u["cell"], u["repetition"]) for u in final_units if "thermal" in u["flags"]})
    drift = {k: (v or {}).get("flag") for k, v in (sess.meta.get("drift") or {}).items()}
    drifted = sorted(k for k, v in drift.items() if v)
    add(
        "d",
        "no thermal or drift flag",
        not thermal and not drifted,
        f"thermal units {thermal or 'none'}; drift {drift or 'not recorded'}",
    )
    # e: no did_not_fit for the listed reasons
    dnf = sorted(
        {(c["cell"], c.get("reason")) for c in final.values() if c["status"] == "did_not_fit"}
    )
    bad_dnf = [(c, r) for c, r in dnf if r in BAD_DNF_REASONS]
    add(
        "e",
        "no did_not_fit with reason " + ", ".join(BAD_DNF_REASONS),
        not bad_dnf,
        f"did_not_fit: {dnf or 'none'}",
    )
    # f: paging share of the attempt-1 windows
    wins = _attempt1_windows(sess)
    flagged = [w for w in wins if "paging" in w["flags"]]
    pct = 100 * len(flagged) / len(wins) if wins else 0.0
    per_cell: dict[str, dict] = {}
    for w in wins:
        e = per_cell.setdefault(w["cell"], {"windows": 0, "flagged": 0, "flagged_repetitions": []})
        e["windows"] += 1
        if "paging" in w["flags"]:
            e["flagged"] += 1
            e["flagged_repetitions"].append(w["repetition"])
    detail = f"{len(flagged)} of {len(wins)} measured attempt-1 windows paging-flagged ({pct:.1f}%)"
    if stage == "2f":
        add(
            "f",
            "paging share (not applied to 2f: paging is what 2f measures)",
            None,
            detail + "; per cell below",
            applies=False,
        )
    else:
        add(
            "f",
            f"at most {PAGING_LIMIT_PCT}% of the measured windows paging-flagged "
            "(the 2f choice held)",
            pct <= PAGING_LIMIT_PCT,
            detail,
        )
    applicable = [c for c in crit if c["applies"]]
    ok = all(c["pass"] for c in applicable)
    failed = [c["id"] for c in applicable if not c["pass"]]
    if ok:
        nxt = NEXT[stage]
    elif "f" in failed:
        nxt = (
            "STOP and report: more than 20% of the windows are paging-flagged, "
            "so the 2f choice did not hold"
        )
    else:
        nxt = (
            f"STOP and report: criteria {failed} failed; the next session does not start "
            "until a human has looked"
        )
    return {
        "stage": stage,
        "session_id": sess.id,
        "pass": ok,
        "failed": failed,
        "criteria": crit,
        "paging_per_cell": dict(sorted(per_cell.items())),
        "next": nxt,
        "stop_for_human": not ok,
    }


def format_gate(g: dict) -> str:
    lines = [f"gate for {g['stage']} session {g['session_id']}: {'PASS' if g['pass'] else 'FAIL'}"]
    for c in g["criteria"]:
        mark = "n/a " if not c["applies"] else ("PASS" if c["pass"] else "FAIL")
        lines.append(f"  [{mark}] {c['id']}: {c['text']}: {c['detail']}")
    if g["stage"] == "2f":
        lines.append("  paging-flagged windows per cell (attempt 1):")
        for cell, e in g["paging_per_cell"].items():
            reps = f" (repetitions {e['flagged_repetitions']})" if e["flagged"] else ""
            lines.append(f"    {cell}: {e['flagged']} of {e['windows']}{reps}")
    lines.append(f"  next: {g['next']}")
    return "\n".join(lines)
