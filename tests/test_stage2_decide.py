"""The Stage 2 decision tool on fixture sessions: every branch of the rules, the refusals, the
provenance (WP12). Fixture sessions come from ``tests/fixture_session.py``; no GPU, no server."""

from __future__ import annotations

import json
import subprocess

import pytest

from conftest import REPO
from fixture_session import CellSpec, RepSpec, build_session
from smallpc.stage2 import cli, decide, eligibility, rules, specgen
from smallpc.stage2.decide_md import render_markdown

K = {"32K": 32768, "64K": 65536, "128K": 131072}
FAKE_GIT = {"commit": "c0ffee" * 6 + "abcd", "dirty": False}


def fake_git(_root):
    return dict(FAKE_GIT)


def run(stage, dirs, **kw):
    return decide.decide(stage, dirs, root=REPO, git=fake_git, **kw)


# ------------------------------------------------------------------------------ 2f fixtures


def reps2f(flagged=(), faults_bad=1500, anon=(1200.0, 3300.0), slow=1.0):
    return [
        RepSpec(
            i,
            flags=("paging",) if i in flagged else (),
            faults=faults_bad if i in flagged else 40,
            anon_mib=anon,
            slow=slow,
        )
        for i in range(5)
    ]


def cell_2f(ctx, value, *, flagged=(), tg=80.0, status="complete", **kw):
    name = f"s2f-P2-{ctx}-b4096-mtp0-cram{value}"
    return CellSpec(
        name=name, context=K[ctx], placement="P2", batch="b4096", tg=tg, status=status,
        reps=reps2f(flagged) if status == "complete" else None,
        extra={"cache_ram": value}, **kw,
    )  # fmt: skip


def session_2f(tmp_path, spec, sid="s2f"):
    """spec: {ctx: {value: dict(flagged=..., tg=...)}}"""
    cells = [cell_2f(ctx, v, **kw) for ctx, vals in spec.items() for v, kw in vals.items()]
    return build_session(tmp_path, sid, cells)


ALL = (0, 1, 2, 3, 4)


def test_2f_default_stays_when_8192_is_already_clean(tmp_path):
    d = session_2f(
        tmp_path,
        {
            c: {8192: {}, 4096: {}, 2048: {}, 0: {}} if c == "128K" else {8192: {}, 2048: {}}
            for c in K
            if c != "32K"
        },
    )
    r = run("2f", [d])
    assert r["status"] == "decided" and r["chosen_cache_ram"] is None
    assert all(c["chosen"] == 8192 and c["status"] == "decided" for c in r["contexts"].values())
    assert "the default" in r["reason"] and r["human_decision_needed"] == []
    assert r["provenance"]["rule_text"] == list(rules.RULES_BY_STAGE["2f"])


def test_2f_chooses_the_largest_clean_value_when_only_2048_and_0_are_clean(tmp_path):
    d = session_2f(
        tmp_path,
        {
            "128K": {8192: dict(flagged=(1,)), 4096: dict(flagged=(1, 3)), 2048: {}, 0: {}},
            "64K": {8192: dict(flagged=(1,)), 2048: {}},
        },
    )
    r = run("2f", [d])
    assert r["status"] == "decided" and r["chosen_cache_ram"] == 2048
    c128 = r["contexts"]["128K"]
    assert c128["chosen"] == 2048 and "largest tested value" in c128["reason"]
    by = {e["cache_ram"]: e for e in c128["values"]}
    assert by[8192]["paging_flagged_repetitions"] == [1] and by[4096][
        "paging_flagged_repetitions"
    ] == [1, 3]
    assert by[2048]["paging_clean"] and by[0]["paging_clean"]
    assert by[2048]["ratio_vs_8192"] is None or by[2048]["ratio_vs_8192"] < 1.03
    assert r["proposed_cache_ram"] == 2048


def test_2f_clean_only_at_zero_chooses_zero_not_the_default(tmp_path):
    d = session_2f(
        tmp_path,
        {
            "128K": {
                8192: dict(flagged=(1,)),
                4096: dict(flagged=(1,)),
                2048: dict(flagged=(2,)),
                0: {},
            }
        },
    )
    r = run("2f", [d])
    assert r["status"] == "decided" and r["chosen_cache_ram"] == 0  # 0 means disabled, not "unset"
    # the spec generator takes it from the decision file: --cache-ram 0 on every later cell
    p = tmp_path / "2f.json"
    p.write_text(json.dumps(r))
    pol = specgen.read_cache_policy(None, p)
    assert pol.value == 0 and "2f decision" in pol.source


def test_2f_stops_when_no_value_is_clean(tmp_path):
    d = session_2f(
        tmp_path,
        {"128K": {v: dict(flagged=(1,)) for v in (8192, 4096, 2048, 0)}},
    )
    r = run("2f", [d])
    assert r["status"] == "stop" and r["chosen_cache_ram"] is None
    assert "STOP" in r["reason"] and "not the host cache" in r["reason"]
    assert any("2f stop" in h for h in r["human_decision_needed"])
    md = render_markdown(r)
    assert "STOP" in md and "Human decision needed" in md


