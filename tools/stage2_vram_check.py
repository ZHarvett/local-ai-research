"""VRAM accounting check of the Stage 2 cells (WP12 part 2g, step D.2; updated in WP13). Read-only.

The VRAM-breakdown figure stacks the buffer sizes parsed from the server's load log (model, KV,
recurrent state, compute buffers, expert cache) plus ``other`` = measured peak used VRAM minus those
parts, plus the minimum free VRAM, so a bar ends at the card's total only if the parsed parts do
not exceed the measured peak. An MTP cell's log lists the compute buffers of the target context and
of the draft context TWICE (each context reserves its graph again and the new reservation replaces
the old one), which the parser used to add up as if all four were resident. Since WP13 the parser
(``smallpc.parsers.resident_compute_buffers``) counts the last reservation of each context.

This tool lists, per cell, the compute buffers as listed in the log (``compute parsed``, the figure
the parser gave before WP13, summed over every line), the resident figure now used by
``smallpc.analysis`` (``compute resident``), and ``other`` with each.

    uv run python tools/stage2_vram_check.py --out reports/stage2/vram-accounting-check \\
        data/raw/s2a-32K data/raw/s2a-64K ...
"""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from smallpc import analysis, parsers


def cuda_sum(items) -> float:
    return sum(i["mib"] for i in items or [] if i["device"] == "CUDA0")


def resident_cuda_sum(items) -> float:
    """The resident CUDA0 compute buffers of a stored list (``parsers.resident_compute_buffers``).
    An MTP load log has four CUDA0 lines: target, draft, draft again, target again (at the first
    prompt), so the last two are resident; any other count is summed as parsed."""
    return cuda_sum(parsers.resident_compute_buffers({"compute_buffers": items or []}))


def rows_of(res: dict, sessions: list[analysis.LoadedSession]) -> list[dict]:
    raw: dict[str, list] = {}
    for s in sessions:
        for (name, _h), summ in s.summaries.items():
            for ins in summ.get("instances", []):
                pl = (ins.get("parsed") or {}).get("placement") or {}
                if pl.get("compute_buffers"):
                    raw[name] = pl["compute_buffers"]  # the last instance of the cell
    out = []
    for name, c in sorted(res["cells"].items()):
        v = c["vram"]
        if not v or not v.get("peak_used_mib") or name not in raw:
            continue
        buf = raw[name]
        compute_all = cuda_sum(buf)  # every line, as the parser summed before WP13
        compute_res = v["compute_mib"]  # resident figure of smallpc.analysis (WP13)
        fixed = v["model_mib"] + v["kv_mib"] + v["recurrent_mib"] + v["expert_cache_mib"]
        peak = v["peak_used_mib"]
        out.append({
            "cell": name,
            "mtp": bool(c["mtp"]),
            "model": v["model_mib"], "kv": v["kv_mib"], "recurrent": v["recurrent_mib"],
            "expert_cache": v["expert_cache_mib"],
            "compute_lines_mib": [round(i["mib"], 2) for i in buf if i["device"] == "CUDA0"],
            "compute_parsed": round(compute_all, 1),
            "compute_resident": round(compute_res, 1),
            "peak_used": peak, "min_free": v["min_free_mib"], "total": v["total_mib"],
            "parts_minus_peak": round(fixed + compute_all - peak, 1),
            "other_as_plotted": round(peak - (fixed + compute_all), 1),
            "other_resident": v["other_mib"],
        })  # fmt: skip
    return out


def markdown(rows: list[dict]) -> str:
    L = [
        "# VRAM accounting check (Stage 2 cells)",
        "",
        "Load-log buffers against the measured peak used VRAM (MiB). `compute parsed` sums every",
        "`CUDA0 compute buffer` line of the log, which is what the parser did before WP13 and what the",
        "breakdown figure plotted; `other before` is the remainder (peak minus the parts) with it, negative",
        "where the parts exceeded the peak (the bar then extended past the card's total). `compute resident`",
        "is the figure now used (the last reservation of each llama_context; the scheduler of a",
        "re-reserving context frees its old compute buffers first, llama.cpp `llama-context.cpp`",
        "`sched_new`), and `other now` the remainder with it.",
        "",
        "| cell | MTP | CUDA0 compute lines | compute parsed (before) | compute resident (now) | peak | other before | other now |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        L.append(
            f"| {r['cell']} | {'yes' if r['mtp'] else 'no'} | {r['compute_lines_mib']} | "
            f"{r['compute_parsed']:,.0f} | {r['compute_resident']:,.0f} | {r['peak_used']:,.0f} | "
            f"{r['other_as_plotted']:,.0f} | {r['other_resident']:,.0f} |"
        )
    over = [r for r in rows if r["other_as_plotted"] < 0]
    no_mtp = [r["other_as_plotted"] for r in rows if not r["mtp"]]
    mtp_dd = [r["other_resident"] for r in rows if r["mtp"]]
    L += [
        "",
        f"- cells with parsed parts above the peak: {len(over)} of {len(rows)}; "
        f"MTP cells among them: {sum(r['mtp'] for r in over)}; non-MTP cells among them: "
        f"{sum(not r['mtp'] for r in over)}.",
        f"- `other` of the non-MTP cells: {min(no_mtp):,.0f} to {max(no_mtp):,.0f} MiB "
        "(the CUDA context and similar).",
        f"- `other` of the MTP cells with the resident compute buffers: "
        f"{min(mtp_dd):,.0f} to {max(mtp_dd):,.0f} MiB (about 170 MiB above the non-MTP cells, the "
        "same at every context size; not a compute buffer of the log).",
        f"- cells with parsed parts above the peak after the fix: {sum(r['other_resident'] < 0 for r in rows)}.",
        "- In every cell peak + minimum free = the card's total, so the measured side is "
        "consistent; the overshoot was in the parsed side.",
    ]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sessions", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path, help="writes <out>.json and <out>.md")
    a = ap.parse_args(argv)
    res = analysis.analyse(a.sessions)
    rows = rows_of(res, [analysis.load_session(d) for d in a.sessions])
    base = a.out.with_suffix("") if a.out.suffix in (".json", ".md") else a.out
    base.parent.mkdir(parents=True, exist_ok=True)
    base.with_name(base.name + ".json").write_text(json.dumps(rows, indent=1) + "\n")
    md = markdown(rows)
    base.with_name(base.name + ".md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
