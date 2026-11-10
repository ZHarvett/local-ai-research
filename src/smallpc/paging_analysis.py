"""Paging investigation of one sweep session (WP10, part A). Reads data, changes no rule.

    python -m smallpc.paging_analysis SESSION_DIR [--out-dir data/analysis] [--attribute CELL:REP]

For every repetition window (cells and canaries), the warm-up and the server start of every server
instance, this reports llama-server's ``VmSwap`` (start, end, maximum, change), the change in its
major faults, the system-wide ``pswpin`` (and ``pswpout`` when the CSV has it), the minimum
``MemAvailable``, whether swap was already there at the start of the window (a *state*) or grew
(*activity*), and the window's speed figures. Three candidate paging rules are then evaluated on
every window. They are historical: WP10 ran this before the plan changed. Plan v1.4 adopted a
fourth rule (faults only, swap growth recorded as ``swap_activity``) in ``flags.paging``:

* R0: the v1.3 rule as it is: more than 1,000 major faults, or ``VmSwap`` above zero at any sample.
* R1: more than 1,000 major faults, or ``VmSwap`` *growth* of more than 64 MiB during the window.
* R2: more than 1,000 major faults, or an *absolute* ``VmSwap`` change of more than 64 MiB during
  the window (swap-out or swap-in of the server's own pages).

Definitions, with ``v`` the ``VmSwap`` samples of the window (kiB) and ``v0`` its first sample:
growth = ``max(v) - v0`` (never negative); absolute change = ``max(|v_i - v0|)``; net change =
``v_last - v0``. The window's samples are the telemetry rows with ``t0 <= t <= t1``, as the runner
selects them. Telemetry is 2 Hz and starts at the first warm-up request, so the model load itself is
not sampled: the "server start" segment is the state at the first sample (right after load and
prefetch) plus the system-wide counters of the environment snapshot taken before the prefetch.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import flags, labels, telemetry
from .scrub import Identity, scrub_json

SWAP_LIMIT_KIB = 64 * 1024  # R1 and R2: 64 MiB
KIB_PER_MIB = 1024
SIXTEEN_K = 16384
RULES = ("R0", "R1", "R2")
RULE_TEXT = {
    "R0": "v1.3 as is: majflt > 1,000 or VmSwap > 0 at any sample",
    "R1": "majflt > 1,000 or VmSwap growth > 64 MiB in the window",
    "R2": "majflt > 1,000 or absolute VmSwap change > 64 MiB in the window",
}
CAVEATS = [
    "Ten windows from one session on one machine: no causal claim is possible, and every "
    "speed comparison below is anecdotal.",
    "This run has `VmSwap` and `VmRSS` but not `RssAnon`, `RssFile` or `RssShmem`, so it cannot "
    "show what sits in the swapped pages (anonymous heap, shared memory, or something else).",
    "Telemetry starts at the first warm-up request: the model load and the prefetch are not "
    "sampled. The 'server start' rows hold the first sample plus the snapshot's system counters.",
    "`pswpin` is system-wide (other processes swap too) and `pswpout` is not in this run's CSVs; "
    "the per-process view is `VmSwap` and the major faults of llama-server only.",
    "Sampling is 2 Hz: a swap burst shorter than half a second between two samples is seen only "
    "through the next sample's value.",
    "Windows of different server instances differ in everything the OS decided at that moment "
    "(page cache, what was swapped before), so a within-cell comparison also compares instances.",
]


# ------------------------------------------------------------------------------ pure functions


def default_label(session_id: str) -> str:
    """The data label of a session's output: ``screening`` for the Stage 1 and Stage 2 sessions
    (ids starting with "stage"), otherwise ``functional-test``."""
    return "screening" if session_id.startswith("stage") else "functional-test"


def _vals(rows: list[dict], key: str) -> list[float]:
    return [r[key] for r in rows if r.get(key) is not None]


def segment_stats(rows: list[dict]) -> dict:
    """Paging figures of the telemetry rows of one segment (a window, the warm-up, ...)."""
    out: dict = {"n_samples": len(rows)}
    if not rows:
        return out | {"vmswap_recorded": False}
    vms = _vals(rows, "server_vmswap_kib")
    maj = _vals(rows, "majflt")
    swin = _vals(rows, "pswpin")
    swout = _vals(rows, "pswpout")
    mem = _vals(rows, "memavailable_kib")
    rss = _vals(rows, "server_rss_kib")
    out["vmswap_recorded"] = bool(vms)
    if vms:
        v0 = vms[0]
        out["vmswap_start_kib"] = v0
        out["vmswap_end_kib"] = vms[-1]
        out["vmswap_max_kib"] = max(vms)
        out["vmswap_min_kib"] = min(vms)
        out["vmswap_net_change_kib"] = vms[-1] - v0
        out["vmswap_growth_kib"] = max(0.0, max(vms) - v0)
        out["vmswap_abs_change_kib"] = max(abs(v - v0) for v in vms)
        out["vmswap_nonzero_samples"] = sum(1 for v in vms if v > 0)
        grew = out["vmswap_growth_kib"] > 0
        out["nature"] = (
            "none"
            if max(vms) == 0
            else ("state+activity" if v0 > 0 and grew else "state" if v0 > 0 else "activity")
        )
    else:
        out["nature"] = "not recorded"
    out["majflt_change"] = int(maj[-1] - maj[0]) if len(maj) >= 2 else None
    out["pswpin_change"] = int(swin[-1] - swin[0]) if len(swin) >= 2 else None
    out["pswpout_change"] = int(swout[-1] - swout[0]) if len(swout) >= 2 else None
    out["memavailable_min_kib"] = min(mem) if mem else None
    out["rss_start_kib"], out["rss_end_kib"] = (rss[0], rss[-1]) if rss else (None, None)
    for col, name in (
        ("server_rss_anon_kib", "rss_anon"),
        ("server_rss_file_kib", "rss_file"),
        ("server_rss_shmem_kib", "rss_shmem"),
    ):
        v = _vals(rows, col)
        out[f"{name}_start_kib"], out[f"{name}_end_kib"] = (v[0], v[-1]) if v else (None, None)
    return out


def evaluate_rules(stats: dict) -> dict[str, bool]:
    """R0, R1 and R2 on one segment. A segment without ``VmSwap`` is judged on faults only."""
    maj = (stats.get("majflt_change") or 0) > flags.MAJFLT_LIMIT
    if not stats.get("vmswap_recorded"):
        return {r: maj for r in RULES}
    return {
        "R0": maj or stats["vmswap_max_kib"] > 0,
        "R1": maj or stats["vmswap_growth_kib"] > SWAP_LIMIT_KIB,
        "R2": maj or stats["vmswap_abs_change_kib"] > SWAP_LIMIT_KIB,
    }


def attribute_requests(rows: list[dict], requests: list[dict]) -> list[dict]:
    """Share the window's counter increments out to the requests, by time.

    Each interval between two consecutive samples belongs to the request whose
    ``client.t_start_epoch..t_end_epoch`` contains the interval's midpoint, otherwise to the gap
    after the request that ended last before it (``gap_*``). The increments therefore add up to the
    window's totals. ``vmswap_*`` are the signed changes of ``VmSwap`` in kiB.
    """
    reqs = sorted(requests, key=lambda r: r["client"]["t_start_epoch"])
    out = [
        {
            "position": r["position"],
            "kind": r["kind"],
            "depth": r["depth"],
            "t_start_s": None,
            "duration_s": round(r["client"]["t_end_epoch"] - r["client"]["t_start_epoch"], 2),
            "during_majflt": 0,
            "during_pswpin": 0,
            "during_vmswap_kib": 0.0,
            "gap_majflt": 0,
            "gap_pswpin": 0,
            "gap_vmswap_kib": 0.0,
            "vmswap_at_end_kib": None,
            "speed": (r["prompt_per_second"] if r["kind"] in ("A", "short") else None)
            if r["kind"] != "B"
            else r["predicted_per_second"],
            "speed_metric": "PP tokens/s" if r["kind"] in ("A", "short") else "TG tokens/s",
        }
        for r in reqs
    ]
    if not rows or not reqs:
        return out
    t0 = rows[0]["t_epoch"]
    for o, r in zip(out, reqs, strict=True):
        o["t_start_s"] = round(r["client"]["t_start_epoch"] - t0, 2)

    def inc(a: dict, b: dict, key: str) -> float:
        return (b[key] - a[key]) if a.get(key) is not None and b.get(key) is not None else 0.0

    for a, b in zip(rows, rows[1:], strict=False):
        mid = (a["t_epoch"] + b["t_epoch"]) / 2
        idx, in_req = None, False
        for i, r in enumerate(reqs):
            if r["client"]["t_start_epoch"] <= mid <= r["client"]["t_end_epoch"]:
                idx, in_req = i, True
                break
            if r["client"]["t_end_epoch"] < mid:
                idx = i
        if idx is None:  # before the first request
            idx, in_req = 0, False
        pre = "during" if in_req else "gap"
        out[idx][f"{pre}_majflt"] += int(inc(a, b, "majflt"))
        out[idx][f"{pre}_pswpin"] += int(inc(a, b, "pswpin"))
        out[idx][f"{pre}_vmswap_kib"] += inc(a, b, "server_vmswap_kib")
    for o, r in zip(out, reqs, strict=True):
        after = [x for x in rows if x["t_epoch"] >= r["client"]["t_end_epoch"]]
        o["vmswap_at_end_kib"] = after[0].get("server_vmswap_kib") if after else None
    return out


def speed_figures(requests: list[dict]) -> dict:
    """PP_fresh at 16K (Request A), TG of the 16K Request B, mean TG of all B requests, short TG."""

    def first(kind: str, key: str, depth: int | None = None) -> float | None:
        vals = [
            r[key]
            for r in requests
            if r["kind"] == kind and (depth is None or r["depth"] == depth) and r.get(key)
        ]
        return sum(vals) / len(vals) if vals else None

    return {
        "pp_fresh_16k": first("A", "prompt_per_second", SIXTEEN_K),
        "tg_16k": first("B", "predicted_per_second", SIXTEEN_K),
        "tg_b_mean": first("B", "predicted_per_second"),
        "tg_short": first("short", "predicted_per_second"),
        "n_requests": len(requests),
    }


# ----------------------------------------------------------------------------- session reading


def _load_records(session: Path) -> list[dict]:
    from .sweep.records import Store

    return Store(session / "records.jsonl").load().requests


def _segments_of_instance(session: Path, cell: dict, ins: dict, reqs: list[dict]) -> list[dict]:
    tfile = (ins.get("telemetry") or {}).get("file")
    if not tfile or not (session / tfile).exists():
        return []
    rows = telemetry.read_csv(session / tfile)
    mine = [r for r in reqs if r["server_run_id"] == ins["run_id"]]
    warm = sorted(
        (r for r in mine if r["role"] == "warmup"), key=lambda r: r["client"]["t_start_epoch"]
    )
    base = {"cell": cell["cell"], "role": cell["role"], "config_hash": cell["config_hash"]}
    base |= {"instance": ins["instance"], "telemetry_file": tfile}
    segs: list[dict] = []

    snap_vm = (ins.get("snapshot_state") or {}).get("memory", {}).get("vmstat", {}) or {}
    snap_swap = (ins.get("snapshot_state") or {}).get("memory", {}).get("swap_used_kib")
    first = rows[0] if rows else None
    st = segment_stats(rows[:1])
    st["system_swap_used_kib_at_snapshot"] = snap_swap
    st["pswpin_since_snapshot"] = (
        int(first["pswpin"] - snap_vm["pswpin"])
        if first and first.get("pswpin") is not None and snap_vm.get("pswpin") is not None
        else None
    )
    st["pswpout_at_snapshot"] = snap_vm.get("pswpout")
    segs.append(base | {"segment": "server_start", "label": "server start (first sample)", **st})
    if warm:
        t0, t1 = warm[0]["client"]["t_start_epoch"], warm[-1]["client"]["t_end_epoch"]
        w = telemetry.window(rows, t0, t1)
        segs.append(
            base
            | {
                "segment": "warmup",
                "label": "warm-up",
                "t0_epoch": t0,
                "t1_epoch": t1,
                "speed": {
                    "pp_warmup": sum(r["prompt_per_second"] for r in warm) / len(warm),
                    "tg_warmup": sum(r["predicted_per_second"] for r in warm) / len(warm),
                    "n_requests": len(warm),
                },
                **segment_stats(w),
            }
        )
    for win in ins.get("windows", []):
        w = telemetry.window(rows, win["t0_epoch"], win["t1_epoch"])
        wreqs = [r for r in mine if r.get("window_id") == win["window_id"]]
        st = segment_stats(w)
        segs.append(
            base
            | {
                "segment": "window",
                "label": f"repetition {win['repetition']}",
                "window_id": win["window_id"],
                "repetition": win["repetition"],
                "attempt": win["attempt"],
                "t0_epoch": win["t0_epoch"],
                "t1_epoch": win["t1_epoch"],
                "recorded_flags": win.get("flags", []),
                "speed": speed_figures(wreqs),
                "_rows": w,
                "_requests": wreqs,
                **st,
            }
        )
    return segs


def analyse_session(
    session: Path, attribute: list[str] | None = None, label: str | None = None
) -> dict:
    session = Path(session)
    reqs = _load_records(session)
    sj = json.loads((session / "session.json").read_text())
    segs: list[dict] = []
    for f in sorted((session / "cells").glob("*.json")):
        cell = json.loads(f.read_text())
        for ins in cell["instances"]:
            segs += _segments_of_instance(session, cell, ins, reqs)
    attribute = attribute if attribute is not None else ["stock-32K:1"]
    attributions = []
    for s in segs:
        if s["segment"] != "window":
            continue
        s["rules"] = evaluate_rules(s)
        key = f"{s['cell']}:{s['repetition']}"
        if key in attribute or (s.get("majflt_change") or 0) > flags.MAJFLT_LIMIT:
            attributions.append(
                {
                    "window_id": s["window_id"],
                    "cell": s["cell"],
                    "repetition": s["repetition"],
                    "requests": attribute_requests(s["_rows"], s["_requests"]),
                }
            )
    for s in segs:
        if s["segment"] != "window":
            s["rules"] = evaluate_rules(s)
    for att in attributions:  # the same request in the cell's windows without an R0 flag
        sibs = [
            w
            for w in segs
            if w["segment"] == "window"
            and w["cell"] == att["cell"]
            and w["window_id"] != att["window_id"]
            and not w["rules"]["R0"]
        ]
        for q in att["requests"]:
            same = [
                (r["prompt_per_second"] if r["kind"] != "B" else r["predicted_per_second"])
                for w in sibs
                for r in w["_requests"]
                if r["kind"] == q["kind"] and r["depth"] == q["depth"]
            ]
            q["speed_unflagged_windows"] = sum(same) / len(same) if same else None
    windows = [s for s in segs if s["segment"] == "window"]
    agree = sum(1 for w in windows if (("paging" in w["recorded_flags"]) == w["rules"]["R0"]))
    label = label or default_label(sj["session_id"])
    result = {
        "session_id": sj["session_id"],
        "label": label,
        "note": labels.banner(label),
        "rules": RULE_TEXT,
        "definitions": {
            "growth": "max(VmSwap) - first VmSwap sample of the window, never negative",
            "absolute_change": "max |VmSwap_i - first VmSwap sample| over the window",
            "net_change": "last VmSwap - first VmSwap",
            "nature": "state = VmSwap > 0 at the first sample; activity = VmSwap grew; "
            "none = 0 throughout",
        },
        "segments": segs,
        "attribution": attributions,
        "rule_flags_by_window": {
            w["window_id"]: {r: w["rules"][r] for r in RULES} for w in windows
        },
        "r0_matches_recorded_flag": {"agree": agree, "windows": len(windows)},
        "within_config": within_config(windows),
        "caveats": CAVEATS,
    }
    return _clean(result)


def _clean(obj):
    """Drop the private row lists, then scrub names and paths."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def within_config(windows: list[dict]) -> list[dict]:
    """For every configuration that has windows both with and without an R0 flag, the mean speed
    of each group. Anecdotal: the groups also differ in server instance and in time."""
    out = []
    by_cfg: dict[str, list[dict]] = {}
    for w in windows:
        by_cfg.setdefault(w["config_hash"], []).append(w)
    for cfg, ws in sorted(by_cfg.items()):
        flagged = [w for w in ws if w["rules"]["R0"]]
        clean = [w for w in ws if not w["rules"]["R0"]]
        if not flagged or not clean:
            continue

        def mean(group: list[dict], key: str) -> float | None:
            vals = [w["speed"][key] for w in group if w["speed"].get(key) is not None]
            return sum(vals) / len(vals) if vals else None

        row: dict = {
            "config_hash": cfg,
            "cells": sorted({w["cell"] for w in ws}),
            "n_flagged": len(flagged),
            "n_not_flagged": len(clean),
        }
        for key in ("pp_fresh_16k", "tg_16k"):
            a, b = mean(flagged, key), mean(clean, key)
            row[key] = {
                "flagged_mean": a,
                "not_flagged_mean": b,
                "relative_difference": (a - b) / b if a is not None and b else None,
            }
        out.append(row)
    return out