def test_2f_3_percent_condition_rejects_a_value(tmp_path):
    # 4096 is clean but about 5% slower than the clean units of the 8192 cell: rejected; 2048 is within 3%
    d = session_2f(
        tmp_path,
        {
            "128K": {
                8192: dict(flagged=(1,), tg=80.0),
                4096: dict(tg=80.0 * 0.93),
                2048: dict(tg=80.0 * 0.995),
                0: dict(tg=80.0),
            },
            "64K": {8192: dict(flagged=(1,)), 2048: {}},
        },
    )
    r = run("2f", [d])
    by = {e["cache_ram"]: e for e in r["contexts"]["128K"]["values"]}
    assert by[4096]["rejected_by_3pct"] is True and by[4096]["ratio_vs_8192"] > 1.03
    assert by[2048]["rejected_by_3pct"] is False
    assert (
        r["contexts"]["128K"]["chosen"] == 2048
        and "more than 3% slower" in r["contexts"]["128K"]["reason"]
    )
    assert r["chosen_cache_ram"] == 2048


def test_2f_every_clean_value_too_slow_is_no_automatic_decision(tmp_path):
    d = session_2f(
        tmp_path,
        {
            "128K": {
                8192: dict(flagged=(1,)),
                4096: dict(tg=60.0),
                2048: dict(tg=60.0),
                0: dict(tg=60.0),
            }
        },
    )
    r = run("2f", [d])
    assert r["status"] == "no_automatic_decision" and r["chosen_cache_ram"] is None
    assert "more than 3% slower" in r["reason"]


def test_2f_without_a_clean_8192_unit_the_3_percent_test_cannot_run(tmp_path):
    # all five repetitions of the 8192 cell are paging-flagged: no clean unit, no baseline
    d = session_2f(
        tmp_path,
        {"128K": {8192: dict(flagged=ALL), 4096: {}, 2048: {}, 0: {}}},
    )
    r = run("2f", [d])
    assert r["status"] == "no_automatic_decision"
    assert "cannot be evaluated" in r["reason"]


def test_2f_contexts_that_disagree_need_a_human(tmp_path):
    d = session_2f(
        tmp_path,
        {
            "128K": {8192: dict(flagged=(1,)), 4096: {}, 2048: {}, 0: {}},
            "64K": {8192: dict(flagged=(1,)), 2048: {}},
        },
    )
    r = run("2f", [d])
    assert r["contexts"]["128K"]["chosen"] == 4096 and r["contexts"]["64K"]["chosen"] == 2048
    assert r["status"] == "needs_human" and r["proposed_cache_ram"] == 2048
    assert r["chosen_cache_ram"] is None
    assert any("combined value" in h for h in r["human_decision_needed"])
    p = tmp_path / "2f.json"
    p.write_text(json.dumps(r))
    with pytest.raises(
        specgen.SpecGenError, match="a human decides"
    ):  # a spec is not built from it
        specgen.read_cache_policy(None, p)


def test_2f_default_in_one_context_and_a_value_in_the_other_is_a_disagreement(tmp_path):
    d = session_2f(
        tmp_path,
        {
            "128K": {8192: {}, 4096: {}, 2048: {}, 0: {}},
            "64K": {8192: dict(flagged=(2,)), 2048: {}},
        },
    )
    r = run("2f", [d])
    assert r["status"] == "needs_human" and r["proposed_cache_ram"] == 2048


def test_2f_an_incomplete_cell_is_never_clean(tmp_path):
    d = session_2f(
        tmp_path,
        {
            "128K": {
                8192: dict(flagged=(1,)),
                4096: dict(status="did_not_fit", reason="oom_at_load"),
                2048: {},
                0: {},
            }
        },
    )
    r = run("2f", [d])
    by = {e["cache_ram"]: e for e in r["contexts"]["128K"]["values"]}
    assert by[4096]["paging_clean"] is False and "did_not_fit" in by[4096]["not_clean_because"]
    assert r["chosen_cache_ram"] == 2048


def test_2f_window_figures_and_host_cache_from_the_lookup(tmp_path):
    d = session_2f(tmp_path, {"128K": {8192: dict(flagged=(1,)), 4096: {}, 2048: {}, 0: {}}})
    seen = []

    def lookup(sess, ins):
        seen.append(ins["run_id"])
        # the fixture windows are [rep * 100, rep * 100 + 9]: one cache save per repetition
        return [(rep * 100 + 5.0, rep + 1, 1000.0 * (rep + 1)) for rep in range(5)]

    r = run("2f", [d], cache_lookup=lookup)
    assert seen and all("s2f-s2f-P2-128K" in x or "s2f" in x for x in seen)
    e = next(e for e in r["contexts"]["128K"]["values"] if e["cache_ram"] == 8192)
    w1 = next(w for w in e["windows"] if w["repetition"] == 1)
    assert w1["faults"] == 1500 and w1["paging_flagged"] is True
    assert w1["rss_anon_growth_mib"] == pytest.approx(2100.0)
    assert w1["host_cache_first"] == [2, 2000.0] and w1["host_cache_last"] == [2, 2000.0]
    assert w1["min_free_vram_mib"] == 1200.0 and w1["t_turn_400"] > 0
    assert w1["swap_activity_mib"] is None
    md = render_markdown(r)
    assert "RssAnon growth" in md and "host cache first" in md and "2 / 2,000" in md


