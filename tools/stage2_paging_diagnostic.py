"""Read-only paging diagnostic of the Stage 2a sessions (WP12 part 2c).

    uv run python tools/stage2_paging_diagnostic.py --out data/analysis/stage2/2a-paging

Reads data/raw/s2a-*/ (records, cell summaries, telemetry CSVs, session.json) and
data/logs/<run id>/server.log, and writes `<out>.json` and `<out>.md`. Nothing here changes a flag,
an eligibility rule or a statistic; the numbers are descriptive. The tool does not test any cause.

For every unit (one repetition) that carried the paging flag in attempt 1 it lists the cell, the
repetition, the cell's position in the session order and the minutes since the run started and since
its server started, and attempt 1 and attempt 2 side by side (major faults, RssFile at the start and
end of the window, swap activity and the VmSwap at the start, the host prompt cache size at the last
save inside the window, the minimum MemAvailable, T_turn_400 and PP_fresh and TG at the middle depth).
The summary gives the attempt-2 clean count, the concentration by cell type and the paired
attempt-2 against attempt-1 comparison for the same repetition of the same cell.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from datetime import UTC, datetime
from pathlib import Path

from smallpc import analysis, hostcache

# ruff: noqa: E501
ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "data/logs"
DEFAULT_SESSIONS = ("s2a-32K", "s2a-64K", "s2a-128K")
MID = 1  # index of the middle depth among the three depths


def epoch(utc: str) -> float:
    return datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()


def cell_type(name: str) -> str:
    # s2a-P6-32K-b4096-mtp1 -> "P6 mtp1"
    p = name.split("-")
    return f"{p[1]} {p[4]}"


def r1(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(x, nd)


def collect(sid: str, res: dict) -> list[dict]:
    d = ROOT / "data/raw" / sid
    sess = analysis.load_session(d)
    sj = json.loads((d / "session.json").read_text())
    order = sj.get("cell_order") or []
    runs = sj.get("runs") or []
    units = {(u["session"], u["cell"], u["repetition"], u["attempt"]): u for u in res["units"]}
    out = []
    for (name, _h), summ in sess.summaries.items():
        if summ.get("role") != "measured":
            continue
        for ins in summ.get("instances", []):
            run_id = ins["run_id"]
            att = ins.get("attempt", 1)
            tel_file = (ins.get("telemetry") or {}).get("file")
            rows = hostcache.telemetry_rows(d / tel_file) if tel_file else []
            cache = hostcache.cache_series(sess.requests, run_id, LOGS / run_id / "server.log")
            run = runs[0] if att == 1 else runs[-1]
            run_start = epoch(run["start_utc"])
            srv_start = epoch(ins["started_utc"])
            for w in ins.get("windows", []):
                t0, t1 = w.get("t0_epoch"), w.get("t1_epoch")
                fig = hostcache.window_figures(rows, t0, t1, cache) if rows and t0 else None
                paging = w.get("paging") or {}
                u = units.get((sid, name, w["repetition"], w["attempt"]))
                depths = sorted(u["metrics"]) if u else []
                md = u["metrics"][depths[MID]] if len(depths) > MID else {}
                out.append(
                    {
                        "session": sid,
                        "cell": name,
                        "type": cell_type(name),
                        "context": name.split("-")[2],
                        "cell_position": order.index(name) + 1 if name in order else None,
                        "cells_in_session": len(order),
                        "repetition": w["repetition"],
                        "attempt": w["attempt"],
                        "flagged": "paging" in (w.get("flags") or []),
                        "min_since_run_start": r1((t0 - run_start) / 60) if t0 else None,
                        "min_since_server_start": r1((t0 - srv_start) / 60) if t0 else None,
                        "faults": paging.get("major_faults"),
                        "rss_file_start_mib": r1(w.get("rss_file_start_mib"), 0),
                        "rss_file_end_mib": r1(w.get("rss_file_end_mib"), 0),
                        "swap_activity_mib": r1(w.get("swap_activity_mib"), 1),
                        "vmswap_start_mib": r1(w.get("vmswap_start_mib"), 0),
                        "host_cache_last": (
                            list(hostcache.cache_in_window(cache, t0, t1)[1])
                            if t0 and cache
                            else None
                        ),
                        "min_memavail_gib": r1(fig["memavail_min_gib"], 1) if fig else None,
                        "mid_depth": int(depths[MID]) if len(depths) > MID else None,
                        "t_turn_400": r1(u["rep"]["t_turn_400_mean"], 3) if u else None,
                        "pp_fresh_mid": r1(md.get("pp_fresh"), 0),
                        "tg_mid": r1(md.get("tg"), 1),
                    }
                )
    return out


def pct(a2: float | None, a1: float | None) -> float | None:
    if a2 is None or a1 is None or a1 == 0:
        return None
    return 100.0 * (a2 / a1 - 1.0)


def summarise(windows: list[dict]) -> dict:
    a1 = {(w["session"], w["cell"], w["repetition"]): w for w in windows if w["attempt"] == 1}
    a2 = {(w["session"], w["cell"], w["repetition"]): w for w in windows if w["attempt"] == 2}
    flagged = sorted(k for k, w in a1.items() if w["flagged"])
    paired = [(a1[k], a2[k]) for k in flagged if k in a2]
    clean2 = [k for k in flagged if k in a2 and not a2[k]["flagged"]]
    still = [k for k in flagged if k in a2 and a2[k]["flagged"]]
    by_type: dict[str, dict] = {}
    by_group: dict[str, dict] = {}
    for w in a1.values():
        for table, key in (
            (by_type, f"{w['context']} {w['type']}"),
            (by_group, "MTP" if not w["type"].endswith("mtp0") else "no MTP"),
            (by_group, w["type"].split()[0]),
            (by_group, w["context"]),
        ):
            e = table.setdefault(key, {"windows": 0, "flagged": 0})
            e["windows"] += 1
            e["flagged"] += int(w["flagged"])
    speed = {}
    for metric in ("t_turn_400", "pp_fresh_mid", "tg_mid"):
        d = [pct(b[metric], a[metric]) for a, b in paired]
        d = [x for x in d if x is not None]
        speed[metric] = (
            {
                "n": len(d),
                "mean_pct": r1(st.mean(d), 2),
                "min_pct": r1(min(d), 2),
                "max_pct": r1(max(d), 2),
            }
            if d
            else None
        )
    clean_pairs = [(a1[k], a2[k]) for k in clean2]
    speed_clean = {}
    for metric in ("t_turn_400", "pp_fresh_mid", "tg_mid"):
        d = [x for x in (pct(b[metric], a[metric]) for a, b in clean_pairs) if x is not None]
        speed_clean[metric] = (
            {
                "n": len(d),
                "mean_pct": r1(st.mean(d), 2),
                "min_pct": r1(min(d), 2),
                "max_pct": r1(max(d), 2),
            }
            if d
            else None
        )
    # speed of flagged against unflagged windows of the same cell and attempt 1 (confounded by repetition)
    within = []
    for cell in sorted({k[1] for k in a1}):
        f = [
            w["t_turn_400"]
            for k, w in a1.items()
            if k[1] == cell and w["flagged"] and w["t_turn_400"]
        ]
        u = [
            w["t_turn_400"]
            for k, w in a1.items()
            if k[1] == cell and not w["flagged"] and w["t_turn_400"]
        ]
        if f and u:
            within.append(
                {
                    "cell": cell,
                    "flagged_mean": r1(st.mean(f), 3),
                    "n_flagged": len(f),
                    "unflagged_mean": r1(st.mean(u), 3),
                    "n_unflagged": len(u),
                    "pct": r1(pct(st.mean(f), st.mean(u)), 2),
                }
            )
    # was the previous window of the same cell a swap-growth window? (descriptive)
    prev = []
    for k in flagged:
        p = a1.get((k[0], k[1], k[2] - 1))
        prev.append(
            {
                "cell": k[1],
                "repetition": k[2],
                "previous_window_swap_activity_mib": p["swap_activity_mib"] if p else None,
                "vmswap_start_mib": a1[k]["vmswap_start_mib"],
            }
        )
    return {
        "attempt1_windows": len(a1),
        "attempt1_flagged": len(flagged),
        "attempt2_units": len(paired),
        "attempt2_clean": len(clean2),
        "attempt2_still_flagged": [list(k) for k in still],
        "by_cell_type": by_type,
        "by_group": by_group,
        "paired_attempt2_vs_attempt1_all": speed,
        "paired_attempt2_vs_attempt1_clean_attempt2": speed_clean,
        "flagged_vs_unflagged_same_cell_attempt1": within,
        "previous_window_swap": prev,
    }


def fmt(x, nd=None):
    if x is None:
        return "-"
    if isinstance(x, float) and nd is not None:
        return f"{x:,.{nd}f}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def render(windows: list[dict], summ: dict) -> str:
    a1 = {(w["session"], w["cell"], w["repetition"]): w for w in windows if w["attempt"] == 1}
    a2 = {(w["session"], w["cell"], w["repetition"]): w for w in windows if w["attempt"] == 2}
    flagged = sorted(k for k, w in a1.items() if w["flagged"])
    L = [
        "# Stage 2a paging diagnostic",
        "",
        "**SCREENING, descriptive only.** Read-only: it changes no flag, eligibility rule or statistic and tests no cause.",
        "Written by `tools/stage2_paging_diagnostic.py` from `data/raw/s2a-*`. Attempt 1 is the main session, attempt 2 the one `--rerun-flagged` pass "
        "(a fresh server whose first repetitions are the re-run units). Times: minutes since the start of the run that contains the window "
        "(attempt 1: the session; attempt 2: the re-run) and since that window's server was started.",
        "",
    ]
    L += [
        "## Flagged attempt-1 units, attempt 1 against attempt 2",
        "",
        "| cell | rep | cell pos / min since run start / min since server start (a1) | a1 faults | a1 RssFile start→end | a1 swap act. / VmSwap start (MiB) | a1 host cache (prompts, MiB) | a1 min MemAvail (GiB) | a1 T_turn_400 / PP_fresh mid / TG | a2 flag | a2 min since run / server start | a2 faults | a2 RssFile start→end | a2 swap act. / VmSwap start | a2 host cache | a2 min MemAvail | a2 T_turn_400 / PP_fresh mid / TG |",
        "|" + "---|" * 17,
    ]
    for k in flagged:
        w, b = a1[k], a2.get(k)

        def side(x):
            if x is None:
                return ["-"] * 7
            return [
                f"{fmt(x['faults'])}",
                f"{fmt(x['rss_file_start_mib'])}→{fmt(x['rss_file_end_mib'])}",
                f"{fmt(x['swap_activity_mib'], 1)} / {fmt(x['vmswap_start_mib'])}",
                "-"
                if not x["host_cache_last"]
                else f"{x['host_cache_last'][0]}, {x['host_cache_last'][1]:,.0f}",
                fmt(x["min_memavail_gib"], 1),
                f"{fmt(x['t_turn_400'], 3)} / {fmt(x['pp_fresh_mid'])} / {fmt(x['tg_mid'], 1)}",
            ]

        s1, s2 = side(w), side(b)
        L.append(
            f"| `{w['cell'][4:]}` | {k[2]} | {w['cell_position']}/{w['cells_in_session']} / {fmt(w['min_since_run_start'], 1)} / {fmt(w['min_since_server_start'], 1)} | "
            + " | ".join(s1[:6])
            + " | "
            + ("-" if b is None else ("yes" if b["flagged"] else "no"))
            + " | "
            + (
                "-"
                if b is None
                else f"{fmt(b['min_since_run_start'], 1)} / {fmt(b['min_since_server_start'], 1)}"
            )
            + " | "
            + " | ".join(s2[:6])
            + " |"
        )
    L += [
        "",
        f"Middle depth: 32K context {fmt(next(w['mid_depth'] for w in a1.values() if w['context'] == '32K'))} tokens, "
        f"64K {fmt(next(w['mid_depth'] for w in a1.values() if w['context'] == '64K'))}, 128K {fmt(next(w['mid_depth'] for w in a1.values() if w['context'] == '128K'))}.",
        "",
    ]
    L += [
        "## Summary",
        "",
        f"- Attempt-1 windows: {summ['attempt1_windows']}, paging-flagged: {summ['attempt1_flagged']}.",
        f"- Attempt-2 units run: {summ['attempt2_units']}; **clean: {summ['attempt2_clean']}**; still flagged: "
        + (", ".join(f"`{c[4:]}` rep {r}" for _s, c, r in summ["attempt2_still_flagged"]) or "none")
        + ".",
        "",
        "### Concentration by cell type (attempt-1 flagged windows / windows)",
        "",
        "| group | flagged / windows |",
        "|---|---|",
    ]
    for g, e in sorted(summ["by_group"].items()):
        L.append(f"| {g} | {e['flagged']} / {e['windows']} |")
    L += ["", "| context and cell type | flagged / windows |", "|---|---|"]
    for g, e in sorted(summ["by_cell_type"].items()):
        L.append(f"| {g} | {e['flagged']} / {e['windows']} |")
    L += [
        "",
        "### Paired attempt 2 against attempt 1 (same repetition index of the same cell)",
        "",
        "Percentage difference (attempt 2 relative to attempt 1), mean and range over the paired units. The same repetition index removes the "
        "repetition (prompt-variant) confound; it does not remove the effect of a fresh server (attempt 2 is the first repetition of a new server). "
        "**Anecdotal**: a handful of units, no interval.",
        "",
        "| units | metric | n | mean % | min % | max % |",
        "|---|---|---|---|---|---|",
    ]
    for label, key in (
        ("all re-run units", "paired_attempt2_vs_attempt1_all"),
        ("attempt 2 clean only", "paired_attempt2_vs_attempt1_clean_attempt2"),
    ):
        for m, e in summ[key].items():
            L.append(
                f"| {label} | {m} | "
                + (
                    f"{e['n']} | {e['mean_pct']:+.2f} | {e['min_pct']:+.2f} | {e['max_pct']:+.2f} |"
                    if e
                    else "- | - | - | - |"
                )
            )
    L += [
        "",
        "T_turn_400 lower, PP_fresh and TG higher in attempt 2 would mean the flagged attempt-1 window was the slower one.",
        "",
        "### Flagged against unflagged windows of the same cell (attempt 1, T_turn_400, confounded by repetition)",
        "",
        "| cell | flagged mean (n) | unflagged mean (n) | difference |",
        "|---|---|---|---|",
    ]
    for e in summ["flagged_vs_unflagged_same_cell_attempt1"]:
        L.append(
            f"| `{e['cell'][4:]}` | {e['flagged_mean']} ({e['n_flagged']}) | {e['unflagged_mean']} ({e['n_unflagged']}) | {e['pct']:+.2f} % |"
        )
    L += [
        "",
        "### Swap carried into the flagged window (descriptive)",
        "",
        "| cell | rep | swap activity of the previous window (MiB) | VmSwap at the start of the flagged window (MiB) |",
        "|---|---|---|---|",
    ]
    for e in summ["previous_window_swap"]:
        L.append(
            f"| `{e['cell'][4:]}` | {e['repetition']} | {fmt(e['previous_window_swap_activity_mib'], 1)} | {fmt(e['vmswap_start_mib'])} |"
        )
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="output path without extension")
    ap.add_argument("--sessions", nargs="*", default=list(DEFAULT_SESSIONS))
    a = ap.parse_args()
    dirs = [ROOT / "data/raw" / s for s in a.sessions]
    res = analysis.analyse(dirs)
    windows = []
    for s in a.sessions:
        windows += collect(s, res)
    summ = summarise(windows)
    out = Path(a.out)
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(
        json.dumps(
            {"label": "screening", "sessions": a.sessions, "summary": summ, "windows": windows},
            indent=1,
        )
        + "\n"
    )
    out.with_suffix(".md").write_text(render(windows, summ))
    print(f"wrote {out.with_suffix('.json')} and {out.with_suffix('.md')}")


if __name__ == "__main__":
    main()
