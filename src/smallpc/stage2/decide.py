"""The decision tool of Stage 2 (plan v1.6 section 5.4): applies the declared rules to session data.

``python -m smallpc.stage2 decide --stage 2f|2a|2a2|2b|2c|2d --sessions <dirs...> --out <json+md>``

Built on ``smallpc.analysis`` (units, cells, swap sensitivity), ``smallpc.select`` (eligibility
and the section 3.3 tie-break) and ``smallpc.stats`` (paired differences and ratios); none of it
is reimplemented here. Interpretations of the plan text that the plan leaves open are in
``docs/decisions.md`` ("WP12 decisions"); every output names the rule it applied and records its
provenance (sessions, spec hashes, plan version, code commit, llama.cpp commit, the rule text).

Output ``status`` of ``2f``: ``decided`` (``chosen_cache_ram``: a size in MiB, or null when the
default stays), ``needs_human`` (the contexts disagree; ``proposed_cache_ram``),
``no_automatic_decision`` or ``stop``. Every other stage reports its verdicts per context.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .. import analysis, hostcache, labels, select, stats
from ..config import repo_root
from . import eligibility as el
from .shortlist import Shortlist, load_shortlist

CRAM_DEFAULT = 8192
REPETITIONS = 5
TOLERANCE_2F = 0.03  # "more than 3% above the mean of the 8192 cell's clean units"
MTP_DRAFT = "draft-mtp"
STAGES = ("2f", "2a", "2a2", "2b", "2c", "2d")
CacheLookup = Callable[[analysis.LoadedSession, dict], list]


# ------------------------------------------------------------------------------------ helpers


def pending_sanity(res: dict) -> dict:
    """The sanity state used before the sanity check has run: every cell assumed to pass (the check
    runs after 2a on the winners), so the section 3.3 eligibility is judged on everything else. The
    outputs say "sanity pending"."""
    return {"cells": {n: "pass" for n in res["cells"]}}


def draft_n(cell: dict) -> int:
    """The draft length of a cell (0 = MTP off), from its resolved config."""
    r = cell["resolved"]
    if r.get("spec_type") != MTP_DRAFT:
        return 0
    return int(r.get("spec_draft_n_max") or 0)


def _elig(cell: dict, res: dict) -> dict:
    return select.eligibility(cell, "final", pending_sanity(res))


def _mean(cell: dict) -> float | None:
    s = cell["rep_metrics"]["t_turn_400_mean"]["stats"]
    return None if s is None else s["mean"]


def _round(x: Any, nd: int = 4) -> Any:
    return round(x, nd) if isinstance(x, float) else x


def _stat(cell: dict, metric: str) -> dict | None:
    s = cell["rep_metrics"].get(metric, {}).get("stats")
    return None if s is None else {k: s[k] for k in ("n", "mean", "min", "max", "ci")}


def _diff(d: dict) -> dict:
    """A ``select._paired`` / ``stats.paired_difference`` result without the per-key lists."""
    return {k: d[k] for k in ("n", "mean", "ci", "ci_method", "excludes_zero") if k in d} | {
        "differences": d.get("differences")
    }


def _ratio(a: dict | None, b: dict | None) -> dict | None:
    """Paired ratio a / b of two ``{key: value}`` series (None if they share fewer than 2 keys)."""
    if not a or not b:
        return None
    keys = sorted(set(a) & set(b))
    if len(keys) < 2:
        return None
    r = stats.paired_ratio({k: a[k] for k in keys}, {k: b[k] for k in keys})
    return {k: r[k] for k in ("n", "geomean", "ci", "ci_method")}


def _unit_means(res: dict, cell: str, metric: str) -> dict[str, float]:
    """Per clean final unit of a cell, the mean over its depths of a per-depth metric."""
    out = {}
    for u in res["units"]:
        if u["cell"] != cell or u["superseded"] or not u["clean"]:
            continue
        vals = [m[metric] for m in u["metrics"].values() if m.get(metric) is not None]
        if vals and len(vals) == len(u["metrics"]):
            out[u["key"]] = sum(vals) / len(vals)
    return out


def _by_context(res: dict) -> dict[str, list[dict]]:
    return select._by_context(res)


def _coord(cell: dict, key: str) -> str | None:
    return (cell.get("coords") or {}).get(key)


# ------------------------------------------------------------------------------- 2f windows


def _default_cache_lookup(logs_root: Path) -> CacheLookup:
    def lookup(sess: analysis.LoadedSession, ins: dict) -> list:
        run_id = ins.get("run_id")
        if not run_id:
            return []
        return hostcache.cache_series(sess.requests, run_id, logs_root / run_id / "server.log")

    return lookup


def cell_windows(
    sessions: dict[str, analysis.LoadedSession], res: dict, cell: str, lookup: CacheLookup
) -> list[dict]:
    """The measured windows of a cell with the figures 2f needs: faults, the paging flag, swap
    activity, RssAnon growth, host prompt cache size (first and last save in the window) and the
    minimum free VRAM, with the unit's T_turn_400."""
    tt = {
        (u["session"], u["cell"], u["repetition"], u["attempt"]): u["rep"]["t_turn_400_mean"]
        for u in res["units"]
    }
    out = []
    for sid, sess in sessions.items():
        for (name, _h), summ in sess.summaries.items():
            if name != cell or summ.get("role") != "measured":
                continue
            for ins in summ.get("instances", []):
                cache = lookup(sess, ins)
                for w in ins.get("windows", []):
                    paging = w.get("paging") or {}
                    a0, a1 = w.get("rss_anon_start_mib"), w.get("rss_anon_end_mib")
                    first = last = None
                    if w.get("t0_epoch") is not None and w.get("t1_epoch") is not None:
                        first, last = hostcache.cache_in_window(cache, w["t0_epoch"], w["t1_epoch"])
                    out.append(
                        {
                            "session": sid,
                            "repetition": w["repetition"],
                            "attempt": w["attempt"],
                            "faults": paging.get("major_faults"),
                            "paging_flagged": "paging" in (w.get("flags") or []),
                            "swap_activity_mib": w.get("swap_activity_mib"),
                            "rss_anon_growth_mib": None if a0 is None or a1 is None else a1 - a0,
                            "host_cache_first": first,
                            "host_cache_last": last,
                            "min_free_vram_mib": w.get("min_free_vram_mib"),
                            "t_turn_400": tt.get((sid, cell, w["repetition"], w["attempt"])),
                        }
                    )
    return sorted(out, key=lambda w: (w["attempt"], w["repetition"]))


