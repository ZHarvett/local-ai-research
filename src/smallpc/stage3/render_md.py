"""Markdown of the Stage 3 headline result: figures as ``mean [95% CI]``, raw evidence, no adjectives."""

# ruff: noqa: E501
from __future__ import annotations

from ..report import f_stats, kk

DIRECTION = {"t_turn_400": "lower is faster", "t_reread": "lower is faster", "pp_fresh": "higher is faster",
             "tg": "higher is faster", "ttft": "lower is faster"}  # fmt: skip
PER_DEPTH = (
    ("pp_fresh", "PP_fresh (tok/s)", 1),
    ("pp_inc", "PP_inc (tok/s)", 1),
    ("tg", "TG (tok/s)", 2),
    ("t_b", "T_B (s)", 3),
    ("predicted_n", "predicted_n", 1),
    ("t_reread", "T_reread (s)", 3),
    ("ttft", "TTFT (s)", 3),
)


def ratio_cell(r: dict) -> str:
    if r["geomean"] is None:
        return "n/a"
    ci = "" if r["ci"] is None else f" [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}]"
    return f"{r['geomean']:.3f}{ci} (n={r['n_paired']})"


def _ratio_rows(table: dict) -> list[str]:
    rows = [
        "| metric | tuned / stock, geometric mean [95% CI] (paired units) | reading |",
        "|---|---|---|",
    ]
    for k, r in table.items():
        base = k.split("@")[0]
        d = f" at {kk(int(k.split('@')[1]))}" if "@" in k else ""
        rows.append(f"| {base}{d} | {ratio_cell(r)} | {DIRECTION[base]} |")
    return rows


def _cell_block(name: str, f: dict, view: str) -> list[str]:
    L = [
        f"**{name}, {view}**: n_clean {f['n_clean']}, n_total {f['n_total']}; "
        f"T_turn_400 {f_stats(f['t_turn_400'], 3)} s; T_reread {f_stats(f['t_reread'], 3)} s; "
        f"minimum free VRAM {_n(f['min_free_vram_mib'])} MiB; peak VRAM {_n(f['peak_vram_mib'])} MiB; "
        f"MTP acceptance {_acc(f['mtp_acceptance'])}",
        "",
        "| depth | " + " | ".join(lbl for _, lbl, _ in PER_DEPTH) + " |",
        "|---|" + "---|" * len(PER_DEPTH),
    ]
    for d in f["depths"]:
        row = f["per_depth"][str(d)]
        L.append(
            f"| {kk(d)} | " + " | ".join(f_stats(row[m], dig) for m, _, dig in PER_DEPTH) + " |"
        )
    if f["flagged_units"]:
        L += ["", "Units with an unresolved flag (counted in this view): " + "; ".join(
            f"{u['unit']} attempt {u['attempt']}: {', '.join(u['flags'])}"
            + (f", swap growth {u['swap_activity_mib']:.0f} MiB" if u["swap_activity_mib"] is not None else "")
            for u in f["flagged_units"])]  # fmt: skip
    return L + [""]


def _n(v) -> str:
    return "-" if v is None else f"{v:,.0f}"


def _acc(a: dict) -> str:
    if a["pooled_request_b"] is None:
        return "-"
    return (
        f"{a['pooled_request_b']:.3f} pooled over Request B, per unit {f_stats(a['per_unit'], 3)}"
    )