def test_2f_cells_without_cache_ram_are_not_a_2f_session(tmp_path):
    d = build_session(tmp_path, "x", [CellSpec(name="a", context=K["64K"])])
    with pytest.raises(ValueError, match="not a 2f session"):
        run("2f", [d])


# ------------------------------------------------------------------------------ 2a


def c2a(ctx, place, n, *, tg=80.0, pp=1000.0, accept=0.7, **kw):
    spec = {"spec_draft_n_max": n} if n else {}
    return CellSpec(
        name=f"s2a-{place}-{ctx}-b4096-mtp{n}", context=K[ctx], placement=place, batch="b4096",
        tg=tg, pp=pp, accept=accept, spec_type="draft-mtp" if n else None,
        extra={**spec, "cache_ram": 2048}, **kw,
    )  # fmt: skip


def session_2a(tmp_path, ctx_cells, sid="s2a"):
    return build_session(tmp_path, sid, [c for cells in ctx_cells.values() for c in cells])


def top_for(ctx):
    return {"32K": "P6", "64K": "P6", "128K": "P2"}[ctx]


def second_for(ctx):
    return {"32K": "P2", "64K": "P2", "128K": "P6"}[ctx]


def cells_2a(ctx, tgs, *, pp_mtp=1000.0, second_tg=80.0, accepts=(0.8, 0.7, 0.6)):
    """tgs: {0: tg, 1: tg, 2: tg, 3: tg} for the top placement."""
    top, sec = top_for(ctx), second_for(ctx)
    out = [
        c2a(ctx, top, n, tg=tg, pp=1000.0 if n == 0 else pp_mtp, accept=accepts[max(n - 1, 0)])
        for n, tg in tgs.items()
    ]
    return out + [c2a(ctx, sec, 0, tg=second_tg)]


def test_2a_mtp_wins_and_a_draft_length_tie_goes_to_the_smaller(tmp_path):
    # n = 2 and n = 3 are identical (a tie), n = 1 is clearly slower, MTP off is far slower than all
    d = session_2a(
        tmp_path, {"32K": cells_2a("32K", {0: 80.0, 1: 95.0, 2: 110.0, 3: 110.0}, pp_mtp=900.0)}
    )
    r = run("2a", [d])
    e = r["contexts"]["32K"]
    dl = e["draft_length"]
    assert dl["best_n"] == 2 and dl["tied"] == [2, 3] and "smallest wins" in dl["reason"]
    assert e["mtp_vs_off"]["mtp_wins_on_t_turn_400"] is True
    assert e["mtp_vs_off"]["section_3_3_step"] == "ci_excludes_zero"
    assert e["top_config"] == {"mtp": 2, "cell": "s2a-P6-32K-b4096-mtp2"}
    assert e["input_2a2"] == {
        "top_cell": "P6-32K-b4096",
        "second_cell": "P2-32K-b4096",
        "top_mtp": 2,
        "second_mtp": 2,
        "best_n": 2,
        "best_n_reason": None,
        "borrowed_draft_lengths": [],
        "second_mtps": [2],
    }
    # acceptance per draft length, and the paired prefill effect (PP_fresh with MTP about 10% lower)
    assert set(e["acceptance"]) == {"1", "2", "3"}
    assert e["acceptance"]["1"]["pooled"]["all"] == pytest.approx(0.8, abs=0.02)
    pf = e["effects"]["pp_fresh"]["pooled"]
    assert pf["n"] == 5 and 0.85 < pf["geomean"] < 0.95 and pf["ci"][1] < 1.0
    assert set(e["effects"]["pp_fresh"]["per_depth"]) == {"8192", "16384", "24576"}
    assert e["effects"]["tg"]["pooled"]["geomean"] > 1.2
    assert r["human_decision_needed"] == []
    md = render_markdown(r)
    assert (
        "best draft length: **2**" in md
        and "PP_fresh (prefill), pooled" in md
        and "Acceptance" in md
    )


def test_2a_a_clear_best_draft_length_wins_even_if_larger(tmp_path):
    d = session_2a(tmp_path, {"32K": cells_2a("32K", {0: 80.0, 1: 90.0, 2: 100.0, 3: 125.0})})
    e = run("2a", [d])["contexts"]["32K"]
    assert e["draft_length"]["best_n"] == 3 and e["draft_length"]["tied"] == [3]
    assert e["input_2a2"]["top_mtp"] == 3 and e["input_2a2"]["second_mtp"] == 3


def synth_cell(name, tt, rr=None):
    """A cell entry reduced to what the draft-length rule reads: per-repetition T_turn_400 and
    T_reread (lists of 5), as ``analysis`` would give them."""
    from smallpc import stats

    rr = rr or [1.0 + 0.001 * i for i in range(5)]
    mk = lambda v: {"values": {f"s:{i}": x for i, x in enumerate(v)}, "stats": stats.summarize(v)}  # noqa: E731
    return {"name": name, "rep_metrics": {"t_turn_400_mean": mk(tt), "t_reread_mean": mk(rr)}}


