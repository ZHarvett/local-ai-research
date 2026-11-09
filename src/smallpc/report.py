"""Reports from sweep sessions: ``render``, ``coverage`` and ``repro`` (WP10).

    python -m smallpc.report render --sessions DIR... --out DIR --label LABEL
        (LABEL: functional-test, screening or results)
    python -m smallpc.report coverage --spec SPEC.toml --sessions DIR...
    python -m smallpc.report repro --original DIR... --rerun DIR... --cells stock-64K,tuned-64K

``render`` writes ``report.md`` and SVG figures (``figures/``) that are byte-for-byte reproducible:
matplotlib's ``svg.hashsalt`` is fixed, the SVG metadata has no date and no creator, text stays text
(``svg.fonttype none``) and nothing in the report is a wall-clock time. ``coverage`` verifies S1
(exit code 1 if any cell is partial or missing); ``repro`` is the S2 check.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import analysis, labels, select, stats  # noqa: E402
from .config import load_sweep, repo_root  # noqa: E402
from .scrub import Identity, scrub_text  # noqa: E402
from .sweep import spec as sp  # noqa: E402

PLAN_PATH = "docs/plans/step-0-baseline.md"
PCT = "acceptance"

# Categorical slots of the reference palette (light mode, fixed order). The stock cell is neutral
# ink, never a slot; cells beyond the slots are folded into one gray group.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
INK, MUTED, GRID, OTHER = "#0b0b0b", "#52514e", "#dcdbd5", "#b8b7b0"
VRAM_PARTS = [
    ("model_mib", "model", SERIES[0]),
    ("kv_mib", "KV cache", SERIES[1]),
    ("recurrent_mib", "recurrent state", SERIES[2]),
    ("compute_mib", "compute buffers", SERIES[3]),
    ("other_mib", "other (CUDA context, ...)", SERIES[6]),
]


# ------------------------------------------------------------------------------- formatting


def f_stats(s: dict | None, digits: int = 2, scale: float = 1.0) -> str:
    """``mean [lo, hi]``; the CI only for n of at least 2."""
    if not s:
        return "-"
    txt = f"{s['mean'] * scale:.{digits}f}"
    if s["ci"] is not None:
        txt += f" [{s['ci'][0] * scale:.{digits}f}, {s['ci'][1] * scale:.{digits}f}]"
    return txt


def kk(depth: int) -> str:
    return f"{depth // 1024}K"


def demote(md: str, by: int = 1) -> str:
    return re.sub(r"^(#+) ", lambda m: "#" * (len(m[1]) + by) + " ", md, flags=re.M)


def rep_mean_over_depths(cell: dict, metric: str) -> dict[str, float]:
    """Per-repetition mean over the cell's depths of a per-depth metric (clean units that have the
    metric at every depth)."""
    depths = cell["depths"]
    per = [cell["depth_metrics"][str(d)][metric]["values"] for d in depths]
    if not per:
        return {}
    keys = set(per[0]).intersection(*per[1:])
    return {k: sum(p[k] for p in per) / len(per) for k in sorted(keys)}


def summ(values: dict[str, float]) -> dict | None:
    return stats.summarize(list(values.values())) if values else None


def contexts(res: dict) -> dict[str, list[dict]]:
    return select._by_context(res)


def ordered(cells: list[dict]) -> list[dict]:
    """Stock first, then candidates by mean T_turn_400 (cells without data last), then name."""
    inf = float("inf")
    return sorted(
        cells,
        key=lambda c: (c["profile"] != "stock", select.mean_tt(c) or inf, c["name"]),
    )


# ---------------------------------------------------------------------------------- figures


def _setup() -> None:
    plt.rcParams.update(
        {
            "svg.hashsalt": "smallpc-report",
            "svg.fonttype": "none",
            "font.family": "sans-serif",
            "font.sans-serif": ["DejaVu Sans"],
            "font.size": 9,
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK,
            "text.color": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _svg(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", metadata={"Date": None, "Creator": None})
    plt.close(fig)
    return buf.getvalue().decode()


def _no_data(ax, what: str) -> None:
    ax.set_axis_off()
    ax.text(0.5, 0.5, f"no data\n{what}", ha="center", va="center", color=MUTED, fontsize=10)


def _style_map(cells: list[dict]) -> dict[str, dict]:
    """Colour, marker and line style per cell: stock is ink, the first candidates take the fixed
    categorical slots in order of mean T_turn_400, the rest are gray ('other cells')."""
    out: dict[str, dict] = {}
    slot = 0
    for c in ordered(cells):
        if c["profile"] == "stock":
            out[c["name"]] = {"color": INK, "marker": "h", "ls": "--", "lw": 1.6, "z": 5}
        elif slot < len(SERIES):
            out[c["name"]] = {"color": SERIES[slot], "marker": MARKERS[slot], "ls": "-",
                              "lw": 1.5, "z": 4}  # fmt: skip
            slot += 1
        else:
            out[c["name"]] = {"color": OTHER, "marker": "", "ls": "-", "lw": 0.8, "z": 1}
    return out


def _legend(ax, handles, n_other: int) -> None:
    if n_other:
        handles = [
            *handles,
            plt.Line2D([], [], color=OTHER, lw=0.8, label=f"{n_other} other cells"),
        ]
    if len(handles) >= 2:
        ax.legend(handles=handles, fontsize=7, frameon=False, loc="upper center",
                  bbox_to_anchor=(0.5, -0.2), ncol=1)  # fmt: skip


def _frame(label: str, title: str, n: int, height: float = 4.6):
    """Figure with one panel per context, a wrapped title and the data label above the panels."""
    _setup()
    width = max(7.6, 4.6 * max(n, 1))
    fig, axes = plt.subplots(1, max(n, 1), figsize=(width, height), squeeze=False)
    head = textwrap.fill(f"[{label}] {title}", int(width * 10.5))
    ban = textwrap.fill(labels.banner(label), int(width * 19))
    h_title = (head.count("\n") + 1) * 0.19
    h_ban = (ban.count("\n") + 1) * 0.13
    fig.text(0.01, 1 - 0.05 / height, head, fontsize=10, va="top", ha="left")
    fig.text(0.01, 1 - (0.05 + h_title + 0.04) / height, ban, fontsize=7, va="top", ha="left",
             color=MUTED)  # fmt: skip
    fig._top = 1 - (0.05 + h_title + h_ban + 0.35) / height  # type: ignore[attr-defined]
    return fig, axes[0]


def _finish(fig):
    fig.tight_layout(rect=(0, 0, 1, fig._top))
    return _svg(fig)


def fig_depth_lines(res: dict, label: str, metric: str, ylabel: str, title: str) -> str:
    ctxs = contexts(res)
    fig, axes = _frame(label, title, len(ctxs))
    if not ctxs:
        _no_data(axes[0], "no cells in the sessions")
    for ax, (ctx, cells) in zip(axes, ctxs.items(), strict=False):
        style = _style_map(cells)
        handles, n_other, drawn = [], 0, False
        for c in ordered(cells):
            xs, ys, err = [], [], []
            for d in c["depths"]:
                s = c["depth_metrics"][str(d)][metric]["stats"]
                if s:
                    xs.append(d / 1024)
                    ys.append(s["mean"])
                    err.append((s["ci"][1] - s["ci"][0]) / 2 if s["ci"] else 0.0)
            if not xs:
                continue
            drawn = True
            st = style[c["name"]]
            ax.errorbar(xs, ys, yerr=err, color=st["color"], marker=st["marker"], ls=st["ls"],
                        lw=st["lw"], ms=5, capsize=3, zorder=st["z"], label=c["name"])  # fmt: skip
            if st["color"] == OTHER:
                n_other += 1
            else:
                handles.append(plt.Line2D([], [], color=st["color"], marker=st["marker"],
                                          ls=st["ls"], lw=st["lw"], label=c["name"]))  # fmt: skip
        if not drawn:
            _no_data(ax, f"{ctx}: no clean repetitions")
            continue
        ax.set_title(ctx, fontsize=9, loc="left")
        ax.set_xticks(sorted({d / 1024 for c in cells for d in c["depths"]}))
        ax.set_xlabel("prompt length / depth (K tokens)")
        ax.set_ylabel(ylabel)
        _legend(ax, handles, n_other)
    return _finish(fig)


def fig_turn_times(res: dict, label: str) -> str:
    ctxs = contexts(res)
    fig, axes = _frame(
        label, "T_turn_400 (estimated) and T_B (measured), mean over depths", len(ctxs), 5
    )
    if not ctxs:
        _no_data(axes[0], "no cells in the sessions")
    for ax, (ctx, cells) in zip(axes, ctxs.items(), strict=False):
        rows = []
        for c in ordered(cells):
            tt, tb = (
                summ(rep_mean_over_depths(c, "t_turn_400")),
                summ(rep_mean_over_depths(c, "t_b")),
            )
            pn = summ(rep_mean_over_depths(c, "predicted_n"))
            if tt and tb:
                rows.append((c["name"], tt, tb, pn["mean"] if pn else None))
        if not rows:
            _no_data(ax, f"{ctx}: no clean repetitions")
            continue
        h = 0.38
        for i, (_name, tt, tb, pn) in enumerate(rows):
            for off, s, col in ((-h / 2, tt, SERIES[0]), (h / 2, tb, SERIES[1])):
                err = (s["ci"][1] - s["ci"][0]) / 2 if s["ci"] else 0
                ax.barh(i + off, s["mean"], height=h - 0.04, color=col, xerr=err or None,
                        error_kw={"ecolor": INK, "lw": 0.8, "capsize": 2})  # fmt: skip
            if pn is not None:
                end = tb["mean"] + ((tb["ci"][1] - tb["ci"][0]) / 2 if tb["ci"] else 0)
                ax.text(end, i + h / 2, f"  predicted_n {pn:.0f}", va="center", fontsize=6.5,
                        color=MUTED)  # fmt: skip
        ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=7)
        ax.invert_yaxis()
        ax.set_xlabel("seconds")
        ax.set_title(ctx, fontsize=9, loc="left")
        ax.set_xlim(0, max(r[2]["ci"][1] if r[2]["ci"] else r[2]["mean"] for r in rows) * 1.5)
        handles = [
            plt.Rectangle((0, 0), 1, 1, color=SERIES[0], label="T_turn_400 (estimate)"),
            plt.Rectangle((0, 0), 1, 1, color=SERIES[1], label="T_B (measured)"),
        ]
        ax.legend(handles=handles, fontsize=7, frameon=False, loc="upper center",
                  bbox_to_anchor=(0.5, -0.14))  # fmt: skip
    return _finish(fig)


def fig_vram(res: dict, label: str) -> str:
    ctxs = contexts(res)
    fig, axes = _frame(label, "VRAM breakdown per cell (MiB)", len(ctxs), 5)
    if not ctxs:
        _no_data(axes[0], "no cells in the sessions")
    for ax, (ctx, cells) in zip(axes, ctxs.items(), strict=False):
        rows = [c for c in ordered(cells) if c["vram"] and c["vram"].get("peak_used_mib")]
        if not rows:
            _no_data(ax, f"{ctx}: no placement or VRAM data")
            continue
        for i, c in enumerate(rows):
            left = 0.0
            for key, _name, col in VRAM_PARTS:
                v = c["vram"].get(key) or 0.0
                ax.barh(i, v, left=left, color=col, height=0.6, edgecolor="white", lw=1.0)
                left += v
            free = c["min_free_vram_mib"] or 0.0
            ax.barh(i, free, left=left, color="white", height=0.6, edgecolor=OTHER, hatch="////",
                    lw=0.5)  # fmt: skip
        total = rows[0]["vram"].get("total_mib")
        if total:
            ax.axvline(total, color=INK, lw=1)
            ax.annotate(f"total {total:,.0f} ", (total, 1.0), xycoords=("data", "axes fraction"),
                        ha="right", va="bottom", fontsize=6.5, color=MUTED)  # fmt: skip
        ax.set_yticks(range(len(rows)), [c["name"] for c in rows], fontsize=7)
        ax.invert_yaxis()
        ax.set_xlabel("MiB")
        ax.set_title(ctx, fontsize=9, loc="left")
        handles = [
            plt.Rectangle((0, 0), 1, 1, color=col, label=name) for _, name, col in VRAM_PARTS
        ]
        handles.append(plt.Rectangle((0, 0), 1, 1, fc="white", ec=OTHER, hatch="////",
                                     label="minimum free"))  # fmt: skip
        ax.legend(handles=handles, fontsize=7, frameon=False, loc="upper center",
                  bbox_to_anchor=(0.5, -0.2), ncol=2)  # fmt: skip
    return _finish(fig)


def fig_cache(res: dict, label: str) -> str:
    fig, axes = _frame(
        label, "Expert-cache hit rate vs cache size (decode-sized batches only)", 1, 4.4
    )
    ax = axes[0]
    pts: dict[str, list[tuple[float, float, str]]] = {}
    for ctx, cells in contexts(res).items():
        for c in cells:
            hr = c["cache"]["decode_hit_rate_pct"]
            size = (c["cache"]["config"] or {}).get("cache_mib") or c["cache_mib"]
            if c["cache"]["present"] and hr is not None and size:
                pts.setdefault(ctx, []).append((float(size), hr, c["name"]))
    if not pts:
        _no_data(ax, "no expert-cache cells in these sessions")
    else:
        for i, (ctx, p) in enumerate(sorted(pts.items())):
            p.sort()
            ax.plot([x for x, _, _ in p], [y for _, y, _ in p], color=SERIES[i], marker=MARKERS[i],
                    lw=1.5, ms=6, label=ctx)  # fmt: skip
        ax.set_xlabel("expert cache size (MiB)")
        ax.set_ylabel("decode-batch hit rate (%)")
        ax.set_ylim(0, 100)
        ax.legend(fontsize=7, frameon=False, title="context", title_fontsize=7)
    return _finish(fig)


def _prefill(r: dict, lab: str) -> str:
    return fig_depth_lines(
        r, lab, "pp_fresh", "tokens/s",
        "Prefill speed (PP_fresh, Request A) vs prompt length; bars: 95% CI",
    )  # fmt: skip


def _decode(r: dict, lab: str) -> str:
    return fig_depth_lines(
        r, lab, "tg", "tokens/s", "Decode speed (TG, Request B) vs depth; bars: 95% CI"
    )


FIGURES = {
    "prefill-speed.svg": ("Prefill speed (PP_fresh) vs prompt length", _prefill),
    "decode-speed.svg": ("Decode speed (TG) vs depth", _decode),
    "turn-time.svg": ("T_turn_400 (estimated) and T_B (measured)", fig_turn_times),
    "vram-breakdown.svg": ("VRAM breakdown per context", fig_vram),
    "expert-cache-hit-rate.svg": ("Expert-cache hit rate vs cache size", fig_cache),
}


def render_figures(res: dict, label: str) -> dict[str, str]:
    return {name: fn(res, label) for name, (_t, fn) in FIGURES.items()}


# ------------------------------------------------------------------------------------ report


def _table(banner: str, header: list[str], rows: list[list[str]]) -> list[str]:
    out = []
    if banner:
        out += [f"> {banner}", ""]
    out.append("| " + " | ".join(header) + " |")
    out.append("|" + "---|" * len(header))
    out += ["| " + " | ".join(r) + " |" for r in rows]
    out.append("")
    return out


def _n_cell(c: dict) -> str:
    txt = f"{c['n_clean']}/{c['n_total']}"
    return txt + (f" {labels.NOT_REPORTABLE}" if c["n_clean"] < labels.MIN_REPORTABLE_N else "")


def results_rows(c: dict, depths: list[int], rerun_units: dict[str, int]) -> list[str]:
    if c["status"] in ("did_not_fit", "not_applicable") or not c["n_total"]:
        why = f"{c['status']}" + (f" ({c['reason']})" if c["reason"] else "")
        return (
            [c["name"], why] + ["-"] * (2 * len(depths) + 5) + [", ".join(c["unit_flags"]) or "-"]
        )
    cols = [c["name"], _n_cell(c)]
    for metric in ("pp_fresh", "tg"):
        for d in depths:
            blk = c["depth_metrics"].get(str(d))
            cols.append(f_stats(blk[metric]["stats"], 1) if blk else "-")
    tt = c["rep_metrics"]["t_turn_400_mean"]["stats"]
    tb = summ(rep_mean_over_depths(c, "t_b"))
    pn = summ(rep_mean_over_depths(c, "predicted_n"))
    rr = c["rep_metrics"]["t_reread_mean"]["stats"]
    tf = summ(rep_mean_over_depths(c, "ttft"))
    cols.append(f_stats(tt))
    cols.append(f_stats(tb) + (f" (predicted_n {pn['mean']:.0f})" if tb and pn else ""))
    cols.append(f_stats(rr))
    cols.append(f_stats(tf))
    ap = c["acceptance_pooled"]
    acc = c["rep_metrics"]["acceptance"]["stats"]
    if c["mtp"] and ap["B"] is not None:
        cols.append(f"{f_stats(acc, 1, 100)} % (pooled {ap['B'] * 100:.1f} %)")
    else:
        cols.append("-")
    fl = list(c["unit_flags"])
    if rerun_units.get(c["name"]):
        fl.append(f"{rerun_units[c['name']]} unit(s) re-run (attempt 2 used)")
    cols.append(", ".join(fl) or "-")
    return cols


def paired_rows(res: dict, cells: list[dict]) -> list[list[str]]:
    stock = next((c for c in cells if c["profile"] == "stock"), None)
    if stock is None:
        return []
    rows = []
    for c in ordered(cells):
        if c is stock or not c["n_clean"]:
            continue
        cells_out = [c["name"]]
        n = 0
        for metric in ("t_turn_400", "pp_fresh", "tg"):
            a, b = rep_mean_over_depths(c, metric), rep_mean_over_depths(stock, metric)
            if not (set(a) & set(b)):
                cells_out.append("-")
                continue
            r = stats.paired_ratio(a, b)
            n = r["n"]
            txt = f"{r['geomean']:.3f}"
            if r["ci"]:
                txt += f" [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]"
            cells_out.append(txt)
        rows.append([cells_out[0], str(n), *cells_out[1:]])
    return rows


def plan_version(root: Path | None = None) -> str:
    p = (root or repo_root()) / PLAN_PATH
    if p.exists():
        for line in p.read_text().splitlines()[:12]:
            if m := re.search(r"\b[Vv](?:ersion)?\s?(\d+\.\d+)\b", line):
                return f"v{m[1]}"
    return "unknown"


def render_report(
    res: dict, label: str, *, command: str, plan: str, sanity: dict | None = None
) -> str:
    ban = labels.banner(label)
    mode = "final" if label == "results" else "screening"
    sel = (select.select_final if mode == "final" else select.select_screening)(res, sanity)
    L: list[str] = []
    A = L.append
    A(f"# Baseline report ({label})")
    A("")
    A(f"> **{ban}**")
    A("")
    # ------------------------------------------------------------------ provenance
    A("## Provenance")
    A("")
    A(f"- Plan version: {plan}")
    A("- Regenerate with: `" + command + "`")
    A(
        "- Statistics: mean, n, min, max and a 95% CI (wider of the percentile-bootstrap interval, "
        "10,000 resamples, fixed seed, and the t interval); CIs shown for n of at least 2."
    )
    A("")
    rows = []
    for s in res["sessions"]:
        git = (s["git_commit"] or "-")[:10] + (" (dirty)" if s["git_dirty"] else "")
        rows.append(
            [
                s["session_id"],
                f"{s['spec'] or '-'} `{(s['spec_sha256'] or '-')[:16]}`",
                f"`{(s['manifest_sha256'] or '-')[:16]}`",
                git + (" **--allow-dirty**" if s["allow_dirty"] else ""),
                ", ".join(f"`{c}`" for c in s["request_commits"]) or "-",
                ", ".join(f"`{x}`" for x in s["snapshot_ids"]) or "-",
                f"`{(s['llama_cpp_commit'] or '-')[:10]}`",
                s["state"] or "-",
            ]
        )
    L += _table(
        ban,
        ["session", "spec / sha-256", "manifest sha-256", "session commit", "record commits",
         "snapshot ids", "llama.cpp", "state"],
        rows,
    )  # fmt: skip
    dirty = [s for s in res["sessions"] if s["allow_dirty"]]
    for s in dirty:
        A(
            f"Session `{s['session_id']}` was run with `--allow-dirty`: its recorded commit is not "
            "exact (uncommitted paths: " + ", ".join(f"`{p}`" for p in s["dirty_paths"]) + ")."
        )
        A("")
    # ------------------------------------------------------------------ health
    A("## Session health")
    A("")
    hrows = []
    for s in res["sessions"]:
        drift = (
            ", ".join(
                f"{w}: {d['flag'] or ('none' if d['complete'] else 'not assessed')}"
                for w, d in s["drift"].items()
            )
            or "no drift record"
        )
        idle = s["idle"]
        hrows.append(
            [
                s["session_id"],
                f"checked {s['inhibit']['checked']}, active {s['inhibit']['active']}",
                f"{idle['checks']} checks, {idle['failed_checks']} failed, total wait "
                f"{idle['total_waited_s']:.0f} s, max busy {idle['busy_pct_max']} %",
                drift,
            ]
        )
    L += _table(ban, ["session", "systemd-inhibit", "idle precondition", "drift flag"], hrows)
    crow = []
    for s in res["sessions"]:
        for which, part in s["canaries"].items():
            for role, c in part.items():
                crow.append(
                    [
                        s["session_id"],
                        which,
                        role.replace("canary_", ""),
                        str(len(c["repetitions"])),
                        f_stats(c["pp_fresh_16k"]["stats"], 1),
                        f_stats(c["tg_16k"]["stats"], 1),
                        f_stats(c["tg_short"]["stats"], 1),
                        ", ".join(c["flags"]) or "-",
                    ]
                )
    if crow:
        A("Canaries (never part of cell statistics):")
        A("")
        L += _table(
            ban,
            ["session", "run", "phase", "reps", "PP_fresh 16K (tok/s)", "TG 16K (tok/s)",
             "TG short (tok/s)", "flags"],
            crow,
        )  # fmt: skip
    # ------------------------------------------------------------------ results
    A("## Results")
    A("")
    rerun_units: dict[str, int] = {}
    for u in res["units"]:
        if u["superseded"]:
            rerun_units[u["cell"]] = rerun_units.get(u["cell"], 0) + 1
    reportable_only = label == "results"
    appendix_cells: list[dict] = []
    ctxs = contexts(res)
    if not ctxs:
        A("No cells with a context in these sessions.")
        A("")
    for ctx, cells in ctxs.items():
        A(f"### {ctx}")
        A("")
        depths = sorted({d for c in cells for d in c["depths"]})
        shown = []
        for c in ordered(cells):
            if reportable_only and c["n_clean"] < labels.MIN_REPORTABLE_N and c["n_total"]:
                appendix_cells.append(c)
            else:
                shown.append(c)
        header = (
            ["cell", "n_clean/n_total"]
            + [f"PP_fresh {kk(d)} (tok/s)" for d in depths]
            + [f"TG {kk(d)} (tok/s)" for d in depths]
            + ["T_turn_400 (s)", "T_B (s)", "T_reread (s)", "TTFT (s)", "acceptance", "flags"]
        )
        L += _table(ban, header, [results_rows(c, depths, rerun_units) for c in shown])
        A(
            "Values are mean [95% CI] over clean repetitions. T_turn_400, T_B, T_reread and TTFT "
            "are means over the depths of §5.3 per repetition. T_turn_400 is an estimate (400 "
            "tokens); T_B is the measured time of Request B and is always shown with its "
            "`predicted_n`."
        )
        A("")
    nocx = [c for c in res["cells"].values() if not c["context_label"]]
    if nocx:
        A("### Cells without context information")
        A("")
        L += _table(
            ban,
            ["cell", "status", "reason"],
            [[c["name"], c["status"] or "missing", c["reason"] or "-"] for c in nocx],
        )
        A(
            "Cells that never started (not_applicable) have no resolved configuration, so no "
            "context is known."
        )
        A("")
    # ------------------------------------------------------------------ eligibility and selection
    A("## Eligibility and selection")
    A("")
    A(demote(select.render_markdown(sel, label), 1).split("\n", 3)[3].strip("\n"))
    A("")
    # ------------------------------------------------------------------ paired
    A("## Paired comparisons with stock")
    A("")
    any_pair = False
    for ctx, cells in ctxs.items():
        prow = paired_rows(res, cells)
        if not prow:
            continue
        any_pair = True
        A(f"### {ctx}")
        A("")
        L += _table(
            ban,
            ["candidate vs stock", "pairs", "T_turn_400 ratio", "PP_fresh ratio", "TG ratio"],
            prow,
        )
    if any_pair:
        A(
            "Geometric mean of per-repetition ratios (candidate / stock, repetitions that are "
            "clean in both cells) with a 95% bootstrap CI (10,000 resamples), shown for 2 or more "
            "pairs. A T_turn_400 ratio below 1 means the candidate is faster; PP_fresh and TG "
            "ratios above 1 mean it is faster. The bootstrap CI alone is narrow at small n."
        )
    else:
        A("No context has both a stock cell and a candidate with clean repetitions.")
    A("")
    # ------------------------------------------------------------------ VRAM
    A("## VRAM breakdown")
    A("")
    for ctx, cells in ctxs.items():
        vrows = []
        for c in ordered(cells):
            v = c["vram"]
            if not v:
                continue
            vrows.append(
                [
                    c["name"],
                    f"{v['model_mib']:,.0f}",
                    f"{v['kv_mib']:,.0f} ({v['kv_type'] or '-'})",
                    f"{v['recurrent_mib']:,.0f}",
                    f"{v['compute_mib']:,.0f}",
                    "-" if v["other_mib"] is None else f"{v['other_mib']:,.0f}",
                    "-" if v["peak_used_mib"] is None else f"{v['peak_used_mib']:,.0f}",
                    "-" if c["min_free_vram_mib"] is None else f"{c['min_free_vram_mib']:,.0f}",
                    "-" if v["expert_layers_on_cpu"] is None else str(v["expert_layers_on_cpu"]),
                ]
            )
        if not vrows:
            continue
        A(f"### {ctx}")
        A("")
        L += _table(
            ban,
            ["cell", "model", "KV", "recurrent state", "compute buffers", "other", "peak used",
             "min free (final windows)", "expert layers on CPU"],
            vrows,
        )  # fmt: skip
    A(
        "MiB, from each cell summary's parsed placement (buffers on the GPU) and its windows. "
        "'other' is peak used minus the listed buffers (CUDA context, graphs, allocator slack)."
    )
    A("")
    # ------------------------------------------------------------------ expert cache
    A("## Expert cache")
    A("")
    crows = []
    for _ctx, cells in ctxs.items():
        for c in ordered(cells):
            ca = c["cache"]
            if not ca["present"]:
                continue
            dec = next((k for k in ca["classes"] if "<" in k["name"]), None)
            lb = ca["large_batch_copies"] or {}
            size = (ca["config"] or {}).get("cache_mib") or c["cache_mib"]
            crows.append(
                [
                    c["name"],
                    "-" if not size else f"{size:,.0f}",
                    "-"
                    if ca["decode_hit_rate_pct"] is None
                    else f"{ca['decode_hit_rate_pct']:.1f} %",
                    "-" if not dec else f"{dec['hits']:,}",
                    "-" if not dec else f"{dec['misses']:,}",
                    f"{lb.get('experts', 0):,}",
                    f"{sum(k['uploaded_mib'] for k in ca['classes']):,.0f}",
                ]
            )
    if crows:
        L += _table(
            ban,
            ["cell", "cache MiB", "decode-batch hit rate", "hits", "misses",
             "large-batch experts copied", "uploaded MiB"],
            crows,
        )  # fmt: skip
    else:
        A("No expert-cache cells in these sessions.")
        A("")
    A(
        "Limitation: the server's statistics give hit rates for **decode-sized batches only** "
        "(`ubatch <= 8`); prefill-sized batches report only how many experts were copied from the "
        "cache. The counts cover everything the server served (warm-up, every repetition and "
        "attempt), not only clean repetitions."
    )
    A("")
    # ------------------------------------------------------------------ diagnostics
    A("## Excluded diagnostic results")
    A("")
    if res["diagnostics"]:
        drows = [
            [
                d["cell"],
                d["session"],
                str(d["repetition"]),
                str(d["attempt"]),
                ", ".join(d["flags"]),
                "-" if d["t_turn_400_mean"] is None else f"{d['t_turn_400_mean']:.2f}",
                d["why"],
            ]
            for d in res["diagnostics"]
        ]
        L += _table(
            "excluded diagnostic result. " + ban,
            [
                "cell",
                "session",
                "repetition",
                "attempt",
                "flags",
                "T_turn_400 (s), mean over depths",
                "why",
            ],
            drows,
        )
        A(
            "These units are not in any headline number above. Flagged units stay here with their "
            "flags; attempt 1 of a re-run unit is replaced by attempt 2."
        )
    else:
        A("None: no flagged unit and no re-run unit.")
    A("")
    # ------------------------------------------------------------------ appendix
    A("## Appendix: screening data")
    A("")
    A(
        "Screening results (fewer than 5 clean repetitions) are used only for shortlisting and are "
        "never reported as results (§5.5)."
    )
    A("")
    small = [
        c for c in res["cells"].values() if c["n_total"] and c["n_clean"] < labels.MIN_REPORTABLE_N
    ]
    arows = [
        [
            c["name"],
            c["context_label"] or "-",
            _n_cell(c),
            f_stats(c["rep_metrics"]["t_turn_400_mean"]["stats"]),
        ]
        for c in sorted(small, key=lambda c: (c["context"] or 0, c["name"]))
    ]
    if arows:
        L += _table(ban, ["cell", "context", "n_clean/n_total", "T_turn_400 (s)"], arows)
    else:
        A("No cell is below 5 clean repetitions.")
        A("")
    A("## Figures")
    A("")
    for name, (title, _fn) in FIGURES.items():
        A(f"![{title}](figures/{name})")
        A("")
    return scrub_text("\n".join(L).rstrip() + "\n", Identity.current())


def cmd_render(a: argparse.Namespace) -> int:
    res = analysis.analyse(a.sessions)
    sanity = json.loads(a.sanity.read_text()) if a.sanity else None
    command = (
        "python -m smallpc.report render --sessions "
        + " ".join(str(p) for p in a.sessions)
        + f" --out {a.out} --label {a.label}"
    )
    md = render_report(res, a.label, command=command, plan=a.plan or plan_version(), sanity=sanity)
    out = Path(a.out)
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(md)
    for name, svg in render_figures(res, a.label).items():
        (out / "figures" / name).write_text(svg)
    print(f"wrote {out}/report.md and {len(FIGURES)} figures")
    return 0


# ---------------------------------------------------------------------------------- coverage


def cell_coverage(
    spec_path: Path, sessions_paths: list[Path], root: Path | None = None
) -> list[dict]:
    """S1: for every cell the spec expands to, complete / did_not_fit / not_applicable / partial /
    missing, the repetitions by attempt, the clean units and the unresolved flags."""
    spec = load_sweep(spec_path)
    cdefs = sp.expand(spec, root or repo_root())
    res = analysis.analyse(sessions_paths)
    sessions = [analysis.load_session(p) for p in sessions_paths]
    resolutions: dict[str, dict] = {}
    for s in sessions:
        f = s.dir / "resolutions.jsonl"
        if f.exists():
            for line in f.read_text().splitlines():
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                resolutions[o["cell"]] = o
    by_att: dict[str, dict[int, set[int]]] = {}
    for u in res["units"]:
        by_att.setdefault(u["cell"], {}).setdefault(u["attempt"], set()).add(u["repetition"])
    out = []
    for cd in cdefs:
        c = res["cells"].get(cd.name)
        reso = resolutions.get(cd.name)
        reps = by_att.get(cd.name, {})
        final = c["status"] if c else None
        n_done = len({r for rs in reps.values() for r in rs})
        if final == "complete" and n_done >= spec.repetitions:
            state = "complete"
        elif final == "did_not_fit":
            state = "did_not_fit"
        elif final == "not_applicable" or (reso and reso.get("not_applicable") and not final):
            state = "not_applicable"
        elif n_done or final:
            state = "partial"
        else:
            state = "missing"
        reason = (c or {}).get("reason") or ((reso or {}).get("not_applicable"))
        out.append(
            {
                "cell": cd.name,
                "state": state,
                "reason": reason if state in ("did_not_fit", "not_applicable") else None,
                "expected_repetitions": spec.repetitions,
                "repetitions_by_attempt": {str(a): sorted(r) for a, r in sorted(reps.items())},
                "n_clean": c["n_clean"] if c else 0,
                "n_total": c["n_total"] if c else 0,
                "unresolved_flags": c["unit_flags"] if c else [],
                "resolved": (reso or {}).get("fields"),
            }
        )
    return out


def render_coverage(rows: list[dict]) -> str:
    L = ["| cell | state | reason | repetitions by attempt | clean units | unresolved flags |",
         "|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows:
        reps = "; ".join(
            f"a{a}: {','.join(map(str, v))}" for a, v in r["repetitions_by_attempt"].items()
        )
        L.append(
            f"| {r['cell']} | {r['state']} | {r['reason'] or '-'} | {reps or '-'} "
            f"| {r['n_clean']}/{r['n_total']} (of {r['expected_repetitions']}) "
            f"| {', '.join(r['unresolved_flags']) or '-'} |"
        )
    tot = {k: sum(1 for r in rows if r["state"] == k) for k in
           ("complete", "did_not_fit", "not_applicable", "partial", "missing")}  # fmt: skip
    L.append("")
    L.append(
        f"Totals: {len(rows)} cells: "
        + ", ".join(f"{v} {k}" for k, v in tot.items())
        + f"; {sum(1 for r in rows if r['unresolved_flags'])} cell(s) with unresolved flags."
    )
    return "\n".join(L)


def cmd_coverage(a: argparse.Namespace) -> int:
    rows = cell_coverage(a.spec, a.sessions)
    print(render_coverage(rows))
    bad = [r["cell"] for r in rows if r["state"] in ("partial", "missing")]
    if bad:
        print(f"\nS1 NOT satisfied: partial or missing: {', '.join(bad)}", file=sys.stderr)
        return 1
    return 0


# -------------------------------------------------------------------------------------- repro

REPRO_METRICS = (
    ("T_turn_400 (s)", lambda c: c["rep_metrics"]["t_turn_400_mean"]),
    ("fresh prefill 32K (tok/s)", lambda c: c["depth_metrics"].get("32768", {}).get("pp_fresh")),
    ("decode at 32K depth (tok/s)", lambda c: c["depth_metrics"].get("32768", {}).get("tg")),
)
REPRO_REL = 0.05


def repro_check(original: dict, rerun: dict, cells: list[str]) -> list[dict]:
    """S2: each re-measured mean must lie inside the original 95% CI or within 5% of the original
    mean, whichever is wider."""
    rows = []
    for name in cells:
        for metric, get in REPRO_METRICS:
            o = (
                (get(original["cells"][name]) or {}).get("stats")
                if name in original["cells"]
                else None
            )
            r = (get(rerun["cells"][name]) or {}).get("stats") if name in rerun["cells"] else None
            row = {"cell": name, "metric": metric, "original": o, "rerun": r}
            if not o or not r:
                row |= {"pass": False, "lo": None, "hi": None, "why": "missing data"}
            else:
                lo = o["mean"] * (1 - REPRO_REL)
                hi = o["mean"] * (1 + REPRO_REL)
                lo, hi = min(lo, hi), max(lo, hi)
                if o["ci"] is not None:
                    lo, hi = min(lo, o["ci"][0]), max(hi, o["ci"][1])
                row |= {"lo": lo, "hi": hi, "pass": lo <= r["mean"] <= hi, "why": ""}
            rows.append(row)
    return rows


def render_repro(rows: list[dict]) -> str:
    L = ["| cell | metric | original mean [95% CI] | allowed range | re-measured mean | result |",
         "|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows:
        L.append(
            f"| {r['cell']} | {r['metric']} | {f_stats(r['original'], 3)} "
            + ("| - " if r["lo"] is None else f"| [{r['lo']:.3f}, {r['hi']:.3f}] ")
            + f"| {'-' if not r['rerun'] else format(r['rerun']['mean'], '.3f')} "
            + f"| {'PASS' if r['pass'] else 'FAIL' + (' (' + r['why'] + ')' if r['why'] else '')} |"
        )
    return "\n".join(L)


def cmd_repro(a: argparse.Namespace) -> int:
    rows = repro_check(analysis.analyse(a.original), analysis.analyse(a.rerun), a.cells.split(","))
    print(render_repro(rows))
    return 0 if all(r["pass"] for r in rows) else 1


# ------------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.report")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--sessions", nargs="+", required=True, type=Path)
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--label", required=True, choices=labels.LABELS)
    r.add_argument("--sanity", type=Path)
    r.add_argument("--plan", help="plan version to print (default: read from the plan file)")
    c = sub.add_parser("coverage")
    c.add_argument("--spec", required=True, type=Path)
    c.add_argument("--sessions", nargs="+", required=True, type=Path)
    p = sub.add_parser("repro")
    p.add_argument("--original", nargs="+", required=True, type=Path)
    p.add_argument("--rerun", nargs="+", required=True, type=Path)
    p.add_argument("--cells", required=True, help="comma-separated, e.g. stock-64K,tuned-64K")
    a = ap.parse_args(argv)
    return {"render": cmd_render, "coverage": cmd_coverage, "repro": cmd_repro}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