# ------------------------------------------------------------------------------------- 2f


def _value_entry(cell: dict, windows: list[dict]) -> dict:
    a1 = [w for w in windows if w["attempt"] == 1]
    flagged = [w["repetition"] for w in a1 if w["paging_flagged"]]
    complete = cell["status"] == "complete" and len({w["repetition"] for w in a1}) >= REPETITIONS
    why = None
    if cell["status"] != "complete":
        why = f"cell status is {cell['status']}, not complete"
    elif not complete:
        why = f"only {len(a1)} attempt-1 windows of {REPETITIONS}"
    return {
        "cache_ram": cell["resolved"].get("cache_ram"),
        "cell": cell["name"],
        "status": cell["status"],
        "windows_attempt1": len(a1),
        "paging_flagged_repetitions": flagged,
        "paging_clean": complete and not flagged,
        "not_clean_because": why
        or (f"paging flag in repetition(s) {flagged}" if flagged else None),
        "n_clean_units": cell["n_clean"],
        "t_turn_400_mean": _mean(cell),
        "t_turn_400": _stat(cell, "t_turn_400_mean"),
        "ratio_vs_8192": None,
        "rejected_by_3pct": None,
        "windows": windows,
    }


def decide_context_2f(entries: list[dict]) -> dict:
    """The 2f rule for one context (plan text in ``rules.RULE_2F``)."""
    vals = sorted(entries, key=lambda e: -e["cache_ram"])
    base = next((e for e in vals if e["cache_ram"] == CRAM_DEFAULT), None)
    out: dict = {"values": vals, "chosen": None, "status": None, "reason": None}
    if base is None:
        out.update(
            status="no_automatic_decision", reason="this context has no 8192 cell to compare with"
        )
        return out
    if base["paging_clean"]:
        out.update(
            status="decided",
            chosen=CRAM_DEFAULT,
            reason="the 8192 cell has no paging-flagged window in any of its 5 repetitions: "
            "the default stays",
        )
        return out
    clean = [e for e in vals if e["cache_ram"] < CRAM_DEFAULT and e["paging_clean"]]
    if not clean:
        out.update(
            status="stop",
            reason="no tested value is clean (8192: "
            f"{base['not_clean_because']}): STOP and report; the cause is then not the host cache",
        )
        return out
    base_mean = base["t_turn_400_mean"]
    if base_mean is None:
        out.update(
            status="no_automatic_decision",
            reason="the 8192 cell has no clean unit, so the 3% condition cannot be evaluated; "
            f"clean values: {[e['cache_ram'] for e in clean]}. A human decides",
        )
        return out
    for e in clean:
        if e["t_turn_400_mean"] is None:
            out.update(
                status="no_automatic_decision",
                reason=f"the clean value {e['cache_ram']} has no clean unit with a T_turn_400",
            )
            return out
        e["ratio_vs_8192"] = e["t_turn_400_mean"] / base_mean
        e["rejected_by_3pct"] = e["ratio_vs_8192"] > 1 + TOLERANCE_2F
    chosen = next((e for e in clean if not e["rejected_by_3pct"]), None)
    if chosen is None:
        out.update(
            status="no_automatic_decision",
            reason="every clean value is more than 3% slower than the 8192 cell's clean units "
            f"({[(e['cache_ram'], round(e['ratio_vs_8192'], 4)) for e in clean]}); a human decides",
        )
        return out
    skipped = [
        e["cache_ram"]
        for e in clean
        if e["rejected_by_3pct"] and e["cache_ram"] > chosen["cache_ram"]
    ]
    out.update(
        status="decided",
        chosen=chosen["cache_ram"],
        reason=f"{chosen['cache_ram']} is the largest tested value with no paging-flagged window "
        f"and its mean T_turn_400 is {100 * (chosen['ratio_vs_8192'] - 1):+.2f}% against the "
        "8192 cell's clean units (limit +3%)"
        + (f"; larger clean values {skipped} were more than 3% slower" if skipped else ""),
    )
    return out