def test_draft_length_rule_on_controlled_numbers():
    base = [6.0, 6.1, 5.9, 6.05, 5.95]
    noise = [0.01, -0.01, 0.02, -0.02, 0.0]
    cells = {
        1: synth_cell("n1", [b + n for b, n in zip(base, noise, strict=True)]),
        2: synth_cell("n2", [b - n for b, n in zip(base, noise, strict=True)]),
        3: synth_cell("n3", [b + 0.005 for b in base]),
    }
    # all three are within noise of each other: the smallest draft length wins
    dl = decide.best_draft_length(cells)
    assert dl["tied"] == [1, 2, 3] and dl["best_n"] == 1 and "smallest wins" in dl["reason"]
    # n = 3 clearly the fastest (every repetition 0.5 s better): it wins although it is the largest
    fast = {**cells, 3: synth_cell("n3", [b - 0.5 + 0.01 * i for i, b in enumerate(base)])}
    dl = decide.best_draft_length(fast)
    assert dl["best_n"] == 3 and dl["best_mean_n"] == 3 and dl["tied"] == [3]
    # n = 2 and n = 3 tie for the best, n = 1 is clearly worse: the smaller of the tied pair
    mixed = {
        1: synth_cell("n1", [b + 0.5 for b in base]),
        2: synth_cell("n2", [b - 0.4 + n for b, n in zip(base, noise, strict=True)]),
        3: synth_cell("n3", [b - 0.4 - n for b, n in zip(base, noise, strict=True)]),
    }
    dl = decide.best_draft_length(mixed)
    assert dl["tied"] == [2, 3] and dl["best_n"] == 2
    assert dl["candidates"][-1]["vs_best"]["distinguishable"] is True
    # independent of the order the cells are given in
    assert decide.best_draft_length(dict(reversed(list(mixed.items()))))["best_n"] == 2
    assert decide.best_draft_length({})["best_n"] is None


def test_draft_length_rule_notes_a_step_2_preference_for_a_human():
    base = [6.0, 6.1, 5.9, 6.05, 5.95]
    noise = [0.01, -0.01, 0.02, -0.02, 0.0]
    best = synth_cell("n3", [b - 0.001 for b in base], rr=[2.0 + 0.001 * i for i in range(5)])
    # T_turn_400 tied, but T_reread of n = 2 is clearly lower: section 3.3 step 2 would pick it
    other = synth_cell(
        "n2",
        [b + n for b, n in zip(base, noise, strict=True)],
        rr=[1.5 + 0.001 * i for i in range(5)],
    )
    dl = decide.best_draft_length({3: best, 2: other})
    assert dl["best_n"] == 3 and dl["human_decision_needed"]
    assert "step 2 would prefer draft length 2" in dl["human_decision_needed"][0]


def test_2a_mtp_losing_keeps_mtp_off_but_still_names_a_draft_length_for_2a2(tmp_path):
    d = session_2a(tmp_path, {"32K": cells_2a("32K", {0: 80.0, 1: 60.0, 2: 62.0, 3: 55.0})})
    e = run("2a", [d])["contexts"]["32K"]
    m = e["mtp_vs_off"]
    assert m["winner"] == "s2a-P6-32K-b4096-mtp0" and m["mtp_wins_on_t_turn_400"] is False
    assert e["top_config"]["mtp"] == 0
    assert (
        e["input_2a2"]["top_mtp"] == 0
        and e["input_2a2"]["second_mtp"] == e["draft_length"]["best_n"]
    )


def test_2a_mtp_tied_with_off_prefers_no_mtp(tmp_path):
    d = session_2a(tmp_path, {"32K": cells_2a("32K", {0: 80.0, 1: 80.0, 2: 80.0, 3: 80.0})})
    e = run("2a", [d])["contexts"]["32K"]
    m = e["mtp_vs_off"]
    assert m["mtp_wins_on_t_turn_400"] is False and m["winner"] == "s2a-P6-32K-b4096-mtp0"
    assert m["section_3_3_step"] in ("no_mtp", "t_reread")


def test_2a_ineligible_cells_are_left_out_and_reported(tmp_path):
    cells = cells_2a("32K", {0: 80.0, 1: 95.0, 2: 110.0, 3: 112.0})
    for c in cells:
        if c.name.endswith("mtp3"):
            c.min_free = 400.0  # below the 512 MiB line
    e = run("2a", [session_2a(tmp_path, {"32K": cells})])["contexts"]["32K"]
    assert e["eligibility"]["s2a-P6-32K-b4096-mtp3"]["eligible"] is False
    assert "below 512" in e["eligibility"]["s2a-P6-32K-b4096-mtp3"]["reasons"][0]
    assert e["draft_length"]["best_n"] == 2 and 3 not in [
        c["n"] for c in e["draft_length"]["candidates"]
    ]


def test_2a_without_an_eligible_mtp_cell_has_no_draft_length(tmp_path):
    cells = [c for c in cells_2a("32K", {0: 80.0, 1: 90.0}) if "mtp1" not in c.name]
    e = run("2a", [session_2a(tmp_path, {"32K": cells})])["contexts"]["32K"]
    assert e["draft_length"]["best_n"] is None and e["input_2a2"]["second_mtp"] is None
    assert e["mtp_vs_off"] is None


def _no_mtp(ctx):
    """A context whose top placement has no eligible MTP cell (only MTP off was run)."""
    return cells_2a(ctx, {0: 80.0})


