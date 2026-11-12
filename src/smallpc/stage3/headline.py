"""The Stage 3 headline tables under the rules of plan v1.7 section 5.4.

``headline(paths, sanity, ...)`` returns one JSON-serialisable object; ``render_md.render`` writes
the Markdown. Per context (a stock cell and a tuned cell of one session):

* the tuned cell's eligibility in final mode (``smallpc.select.eligibility``), with its reasons;
  if it is not eligible nothing is substituted and a human decision is requested;
* both cells' figures in both views (clean units only, and all units with the flags listed);
* the paired ratios tuned / stock in both views;
* the headline choice by the headline rule, the disagreement statement, the swap sensitivity.
"""

# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import analysis, labels, select
from ..config import repo_root
from ..report import _ci_moved
from ..stage2 import eligibility
from . import rules, views

SCHEMA = 1
DEPTH_METRICS = ("pp_fresh", "pp_inc", "tg", "t_turn_400", "t_b", "predicted_n", "t_reread", "ttft")


# ---------------------------------------------------------------------------- cell figures


def cell_figures(cell: dict, flagged: list[dict]) -> dict:
    """The reported figures of one cell in one view (``mean [95% CI]`` blocks from ``stats``)."""
    acc = cell["acceptance_pooled"]
    return {
        "n_clean": cell["n_clean"],
        "n_total": cell["n_total"],
        "status": cell["status"],
        "t_turn_400": views.trimmed(cell["rep_metrics"]["t_turn_400_mean"]["stats"]),
        "t_reread": views.trimmed(cell["rep_metrics"]["t_reread_mean"]["stats"]),
        "depths": cell["depths"],
        "per_depth": {
            str(d): {
                m: views.trimmed(cell["depth_metrics"][str(d)][m]["stats"]) for m in DEPTH_METRICS
            }
            for d in cell["depths"]
        },
        "min_free_vram_mib": cell["min_free_vram_mib"],
        "peak_vram_mib": cell["peak_vram_mib"],
        "vram": cell["vram"],
        "mtp_acceptance": {
            "per_unit": views.trimmed(cell["rep_metrics"]["acceptance"]["stats"]),
            "pooled_request_b": acc["B"],
        },
        "flagged_units": flagged,
    }


def flagged_units(data: views.Data, cell: str) -> list[dict]:
    return [
        {
            "unit": u["key"],
            "repetition": u["repetition"],
            "attempt": u["attempt"],
            "flags": list(u["reasons"]),
            "swap_activity_mib": u["swap_activity_mib"],
        }
        for u in data.units
        if u["cell"] == cell and not u["superseded"] and not u["clean"]
    ]


# ---------------------------------------------------------------------------- sanity


def sanity_for(cell_name: str, sanity: dict | None, root: Path) -> tuple[dict | None, str | None]:
    """The ``select.eligibility`` sanity input for a tuned cell and a note. The sanity file of the
    tuned config files is keyed by file stem (``tuned-32k``); the entry's ``config_sha256`` must be
    the hash of the file as it is now."""
    if not sanity:
        return None, "no sanity file given"
    table = sanity.get("cells", sanity)
    stem = cell_name.lower()
    entry = table.get(cell_name) or table.get(stem)
    if entry is None:
        return {"cells": {cell_name: "not run"}}, f"no entry for {stem!r} in the sanity file"
    state = entry.get("result") if isinstance(entry, dict) else entry
    note = None
    cfg = root / "configs/server" / f"{stem}.toml"
    sha = entry.get("config_sha256") if isinstance(entry, dict) else None
    if sha and cfg.exists() and hashlib.sha256(cfg.read_bytes()).hexdigest() != sha:
        state, note = "not run", f"the sanity run was on a different version of {cfg.name}"
    return {"cells": {cell_name: {"result": state}}}, note


# ---------------------------------------------------------------------------- one context


