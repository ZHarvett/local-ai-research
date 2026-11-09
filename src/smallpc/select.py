"""Eligibility and selection of step plan section 3.3 (docs/decisions.md, WP10 decisions 2 to 4).

    python -m smallpc.select --mode screening|final --sessions DIR... [--sanity FILE.json]
        [--label functional-test|screening|results] [--out-json F] [--out-md F]

Eligibility (every cell gets a line with the reasons it failed):

* its final cell status is ``complete``;
* the minimum of ``windows[*].min_free_vram_mib`` over its final-attempt windows is at least 512;
* it has no flagged unit once attempts are resolved (and no drift flag);
* ``n_clean`` meets the minimum of the mode: 2 in screening, 5 in final;
* it has not failed the output sanity check: ``pass``, ``fail`` or ``not run``; ``not run`` is
  allowed in screening, in final mode it must be ``pass``.

Stock cells are reference rows: never shortlisted, never selected.

Final selection (reading of the section 3.3 tie-break, decision 3): order eligible cells of a
context by mean T_turn_400; compare the best with the runner-up by the paired per-repetition
difference (wider of the bootstrap and t CI). CI excludes zero: the best wins. Otherwise the paired
T_reread difference: if its CI excludes zero the lower mean T_reread wins; else "still tied": prefer
no MTP, then no expert cache, then the lower peak VRAM use. Further eligible cells whose paired
T_turn_400 difference from the winner has a CI including zero are listed as "statistically tied
with the winner" (information only).

Screening shortlist (decision 4): no tie-break at n = 2. The 2 eligible cells with the lowest mean
T_turn_400 per context; pairs in the top 4 whose means differ by less than the larger of the two
ranges are flagged "too close to call at n = 2".
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from . import analysis, labels, stats

MIN_FREE_VRAM_MIB = 512
MIN_CLEAN = {"screening": 2, "final": 5}
SANITY_STATES = ("pass", "fail", "not run")
TOO_CLOSE = "too close to call at n = 2"


# ------------------------------------------------------------------------------- eligibility


def sanity_state(name: str, sanity: dict | None) -> str:
    """``pass``, ``fail`` or ``not run`` for a cell. ``sanity`` is ``{cell: state}`` or
    ``{"cells": {cell: state-or-{"result": state}}}`` (the shape of ``sanity.check_candidate``)."""
    if not sanity:
        return "not run"
    table = sanity.get("cells", sanity)
    v = table.get(name)
    if isinstance(v, dict):
        v = v.get("result")
    return v if v in SANITY_STATES else "not run"


def mean_tt(cell: dict) -> float | None:
    s = cell["rep_metrics"]["t_turn_400_mean"]["stats"]
    return None if s is None else s["mean"]


def eligibility(cell: dict, mode: str, sanity: dict | None = None) -> dict:
    """Is the cell eligible for selection in this mode, and if not, why not (all reasons)."""
    reasons = []
    st = cell["status"]
    if st != "complete":
        why = f" ({cell['reason']})" if cell.get("reason") else ""
        reasons.append(f"final status is {st or 'missing'}{why}, not complete")
    free = cell["min_free_vram_mib"]
    if free is None:
        reasons.append("no VRAM measurement (no final-attempt window)")
    elif free < MIN_FREE_VRAM_MIB:
        reasons.append(f"minimum free VRAM {free:g} MiB is below {MIN_FREE_VRAM_MIB}")
    if cell["flagged_units"]:
        fl = ", ".join(cell["unit_flags"])
        reasons.append(f"flagged unit(s) {', '.join(cell['flagged_units'])} ({fl})")
    need = MIN_CLEAN[mode]
    if cell["n_clean"] < need:
        reasons.append(f"n_clean {cell['n_clean']} is below {need} ({mode} mode)")
    san = sanity_state(cell["name"], sanity)
    if san == "fail":
        reasons.append("failed the output sanity check")
    elif san == "not run" and mode == "final":
        reasons.append("output sanity check not run (must pass in final mode)")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "sanity": san,
        "n_clean": cell["n_clean"],
        "n_total": cell["n_total"],
        "min_free_vram_mib": free,
    }


def _by_context(res: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for c in res["cells"].values():
        if c["context_label"]:
            out.setdefault(c["context_label"], []).append(c)
    return dict(sorted(out.items(), key=lambda kv: min(c["context"] or 0 for c in kv[1])))


def _row(cell: dict, el: dict) -> dict:
    s = cell["rep_metrics"]["t_turn_400_mean"]["stats"]
    r = cell["rep_metrics"]["t_reread_mean"]["stats"]
    return {
        "cell": cell["name"],
        "profile": cell["profile"],
        "reference": cell["profile"] == "stock",
        "status": cell["status"],
        "n_clean": cell["n_clean"],
        "n_total": cell["n_total"],
        "t_turn_400": s,
        "t_reread": r,
        "range": None if s is None else s["max"] - s["min"],
        "eligible": el["eligible"],
        "reasons": el["reasons"],
        "sanity": el["sanity"],
        "mtp": cell["mtp"],
        "cache_mib": cell["cache_mib"],
        "peak_vram_mib": cell["peak_vram_mib"],
        "flags": cell["unit_flags"],
    }


def _vram_cache(cell: dict) -> dict:
    return {
        "vram": cell["vram"],
        "min_free_vram_mib": cell["min_free_vram_mib"],
        "cache": {
            "present": cell["cache"]["present"],
            "decode_hit_rate_pct": cell["cache"]["decode_hit_rate_pct"],
            "classes": cell["cache"]["classes"],
            "large_batch_copies": cell["cache"]["large_batch_copies"],
        },
    }


# ------------------------------------------------------------------------------- screening


def select_screening(res: dict, sanity: dict | None = None) -> dict:
    out: dict = {"mode": "screening", "min_clean": MIN_CLEAN["screening"], "contexts": {}}
    for ctx, cells in _by_context(res).items():
        rows = [_row(c, eligibility(c, "screening", sanity)) for c in cells]
        cand = sorted(
            (r for r in rows if r["eligible"] and not r["reference"]),
            key=lambda r: (r["t_turn_400"]["mean"], r["cell"]),
        )
        top4 = cand[:4]
        close = []
        for a, b in itertools.combinations(top4, 2):
            diff = abs(a["t_turn_400"]["mean"] - b["t_turn_400"]["mean"])
            lim = max(a["range"], b["range"])
            if diff < lim:
                close.append(
                    {
                        "cells": [a["cell"], b["cell"]],
                        "mean_difference": diff,
                        "larger_range": lim,
                        "note": TOO_CLOSE,
                    }  # fmt: skip
                )
        short = [r["cell"] for r in cand[:2]]
        by_name = {c["name"]: c for c in cells}
        out["contexts"][ctx] = {
            "rows": rows,
            "ranking": [r["cell"] for r in cand],
            "shortlist": short,
            "too_close": close,
            "stock": next((r["cell"] for r in rows if r["reference"]), None),
            "details": {n: _vram_cache(by_name[n]) for n in short},
        }
    return out


# ----------------------------------------------------------------------------------- final


def _paired(a: dict, b: dict, metric: str) -> dict:
    """Paired difference b - a of a per-repetition metric (positive: a is faster / lower)."""
    d = stats.paired_difference(
        b["rep_metrics"][metric]["values"], a["rep_metrics"][metric]["values"]
    )
    return {k: v for k, v in d.items() if k not in ("differences",)} | {
        "differences": d["differences"]
    }


def _tie_break(best: dict, runner: dict) -> tuple[dict, dict, dict]:
    """(winner, loser, decision) for the best-mean cell against the runner-up."""
    c1 = _paired(best, runner, "t_turn_400_mean")
    decision: dict = {"t_turn_400_difference": c1}
    if c1["excludes_zero"]:
        decision["step"] = "ci_excludes_zero"
        decision["text"] = "the paired T_turn_400 CI excludes zero: the best mean wins"
        if (c1["mean"] or 0) < 0:
            decision["note"] = "paired mean points the other way (the cells share few repetitions)"
        return best, runner, decision
    if c1["n"] == 0:
        decision["note"] = "no shared repetitions: the comparison is unpaired and not decisive"
    c2 = _paired(best, runner, "t_reread_mean")
    decision["t_reread_difference"] = c2
    if c2["excludes_zero"]:
        lo = min((best, runner), key=lambda c: c["rep_metrics"]["t_reread_mean"]["stats"]["mean"])
        win, lose = (best, runner) if lo is best else (runner, best)
        decision["step"] = "t_reread"
        decision["text"] = (
            "T_turn_400 tied; the paired T_reread CI excludes zero: lower T_reread wins"
        )
        return win, lose, decision
    # still tied: fewer moving parts, then VRAM
    if best["mtp"] != runner["mtp"]:
        win, lose = (runner, best) if best["mtp"] else (best, runner)
        decision["step"] = "no_mtp"
        decision["text"] = "still tied; prefer no MTP"
        return win, lose, decision
    if bool(best["cache_mib"]) != bool(runner["cache_mib"]):
        win, lose = (runner, best) if best["cache_mib"] else (best, runner)
        decision["step"] = "no_cache"
        decision["text"] = "still tied; prefer no expert cache"
        return win, lose, decision
    inf = float("inf")
    pb, pr = best["peak_vram_mib"] or inf, runner["peak_vram_mib"] or inf
    if pb != pr:
        win, lose = (best, runner) if pb < pr else (runner, best)
        decision["step"] = "peak_vram"
        decision["text"] = "still tied, same MTP and cache status; prefer the lower peak VRAM use"
        return win, lose, decision
    decision["step"] = "name"
    decision["text"] = "complete tie; the cell name order decides (deterministic, not a finding)"
    win, lose = sorted((best, runner), key=lambda c: c["name"])
    return win, lose, decision


def select_final(res: dict, sanity: dict | None = None) -> dict:
    out: dict = {"mode": "final", "min_clean": MIN_CLEAN["final"], "contexts": {}}
    for ctx, cells in _by_context(res).items():
        rows = [_row(c, eligibility(c, "final", sanity)) for c in cells]
        by_name = {c["name"]: c for c in cells}
        cand = sorted(
            (r for r in rows if r["eligible"] and not r["reference"]),
            key=lambda r: (r["t_turn_400"]["mean"], r["cell"]),
        )
        entry: dict = {
            "rows": rows,
            "ranking": [r["cell"] for r in cand],
            "stock": next((r["cell"] for r in rows if r["reference"]), None),
            "winner": None,
            "runner_up": None,
            "decision": None,
            "tied_with_winner": [],
        }
        if len(cand) == 1:
            entry["winner"] = cand[0]["cell"]
            entry["decision"] = {"step": "only_eligible", "text": "the only eligible cell"}
        elif len(cand) >= 2:
            win, lose, dec = _tie_break(by_name[cand[0]["cell"]], by_name[cand[1]["cell"]])
            entry["winner"], entry["runner_up"], entry["decision"] = win["name"], lose["name"], dec
            for r in cand[2:]:
                d = _paired(win, by_name[r["cell"]], "t_turn_400_mean")
                entry["tied_with_winner"].append(
                    {
                        "cell": r["cell"],
                        "paired_difference_mean": d["mean"],
                        "ci": d["ci"],
                        "tied": d["excludes_zero"] is False,
                        "comparable": d["n"] >= 2,
                    }
                )
        if entry["winner"]:
            entry["details"] = {
                n: _vram_cache(by_name[n])
                for n in (entry["winner"], entry["runner_up"])
                if n is not None
            }
        out["contexts"][ctx] = entry
    return out


# ------------------------------------------------------------------------------- Markdown


def _fmt(s: dict | None, digits: int = 2) -> str:
    if s is None:
        return "-"
    txt = f"{s['mean']:.{digits}f}"
    if s["ci"] is not None:
        txt += f" [{s['ci'][0]:.{digits}f}, {s['ci'][1]:.{digits}f}]"
    return txt


def render_markdown(result: dict, label: str | None = None) -> str:
    mode = result["mode"]
    L: list[str] = []
    ban = labels.banner(label)
    L.append(f"# Eligibility and {'screening shortlist' if mode == 'screening' else 'selection'}")
    L.append("")
    if ban:
        L += [f"> **{ban}**", ""]
    L.append(
        f"Mode **{mode}**: a cell needs at least {result['min_clean']} clean repetitions, a "
        f"complete status, at least {MIN_FREE_VRAM_MIB} MiB free VRAM at its tightest, no flagged "
        "unit and a sanity check that has not failed"
        + (" (and must pass)." if mode == "final" else " (`not run` is allowed).")
    )
    L.append("")
    for ctx, c in result["contexts"].items():
        L.append(f"## {ctx}")
        L.append("")
        if ban:
            L += [f"> {ban}", ""]
        L.append(
            "| cell | role | n_clean/n_total | mean T_turn_400 (s) [95% CI] | eligible | "
            "reasons it is not | sanity |"
        )
        L.append("|---|---|---|---|---|---|---|")
        for r in c["rows"]:
            role = "reference (stock)" if r["reference"] else "candidate"
            fl = f" flags: {', '.join(r['flags'])}" if r["flags"] and not r["reasons"] else ""
            L.append(
                f"| {r['cell']} | {role} | {r['n_clean']}/{r['n_total']} | {_fmt(r['t_turn_400'])} "
                f"| {'yes' if r['eligible'] else 'no'} "
                f"| {'; '.join(r['reasons']) or '-'}{fl} | {r['sanity']} |"
            )
        L.append("")
        if mode == "screening":
            sl = c["shortlist"]
            L.append(
                f"**Shortlist ({ctx}):** {', '.join(f'`{n}`' for n in sl) if sl else 'none'}"
                + (f" (only {len(sl)} eligible cell)" if len(sl) == 1 else "")
                + (f". Reference: `{c['stock']}` (never shortlisted)." if c["stock"] else ".")
            )
            L.append("")
            if len(c["ranking"]) > 1:
                L.append(
                    "Ranking by mean T_turn_400: " + " < ".join(f"`{n}`" for n in c["ranking"])
                )
                L.append("")
            for p in c["too_close"]:
                L.append(
                    f"- `{p['cells'][0]}` and `{p['cells'][1]}`: {p['note']} (means differ by "
                    f"{p['mean_difference']:.3f} s, larger range {p['larger_range']:.3f} s)."
                )
            if c["too_close"]:
                L.append("")
            if not c["ranking"]:
                L.append("No eligible candidate in this context.")
                L.append("")
        else:
            if c["winner"] is None:
                L.append("**No eligible candidate**: no tuned configuration for this context.")
                L.append("")
            else:
                dec = c["decision"]
                L.append(f"**Winner ({ctx}):** `{c['winner']}`. Decision: {dec['text']}.")
                if c["runner_up"]:
                    L.append(f"Runner-up: `{c['runner_up']}`.")
                for k, name in (
                    ("t_turn_400_difference", "T_turn_400"),
                    ("t_reread_difference", "T_reread"),
                ):
                    d = dec.get(k)
                    if d and d["ci"] is not None:
                        L.append(
                            f"- paired {name} difference (runner-up minus best mean), "
                            f"n = {d['n']}: "
                            f"{d['mean']:.3f} s, CI [{d['ci'][0]:.3f}, {d['ci'][1]:.3f}] "
                            f"({d['ci_method']})."
                        )
                    elif d:
                        L.append(f"- paired {name} difference: not available (n = {d['n']}).")
                if dec.get("note"):
                    L.append(f"- note: {dec['note']}.")
                L.append("")
                for t in c["tied_with_winner"]:
                    if t["tied"]:
                        L.append(
                            f"- `{t['cell']}`: statistically tied with the winner (paired "
                            "T_turn_400 difference, CI includes zero; information only)."
                        )
                    elif not t["comparable"]:
                        L.append(f"- `{t['cell']}`: not comparable with the winner (no pairs).")
                L.append("")
        for name, d in c.get("details", {}).items():
            v = d["vram"] or {}
            hit = d["cache"]["decode_hit_rate_pct"]
            other = v.get("other_mib")
            L.append(
                f"- `{name}`: VRAM model {v.get('model_mib', 0):.0f}, KV {v.get('kv_mib', 0):.0f}, "
                f"recurrent {v.get('recurrent_mib', 0):.0f}, "
                f"compute {v.get('compute_mib', 0):.0f}, "
                f"other {'-' if other is None else other} MiB; "
                f"minimum free {d['min_free_vram_mib']} MiB; expert-cache decode-batch hit rate "
                f"{'-' if hit is None else f'{hit:.1f}%'}."
            )
        if c.get("details"):
            L.append("")
    return "\n".join(L).rstrip() + "\n"


# ------------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.select")
    ap.add_argument("--mode", choices=["screening", "final"], required=True)
    ap.add_argument("--sessions", nargs="+", required=True, type=Path)
    ap.add_argument("--sanity", type=Path, help="JSON: {cell: pass|fail|not run}")
    ap.add_argument("--label", choices=labels.LABELS)
    ap.add_argument("--out-json", type=Path)
    ap.add_argument("--out-md", type=Path)
    a = ap.parse_args(argv)
    res = analysis.analyse(a.sessions)
    sanity = json.loads(a.sanity.read_text()) if a.sanity else None
    result = (select_screening if a.mode == "screening" else select_final)(res, sanity)
    md = render_markdown(result, a.label)
    out_json = a.out_json or Path(f"data/analysis/select-{a.mode}.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=1) + "\n")
    if a.out_md:
        a.out_md.parent.mkdir(parents=True, exist_ok=True)
        a.out_md.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