def test_2a_borrows_the_draft_length_of_the_other_context(tmp_path):
    # 32K and 64K each have a best draft length 2 (a tie goes to the smaller); 128K has none
    tie = {0: 80.0, 1: 95.0, 2: 110.0, 3: 110.0}
    d = session_2a(
        tmp_path,
        {"32K": cells_2a("32K", tie), "64K": cells_2a("64K", tie), "128K": _no_mtp("128K")},
    )
    r = run("2a", [d])
    assert r["human_decision_needed"] == []
    e = r["contexts"]["128K"]
    assert e["draft_length"]["best_n"] is None and e["draft_length"]["reason"] == (
        "no eligible MTP cell"
    )
    assert e["borrowed_draft_lengths"] == [2]
    assert e["input_2a2"] == {
        "top_cell": "P2-128K-b4096",
        "second_cell": "P6-128K-b4096",
        "top_mtp": 0,  # the anchor is the top placement with MTP off
        "second_mtp": None,
        "best_n": None,
        "best_n_reason": "no eligible MTP cell",
        "borrowed_draft_lengths": [2],
        "second_mtps": [2],
    }
    # a context with an eligible MTP cell is unchanged: its own best draft length, nothing borrowed
    e32 = r["contexts"]["32K"]["input_2a2"]
    assert e32["second_mtps"] == [2] and e32["borrowed_draft_lengths"] == [] and e32["top_mtp"] == 2
    assert "borrowed draft lengths for the second placement" in render_markdown(r)


def test_2a_two_other_contexts_that_disagree_both_lengths_are_borrowed(tmp_path):
    d = session_2a(
        tmp_path,
        {
            "32K": cells_2a("32K", {0: 80.0, 1: 95.0, 2: 110.0, 3: 110.0}),  # best 2
            "64K": cells_2a("64K", {0: 80.0, 1: 90.0, 2: 100.0, 3: 125.0}),  # best 3
            "128K": _no_mtp("128K"),
        },
    )
    r = run("2a", [d])
    assert r["human_decision_needed"] == []
    e = r["contexts"]["128K"]["input_2a2"]
    assert e["borrowed_draft_lengths"] == [2, 3] and e["second_mtps"] == [2, 3]
    assert e["top_mtp"] == 0 and e["best_n"] is None
    # the contexts that have their own best draft length borrow nothing
    assert r["contexts"]["32K"]["input_2a2"]["second_mtps"] == [2]
    assert r["contexts"]["64K"]["input_2a2"]["second_mtps"] == [3]
    j, _ = decide.write_outputs(r, tmp_path / "out/2a")
    sub = json.loads((tmp_path / "out/2a-2a2-input.json").read_text())
    assert sub["contexts"]["128K"]["input_2a2"]["second_mtps"] == [2, 3]


def test_2a_no_context_has_an_eligible_mtp_cell_needs_a_human(tmp_path):
    d = session_2a(tmp_path, {"32K": _no_mtp("32K"), "128K": _no_mtp("128K")})
    r = run("2a", [d])
    assert r["human_decision_needed"]
    assert any("no eligible MTP cell in any context" in m for m in r["human_decision_needed"])
    for ctx in ("32K", "128K"):
        i = r["contexts"][ctx]["input_2a2"]
        assert i["best_n"] is None and i["borrowed_draft_lengths"] == [] and i["second_mtps"] == []
    # the spec generator refuses such an input rather than guessing
    decide.write_outputs(r, tmp_path / "out/2a")
    with pytest.raises(specgen.SpecGenError, match="no draft length to borrow"):
        specgen.read_2a_result(tmp_path / "out/2a-2a2-input.json", specgen.load_shortlist(REPO))


def test_2a_three_contexts_and_the_2a2_input_files(tmp_path):
    d = session_2a(
        tmp_path,
        {c: cells_2a(c, {0: 80.0, 1: 95.0, 2: 110.0, 3: 110.0}) for c in ("32K", "64K", "128K")},
    )
    r = run("2a", [d])
    assert list(r["contexts"]) == ["32K", "64K", "128K"]
    assert r["contexts"]["128K"]["top"] == "P2-128K-b4096"
    j, m = decide.write_outputs(r, tmp_path / "out/2a")
    inp = tmp_path / "out/2a-2a2-input.json"
    assert j.exists() and m.exists() and inp.exists()
    # the spec generator reads the 2a result as it is, or the small input file
    for f in (j, inp):
        res = specgen.read_2a_result(f, specgen.load_shortlist(REPO))
        assert set(res) == {"32K", "64K", "128K"} and res["64K"].top_mtp == 2
    text = specgen.generate("2a2", root=REPO, cache_ram="2048", from_2a=inp)
    assert "stage2-2a2" in text


# ------------------------------------------------------------------------------ 2a2


def c2a2(ctx, place, n, *, tg=80.0, **kw):
    spec = {"spec_draft_n_max": n} if n else {}
    return CellSpec(
        name=f"s2a2-{place}-{ctx}-b4096-mtp{n}", context=K[ctx], placement=place, batch="b4096",
        tg=tg, spec_type="draft-mtp" if n else None, extra={**spec, "cache_ram": 2048}, **kw,
    )  # fmt: skip