def context_entry(data: views.Data, ctx: str, stock: dict, tuned: dict, all_cells: dict,
                  sanity: dict | None, root: Path) -> dict:  # fmt: skip
    s_all, t_all = all_cells[stock["name"]], all_cells[tuned["name"]]
    san, san_note = sanity_for(tuned["name"], sanity, root)
    el = select.eligibility(tuned, "final", san)
    cells = {
        "stock": {
            "name": stock["name"],
            "clean": cell_figures(stock, []),
            "all": cell_figures(s_all, flagged_units(data, stock["name"])),
        },
        "tuned": {
            "name": tuned["name"],
            "clean": cell_figures(tuned, []),
            "all": cell_figures(t_all, flagged_units(data, tuned["name"])),
        },
    }
    r_clean, r_all = views.ratios(tuned, stock), views.ratios(t_all, s_all)
    paired_clean = len(r_clean["t_turn_400"]["keys"])
    stock_ok = stock["status"] == "complete"
    use_clean = (
        stock_ok
        and stock["n_clean"] >= rules.MIN_CLEAN_PAIRED
        and tuned["n_clean"] >= rules.MIN_CLEAN_PAIRED
        and paired_clean >= rules.MIN_CLEAN_PAIRED
    )
    entry: dict = {
        "context": ctx,
        "stock_cell": stock["name"],
        "tuned_cell": tuned["name"],
        "tuned_eligibility": {**el, "sanity_note": san_note},
        "stock_status": stock["status"],
        "cells": cells,
        "ratios": {"clean": _ratio_table(r_clean), "all": _ratio_table(r_all)},
        "paired_clean_units": paired_clean,
        "human_decision_needed": [],
    }
    if not el["eligible"]:
        entry["human_decision_needed"].append(
            f"{tuned['name']} is not eligible in final mode ({'; '.join(el['reasons'])}): the step "
            "lead decides, nothing is substituted"
        )
    if not stock_ok:
        entry["human_decision_needed"].append(
            f"{stock['name']} has final status {stock['status']!r}, not complete"
        )
    # headline choice
    if not el["eligible"] or not stock_ok:
        entry["headline"] = {"choice": None, "label": None, "deviation": None,
                             "note": "no headline for this context (see the human decision)"}  # fmt: skip
    elif use_clean:
        entry["headline"] = {"choice": "clean", "label": None, "deviation": None, "note": None}
    else:
        lifted = flagged_units(data, stock["name"])
        entry["headline"] = {
            "choice": "all",
            "label": rules.STOCK_LABEL,
            "deviation": (
                f"S4(d) deviation for this context: the headline rests on {len(lifted)} stock "
                f"unit(s) with an unresolved flag ({_unit_flags(lifted)}) because "
                f"{stock['name']} has {stock['n_clean']} clean and {tuned['name']} "
                f"{tuned['n_clean']} clean unit(s) ({paired_clean} paired; at least "
                f"{rules.MIN_CLEAN_PAIRED} needed for the clean-units headline). "
                f"Rule S4(d): {rules.s4d_text()}"
            ),
            "note": "the clean-units figures are shown beside it",
        }
    dis = views.disagreements(r_clean, r_all)
    entry["disagreement"] = {
        "disagree": bool(dis),
        "items": dis,
        "statement": _disagree_text(tuned["name"], stock["name"], dis),
    }
    entry["swap_sensitivity"] = _swap_sensitivity(data, entry, stock, tuned)
    return entry


def _unit_flags(units: list[dict]) -> str:
    return "; ".join(f"{u['unit']}: {', '.join(u['flags'])}" for u in units) or "none"


def _ratio_table(r: dict) -> dict:
    return {k: views.slim(v) | {"keys": v["keys"]} for k, v in r.items()}


def _fmt_ci(r: dict) -> str:
    if r["geomean"] is None:
        return "n/a"
    ci = "" if r["ci"] is None else f" [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]"
    return f"{r['geomean']:.3f}{ci}"


def _disagree_text(tuned: str, stock: str, items: list[dict]) -> str:
    if not items:
        return "The clean-units and all-units versions agree in sign and in whether each interval excludes 1.0."
    parts = []
    for i in items:
        kinds = " and ".join(
            {"sign": "sign", "interval": "whether the interval excludes 1.0"}[k] for k in i["kinds"]
        )
        parts.append(
            f"{i['metric']} (clean {_fmt_ci(i['a'])}, all units {_fmt_ci(i['b'])}; they differ in {kinds})"
        )
    return (
        f"The clean-units and all-units versions of {tuned} / {stock} DISAGREE: "
        + "; ".join(parts)
        + "."
    )


# ---------------------------------------------------------------------------- swap sensitivity


