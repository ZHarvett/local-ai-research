"""Markdown of a Stage 2 decision (the JSON of ``smallpc.stage2.decide`` is the record)."""

# ruff: noqa: E501  (table headers and format strings)
from __future__ import annotations

from typing import Any


def _n(v: Any, fmt: str = "{:,.2f}") -> str:
    return "-" if v is None else fmt.format(v)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out + [""]


def _ci(s: dict | None, nd: int = 3) -> str:
    if not s:
        return "-"
    ci = s.get("ci")
    rng = "-" if not ci else f"[{ci[0]:.{nd}f}, {ci[1]:.{nd}f}]"
    return f"{s['mean']:.{nd}f} {rng}"


def _ratio(r: dict | None) -> str:
    if not r:
        return "-"
    ci = r.get("ci")
    return f"{r['geomean']:.4f}" + ("" if not ci else f" [{ci[0]:.4f}, {ci[1]:.4f}]")


def _diff(d: dict | None) -> str:
    if not d or d.get("mean") is None:
        return "-"
    ci = d.get("ci")
    return f"{d['mean']:+.3f}" + ("" if not ci else f" [{ci[0]:+.3f}, {ci[1]:+.3f}]")


def _cache(c: Any) -> str:
    return "-" if not c else f"{c[0]} / {c[1]:,.0f}"


def _head(res: dict, title: str) -> list[str]:
    out = [f"# {title}", "", f"**{res['banner']}**", ""]
    if res["provenance"].get("eligibility_override"):
        out += ["**Eligibility override used (unit tests only): not a valid decision.**", ""]
    return out


def _human(res: dict) -> list[str]:
    h = res.get("human_decision_needed") or []
    if not h:
        return ["## Human decision needed", "", "None.", ""]
    return ["## Human decision needed", ""] + [f"- {x}" for x in h] + [""]


def _provenance(res: dict) -> list[str]:
    p = res["provenance"]
    out = ["## Provenance", ""]
    rows = [
        [
            s["session_id"],
            s["spec_path"] or "-",
            (s["spec_sha256"] or "-")[:16],
            s["session_git_commit"][:10] if s["session_git_commit"] else "-",
        ]
        for s in p["sessions"]
    ]
    out += _table(["session", "spec", "spec sha256", "session code commit"], rows)
    code = p["code"]
    out += [
        f"- plan version: {p['plan_version']}",
        f"- code commit of this tool: {code.get('commit')} (dirty: {code.get('dirty')})",
        f"- llama.cpp commit: {p['llama_cpp_commit']} (build-info: {p['llama_cpp_build_info_commit']})",
        "",
    ]
    for w in p["warnings"] + res.get("warnings", []):
        out.append(f"- warning: {w}")
    if p["warnings"] or res.get("warnings"):
        out.append("")
    out += ["### Rule text applied (plan v" + p["plan_version"] + ", verbatim)", ""]
    for text in p["rule_text"]:
        out += ["> " + line if line else ">" for line in text.split("\n")] + [""]
    return out


def _render_2f(res: dict) -> list[str]:
    out = _head(res, "Stage 2f decision: host prompt cache (--cache-ram)")
    chosen = res["chosen_cache_ram"]
    out += [
        "## Decision",
        "",
        f"- status: **{res['status']}**",
        f"- chosen `--cache-ram`: **{'default (8192) stays' if res['status'] == 'decided' and chosen is None else chosen}**"
        if res["status"] == "decided"
        else f"- proposed `--cache-ram`: {res['proposed_cache_ram']}",
        f"- reason: {res['reason']}",
        "",
    ]
    out += _human(res)
    for ctx, d in res["contexts"].items():
        out += [f"## {ctx}", "", f"Status **{d['status']}**: {d['reason']}", ""]
        rows = []
        for e in d["values"]:
            rows.append(
                [
                    str(e["cache_ram"]),
                    f"`{e['cell']}`",
                    e["status"],
                    str(e["paging_flagged_repetitions"] or "none"),
                    "yes" if e["paging_clean"] else "no",
                    _ci(e["t_turn_400"]),
                    _n(e["ratio_vs_8192"], "{:.4f}"),
                    {True: "yes", False: "no", None: "-"}[e["rejected_by_3pct"]],
                ]
            )
        out += _table(
            [
                "cache_ram",
                "cell",
                "status",
                "paging-flagged reps",
                "clean",
                "mean T_turn_400 (s) [95% CI]",
                "ratio vs 8192",
                ">3% slower",
            ],
            rows,
        )
        wrows = []
        for e in d["values"]:
            for w in e["windows"]:
                wrows.append(
                    [
                        str(e["cache_ram"]),
                        f"{w['repetition']}/a{w['attempt']}",
                        _n(w["faults"], "{:,.0f}"),
                        "yes" if w["paging_flagged"] else "",
                        _n(w["swap_activity_mib"], "{:,.1f}"),
                        _n(w["rss_anon_growth_mib"], "{:,.0f}"),
                        _cache(w["host_cache_first"]),
                        _cache(w["host_cache_last"]),
                        _n(w["min_free_vram_mib"], "{:,.0f}"),
                        _n(w["t_turn_400"], "{:.3f}"),
                    ]
                )
        out += ["Per window (attempt 1 decides the flag):", ""]
        out += _table(
            [
                "cache_ram",
                "rep/attempt",
                "major faults",
                "paging flag",
                "swap activity (MiB)",
                "RssAnon growth (MiB)",
                "host cache first (prompts / MiB)",
                "host cache last",
                "min free VRAM (MiB)",
                "T_turn_400 (s)",
            ],
            wrows,
        )
    return out + _provenance(res)