def decide_2f(res: dict, sessions: dict, lookup: CacheLookup) -> dict:
    by_ctx: dict[str, list[dict]] = {}
    warnings = []
    for c in res["cells"].values():
        if c["profile"] == "stock" or c["resolved"].get("cache_ram") is None:
            continue
        w = cell_windows(sessions, res, c["name"], lookup)
        if any(x["attempt"] > 1 for x in w):
            warnings.append(
                f"{c['name']} has attempt-2 windows (a re-run): the paging flag is read from "
                "attempt 1 only, T_turn_400 from the final units"
            )
        by_ctx.setdefault(c["context_label"] or "?", []).append(_value_entry(c, w))
    if not by_ctx:
        raise ValueError("no cell with an explicit cache_ram in these sessions: not a 2f session")
    contexts = {ctx: decide_context_2f(v) for ctx, v in sorted(by_ctx.items())}
    status, chosen, proposed, human, reason = _combine_2f(contexts)
    return {
        "stage": "2f",
        "status": status,
        "chosen_cache_ram": chosen,
        "proposed_cache_ram": proposed,
        "reason": reason,
        "human_decision_needed": human,
        "contexts": contexts,
        "warnings": warnings,
    }


def _combine_2f(contexts: dict) -> tuple[str, int | None, int | None, list[str], str]:
    stops = [c for c, d in contexts.items() if d["status"] == "stop"]
    if stops:
        why = f"{', '.join(stops)}: " + "; ".join(contexts[c]["reason"] for c in stops)
        return "stop", None, None, [f"2f stop: {why}"], why
    manual = [c for c, d in contexts.items() if d["status"] == "no_automatic_decision"]
    if manual:
        why = "; ".join(f"{c}: {contexts[c]['reason']}" for c in manual)
        return "no_automatic_decision", None, None, [f"2f no automatic decision: {why}"], why
    values = {c: d["chosen"] for c, d in contexts.items()}
    low = min(values.values())
    if len(set(values.values())) > 1:
        why = (
            f"the contexts choose different values {values}; the plan does not say how to combine "
            f"them. Proposed: the smallest, {low}. A human confirms"
        )
        return "needs_human", None, low, [f"2f combined value: {why}"], why
    chosen = None if low == CRAM_DEFAULT else low
    why = f"every context chooses {low}: " + (
        "the default (8192) stays" if chosen is None else f"{low} MiB is used from here on"
    )
    return "decided", chosen, low, [], why