def _swap_sensitivity(data: views.Data, entry: dict, stock: dict, tuned: dict) -> dict:
    """Section 5.5: the headline ratios again without the units whose window shows more than
    64 MiB of swap growth. Fewer than 2 paired units left: inconclusive."""
    ch = entry["headline"]["choice"]
    if ch is None:
        return {"computed": False, "note": "no headline for this context"}
    names = [stock["name"], tuned["name"]]
    base_units = data.lifted() if ch == "all" else data.units

    def heavy(u: dict) -> bool:
        swap = u["swap_activity_mib"]
        return swap is not None and swap > analysis.SWAP_HEAVY_MIB

    removed = [
        {"unit": u["key"], "cell": u["cell"], "swap_activity_mib": u["swap_activity_mib"],
         "flags": list(u["reasons"])}
        for u in base_units
        if u["cell"] in names and not u["superseded"] and (ch == "all" or u["clean"]) and not u["problems"] and heavy(u)
    ]  # fmt: skip
    unavailable = [
        u["key"] for u in base_units
        if u["cell"] in names and not u["superseded"] and u["swap_activity_mib"] is None
    ]  # fmt: skip
    if not removed:
        return {"computed": True, "removed": [], "unavailable_units": unavailable, "changes": [],
                "inconclusive": False, "paired_units_left": entry["ratios"][ch]["t_turn_400"]["n_paired"],
                "note": "no unit of these cells shows swap growth above 64 MiB: nothing to remove"}  # fmt: skip
    alt = data.without(base_units, heavy, names)
    r1 = views.ratios(alt[tuned["name"]], alt[stock["name"]])
    r0 = entry["ratios"][ch]
    left = r1["t_turn_400"]["n_paired"]
    changes = []
    for k, a in r0.items():
        b = r1[k]
        if a["geomean"] is None:
            continue
        if b["geomean"] is None:
            changes.append({"metric": k, "what": "no pairs left"})
            continue
        if views.sign_of(a["geomean"]) != views.sign_of(b["geomean"]):
            changes.append({"metric": k, "what": f"sign: {_fmt_ci(a)} -> {_fmt_ci(b)}"})
        elif a["ci"] is not None and _ci_moved(a["ci"], b["ci"]):
            changes.append({"metric": k, "what": f"interval moved: {_fmt_ci(a)} -> {_fmt_ci(b)}"})
    inconclusive = left < 2
    return {
        "computed": True,
        "removed": removed,
        "unavailable_units": unavailable,
        "paired_units_left": left,
        "inconclusive": inconclusive,
        "changes": [] if inconclusive else changes,
        "ratios_without": _ratio_table(r1),
        "note": (
            f"inconclusive: {left} paired unit(s) left, fewer than 2" if inconclusive
            else ("headline comparison changes: " + "; ".join(c['metric'] for c in changes)
                  if changes else "no sign change and no interval moved by more than its half-width")
        ),
    }  # fmt: skip


# ---------------------------------------------------------------------------- the whole thing


def provenance(checks: list[dict], root: Path, override_used: bool) -> dict:
    files = sorted((root / "configs/server").glob("stock-*k.toml"))
    files += sorted((root / "configs/server").glob("tuned-*k.toml"))
    cfg_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return {
        "sessions": [
            {
                "session_id": c["session_id"],
                "spec_path": c["spec_path"],
                "spec_sha256": c["spec_sha256"],
                "spec_file_matches": c["spec_file_matches"],
                "session_git_commit": c["git_commit"],
                "state": c["state"],
                "filters": c["filters"],
            }
            for c in checks
        ],
        "warnings": [w for c in checks for w in c["warnings"]],
        "plan_version": rules.plan_version(root),
        "code": eligibility.git_state(root),
        "llama_cpp_commit": next(
            (c["llama_cpp_commit"] for c in checks if c["llama_cpp_commit"]), None
        ),
        "config_file_sha256": cfg_hashes,
        "rule_text": rules.stage_rules(root),
        "eligibility_override": override_used,
    }


def headline(
    paths: list[Path],
    sanity: dict | None = None,
    sanity_path: str | None = None,
    *,
    root: Path | None = None,
    allow_ineligible: bool = False,
) -> dict:
    """Refuses (``eligibility.Refused``) a session recorded with ``allow_dirty``, with a
    functional-test id or spec header, or not complete. ``allow_ineligible`` is for unit tests."""
    root = Path(root) if root else repo_root()
    checks, override = eligibility.check_sessions([Path(p) for p in paths], root, allow_ineligible)
    data = views.Data(paths)
    cells = data.res["cells"]
    by_ctx: dict[str, dict[str, dict]] = {}
    for c in cells.values():
        ctx = c["context_label"]
        if ctx and c["profile"] in ("stock", "tuned"):
            by_ctx.setdefault(ctx, {})[c["profile"]] = c
    order = sorted(by_ctx, key=lambda k: min(c["context"] or 0 for c in by_ctx[k].values()))
    all_cells = data.all_cells()
    contexts, problems = {}, []
    for ctx in order:
        pair = by_ctx[ctx]
        if "stock" not in pair or "tuned" not in pair:
            problems.append(f"{ctx}: needs one stock and one tuned cell, found {sorted(pair)}")
            continue
        contexts[ctx] = context_entry(
            data, ctx, pair["stock"], pair["tuned"], all_cells, sanity, root
        )
    disagree = [c for c, e in contexts.items() if e["disagreement"]["disagree"]]
    return {
        "schema": SCHEMA,
        "label": "results",
        "banner": labels.banner("results"),
        "title": "Stage 3 headline: stock against tuned (plan v1.7 section 5.4)",
        "problems": problems,
        "disagreeing_contexts": disagree,
        "human_decision_needed": [h for e in contexts.values() for h in e["human_decision_needed"]],
        "contexts": contexts,
        "sanity_file": sanity_path,
        "provenance": provenance(checks, root, override),
    }


def write_outputs(result: dict, out: Path) -> tuple[Path, Path]:
    from .render_md import render

    base = out.with_suffix("") if out.suffix in (".json", ".md") else out
    base.parent.mkdir(parents=True, exist_ok=True)
    j, m = base.with_name(base.name + ".json"), base.with_name(base.name + ".md")
    j.write_text(json.dumps(result, indent=1, default=str) + "\n")
    m.write_text(render(result))
    return j, m