def _render_2a(res: dict) -> list[str]:
    out = _head(res, "Stage 2a decision: MTP")
    out += ["Sanity check: " + res["sanity"], ""] + _human(res)
    for ctx, e in res["contexts"].items():
        dl = e["draft_length"]
        out += [f"## {ctx}: top `{e['top']}`, second `{e['second']}`", ""]
        out += [f"- best draft length: **{dl['best_n']}** ({dl['reason']})"]
        m = e.get("mtp_vs_off")
        if m:
            out += [
                f"- MTP against MTP off (same placement): winner `{m['winner']}` by section 3.3 step "
                f"`{m['section_3_3_step']}` ({m['decision_text']}); MTP wins on T_turn_400: "
                f"**{'yes' if m['mtp_wins_on_t_turn_400'] else 'no'}**; paired T_turn_400 difference "
                f"(off minus MTP): {_diff(m['t_turn_400_difference_off_minus_mtp'])} s"
            ]
        out += [
            f"- top placement 2a-best configuration: MTP draft length {e['top_config']['mtp']} (0 = off)",
            "",
        ]
        rows = [
            [str(c["n"]), f"`{c['cell']}`", _n(c["t_turn_400_mean"], "{:.3f}"),
             "-" if not c["vs_best"] else _diff(c["vs_best"]["t_turn_400_difference"]),
             "-" if not c["vs_best"] else _diff(c["vs_best"]["t_reread_difference"]),
             "-" if not c["vs_best"] else ("yes" if c["vs_best"]["distinguishable"] else "no")]
            for c in dl["candidates"]
        ]  # fmt: skip
        out += ["Draft lengths against the best mean (difference: other minus best):", ""]
        out += _table(
            [
                "n",
                "cell",
                "mean T_turn_400 (s)",
                "T_turn_400 diff (CI)",
                "T_reread diff (CI)",
                "distinguishable",
            ],
            rows,
        )
        arows = []
        for n, a in e["acceptance"].items():
            p = a["pooled"]
            arows.append(
                [
                    n,
                    _n(p["B"], "{:.3f}"),
                    _n(p["short"], "{:.3f}"),
                    _n(p["all"], "{:.3f}"),
                    _ci(a["per_repetition"]),
                ]
            )
        out += ["Acceptance (draft_n_accepted / draft_n):", ""]
        out += _table(["n", "Request B", "short point", "all", "per repetition mean [CI]"], arows)
        eff = e.get("effects")
        if eff:
            out += [
                f"Effect of MTP (draft length {dl['best_n']}) against off, paired ratio MTP / off per repetition:",
                "",
            ]
            rows = [["PP_fresh (prefill), pooled", _ratio(eff["pp_fresh"]["pooled"])]]
            rows += [
                [f"PP_fresh at depth {d}", _ratio(r)]
                for d, r in eff["pp_fresh"]["per_depth"].items()
            ]
            rows += [["TG (decode), pooled", _ratio(eff["tg"]["pooled"])]]
            rows += [[f"TG at depth {d}", _ratio(r)] for d, r in eff["tg"]["per_depth"].items()]
            out += _table(["metric", "geometric mean ratio [95% CI]"], rows)
        sp = e["second_placement"]
        out += [
            f"Second placement `{sp['cell']}` (MTP off): eligible {sp['eligible']}, T_turn_400 {_ci(sp['t_turn_400'])} s",
            "",
        ]
        out += [f"2a2 input: `{e['input_2a2']}`", ""]
    return out + _provenance(res)