# ------------------------------------------------------------------------------------- 2a


def _pair_text(d: dict) -> str:
    if d["n"] < 2 or d["ci"] is None:
        return f"n = {d['n']}: no interval"
    return f"{_round(d['mean'], 3):+} s, 95% CI [{d['ci'][0]:.3f}, {d['ci'][1]:.3f}]"


def best_draft_length(cells_by_n: dict[int, dict]) -> dict:
    """The best draft length among eligible MTP cells (plan text ``rules.RULE_2A``): the best-mean
    cell wins unless other cells are not distinguishable from it by section 3.3 steps 1 and 2
    (the paired T_turn_400 CI and the paired T_reread CI both include zero); then the smallest
    such draft length wins."""
    if not cells_by_n:
        return {"best_n": None, "reason": "no eligible MTP cell", "candidates": []}
    ranked = sorted(cells_by_n.items(), key=lambda kv: (_mean(kv[1]), kv[0]))
    best_n, best = ranked[0]
    rows = [{"n": best_n, "cell": best["name"], "t_turn_400_mean": _mean(best), "vs_best": None}]
    tied = [best_n]
    human = []
    for n, c in ranked[1:]:
        c1 = select._paired(best, c, "t_turn_400_mean")
        c2 = select._paired(best, c, "t_reread_mean")
        t1, t2 = bool(c1["excludes_zero"]), bool(c2["excludes_zero"])
        rows.append(
            {
                "n": n,
                "cell": c["name"],
                "t_turn_400_mean": _mean(c),
                "vs_best": {
                    "t_turn_400_difference": _diff(c1),
                    "t_reread_difference": _diff(c2),
                    "distinguishable": t1 or t2,
                    "step": "1 (T_turn_400)" if t1 else ("2 (T_reread)" if t2 else None),
                },
            }
        )
        if not (t1 or t2):
            tied.append(n)
        elif not t1 and t2:
            lo = min((best, c), key=lambda x: x["rep_metrics"]["t_reread_mean"]["stats"]["mean"])
            if lo is c:
                human.append(
                    f"section 3.3 step 2 would prefer draft length {n} (lower T_reread) over the "
                    f"best-mean draft length {best_n}; the rule applied here keeps {best_n}"
                )
    chosen = min(tied)
    if len(tied) == 1:
        why = (
            f"draft length {chosen} has the best mean T_turn_400 and the others are distinguishable"
        )
    else:
        why = (
            f"draft lengths {sorted(tied)} are not distinguishable from the best mean "
            f"(draft length {best_n}) by section 3.3 steps 1 and 2: the smallest wins"
        )
    return {"best_n": chosen, "best_mean_n": best_n, "tied": sorted(tied), "reason": why,
            "candidates": rows, "human_decision_needed": human}  # fmt: skip


def _mtp_vs_off(mtp: dict, off: dict) -> dict:
    """MTP against the same placement with MTP off by section 3.3. MTP joins only if it wins on
    T_turn_400 (step 1)."""
    a, b = (mtp, off) if _mean(mtp) <= _mean(off) else (off, mtp)
    win, lose, dec = select._tie_break(a, b)
    joins = win["name"] == mtp["name"] and dec["step"] == "ci_excludes_zero"
    return {
        "mtp_cell": mtp["name"],
        "off_cell": off["name"],
        "winner": win["name"],
        "section_3_3_step": dec["step"],
        "decision_text": dec["text"],
        "mtp_wins_on_t_turn_400": joins,
        "t_turn_400_difference_off_minus_mtp": _diff(select._paired(mtp, off, "t_turn_400_mean")),
        "t_reread_difference_off_minus_mtp": _diff(select._paired(mtp, off, "t_reread_mean")),
        "mtp_t_turn_400_mean": _mean(mtp),
        "off_t_turn_400_mean": _mean(off),
    }


def _depth_mean(cell: dict, depth: str, metric: str) -> float | None:
    st = cell["depth_metrics"][depth][metric]["stats"]
    return None if st is None else st["mean"]


