"""Read-only diagnostics of the Stage 1 sessions (WP11 part 2): memory behaviour of the windows that
paged, and the speed difference between repetition 1 and repetition 0.

    uv run python tools/stage1_diagnostics.py > reports/stage1/diagnostics.md

Reads data/raw/stage1-*/ (records, cell summaries, telemetry CSVs) and data/logs/<run id>/server.log;
writes nothing but its Markdown to stdout. Nothing here changes a flag, an eligibility rule or a
statistic; the numbers are descriptive and the report labels them as such.

Host prompt cache size: the line ``srv update: - cache state: N prompts, X MiB (limits: ...)`` that
llama-server logs when a new task makes it save the idle slot's prompt (-lv 4). Log times are
"minutes.seconds.ms.us" since process start; they are aligned to the wall clock by matching the
k-th ``slot print_timing ... total time`` line to the end time of the k-th request of the instance.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import statistics as st
import sys
from pathlib import Path

# ruff: noqa: E501
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
LOGS = ROOT / "data/logs"
SWAP_HEAVY_MIB = 64.0
MIB = 1024.0

TS = r"(\d+)\.(\d\d)\.(\d{3})\.(\d{3})"
RE_STATE = re.compile(TS + r" .*cache state: (\d+) prompts?, ([\d.]+) MiB")
RE_TIMING = re.compile(TS + r" I slot print_timing: id\s+\d+ \| task \d+ \|\s+total time")


def rel_s(m: tuple[str, ...]) -> float:
    return int(m[0]) * 60 + int(m[1]) + int(m[2]) / 1e3 + int(m[3]) / 1e6


def load_session(sid: str) -> dict:
    d = RAW / sid
    reqs = []
    for line in (d / "records.jsonl").read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("record_type") == "request":
            reqs.append(r)
    cells = {}
    for f in sorted((d / "cells").glob("*.json")):
        s = json.loads(f.read_text())
        cells[s["cell"]] = s
    return {"sid": sid, "dir": d, "reqs": reqs, "cells": cells}


def telemetry_rows(sess: dict, tfile: str) -> list[dict]:
    path = sess["dir"] / tfile
    out = []
    with gzip.open(path, "rt") as fh:
        for r in csv.DictReader(fh):
            row = {}
            for k in (
                "t_epoch",
                "majflt",
                "memavailable_kib",
                "server_vmswap_kib",
                "server_rss_anon_kib",
                "server_rss_file_kib",
                "server_rss_shmem_kib",
            ):
                try:
                    row[k] = float(r[k])
                except (KeyError, ValueError):
                    row[k] = None
            out.append(row)
    return out


def cache_series(sess: dict, run_id: str) -> list[tuple[float, int, float]]:
    """[(epoch, n_prompts, MiB)] of the host prompt cache, from the server log of one instance."""
    log = LOGS / run_id / "server.log"
    if not log.exists():
        return []
    ends = sorted(
        r["client"]["t_end_epoch"]
        for r in sess["reqs"]
        if r["server_run_id"] == run_id and r["client"].get("t_end_epoch")
    )
    timings, states = [], []
    for line in log.read_text(errors="replace").splitlines():
        m = RE_TIMING.match(line)
        if m:
            timings.append(rel_s(m.groups()))
            continue
        m = RE_STATE.match(line)
        if m:
            g = m.groups()
            states.append((rel_s(g[:4]), int(g[4]), float(g[5])))
    if not timings or len(timings) != len(ends):
        return []
    offs = [e - t for e, t in zip(ends, timings, strict=True)]
    off = st.median(offs)
    return [(off + t, n, mib) for t, n, mib in states]


def window_diag(sess: dict, cell: str, w: dict, run_id: str, tfile: str, cache) -> dict:
    t0, t1 = w["t0_epoch"], w["t1_epoch"]
    rows = [r for r in telemetry_rows(sess, tfile) if t0 <= (r["t_epoch"] or 0) <= t1]
    first, last = rows[0], rows[-1]

    def mib(row, k):
        return None if row[k] is None else row[k] / MIB

    vm = [r["server_vmswap_kib"] for r in rows if r["server_vmswap_kib"] is not None]
    mem = [r["memavailable_kib"] for r in rows if r["memavailable_kib"] is not None]
    fl = [r["majflt"] for r in rows if r["majflt"] is not None]
    c_in = [(n, m) for (t, n, m) in cache if t0 - 1 <= t <= t1 + 1]
    return {
        "cell": cell,
        "rep": w["repetition"],
        "attempt": w["attempt"],
        "anon": (mib(first, "server_rss_anon_kib"), mib(last, "server_rss_anon_kib")),
        "file": (mib(first, "server_rss_file_kib"), mib(last, "server_rss_file_kib")),
        "shmem": (mib(first, "server_rss_shmem_kib"), mib(last, "server_rss_shmem_kib")),
        "vmswap": (vm[0] / MIB, vm[-1] / MIB, max(vm) / MIB) if vm else (None, None, None),
        "faults": (fl[-1] - fl[0]) if fl else None,
        "memavail_min_gib": min(mem) / MIB / MIB if mem else None,
        "cache_first": c_in[0] if c_in else None,  # (prompts, MiB) at the window's first save
        "cache_last": c_in[-1]
        if c_in
        else None,  # ... and at its last save (the last slot is not in it)
        "swap_activity": w.get("swap_activity_mib"),
        "flags": w.get("flags", []),
    }


def all_windows(sess: dict) -> list[dict]:
    out = []
    for cell, s in sess["cells"].items():
        if s["role"] in ("canary_start", "canary_end"):
            continue
        for inst in s["instances"]:
            run_id = inst["run_id"]
            tf = next(
                (
                    r["telemetry"]["file"]
                    for r in sess["reqs"]
                    if r["server_run_id"] == run_id and r.get("telemetry")
                ),
                None,
            )
            if not tf:
                continue
            cache = cache_series(sess, run_id)
            for w in inst.get("windows", []):
                d = window_diag(sess, cell, w, run_id, tf, cache)
                d["session"] = sess["sid"]
                d["cache_available"] = bool(cache)
                out.append(d)
    return out


def rep_metrics(sess: dict, cell: str, rep: int, attempt: int) -> dict | None:
    rr = [
        r
        for r in sess["reqs"]
        if r["cell"] == cell
        and r["role"] == "measured"
        and r["repetition"] == rep
        and r["attempt"] == attempt
    ]
    if not rr:
        return None
    pp, tg, tt = {}, {}, {}
    for r in rr:
        d = r["depth"]
        if r["kind"] == "A":
            pp[d] = r["prompt_per_second"]
        if r["kind"] == "B":
            tg[d] = r["predicted_per_second"]
            tt[d] = r["prompt_ms"] / 1e3 + 400 * r["timings"]["predicted_per_token_ms"] / 1e3
    depths = sorted(pp)
    return {
        "depths": depths,
        "pp": [pp[d] for d in depths],
        "tg": [tg[d] for d in depths],
        "tt": st.mean(tt[d] for d in depths),
    }


def pct(a: float, b: float) -> float:
    return 100.0 * (b - a) / a


def speed_row(m0: dict, m1: dict) -> dict:
    return {
        "pp": [pct(a, b) for a, b in zip(m0["pp"], m1["pp"], strict=True)],
        "tg": [pct(a, b) for a, b in zip(m0["tg"], m1["tg"], strict=True)],
        "tt": pct(m0["tt"], m1["tt"]),
    }


def f1(x, d=1):
    return "-" if x is None else f"{x:,.{d}f}"


def arrow(p, d=0):
    return f"{f1(p[0], d)}→{f1(p[1], d)}"


def mem_table(ws: list[dict]) -> list[str]:
    out = [
        "| cell | window | RssAnon s→e | RssFile s→e | RssShmem s→e | VmSwap s / e / max | major faults "
        "| MemAvail min (GiB) | host cache at first→last save (prompts, MiB) | ΔRssAnon | Δ(RssAnon+VmSwap) | Δ host cache |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for w in ws:
        a0, a1 = w["anon"]
        v0, v1, vm = w["vmswap"]
        foot = None if None in (a0, a1, v0, v1) else (a1 + v1) - (a0 + v0)
        cf, cl = w["cache_first"], w["cache_last"]
        dc = None if not (cf and cl) else cl[1] - cf[1]
        cache = "n/a" if not (cf and cl) else f"{cf[0]}, {cf[1]:,.0f} → {cl[0]}, {cl[1]:,.0f}"
        out.append(
            f"| {w['cell']} | r{w['rep']} a{w['attempt']}{' ⚑' if w['flags'] else ''} | {arrow(w['anon'])} | "
            f"{arrow(w['file'])} | {arrow(w['shmem'])} | {f1(v0, 0)} / {f1(v1, 0)} / {f1(vm, 0)} | "
            f"{f1(w['faults'], 0)} | {f1(w['memavail_min_gib'])} | {cache} | "
            f"{f1(None if a0 is None else a1 - a0, 0)} | {f1(foot, 0)} | {f1(dc, 0)} |"
        )
    return out


def pearson(xs, ys):
    if len(xs) < 3:
        return None
    mx, my = st.mean(xs), st.mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return (
        None
        if sx == 0 or sy == 0
        else sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)
    )


def hypothesis(ws: list[dict]) -> list[str]:
    pts = []
    for w in ws:
        a0, a1 = w["anon"]
        v0, v1, _ = w["vmswap"]
        cf, cl = w["cache_first"], w["cache_last"]
        if None in (a0, a1, v0, v1) or not (cf and cl):
            continue
        pts.append(((a1 + v1) - (a0 + v0), cl[1] - cf[1], w))
    if not pts:
        return ["No window had both telemetry and a cache series."]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    r = pearson(xs, ys)
    sl = (
        sum(x * y for x, y in zip(xs, ys, strict=True)) / sum(y * y for y in ys)
        if sum(y * y for y in ys)
        else None
    )
    lines = [
        f"- {len(pts)} windows with both series. Growth of the anonymous footprint (RssAnon + VmSwap, MiB) against growth of the host prompt cache between "
        f"its first and last save in the window (MiB): Pearson r = {f1(r, 3)}; least-squares slope through the origin {f1(sl, 2)} MiB of footprint per MiB of cache."
    ]
    for label, sel in (
        ("repetition 0, attempt 1", lambda w: w["rep"] == 0 and w["attempt"] == 1),
        ("repetition 1, attempt 1", lambda w: w["rep"] == 1 and w["attempt"] == 1),
        ("repetition 1, attempt 2", lambda w: w["rep"] == 1 and w["attempt"] == 2),
    ):
        sub = [p for p in pts if sel(p[2])]
        if sub:
            lines.append(
                f"  - {label}: n = {len(sub)}, median Δfootprint {f1(st.median(p[0] for p in sub), 0)} MiB, median Δcache {f1(st.median(p[1] for p in sub), 0)} MiB, "
                f"median host cache at the last save {f1(st.median(p[2]['cache_last'][1] for p in sub), 0)} MiB."
            )
    return lines


def speed_tables(sessions: dict[str, dict], flagged: set[tuple[str, str]], ctx_filter=None):
    rows = []
    for sid, sess in sessions.items():
        for cell in sess["cells"]:
            if sess["cells"][cell]["role"] in ("canary_start", "canary_end"):
                continue
            m0, m1 = rep_metrics(sess, cell, 0, 1), rep_metrics(sess, cell, 1, 1)
            if not (m0 and m1):
                continue
            rows.append((sid, cell, (sid, cell) in flagged, speed_row(m0, m1)))
    return rows


def group_stats(rows) -> str:
    if not rows:
        return "-"
    pp = [st.mean(r[3]["pp"]) for r in rows]
    tg = [st.mean(r[3]["tg"]) for r in rows]
    tt = [r[3]["tt"] for r in rows]

    def s(x):
        return f"{st.mean(x):+.1f} (min {min(x):+.1f}, max {max(x):+.1f})"

    return f"n = {len(rows)} cells; PP_fresh {s(pp)}; TG {s(tg)}; T_turn_400 {s(tt)}"


def is_cache_cell(cell: str) -> bool:
    return cell.split("-")[0] in ("P3", "P4", "P5", "P6", "P7")


def main() -> None:
    sessions = {sid: load_session(sid) for sid in ("stage1-32K", "stage1-64K", "stage1-128K")}
    print("# Stage 1 diagnostics (read-only, descriptive)\n")
    print(
        "> SCREENING DATA (2 repetitions). Anecdotal: single runs, one machine state, no claim beyond the numbers shown.\n"
    )
    wins = {sid: all_windows(s) for sid, s in sessions.items()}

    # ---------------------------------------------------------------- flagged sets
    flagged: set[tuple[str, str]] = set()
    for sid, ws in wins.items():
        for w in ws:
            if w["attempt"] == 1 and w["flags"]:
                flagged.add((sid, w["cell"]))
    f128 = sorted(c for s, c in flagged if s == "stage1-128K")

    # ---------------------------------------------------------------- (b) 128K memory
    print("## B. Memory diagnostic, 128K\n")
    print(
        "Windows: flagged cells (`paging`, ⚑) and the controls P8-128K-b2048 and P9-128K-b2048, repetition 0 and 1 of attempt 1, "
        "and the attempt-2 window of every re-run unit. Sizes in MiB. Cache = host prompt cache reported by the server log "
        "(`cache state: N prompts, X MiB`); the first and last value inside the window (the last slot is saved only when the next fresh request arrives, so the value at the end of a window omits it).\n"
    )
    sel = f128 + ["P8-128K-b2048", "P9-128K-b2048"]
    ws = [w for w in wins["stage1-128K"] if w["cell"] in sel]
    ws.sort(key=lambda w: (sel.index(w["cell"]), w["attempt"], w["rep"]))
    for line in mem_table(ws):
        print(line)
    print()
    print(
        "Hypothesis test (descriptive): does the growth of RssAnon track the growth of the host prompt cache?\n"
    )
    for line in hypothesis(ws):
        print(line)
    print()
    no_cache = [w for w in ws if not w["cache_available"]]
    if no_cache:
        print(
            "Windows without a usable cache series (log missing or request count mismatch): "
            + ", ".join(sorted({f"{w['cell']} r{w['rep']} a{w['attempt']}" for w in no_cache}))
            + ".\n"
        )

    # ---------------------------------------------------------------- (c) 128K speed
    print("## C. Speed effect, repetition 1 against repetition 0 (attempt 1), 128K\n")
    print(
        "% difference = (rep 1 − rep 0) / rep 0. PP_fresh and TG at the three depths (32K / 64K / 96K), T_turn_400 = mean over depths. "
        "Negative T_turn_400 or positive PP/TG = faster in repetition 1.\n"
    )
    rows = speed_tables({"stage1-128K": sessions["stage1-128K"]}, flagged)
    print("| cell | flagged | PP_fresh %diff by depth | TG %diff by depth | T_turn_400 %diff |")
    print("|---|---|---|---|---|")
    for _sid, cell, fl, sp in sorted(rows, key=lambda r: (not r[2], r[1])):
        print(
            f"| {cell} | {'yes' if fl else 'no'} | "
            + " / ".join(f"{x:+.1f}" for x in sp["pp"])
            + " | "
            + " / ".join(f"{x:+.1f}" for x in sp["tg"])
            + f" | {sp['tt']:+.1f} |"
        )
    print()
    fl_rows = [r for r in rows if r[2]]
    un_rows = [r for r in rows if not r[2]]
    print(f"- Flagged cells (128K): {group_stats(fl_rows)}.")
    print(f"- Unflagged cells (128K, P1-b4096, P8, P9): {group_stats(un_rows)}.")
    base_rows = [
        r
        for r in speed_tables({k: v for k, v in sessions.items() if k != "stage1-128K"}, flagged)
        if not r[2]
    ]
    print(f"- Baseline, all unflagged cells of 32K and 64K: {group_stats(base_rows)}.")
    for label, grp in (
        ("no expert cache (P1, P2, P8, P9, stock)", lambda c: not is_cache_cell(c)),
        ("expert cache or CPU experts with a cache (P3 to P7)", is_cache_cell),
    ):
        print(
            f"- {label}: flagged 128K: {group_stats([r for r in fl_rows if grp(r[1])])}; baseline 32K/64K unflagged: {group_stats([r for r in base_rows if grp(r[1])])}."
        )
    print()

    # ---------------------------------------------------------------- (d) 64K
    print("## D. 64K windows with swap growth above 64 MiB (short form)\n")
    w64 = [
        w
        for w in wins["stage1-64K"]
        if w["attempt"] == 1 and (w["swap_activity"] or 0) > SWAP_HEAVY_MIB
    ]
    cells64 = sorted({w["cell"] for w in w64})
    ws64 = [w for w in wins["stage1-64K"] if w["cell"] in cells64]
    ws64.sort(key=lambda w: (w["cell"], w["attempt"], w["rep"]))
    for line in mem_table(ws64):
        print(line)
    print()
    for line in hypothesis(ws64):
        print(line)
    print()
    print(
        "| cell | flagged | PP_fresh %diff by depth (16K/32K/48K) | TG %diff by depth | T_turn_400 %diff |"
    )
    print("|---|---|---|---|---|")
    for _sid, cell, fl, sp in speed_tables({"stage1-64K": sessions["stage1-64K"]}, flagged):
        if cell in cells64:
            print(
                f"| {cell} | {'yes' if fl else 'no'} | "
                + " / ".join(f"{x:+.1f}" for x in sp["pp"])
                + " | "
                + " / ".join(f"{x:+.1f}" for x in sp["tg"])
                + f" | {sp['tt']:+.1f} |"
            )
    print()

    # ---------------------------------------------------------------- re-run units
    print("## E. Re-run units: attempt 2 against attempt 1 (same repetition)\n")
    print(
        "Attempt 1 was repetition 1 on a long-running server (the second repetition after the warm-up); attempt 2 ran as the first measured repetition on a fresh server.\n"
    )
    print(
        "| session | cell | rep | faults a1 → a2 | swap growth MiB a1 → a2 | RssAnon s→e a1 | RssAnon s→e a2 | host cache last save a1 → a2 (MiB) | PP_fresh %diff by depth | TG %diff by depth | T_turn_400 a1 → a2 (s, %) | a2 flags |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    n_a2 = n_a2_clean = n_a2_swap = 0
    a2_faults = []
    for sid, sess in sessions.items():
        by = {(w["cell"], w["rep"], w["attempt"]): w for w in wins[sid]}
        for (cell, rep, att), w2 in sorted(by.items()):
            if att != 2:
                continue
            w1 = by.get((cell, rep, 1))
            m1, m2 = rep_metrics(sess, cell, rep, 1), rep_metrics(sess, cell, rep, 2)
            if not (w1 and m1 and m2):
                continue
            n_a2 += 1
            n_a2_clean += not w2["flags"]
            n_a2_swap += (w2["swap_activity"] or 0) > SWAP_HEAVY_MIB
            a2_faults.append(w2["faults"] or 0)
            sp = speed_row(m1, m2)
            c1 = w1["cache_last"][1] if w1["cache_last"] else None
            c2 = w2["cache_last"][1] if w2["cache_last"] else None
            print(
                f"| {sid} | {cell} | {rep} | {f1(w1['faults'], 0)} → {f1(w2['faults'], 0)} | "
                f"{f1(w1['swap_activity'], 0)} → {f1(w2['swap_activity'], 0)} | {arrow(w1['anon'])} | {arrow(w2['anon'])} | "
                f"{f1(c1, 0)} → {f1(c2, 0)} | "
                + " / ".join(f"{x:+.1f}" for x in sp["pp"])
                + " | "
                + " / ".join(f"{x:+.1f}" for x in sp["tg"])
                + f" | {m1['tt']:.2f} → {m2['tt']:.2f} ({sp['tt']:+.1f}%) | "
                f"{', '.join(w2['flags']) or '-'} |"
            )
    print()
    print(
        f"- Attempt-2 units: {n_a2}; clean (no flag): {n_a2_clean}; with swap growth above {SWAP_HEAVY_MIB:.0f} MiB: {n_a2_swap}; "
        f"median major faults {f1(st.median(a2_faults) if a2_faults else None, 0)}, max {f1(max(a2_faults) if a2_faults else None, 0)}."
    )


if __name__ == "__main__":
    sys.exit(main())