def test_2a2_picks_a_winner_per_context_with_the_anchor_in_the_session(tmp_path):
    cells = [
        c2a2("64K", "P6", 2, tg=100.0),  # the anchor (top placement, 2a-best config)
        c2a2("64K", "P2", 0, tg=80.0),
        c2a2("64K", "P2", 2, tg=118.0),  # the second placement with MTP is clearly the fastest
    ]
    r = run("2a2", [build_session(tmp_path, "s2a2", cells)])
    e = r["contexts"]["64K"]
    assert e["status"] == "decided" and e["winner"] == "s2a2-P2-64K-b4096-mtp2"
    assert (
        e["runner_up"] == "s2a2-P6-64K-b4096-mtp2" and e["decision"]["step"] == "ci_excludes_zero"
    )
    assert r["winners"]["64K"] == {
        "cell": "s2a2-P2-64K-b4096-mtp2", "placement": "P2", "batch": "b4096", "context": "64K", "mtp": 2,
    }  # fmt: skip
    assert r["runners_up"]["64K"]["placement"] == "P6"
    assert e["mtp_vs_off_by_placement"]["P2-mtp2"]["mtp_wins_on_t_turn_400"] is True
    assert r["sanity"].startswith("pending")
    # the 2b to 2d generators read this file
    p = tmp_path / "2a2.json"
    p.write_text(json.dumps(r))
    w = specgen.read_winner(p, specgen.load_shortlist(REPO))
    assert w.entry.placement == "P2" and w.mtp == 2


def test_2a2_without_any_eligible_cell(tmp_path):
    cells = [c2a2("64K", "P2", 0, min_free=300.0), c2a2("64K", "P6", 0, min_free=300.0)]
    r = run("2a2", [build_session(tmp_path, "s2a2", cells)])
    assert r["contexts"]["64K"]["status"] == "no_eligible_cell" and r["winners"] == {}
    assert any("no eligible cell" in h for h in r["human_decision_needed"])


# ------------------------------------------------------------------------------ 2b, 2c, 2d


def pair_cells(stage, tg_a, tg_b, *, swap_a=None, reps_a=None, reps_b=None):
    def mk(name, tg, reps, extra):
        return CellSpec(name=name, context=K["64K"], placement="P6", batch="b4096", tg=tg,
                        reps=reps, extra={"cache_ram": 2048, **extra})  # fmt: skip

    if stage == "2b":
        return [mk("s2b-P6-64K-b4096-mtp0-kvq8", tg_a, reps_a, {"cache_type_k": "q8_0"}),
                mk("s2b-P6-64K-b4096-mtp0-kvf16", tg_b, reps_b, {"cache_type_k": "f16"})]  # fmt: skip
    if stage == "2c":
        return [mk("s2c-P6-64K-b4096-mtp0-lmauto", tg_a, reps_a, {"load_mode": "auto"}),
                mk("s2c-P6-64K-b4096-mtp0-lmnone", tg_b, reps_b, {"load_mode": "none"})]  # fmt: skip
    return [mk("s2d-P6-64K-b4096-mtp0-t8", tg_a, reps_a, {"threads": 8}),
            mk("s2d-P6-64K-b4096-mtp0-tdef", tg_b, reps_b, {})]  # fmt: skip


@pytest.mark.parametrize("stage", ["2b", "2c", "2d"])
def test_pair_stage_clear_winner(tmp_path, stage):
    d = build_session(tmp_path, f"s{stage}", pair_cells(stage, 80.0, 92.0))
    r = run(stage, [d])
    e = r["contexts"]["64K"]
    assert e["status"] == "decided" and e["verdict"]["step"] == "ci_excludes_zero"
    assert e["verdict"]["winner"].endswith(("kvf16", "lmnone", "tdef"))  # the faster (second) cell
    diff = e["verdict"]["decision"]["t_turn_400_difference"]
    assert diff["excludes_zero"] is True and diff["n"] == 5
    assert e["swap_sensitivity"]["changes_the_verdict"] is False
    assert (
        abs(e["effects"]["tg"]["geomean"] - 1.0) > 0.05
    )  # decode differs: ratio of the first to the second cell
    assert e["effects_note"].startswith("paired ratios ") and " / " in e["effects_note"]
    settings = [c["setting"] for c in e["cells"].values()]
    assert len(set(settings)) == 2
    md = render_markdown(r)
    assert f"Stage {stage} decision" in md and "Paired T_turn_400 difference" in md


@pytest.mark.parametrize("stage", ["2b", "2c", "2d"])
def test_pair_stage_tie_is_not_decided_on_speed(tmp_path, stage):
    d = build_session(tmp_path, f"t{stage}", pair_cells(stage, 80.0, 80.0))
    e = run(stage, [d])["contexts"]["64K"]
    assert e["status"] == "decided" and e["verdict"]["step"] != "ci_excludes_zero"
    assert e["verdict"]["decision"]["t_turn_400_difference"]["excludes_zero"] is False