def _mtp_effects(res: dict, mtp: dict, off: dict) -> dict:
    """Prefill and decode effect of MTP: paired ratios (MTP / off) per repetition, pooled over the
    depths and per depth, of PP_fresh (prefill) and TG (decode)."""
    out: dict = {}
    depths = sorted(set(mtp["depth_metrics"]) & set(off["depth_metrics"]), key=int)
    for metric in ("pp_fresh", "tg"):
        out[metric] = {
            "pooled": _ratio(
                _unit_means(res, mtp["name"], metric), _unit_means(res, off["name"], metric)
            ),
            "per_depth": {
                d: _ratio(
                    mtp["depth_metrics"][d][metric]["values"],
                    off["depth_metrics"][d][metric]["values"],
                )
                for d in depths
            },
            "mtp_mean": {d: _depth_mean(mtp, d, metric) for d in mtp["depth_metrics"]},
            "off_mean": {d: _depth_mean(off, d, metric) for d in off["depth_metrics"]},
        }
    return out


def _borrow_draft_lengths(contexts: dict[str, dict]) -> None:
    """Declared rule (docs/decisions.md, "Stage 2a decisions", item 3): when a context's top
    placement has no eligible MTP cell (no best draft length), 2a2 tests that context's second
    placement at every draft length that is the best of another context, and the anchor is the top
    placement with MTP off (``top_mtp`` is already 0 then). Fills ``input_2a2`` for every context:
    ``best_n`` (None when none), ``borrowed_draft_lengths`` and ``second_mtps`` (the draft lengths
    the second placement is tested at, besides MTP off). If no context has a best draft length
    there is nothing to borrow: a human decision."""
    bests = {c: e["draft_length"]["best_n"] for c, e in contexts.items()}
    for ctx, e in contexts.items():
        inp = e["input_2a2"]
        own = bests[ctx]
        if own is not None:
            inp.update(best_n=own, best_n_reason=None, borrowed_draft_lengths=[], second_mtps=[own])
            continue
        borrowed = sorted({n for c, n in bests.items() if c != ctx and n is not None})
        inp.update(
            best_n=None,
            best_n_reason="no eligible MTP cell",
            borrowed_draft_lengths=borrowed,
            second_mtps=borrowed,
        )
        e["borrowed_draft_lengths"] = borrowed
        if not borrowed:
            e["human_decision_needed"].append(
                "no eligible MTP cell in any context: there is no draft length to borrow for "
                "the second placement"
            )


def decide_2a(res: dict, root: Path, sl: Shortlist) -> dict:
    contexts: dict[str, dict] = {}
    for ctx, cells in _by_context(res).items():
        if ctx not in sl.contexts:
            continue
        top, second = sl.top(ctx), sl.second(ctx)
        of_top = {draft_n(c): c for c in cells if _coord(c, "placement") == top.placement}
        of_second = {draft_n(c): c for c in cells if _coord(c, "placement") == second.placement}
        elig = {c["name"]: _elig(c, res) for c in cells}
        eligible_mtp = {n: c for n, c in of_top.items() if n > 0 and elig[c["name"]]["eligible"]}
        choice = best_draft_length(eligible_mtp)
        off = of_top.get(0)
        entry: dict = {
            "top": top.cell,
            "second": second.cell,
            "eligibility": {
                n: {"eligible": e["eligible"], "reasons": e["reasons"], "sanity": "pending"}
                for n, e in elig.items()
            },
            "draft_length": choice,
            "human_decision_needed": list(choice.get("human_decision_needed", [])),
        }
        entry["acceptance"] = {
            str(n): {
                "pooled": c["acceptance_pooled"],
                "per_repetition": _stat(c, "acceptance"),
            }
            for n, c in sorted(of_top.items())
            if n > 0
        }
        top_n = 0
        if off is None or not elig[off["name"]]["eligible"]:
            entry["mtp_vs_off"] = None
            entry["human_decision_needed"].append(
                f"{top.cell}: the MTP-off cell is missing or not eligible, so MTP cannot "
                "be compared"
            )
        elif choice["best_n"] is not None:
            best = of_top[choice["best_n"]]
            entry["mtp_vs_off"] = _mtp_vs_off(best, off)
            entry["effects"] = _mtp_effects(res, best, off)
            top_n = choice["best_n"] if entry["mtp_vs_off"]["mtp_wins_on_t_turn_400"] else 0
            entry["effects_all_draft_lengths"] = {
                str(n): _mtp_effects(res, c, off) for n, c in sorted(eligible_mtp.items())
            }
            alt = res["swap_alt"]["cells"]
            if best["name"] in alt and off["name"] in alt:
                entry["mtp_vs_off_without_heavy_swap_units"] = _mtp_vs_off(
                    alt[best["name"]], alt[off["name"]]
                )
        else:
            entry["mtp_vs_off"] = None
        entry["top_config"] = {
            "mtp": top_n,
            "cell": (of_top[top_n]["name"] if top_n in of_top else None),
        }
        sec_off = of_second.get(0)
        entry["second_placement"] = {
            "cell": sec_off["name"] if sec_off else None,
            "eligible": bool(sec_off and elig[sec_off["name"]]["eligible"]),
            "t_turn_400": None if not sec_off else _stat(sec_off, "t_turn_400_mean"),
        }
        entry["input_2a2"] = {
            "top_cell": top.cell,
            "second_cell": second.cell,
            "top_mtp": top_n,
            "second_mtp": choice["best_n"],
        }
        contexts[ctx] = entry
    if not contexts:
        raise ValueError(
            "no cell of these sessions matches the shortlisted placements: not a 2a session"
        )
    _borrow_draft_lengths(contexts)
    human = [f"{c}: {m}" for c, e in contexts.items() for m in e["human_decision_needed"]]
    return {"stage": "2a", "contexts": contexts, "human_decision_needed": human,
            "sanity": "pending: the check runs after 2a, on the winners"}  # fmt: skip