# -------------------------------------------------------------------------------- Markdown


def _mib(kib: float | None) -> str:
    if kib is None:
        return "-"
    mib = round(kib / KIB_PER_MIB)
    return f"{mib:,}" if mib else "0"  # never "-0"


def _num(v, fmt: str = "{:,.0f}") -> str:
    return "-" if v is None else fmt.format(v)


def render_markdown(res: dict) -> str:
    L: list[str] = []
    L.append(f"# Paging analysis of `{res['session_id']}`")
    L.append("")
    L.append(
        f"**{res.get('note') or labels.banner(res.get('label'))}** This is an investigation; "
        "`flags.paging` is unchanged."
    )
    L.append("")
    L.append("## Per-window table")
    L.append("")
    L.append(
        "VmSwap and RSS in MiB. `nature`: state = swap already there at the window's first sample, "
        "activity = it grew. Speeds are tokens/s: PP_fresh at the 16K pair (Request A) and TG of "
        "the 16K Request B (and the mean TG of all B requests)."
    )
    L.append("")
    L.append(
        "| cell | segment | inst | VmSwap start | end | max | change | nature | major faults "
        "| pswpin | MemAvail min | RSS start→end | PP_fresh 16K | TG 16K | TG B mean |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in res["segments"]:
        sp = s.get("speed", {})
        label = (
            f"window r{s['repetition']}"
            if s["segment"] == "window"
            else "warm-up"
            if s["segment"] == "warmup"
            else "server start"
        )
        pp = sp.get("pp_fresh_16k") if s["segment"] == "window" else sp.get("pp_warmup")
        tg = sp.get("tg_16k") if s["segment"] == "window" else sp.get("tg_warmup")
        if s["segment"] == "server_start":
            maj, swin = "-", _num(s.get("pswpin_since_snapshot"))
        else:
            maj, swin = _num(s.get("majflt_change")), _num(s.get("pswpin_change"))
        L.append(
            f"| {s['cell']} | {label} | {s['instance']} | {_mib(s.get('vmswap_start_kib'))} "
            f"| {_mib(s.get('vmswap_end_kib'))} | {_mib(s.get('vmswap_max_kib'))} "
            f"| {_mib(s.get('vmswap_net_change_kib'))} | {s['nature']} | {maj} | {swin} "
            f"| {_mib(s.get('memavailable_min_kib'))} "
            f"| {_mib(s.get('rss_start_kib'))}→{_mib(s.get('rss_end_kib'))} "
            f"| {_num(pp, '{:,.1f}')} | {_num(tg, '{:,.1f}')} "
            f"| {_num(sp.get('tg_b_mean'), '{:,.1f}')} |"
        )
    L.append("")
    L.append(
        "Rows named *warm-up* show the warm-up requests' speeds (8K prompts, 128 tokens) instead. "
        "On *server start* rows the swap columns are the first telemetry sample, and `pswpin` is "
        "the system-wide change from the environment snapshot to that sample."
    )
    L.append("")
    L.append("## Three candidate rules")
    L.append("")
    for r in RULES:
        L.append(f"- **{r}**: {res['rules'][r]}.")
    L.append("")
    L.append("| window | growth | abs. change | faults | R0 | R1 | R2 | recorded flag |")
    L.append("|---|---|---|---|---|---|---|---|")
    totals = dict.fromkeys(RULES, 0)
    wins = [s for s in res["segments"] if s["segment"] == "window"]
    for s in wins:
        for r in RULES:
            totals[r] += bool(s["rules"][r])
        mark = [("**FLAG**" if s["rules"][r] else "-") for r in RULES]
        L.append(
            f"| {s['window_id']} | {_mib(s.get('vmswap_growth_kib'))} "
            f"| {_mib(s.get('vmswap_abs_change_kib'))} | {_num(s.get('majflt_change'))} "
            f"| {' | '.join(mark)} | {', '.join(s['recorded_flags']) or '-'} |"
        )
    L.append(
        f"| **windows flagged (of {len(wins)})** | | | | "
        + " | ".join(f"**{totals[r]}**" for r in RULES)
        + " | |"
    )
    L.append("")
    a = res["r0_matches_recorded_flag"]
    L.append(
        f"R0 reproduces the paging flag the runner recorded on {a['agree']} of {a['windows']} "
        "windows (check of this script against the recorded data)."
    )
    L.append("")
    for att in res["attribution"]:
        L.append(f"## Which requests the activity belongs to: `{att['window_id']}`")
        L.append("")
        L.append(
            "Each interval between two samples is given to the request that was running at its "
            "midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap "
            "in MiB (signed)."
        )
        L.append("")
        L.append(
            "| pos | request | start (s) | duration (s) | faults during | pswpin during "
            "| VmSwap change during | faults in gap after | VmSwap change in gap "
            "| VmSwap at end | speed (PP for A and short, TG for B) "
            "| same request, window without R0 |"
        )
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for q in att["requests"]:
            name = q["kind"] + (f" {q['depth'] // 1024}K" if q["depth"] else "")
            L.append(
                f"| {q['position']} | {name} | {_num(q['t_start_s'], '{:.1f}')} "
                f"| {q['duration_s']:.1f} | {q['during_majflt']:,} | {q['during_pswpin']:,} "
                f"| {_mib(q['during_vmswap_kib'])} | {q['gap_majflt']:,} "
                f"| {_mib(q['gap_vmswap_kib'])} | {_mib(q['vmswap_at_end_kib'])} "
                f"| {_num(q['speed'], '{:,.1f}')} "
                f"| {_num(q['speed_unflagged_windows'], '{:,.1f}')} |"
            )
        L.append("")
    L.append("## Speed next to paging (anecdotal)")
    L.append("")
    if res["within_config"]:
        L.append(
            "Windows of one configuration, split by the R0 flag. Different server instances and "
            "times; 10 windows in all."
        )
        L.append("")
        L.append(
            "| config | cells | flagged / not | PP_fresh 16K flagged vs not "
            "| TG 16K flagged vs not |"
        )
        L.append("|---|---|---|---|---|")
        for w in res["within_config"]:
            pp, tg = w["pp_fresh_16k"], w["tg_16k"]

            def cmp(x: dict) -> str:
                if x["flagged_mean"] is None or x["not_flagged_mean"] is None:
                    return "-"
                return (
                    f"{x['flagged_mean']:.1f} vs {x['not_flagged_mean']:.1f} "
                    f"({x['relative_difference'] * 100:+.1f}%)"
                )

            L.append(
                f"| `{w['config_hash'][:8]}` | {', '.join(w['cells'])} "
                f"| {w['n_flagged']} / {w['n_not_flagged']} | {cmp(pp)} | {cmp(tg)} |"
            )
        L.append("")
    L.append("## What the data cannot show")
    L.append("")
    for c in res["caveats"]:
        L.append(f"- {c}")
    L.append("")
    return "\n".join(L)


# ----------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.paging_analysis")
    ap.add_argument("session", type=Path, help="a session directory under data/raw/")
    ap.add_argument("--out-dir", type=Path, default=Path("data/analysis"))
    ap.add_argument(
        "--label",
        choices=labels.LABELS,
        help="data label of the output (default: screening for sessions whose id starts with "
        "'stage', otherwise functional-test)",
    )
    ap.add_argument(
        "--attribute",
        action="append",
        help="CELL:REPETITION windows to attribute to requests (default stock-32K:1; windows "
        "with more than 1,000 major faults are always attributed)",
    )
    a = ap.parse_args(argv)
    res = analyse_session(a.session, a.attribute, a.label)
    sid = re.sub(r"[^A-Za-z0-9._-]", "_", res["session_id"])
    a.out_dir.mkdir(parents=True, exist_ok=True)
    res = scrub_json(res, Identity.current())
    (a.out_dir / f"paging-{sid}.json").write_text(json.dumps(res, indent=1) + "\n")
    md = render_markdown(res)
    (a.out_dir / f"paging-{sid}.md").write_text(md + "\n")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