def test_2c_reports_the_paging_figures_of_both_cells(tmp_path):
    reps = [
        RepSpec(i, faults=100 * i, anon_mib=(1000.0, 2000.0 + i), swap_mib=12.5) for i in range(5)
    ]
    d = build_session(tmp_path, "s2c", pair_cells("2c", 80.0, 80.0, reps_a=reps, reps_b=reps))
    e = run("2c", [d], cache_lookup=lambda s, i: [])["contexts"]["64K"]
    assert set(e["paging"]) == {"s2c-P6-64K-b4096-mtp0-lmauto", "s2c-P6-64K-b4096-mtp0-lmnone"}
    w = e["paging"]["s2c-P6-64K-b4096-mtp0-lmauto"][3]
    assert (
        w["faults"] == 300 and w["swap_activity_mib"] == 12.5 and w["rss_anon_growth_mib"] == 1003.0
    )
    assert "Paging figures of" in render_markdown(run("2c", [d], cache_lookup=lambda s, i: []))


def test_pair_stage_swap_sensitivity_can_change_the_verdict(tmp_path):
    # cell b is much faster in repetitions 0 to 2 (which also have heavy swap growth) and slower in 3 and 4
    fast_heavy = [RepSpec(i, swap_mib=500.0, slow=1.4) for i in range(3)] + [
        RepSpec(i, slow=0.8) for i in (3, 4)
    ]
    plain = [RepSpec(i) for i in range(5)]
    d = build_session(
        tmp_path, "s2b", pair_cells("2b", 80.0, 80.0, reps_a=plain, reps_b=fast_heavy)
    )
    e = run("2b", [d])["contexts"]["64K"]
    sw = e["swap_sensitivity"]
    assert {u["repetition"] for u in sw["units_removed"]} == {0, 1, 2}
    assert sw["changes_the_verdict"] is True
    assert e["verdict"]["winner"].endswith("kvf16") and sw["without_heavy_swap_units"][
        "winner"
    ].endswith("kvq8")
    assert any("verdict changes" in h for h in e["human_decision_needed"])


def test_pair_stage_swap_sensitivity_with_fewer_than_two_pairs_is_inconclusive(tmp_path):
    """Step lead's reading: fewer than 2 paired units left after the removal means no paired CI;
    the recomputation is inconclusive and cannot overturn the verdict (no human decision)."""
    heavy = [RepSpec(i, swap_mib=500.0, slow=1.4) for i in range(4)] + [RepSpec(4, slow=0.8)]
    plain = [RepSpec(i) for i in range(5)]
    d = build_session(tmp_path, "s2b", pair_cells("2b", 80.0, 80.0, reps_a=plain, reps_b=heavy))
    res = run("2b", [d])
    e = res["contexts"]["64K"]
    sw = e["swap_sensitivity"]
    assert {u["repetition"] for u in sw["units_removed"]} == {0, 1, 2, 3}
    assert sw["paired_units_left"] == 1 and sw["inconclusive"] is True
    assert sw["changes_the_verdict"] is False and "inconclusive" in sw["note"]
    assert e["human_decision_needed"] == [] and res["human_decision_needed"] == []
    assert "INCONCLUSIVE" in render_markdown(res)


def test_pair_stage_with_one_ineligible_cell(tmp_path):
    cells = pair_cells("2b", 80.0, 92.0)
    cells[1].min_free = 300.0
    e = run("2b", [build_session(tmp_path, "s2b", cells)])["contexts"]["64K"]
    assert e["status"] == "only_one_eligible" and e["verdict"]["winner"].endswith("kvq8")
    assert e["human_decision_needed"]


def test_pair_stage_needs_exactly_two_cells(tmp_path):
    d = build_session(tmp_path, "s2b", pair_cells("2b", 80.0, 92.0)[:1])
    with pytest.raises(ValueError, match="expected exactly 2"):
        run("2b", [d])


def test_2d_skipped_when_the_default_is_8_threads(tmp_path):
    r = decide.decide_2d_skipped(8, root=REPO, git=fake_git)
    assert r["status"] == "skipped" and "not needed" in r["reason"]
    assert r["provenance"]["plan_version"] == "1.8" and r["provenance"]["code"] == FAKE_GIT
    assert "Skipped" in render_markdown(r)
    with pytest.raises(ValueError):
        decide.decide_2d_skipped(16)
    assert (
        cli.main(
            ["decide", "--stage", "2d", "--default-threads", "8", "--out", str(tmp_path / "d")]
        )
        == 0
    )
    assert json.loads((tmp_path / "d.json").read_text())["status"] == "skipped"


# ------------------------------------------------------------------------------ refusals


def small_session(tmp_path, sid="s2f", **kw):
    cells = [cell_2f("64K", 8192), cell_2f("64K", 2048)]
    return build_session(tmp_path, sid, cells, **kw)


def test_refuses_a_session_started_with_allow_dirty(tmp_path):
    d = small_session(tmp_path, allow_dirty=True)
    with pytest.raises(eligibility.Refused, match=r"allow_dirty = true"):
        run("2f", [d])


def test_refuses_the_functional_test_prefix(tmp_path):
    d = small_session(tmp_path, sid=specgen.FT_PREFIX + "2f-cram")
    with pytest.raises(eligibility.Refused, match="functional-test prefix"):
        run("2f", [d])