# ------------------------------------------------------------------------------------- 2a2


def decide_2a2(res: dict, root: Path) -> dict:
    sanity = pending_sanity(res)
    final = select.select_final(res, sanity)
    contexts: dict[str, dict] = {}
    winners: dict[str, dict] = {}
    runners: dict[str, dict] = {}
    for ctx, e in final["contexts"].items():
        cells = {c["name"]: c for c in _by_context(res)[ctx]}
        if not e["winner"]:
            contexts[ctx] = {"status": "no_eligible_cell", "rows": e["rows"]}
            continue

        def info(name: str, cells=cells, ctx=ctx) -> dict:
            c = cells[name]
            return {"cell": name, "placement": _coord(c, "placement"), "batch": _coord(c, "batch"),
                    "context": ctx, "mtp": draft_n(c)}  # fmt: skip

        winners[ctx] = info(e["winner"])
        if e["runner_up"]:
            runners[ctx] = info(e["runner_up"])
        by_place: dict[str, dict[int, dict]] = {}
        for c in cells.values():
            by_place.setdefault(_coord(c, "placement") or "?", {})[draft_n(c)] = c
        verdicts = {}
        for place, byn in by_place.items():
            off = byn.get(0)
            for n, c in sorted(byn.items()):
                if n and off and _elig(c, res)["eligible"] and _elig(off, res)["eligible"]:
                    verdicts[f"{place}-mtp{n}"] = _mtp_vs_off(c, off)
        contexts[ctx] = {
            "status": "decided",
            "winner": e["winner"],
            "runner_up": e["runner_up"],
            "decision": e["decision"],
            "tied_with_winner": e["tied_with_winner"],
            "ranking": e["ranking"],
            "rows": e["rows"],
            "mtp_vs_off_by_placement": verdicts,
            "anchor_present": any(
                _coord(c, "placement") is not None and c["name"] != e["winner"]
                for c in cells.values()
            ),
        }
    human = [f"{c}: no eligible cell" for c, d in contexts.items() if d["status"] != "decided"]
    return {"stage": "2a2", "contexts": contexts, "winners": winners, "runners_up": runners,
            "human_decision_needed": human,
            "sanity": "pending: the check runs on the winners and runners-up next"}  # fmt: skip


# ------------------------------------------------------------------------ 2b, 2c, 2d


def _setting(stage: str, cell: dict) -> str:
    r = cell["resolved"]
    if stage == "2b":
        return {"f16": "FP16 KV (-ctk f16 -ctv f16)"}.get(r.get("cache_type_k"), "8-bit KV (q8_0)")
    if stage == "2c":
        return f"--load-mode {r.get('load_mode', 'default')}"
    return f"-t {r['threads']}" if r.get("threads") else "default threads"


def _pair_verdict(a: dict, b: dict) -> dict:
    """Section 3.3 between two cells: the best-mean cell against the other, with the step that
    decided and the supporting paired figures."""
    best, other = (a, b) if _mean(a) <= _mean(b) else (b, a)
    win, lose, dec = select._tie_break(best, other)
    return {
        "winner": win["name"],
        "loser": lose["name"],
        "step": dec["step"],
        "reason": dec["text"],
        "decision": _clean_decision(dec),
    }