def render(r: dict) -> str:
    L = [f"# {r['title']}", "", f"> **{r['banner']}**", ""]
    # first paragraph: disagreement between the two versions
    if r["disagreeing_contexts"]:
        L.append("**The clean-units and all-units versions disagree** (sign, or one interval excludes 1.0 and the other does not) in: "
                 + ", ".join(r["disagreeing_contexts"]) + ". " + " ".join(
                     r["contexts"][c]["disagreement"]["statement"] for c in r["disagreeing_contexts"]))  # fmt: skip
    else:
        L.append(
            "The clean-units and all-units versions agree in every context (sign, and whether each interval excludes 1.0)."
        )
    if r["human_decision_needed"]:
        L += ["", "**Human decision needed:**"] + [f"- {h}" for h in r["human_decision_needed"]]
    if r["problems"]:
        L += ["", "**Problems:** " + "; ".join(r["problems"])]
    L.append("")
    for ctx, e in r["contexts"].items():
        h, el = e["headline"], e["tuned_eligibility"]
        L += [f"## {ctx}: {e['stock_cell']} and {e['tuned_cell']}", ""]
        if e["disagreement"]["disagree"]:
            L += [e["disagreement"]["statement"], ""]
        L += [
            f"**Tuned cell eligibility (final mode):** {'eligible' if el['eligible'] else 'NOT ELIGIBLE'}; "
            f"n_clean {el['n_clean']} of {el['n_total']}; minimum free VRAM {_n(el['min_free_vram_mib'])} MiB; "
            f"sanity {el['sanity']}" + (f" ({el['sanity_note']})" if el.get("sanity_note") else ""),
        ]
        if el["reasons"]:
            L += [""] + [f"- {x}" for x in el["reasons"]]
        L.append("")
        if h["choice"] is None:
            L += [f"**Headline:** none. {h['note']}", ""]
        elif h["choice"] == "clean":
            L += [f"**Headline: clean units** ({e['paired_clean_units']} clean, paired units).", ""]
            L += _ratio_rows(e["ratios"]["clean"]) + [""]
        else:
            L += [f'**Headline: all units, labelled "{h["label"]}".** {h["deviation"]}', ""]
            L += _ratio_rows(e["ratios"]["all"]) + [""]
            L += ["Clean-units figures beside it:", ""] + _ratio_rows(e["ratios"]["clean"]) + [""]
        if h["choice"] == "clean":
            L += (
                ["Same comparison on all units (flagged units included):", ""]
                + _ratio_rows(e["ratios"]["all"])
                + [""]
            )
        L += ["### Figures", ""]
        for who in ("stock", "tuned"):
            L += _cell_block(e["cells"][who]["name"], e["cells"][who]["clean"], "clean units")
            if (
                e["cells"][who]["all"]["n_clean"] != e["cells"][who]["clean"]["n_clean"]
                or h["choice"] == "all"
            ):
                L += _cell_block(e["cells"][who]["name"], e["cells"][who]["all"], "all units")
        sw = e["swap_sensitivity"]
        L += ["### Swap sensitivity (section 5.5)", "", sw.get("note", "")]
        if sw.get("removed"):
            L += ["", "Removed (swap growth above 64 MiB): " + "; ".join(
                f"{u['cell']} {u['unit']} ({u['swap_activity_mib']:.0f} MiB)" for u in sw["removed"])]  # fmt: skip
        if sw.get("changes"):
            L += [""] + [f"- {c['metric']}: {c['what']}" for c in sw["changes"]]
        L.append("")
    p = r["provenance"]
    L += ["## Provenance", "", f"- plan version: {p['plan_version']}",
          f"- code commit of this tool: {p['code']['commit']} (dirty: {p['code']['dirty']})",
          f"- llama.cpp commit: {p['llama_cpp_commit']}", f"- sanity file: {r['sanity_file']}"]  # fmt: skip
    for s in p["sessions"]:
        L.append(f"- session `{s['session_id']}`: spec `{s['spec_path']}` sha256 {str(s['spec_sha256'])[:16]}, "
                 f"session code commit {str(s['session_git_commit'])[:10]}, state {s['state']}, filters {s['filters']}")  # fmt: skip
    L += [
        f"- config file sha256: {', '.join(f'{k} {v[:12]}' for k, v in p['config_file_sha256'].items())}"
    ]
    if p["eligibility_override"]:
        L += ["- **eligibility override used (unit tests only)**"]
    L += [f"- warning: {w}" for w in p["warnings"]]
    L += ["", "### Rules applied (plan v1.7 section 5.4, verbatim)", ""]
    for text in p["rule_text"].values():
        L += [f"> {text}", ""]
    return "\n".join(L).rstrip() + "\n"