def _render_2a2(res: dict) -> list[str]:
    out = _head(res, "Stage 2a2 decision: winner and runner-up per context")
    out += ["Sanity check: " + res["sanity"], ""] + _human(res)
    for ctx, e in res["contexts"].items():
        out += [f"## {ctx}", ""]
        if e["status"] != "decided":
            out += ["No eligible cell.", ""]
            continue
        out += [
            f"- winner **`{e['winner']}`**, runner-up `{e['runner_up']}`",
            f"- decided by: {e['decision']['text']}",
            "",
        ]
        rows = [
            [
                f"`{r['cell']}`",
                "yes" if r["eligible"] else "no",
                _ci(r["t_turn_400"]),
                "; ".join(r["reasons"]) or "-",
            ]
            for r in e["rows"]
        ]
        out += _table(["cell", "eligible", "mean T_turn_400 (s) [95% CI]", "reasons"], rows)
        for k, m in e["mtp_vs_off_by_placement"].items():
            out += [
                f"- {k} against MTP off: winner `{m['winner']}` (step `{m['section_3_3_step']}`), "
                f"MTP wins on T_turn_400: {'yes' if m['mtp_wins_on_t_turn_400'] else 'no'}"
            ]
        out += [""]
    return out + _provenance(res)


def _render_pair(res: dict) -> list[str]:
    title = {"2b": "KV type", "2c": "load mode", "2d": "threads"}[res["stage"]]
    out = _head(res, f"Stage {res['stage']} decision: {title}")
    out += ["Sanity check: " + res["sanity"], ""] + _human(res)
    for ctx, e in res["contexts"].items():
        out += [f"## {ctx}", ""]
        v = e.get("verdict")
        out += [
            f"Status **{e['status']}**"
            + (f": winner **`{v['winner']}`** by step `{v['step']}` ({v['reason']})" if v else ""),
            "",
        ]
        rows = [
            [
                f"`{n}`",
                c["setting"],
                "yes" if c["eligible"] else "no",
                _ci(c["t_turn_400"]),
                _ci(c["t_reread"]),
                str(c["n_clean"]),
            ]
            for n, c in e["cells"].items()
        ]
        out += _table(
            [
                "cell",
                "setting",
                "eligible",
                "T_turn_400 (s) [95% CI]",
                "T_reread (s) [95% CI]",
                "clean units",
            ],
            rows,
        )
        if v and "decision" in v:
            d = v["decision"]
            out += [
                f"Paired T_turn_400 difference (other minus best, s): {_diff(d.get('t_turn_400_difference'))}"
            ]
            if d.get("t_reread_difference"):
                out += [f"Paired T_reread difference: {_diff(d['t_reread_difference'])}"]
            out += [""]
        if e.get("effects"):
            out += [e["effects_note"] + ":", ""]
            out += _table(
                ["metric", "geometric mean ratio [95% CI]"],
                [[m, _ratio(r)] for m, r in e["effects"].items()],
            )
        sw = e.get("swap_sensitivity")
        if sw:
            out += ["Swap sensitivity (units with more than 64 MiB of swap growth removed): "
                    f"{'the verdict CHANGES' if sw['changes_the_verdict'] else 'no change'}; removed units: {sw['units_removed'] or 'none'}", ""]  # fmt: skip
        for cell, wins in (e.get("paging") or {}).items():
            out += [f"Paging figures of `{cell}`:", ""]
            rows = [
                [f"{w['repetition']}/a{w['attempt']}", _n(w["faults"], "{:,.0f}"), "yes" if w["paging_flagged"] else "",
                 _n(w["swap_activity_mib"], "{:,.1f}"), _n(w["rss_anon_growth_mib"], "{:,.0f}"), _cache(w["host_cache_last"]),
                 _n(w["min_free_vram_mib"], "{:,.0f}")]
                for w in wins
            ]  # fmt: skip
            out += _table(
                [
                    "rep/attempt",
                    "major faults",
                    "paging flag",
                    "swap activity (MiB)",
                    "RssAnon growth (MiB)",
                    "host cache last",
                    "min free VRAM (MiB)",
                ],
                rows,
            )
    return out + _provenance(res)


def render_markdown(res: dict) -> str:
    if res.get("status") == "skipped":
        body = (
            _head(res, "Stage 2d decision: threads")
            + ["## Decision", "", f"**Skipped.** {res['reason']}", ""]
            + _provenance(res)
        )
    elif res["stage"] == "2f":
        body = _render_2f(res)
    elif res["stage"] == "2a":
        body = _render_2a(res)
    elif res["stage"] == "2a2":
        body = _render_2a2(res)
    else:
        body = _render_pair(res)
    return "\n".join(body).rstrip("\n") + "\n"