def _clean_decision(dec: dict) -> dict:
    out = {
        k: v for k, v in dec.items() if k not in ("t_turn_400_difference", "t_reread_difference")
    }
    for k in ("t_turn_400_difference", "t_reread_difference"):
        if k in dec:
            out[k] = _diff(dec[k])
    return out


def _pair_cell(stage: str, cell: dict, elig: dict) -> dict:
    return {
        "setting": _setting(stage, cell),
        "eligible": elig["eligible"],
        "reasons": elig["reasons"],
        "t_turn_400": _stat(cell, "t_turn_400_mean"),
        "t_reread": _stat(cell, "t_reread_mean"),
        "n_clean": cell["n_clean"],
    }


def decide_pair(stage: str, res: dict, sessions: dict, lookup: CacheLookup) -> dict:
    contexts: dict[str, dict] = {}
    for ctx, cells in _by_context(res).items():
        cells = [c for c in cells if c["profile"] != "stock"]
        if len(cells) != 2:
            raise ValueError(f"{stage}: context {ctx} has {len(cells)} cells, expected exactly 2")
        a, b = sorted(cells, key=lambda c: c["name"])
        elig = {c["name"]: _elig(c, res) for c in (a, b)}
        ok = [c for c in (a, b) if elig[c["name"]]["eligible"]]
        entry: dict = {
            "cells": {c["name"]: _pair_cell(stage, c, elig[c["name"]]) for c in (a, b)},
            "sanity": "pending",
            "human_decision_needed": [],
        }
        if len(ok) == 2:
            v = _pair_verdict(a, b)
            entry["verdict"] = v
            entry["status"] = "decided"
            entry["effects"] = {
                m: _ratio(_unit_means(res, a["name"], m), _unit_means(res, b["name"], m))
                for m in ("pp_fresh", "tg", "t_turn_400")
            }
            entry["effects_note"] = f"paired ratios {a['name']} / {b['name']}"
            alt = res["swap_alt"]["cells"]
            if (
                a["name"] in alt
                and b["name"] in alt
                and _mean(alt[a["name"]]) is not None
                and _mean(alt[b["name"]]) is not None
            ):
                v2 = _pair_verdict(alt[a["name"]], alt[b["name"]])
                d1, d2 = (
                    v["decision"].get("t_turn_400_difference"),
                    v2["decision"].get("t_turn_400_difference"),
                )

                def sign(d):
                    return None if not d or d["mean"] is None else d["mean"] > 0

                changed = (
                    v2["winner"] != v["winner"] or v2["step"] != v["step"] or sign(d1) != sign(d2)
                )
                # step lead's reading (Stage 2b decision): fewer than 2 paired units left means
                # the recomputation has no paired CI; it is inconclusive and cannot overturn
                paired_n = (d2 or {}).get("n")
                inconclusive = paired_n is None or paired_n < 2
                entry["swap_sensitivity"] = {
                    "units_removed": [
                        u for u in res["swap_alt"]["removed"] if u["cell"] in (a["name"], b["name"])
                    ],
                    "without_heavy_swap_units": v2,
                    "paired_units_left": paired_n,
                    "inconclusive": inconclusive,
                    "changes_the_verdict": changed and not inconclusive,
                }
                if inconclusive:
                    entry["swap_sensitivity"]["note"] = (
                        f"inconclusive: {paired_n or 0} paired unit(s) left, fewer than 2; "
                        "it cannot overturn the rule's verdict"
                        + (f" (the recomputed winner would be {v2['winner']})" if changed else "")
                    )
                if changed and not inconclusive:
                    entry["human_decision_needed"].append(
                        "the verdict changes when units with more than 64 MiB of swap growth "
                        "are removed"
                    )
            else:
                entry["swap_sensitivity"] = {
                    "units_removed": [],
                    "changes_the_verdict": False,
                    "note": "a cell has no clean unit left without the heavy-swap units",
                }
        elif len(ok) == 1:
            entry["status"] = "only_one_eligible"
            entry["verdict"] = {"winner": ok[0]["name"], "step": "only_eligible",
                                "reason": "the other cell is not eligible"}  # fmt: skip
            entry["human_decision_needed"].append(
                f"only {ok[0]['name']} is eligible: "
                + "; ".join(
                    f"{n}: {', '.join(e['reasons'])}" for n, e in elig.items() if not e["eligible"]
                )
            )
        else:
            entry["status"] = "no_eligible_cell"
            entry["verdict"] = None
            entry["human_decision_needed"].append("neither cell is eligible")
        if stage == "2c":
            entry["paging"] = {
                c["name"]: cell_windows(sessions, res, c["name"], lookup) for c in (a, b)
            }
        contexts[ctx] = entry
    human = [f"{c}: {m}" for c, e in contexts.items() for m in e["human_decision_needed"]]
    return {"stage": stage, "contexts": contexts, "human_decision_needed": human,
            "sanity": "pending: the check runs on the winners next"}  # fmt: skip