def test_refuses_a_session_whose_spec_header_says_functional_test(tmp_path):
    root = tmp_path / "repo"
    (root / "configs/sweeps").mkdir(parents=True)
    ft = specgen.generate("2f", root=REPO, preset="functional-test")
    (root / "configs/sweeps/spec.toml").write_text(ft)
    d = small_session(tmp_path, spec_path="configs/sweeps/spec.toml")
    with pytest.raises(eligibility.Refused, match="spec header .* says functional-test"):
        decide.decide("2f", [d], root=root, git=fake_git)
    # a real spec (no such line) is accepted, and its hash is checked against the session's
    (root / "configs/sweeps/spec.toml").write_text(specgen.generate("2f", root=REPO))
    check = eligibility.session_check(d, root)
    assert check["reasons"] == [] and check["spec_header_checked"] is True
    assert check["spec_file_matches"] is False and any(
        "differs from the spec" in w for w in check["warnings"]
    )


def test_refuses_an_incomplete_session(tmp_path):
    d = small_session(tmp_path, state="interrupted")
    with pytest.raises(eligibility.Refused, match="not 'complete'"):
        run("2f", [d])


def test_the_command_line_has_no_override_and_refusals_exit_2(tmp_path, capsys):
    d = small_session(tmp_path, allow_dirty=True)
    assert (
        cli.main(["decide", "--stage", "2f", "--sessions", str(d), "--out", str(tmp_path / "o")])
        == 2
    )
    assert "refused" in capsys.readouterr().err and not (tmp_path / "o.json").exists()
    with pytest.raises(SystemExit):  # there is no flag for it
        cli.main(
            ["decide", "--stage", "2f", "--sessions", str(d), "--out", "x", "--allow-ineligible"]
        )


def test_the_test_override_is_recorded_and_works_only_under_pytest(tmp_path, monkeypatch):
    d = small_session(tmp_path, allow_dirty=True)
    r = run("2f", [d], allow_ineligible=True)
    assert r["provenance"]["eligibility_override"] is True
    assert "not a valid decision" in render_markdown(r)
    monkeypatch.setenv(eligibility.ENV_OVERRIDE, "1")
    assert run("2f", [d])["provenance"]["eligibility_override"] is True  # pytest is running
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with pytest.raises(eligibility.Refused):  # the variable alone is not enough outside pytest
        run("2f", [d])
    ok = small_session(tmp_path, sid="s2f-ok")
    assert run("2f", [ok])["provenance"]["eligibility_override"] is False


# ------------------------------------------------------------------------------ provenance


@pytest.mark.parametrize("stage", ["2f", "2a", "2a2", "2b"])
def test_every_output_records_its_provenance(tmp_path, stage):
    if stage == "2f":
        d = session_2f(tmp_path, {"64K": {8192: {}, 2048: {}}})
    elif stage == "2a":
        d = session_2a(tmp_path, {"32K": cells_2a("32K", {0: 80.0, 1: 95.0, 2: 100.0, 3: 100.0})})
    elif stage == "2a2":
        d = build_session(tmp_path, "s2a2", [c2a2("64K", "P2", 0), c2a2("64K", "P6", 0, tg=70.0)])
    else:
        d = build_session(tmp_path, "s2b", pair_cells("2b", 80.0, 92.0))
    r = run(stage, [d])
    p = r["provenance"]
    assert p["stage"] == stage and p["plan_version"] == "1.8"
    assert p["code"] == FAKE_GIT and p["eligibility_override"] is False
    assert [s["session_id"] for s in p["sessions"]] == [d.name]
    assert p["sessions"][0]["spec_sha256"] == "a" * 64 and p["sessions"][0]["state"] == "complete"
    assert p["llama_cpp_commit"] == "c" * 40
    assert (
        p["llama_cpp_build_info_commit"]
        == json.loads((REPO / "data/env/build-info.json").read_text())["commit"]
    )
    assert p["rule_text"] == list(rules.RULES_BY_STAGE[stage])
    assert r["label"] == "results" and "RESULTS" in r["banner"]
    # the Markdown carries the same facts
    md = render_markdown(r)
    assert d.name in md and "plan version: 1.8" in md and FAKE_GIT["commit"] in md
    assert ("a" * 16) in md and ("c" * 40) in md
    for text in rules.RULES_BY_STAGE[stage]:
        assert "> " + text.split("\n")[0] in md
    # and the written files
    j, m = decide.write_outputs(r, tmp_path / "out" / f"{stage}.json")
    assert json.loads(j.read_text())["provenance"] == p and m.read_text() == md


def test_the_real_git_state_is_recorded(tmp_path):
    d = small_session(tmp_path)
    r = decide.decide("2f", [d], root=REPO)
    head = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert r["provenance"]["code"]["commit"] == head
    assert isinstance(r["provenance"]["code"]["dirty"], bool)


def test_cli_decide_writes_both_files_and_prints_human_decisions(tmp_path, capsys):
    d = session_2f(
        tmp_path,
        {
            "128K": {8192: dict(flagged=(1,)), 4096: {}, 2048: {}, 0: {}},
            "64K": {8192: dict(flagged=(1,)), 2048: {}},
        },
    )
    assert (
        cli.main(["decide", "--stage", "2f", "--sessions", str(d), "--out", str(tmp_path / "x/2f")])
        == 0
    )
    out = capsys.readouterr().out
    assert "status: needs_human" in out and "HUMAN DECISION NEEDED" in out
    assert (tmp_path / "x/2f.json").exists() and (tmp_path / "x/2f.md").read_text().startswith(
        "# Stage 2f"
    )
