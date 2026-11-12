"""The Stage 3 / Stage 4 session gate: may the next session start?

``python -m smallpc.stage3 gate --session data/raw/stage3-32K [--spec configs/sweeps/stage3.toml]``

Criteria a to e are the Stage 2 gate's own (``smallpc.stage2.gate.gate``, not modified; they do not
depend on the stage): a the runner exited with 0 and the state is complete; b every cell has a final
record; c no accounting, warm_prefill or cache_miss flag; d no thermal or drift flag; e no
did_not_fit with reason startup_failure, startup_timeout, crash_mid_cell or oom_runtime.

Criterion f (plan 5.4, "Stock paging"; the 40% / 1,024 MiB reading of the step lead's decision for
Stage 2a, docs/decisions.md): STOP if more than 40% of the attempt-1 windows of the TUNED cells and
of the canaries are paging-flagged, or if any paging-flagged window among them shows
``swap_activity_mib`` above 1,024. The STOCK cells' paging and swap figures are reported and never
fail the gate: stock keeps ``--cache-ram 8192`` and is expected to page on this machine.
"""

# ruff: noqa: E501
from __future__ import annotations

from pathlib import Path

from .. import analysis
from ..stage2 import gate as stage2_gate
from ..sweep import spec as sp

PAGING_LIMIT_PCT = 40
SWAP_LIMIT_MIB = 1024.0
CANARY_ROLES = ("canary_start", "canary_end")


def _paging_flagged(w: dict) -> bool:
    return "paging" in (w.get("flags") or []) or (w.get("paging") or {}).get("flag") == "paging"


def _group(summ: dict, roles: dict[str, str]) -> str | None:
    """``"stock"``, ``"tuned"`` or ``"canary"`` for a cell summary."""
    if summ.get("role") in CANARY_ROLES:
        return "canary"
    if summ.get("role") != "measured":
        return None
    prof = roles.get(summ["cell"], summ.get("profile"))
    return "stock" if prof == "stock" else "tuned"


def _spec_roles(spec_path: Path | None, root: Path | None) -> dict[str, str]:
    if spec_path is None:
        return {}
    from ..config import load_sweep, repo_root

    cells = sp.expand(load_sweep(spec_path), Path(root) if root else repo_root())
    return {c.name: c.profile for c in cells}


def windows_by_group(sess: analysis.LoadedSession, roles: dict[str, str]) -> list[dict]:
    out = []
    for (cell, _h), summ in sess.summaries.items():
        group = _group(summ, roles)
        if group is None:
            continue
        for ins in summ.get("instances", []):
            for w in ins.get("windows", []):
                if w.get("attempt") != 1:
                    continue
                out.append(
                    {
                        "cell": cell,
                        "group": group,
                        "repetition": w["repetition"],
                        "flagged": _paging_flagged(w),
                        "swap_mib": w.get("swap_activity_mib"),
                        "major_faults": (w.get("paging") or {}).get("major_faults"),
                    }
                )
    return out


def gate(
    session_dir: Path,
    spec_path: Path | None = None,
    *,
    logs_root: Path | None = None,
    root: Path | None = None,
) -> dict:
    # a to e: the Stage 2 gate's functions. The stage argument only selects its "next" text and
    # whether f applies; its criterion f (20% of all windows) is replaced below.
    g = stage2_gate.gate("2a", Path(session_dir), logs_root=logs_root)
    crit = [c for c in g["criteria"] if c["id"] in "abcde"]
    sess = analysis.load_session(session_dir)
    wins = windows_by_group(sess, _spec_roles(spec_path, root))
    judged = [w for w in wins if w["group"] in ("tuned", "canary")]
    flagged = [w for w in judged if w["flagged"]]
    pct = 100 * len(flagged) / len(judged) if judged else 0.0
    heavy = [w for w in flagged if w["swap_mib"] is not None and w["swap_mib"] > SWAP_LIMIT_MIB]
    per_cell: dict[str, dict] = {}
    for w in wins:
        e = per_cell.setdefault(
            w["cell"],
            {"group": w["group"], "windows": 0, "flagged": 0, "flagged_repetitions": [],
             "max_swap_mib": None, "max_faults": 0},
        )  # fmt: skip
        e["windows"] += 1
        if w["flagged"]:
            e["flagged"] += 1
            e["flagged_repetitions"].append(w["repetition"])
        if w["swap_mib"] is not None:
            e["max_swap_mib"] = max(w["swap_mib"], e["max_swap_mib"] or w["swap_mib"])
        e["max_faults"] = max(e["max_faults"], w["major_faults"] or 0)
    stock = [w for w in wins if w["group"] == "stock"]
    stock_flagged = [w for w in stock if w["flagged"]]
    detail = (
        f"{len(flagged)} of {len(judged)} attempt-1 windows of the tuned cells and the canaries "
        f"paging-flagged ({pct:.1f}%, limit {PAGING_LIMIT_PCT}%); flagged windows above "
        f"{SWAP_LIMIT_MIB:.0f} MiB of swap growth: "
        + (
            ", ".join(f"{w['cell']} r{w['repetition']} ({w['swap_mib']:.0f} MiB)" for w in heavy)
            or "none"
        )
        + f". Stock cells (reported, never fail the gate): {len(stock_flagged)} of {len(stock)} "
        "windows paging-flagged"
    )
    crit.append(
        {
            "id": "f",
            "text": f"at most {PAGING_LIMIT_PCT}% of the tuned and canary windows paging-flagged and "
            f"no flagged tuned or canary window above {SWAP_LIMIT_MIB:.0f} MiB of swap growth "
            "(stock windows excluded)",
            "applies": True,
            "pass": pct <= PAGING_LIMIT_PCT and not heavy,
            "detail": detail,
        }
    )
    ok = all(c["pass"] for c in crit)
    failed = [c["id"] for c in crit if not c["pass"]]
    if ok:
        nxt = (
            "PASS: run the one `--rerun-flagged` pass for this session (only if a unit is "
            "flagged), then the next session"
        )
    elif failed == ["f"]:
        nxt = (
            "STOP and report: the tuned or canary windows page more than the rule allows "
            "(40% of windows, or a flagged window above 1,024 MiB of swap growth)"
        )
    else:
        nxt = (
            f"STOP and report: criteria {failed} failed; the next session does not start until a "
            "human has looked"
        )
    return {
        "stage": "stage3",
        "session_id": sess.id,
        "pass": ok,
        "failed": failed,
        "criteria": crit,
        "paging_per_cell": dict(sorted(per_cell.items())),
        "stock_paging": {
            "windows": len(stock),
            "flagged": len(stock_flagged),
            "note": "reported only; stock windows never fail the gate",
        },
        "next": nxt,
        "stop_for_human": not ok,
    }


def format_gate(g: dict) -> str:
    lines = [f"gate for {g['stage']} session {g['session_id']}: {'PASS' if g['pass'] else 'FAIL'}"]
    for c in g["criteria"]:
        lines.append(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['id']}: {c['text']}: {c['detail']}")
    lines.append("  paging-flagged windows per cell (attempt 1; stock cells are reported only):")
    for cell, e in g["paging_per_cell"].items():
        reps = f" (repetitions {e['flagged_repetitions']})" if e["flagged"] else ""
        swap = "-" if e["max_swap_mib"] is None else f"{e['max_swap_mib']:.0f}"
        lines.append(
            f"    {cell} [{e['group']}]: {e['flagged']} of {e['windows']}{reps}; "
            f"largest swap growth {swap} MiB; most major faults {e['max_faults']}"
        )
    lines.append(f"  next: {g['next']}")
    return "\n".join(lines)