def decide_2d_skipped(
    default_threads: int,
    *,
    root: Path | None = None,
    label: str = "results",
    git: Callable[[Path | None], dict] = el.git_state,
) -> dict:
    """2d is skipped and recorded when the default thread count equals the explicit ``-t 8``."""
    if default_threads != 8:
        raise ValueError("2d is skipped only when the default thread count is 8")
    out = {
        "stage": "2d",
        "status": "skipped",
        "reason": f"the default thread count is {default_threads}, the same as -t 8: "
        "2d is not needed",
        "human_decision_needed": [],
        "contexts": {},
        "label": label,
        "banner": labels.banner(label),
        "provenance": el.provenance("2d", [], root, git=git),
    }
    return out


def write_outputs(res: dict, out: Path) -> tuple[Path, Path]:
    """Write ``<out>.json`` and ``<out>.md`` (``out`` may end in .json or .md); a 2a result also
    writes ``<out>-2a2-input.json``, the file the 2a2 spec generator reads."""
    from .decide_md import render_markdown

    base = out.with_suffix("") if out.suffix in (".json", ".md") else out
    base.parent.mkdir(parents=True, exist_ok=True)
    jpath, mpath = base.with_name(base.name + ".json"), base.with_name(base.name + ".md")
    jpath.write_text(json.dumps(res, indent=1) + "\n")
    mpath.write_text(render_markdown(res))
    if res["stage"] == "2a":
        sub = {
            "stage": "2a",
            "contexts": {c: {"input_2a2": e["input_2a2"]} for c, e in res["contexts"].items()},
            "provenance": res["provenance"],
        }
        base.with_name(base.name + "-2a2-input.json").write_text(json.dumps(sub, indent=1) + "\n")
    return jpath, mpath


# ---------------------------------------------------------------------------------- driver


def decide(
    stage: str,
    session_dirs: list[Path],
    *,
    root: Path | None = None,
    allow_ineligible: bool = False,
    label: str = "results",
    logs_root: Path | None = None,
    git: Callable[[Path | None], dict] = el.git_state,
    cache_lookup: CacheLookup | None = None,
) -> dict:
    """Apply the rules of ``stage`` to the sessions. Raises ``eligibility.Refused`` for sessions
    that may not drive a decision."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    root = Path(root) if root else repo_root()
    dirs = [Path(d) for d in session_dirs]
    checks, override = el.check_sessions(dirs, root, allow_ineligible)
    prov = el.provenance(stage, checks, root, override_used=override, git=git)
    res = analysis.analyse(dirs)
    sessions = {s.id: s for s in (analysis.load_session(d) for d in dirs)}
    logs = (
        Path(logs_root)
        if logs_root
        else Path(os.environ.get("SMALLPC_LOG_ROOT", root / "data/logs"))
    )
    lookup = cache_lookup or _default_cache_lookup(logs)
    if stage == "2f":
        out = decide_2f(res, sessions, lookup)
    elif stage == "2a":
        out = decide_2a(res, root, load_shortlist(root))
    elif stage == "2a2":
        out = decide_2a2(res, root)
    else:
        out = decide_pair(stage, res, sessions, lookup)
    out["label"] = label
    out["banner"] = labels.banner(label)
    out["provenance"] = prov
    out["analysis_warnings"] = [w for c in res["cells"].values() for w in c.get("warnings", [])]
    return json.loads(json.dumps(out, default=_json_default))


def _json_default(o: Any) -> Any:
    if isinstance(o, set | tuple):
        return list(o)
    raise TypeError(f"{type(o)} is not JSON serializable")
