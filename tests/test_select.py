"""WP10: eligibility, the screening shortlist and the final selection with its tie-breaks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fixture_session import CellSpec, RepSpec, build_session  # noqa: E402
from smallpc import select, stats  # noqa: E402


def block(values: list[float]) -> dict:
    return {"values": {f"s:{i}": v for i, v in enumerate(values)}, "stats": stats.summarize(values)}


def cell(name, tt, rr=None, *, profile="candidate", status="complete", reason=None, free=1200.0,
         flagged=(), n_clean=None, mtp=False, cache=0, peak=15000.0, ctx="32K"):  # fmt: skip
    rr = rr if rr is not None else [10.0] * len(tt)
    return {
        "name": name, "profile": profile, "context_label": ctx, "context": int(ctx[:-1]) * 1024,
        "status": status, "reason": reason, "min_free_vram_mib": free,
        "flagged_units": list(flagged), "unit_flags": ["paging"] if flagged else [],
        "n_clean": len(tt) if n_clean is None else n_clean, "n_total": len(tt),
        "mtp": mtp, "cache_mib": cache, "peak_vram_mib": peak,
        "rep_metrics": {"t_turn_400_mean": block(tt), "t_reread_mean": block(rr)},
        "vram": {"model_mib": 1.0}, "cache": {"present": False, "decode_hit_rate_pct": None,
                                              "classes": [], "large_batch_copies": None},
    }  # fmt: skip


def res_of(*cells) -> dict:
    return {"cells": {c["name"]: c for c in cells}}


# ----------------------------------------------------------------------------- eligibility

OK5 = [8.0, 8.1, 7.9, 8.05, 7.95]


def test_a_healthy_cell_is_eligible_in_both_modes():
    c = cell("a", OK5)
    assert select.eligibility(c, "screening")["eligible"]
    assert select.eligibility(c, "final", {"a": "pass"})["eligible"]


def test_reason_final_status_is_not_complete():
    for st, reason in (("did_not_fit", "oom_at_load"), ("not_applicable", None), ("interrupted", None),
                       (None, None)):  # fmt: skip
        e = select.eligibility(cell("a", OK5, status=st, reason=reason), "screening")
        assert not e["eligible"] and any("not complete" in r for r in e["reasons"])
    assert "oom_at_load" in select.eligibility(
        cell("a", OK5, status="did_not_fit", reason="oom_at_load"), "screening")["reasons"][0]  # fmt: skip


def test_reason_minimum_free_vram_below_512():
    e = select.eligibility(cell("a", OK5, free=511.9), "screening")
    assert not e["eligible"] and "511.9 MiB is below 512" in e["reasons"][0]
    assert select.eligibility(cell("a", OK5, free=512.0), "screening")["eligible"]  # at least 512
    e = select.eligibility(cell("a", OK5, free=None), "screening")
    assert not e["eligible"] and "no VRAM measurement" in e["reasons"][0]


def test_reason_flagged_unit_after_attempts_are_resolved():
    e = select.eligibility(cell("a", OK5, flagged=["s:3"]), "screening")
    assert not e["eligible"] and "flagged unit(s) s:3 (paging)" in e["reasons"][0]


def test_reason_n_clean_below_the_mode_minimum():
    assert not select.eligibility(cell("a", [8.0], n_clean=1), "screening")["eligible"]
    assert select.eligibility(cell("a", [8.0, 8.1]), "screening")["eligible"]  # 2 is enough
    e = select.eligibility(cell("a", OK5[:4]), "final", {"a": "pass"})
    assert not e["eligible"] and "n_clean 4 is below 5 (final mode)" in e["reasons"][0]
    assert select.eligibility(cell("a", OK5), "final", {"a": "pass"})["eligible"]


def test_reason_sanity_fail_and_not_run():
    c = cell("a", OK5)
    e = select.eligibility(c, "screening", {"a": "fail"})
    assert not e["eligible"] and e["reasons"] == ["failed the output sanity check"]
    assert select.eligibility(c, "screening")["eligible"]  # not run: allowed in screening
    e = select.eligibility(c, "final")
    assert not e["eligible"] and "must pass in final mode" in e["reasons"][0]
    assert not select.eligibility(c, "final", {"a": "fail"})["eligible"]
    # both spellings of the sanity file
    assert select.sanity_state("a", {"cells": {"a": {"result": "pass"}}}) == "pass"
    assert select.sanity_state("a", {"a": "weird"}) == "not run"


def test_every_reason_is_listed():
    c = cell("a", [8.0], status="did_not_fit", reason="oom_runtime", free=100.0, flagged=["s:0"],
             n_clean=0)  # fmt: skip
    e = select.eligibility(c, "final", {"a": "fail"})
    assert len(e["reasons"]) == 5  # status, VRAM, flagged unit, n_clean, sanity fail


# ------------------------------------------------------------------------ final selection


def final(*cells, sanity=None):
    sanity = sanity or {c["name"]: "pass" for c in cells}
    return select.select_final(res_of(*cells), sanity)["contexts"]["32K"]


def test_a_clear_winner_needs_the_ci_to_exclude_zero():
    fast = cell("fast", [8.00, 8.02, 7.99, 8.01, 8.00])
    slow = cell("slow", [9.00, 9.03, 8.98, 9.01, 9.00])
    r = final(slow, fast)
    assert r["winner"] == "fast" and r["runner_up"] == "slow"
    assert r["decision"]["step"] == "ci_excludes_zero"
    d = r["decision"]["t_turn_400_difference"]
    assert d["n"] == 5 and d["excludes_zero"] and d["mean"] == pytest.approx(1.0, abs=0.01)
    assert r["ranking"] == ["fast", "slow"]


def test_stock_is_never_selected_even_if_fastest():
    st = cell("stock", [7.0] * 5, profile="stock")
    a = cell("a", OK5)
    r = final(st, a)
    assert r["winner"] == "a" and r["runner_up"] is None and r["stock"] == "stock"
    assert r["decision"]["step"] == "only_eligible"


TIE_TT_A = [8.00, 8.10, 7.90, 8.05, 7.95]  # mean 8.00
TIE_TT_B = [8.05, 8.05, 7.95, 8.00, 8.00]  # mean 8.01, differences of +-0.05: CI includes zero
RR_SAME_A = [10.0, 10.2, 9.8, 10.1, 9.9]
RR_SAME_B = [10.1, 10.1, 9.9, 10.0, 9.9]


def test_tie_on_t_turn_is_broken_by_t_reread_when_its_ci_excludes_zero():
    a = cell(
        "a", TIE_TT_A, [12.0, 12.1, 11.9, 12.0, 12.0]
    )  # best T_turn_400 mean, but re-reads slowly
    b = cell("b", TIE_TT_B, [10.0, 10.1, 9.9, 10.0, 10.0])
    assert select.mean_tt(a) < select.mean_tt(b)
    r = final(a, b)
    assert r["decision"]["t_turn_400_difference"]["excludes_zero"] is False
    assert r["winner"] == "b" and r["runner_up"] == "a"  # the lower-mean-T_turn cell loses
    assert r["decision"]["step"] == "t_reread"


def test_tie_of_both_is_broken_by_mtp_first():
    a = cell("a", TIE_TT_A, RR_SAME_A, mtp=True)
    b = cell("b", TIE_TT_B, RR_SAME_B)
    r = final(a, b)
    assert r["decision"]["t_reread_difference"]["excludes_zero"] is False
    assert r["winner"] == "b" and r["decision"]["step"] == "no_mtp"
    # ... and the other way round: the best-mean cell has no MTP, so it keeps the win
    r = final(cell("a", TIE_TT_A, RR_SAME_A), cell("b", TIE_TT_B, RR_SAME_B, mtp=True))
    assert r["winner"] == "a" and r["decision"]["step"] == "no_mtp"


def test_then_by_expert_cache():
    a = cell("a", TIE_TT_A, RR_SAME_A, cache=2048)
    b = cell("b", TIE_TT_B, RR_SAME_B, cache=0)
    r = final(a, b)
    assert r["winner"] == "b" and r["decision"]["step"] == "no_cache"
    # MTP outranks the cache: A has no MTP but a cache, B has MTP without cache -> A wins
    r = final(cell("a", TIE_TT_A, RR_SAME_A, cache=2048), cell("b", TIE_TT_B, RR_SAME_B, mtp=True))
    assert r["winner"] == "a" and r["decision"]["step"] == "no_mtp"


def test_then_by_peak_vram_and_finally_by_name():
    a = cell("a", TIE_TT_A, RR_SAME_A, peak=15500.0)
    b = cell("b", TIE_TT_B, RR_SAME_B, peak=14800.0)
    r = final(a, b)
    assert r["winner"] == "b" and r["decision"]["step"] == "peak_vram"
    r = final(cell("a", TIE_TT_A, RR_SAME_A), cell("b", TIE_TT_B, RR_SAME_B))
    assert r["winner"] == "a" and r["decision"]["step"] == "name"


def test_literal_step_2_is_reachable_only_after_step_1_has_failed_to_separate():
    # the reading of decision 3: step 1 answers only when the T_reread CI excludes zero
    a = cell("a", TIE_TT_A, RR_SAME_A, mtp=True)
    b = cell("b", TIE_TT_B, RR_SAME_B)
    assert final(a, b)["decision"]["step"] == "no_mtp"


def test_statistically_tied_further_cells_are_reported_as_information():
    best = cell("best", [8.00, 8.02, 7.99, 8.01, 8.00])  # mean 8.004
    tied = cell("tied", [8.02, 7.98, 8.01, 8.00, 7.99])  # mean 8.000: lowest, indistinguishable
    second = cell("second", [8.50, 8.52, 8.49, 8.51, 8.50])
    worse = cell("worse", [9.50, 9.52, 9.49, 9.51, 9.50])
    r = final(best, second, tied, worse)
    # tied and best cannot be told apart (T_turn_400 and T_reread), so the name order decides
    assert r["ranking"][:2] == ["tied", "best"] and r["decision"]["step"] == "name"
    assert r["winner"] == "best" and r["runner_up"] == "tied"
    others = {t["cell"]: t for t in r["tied_with_winner"]}
    assert set(others) == {"second", "worse"}
    assert not others["second"]["tied"] and not others["worse"]["tied"]  # clearly slower


def test_a_cell_tied_with_the_winner_beyond_the_top_two_is_listed():
    a = cell("a", TIE_TT_A, RR_SAME_A)  # mean 8.000
    b = cell("b", TIE_TT_B, RR_SAME_B)  # mean 8.010
    c = cell("c", [8.04, 8.06, 7.94, 8.02, 7.98], RR_SAME_B)  # mean 8.008
    r = final(a, b, c)
    assert r["ranking"] == ["a", "c", "b"] and r["winner"] == "a" and r["runner_up"] == "c"
    (t,) = r["tied_with_winner"]
    assert t["cell"] == "b" and t["tied"] is True and t["comparable"] is True


def test_no_eligible_candidate():
    r = final(cell("a", OK5, status="did_not_fit"), cell("b", OK5, free=100.0))
    assert r["winner"] is None and r["decision"] is None
    assert "No eligible candidate" in select.render_markdown(
        select.select_final(res_of(cell("a", OK5, status="did_not_fit")), {}), "results"
    )


def test_cells_that_share_no_repetition_are_not_decisive():
    a = cell("a", [8.0, 8.1, 8.0, 8.1, 8.0])
    b = cell("b", [9.0, 9.1, 9.0, 9.1, 9.0])
    b["rep_metrics"]["t_turn_400_mean"]["values"] = {
        f"other:{i}": v for i, v in enumerate([9.0, 9.1, 9.0, 9.1, 9.0])
    }
    b["rep_metrics"]["t_reread_mean"]["values"] = dict(
        b["rep_metrics"]["t_turn_400_mean"]["values"]
    )
    r = final(a, b)
    assert r["decision"]["t_turn_400_difference"]["n"] == 0
    assert "unpaired" in r["decision"]["note"]


# --------------------------------------------------------------------- screening shortlist


def screening(*cells, sanity=None):
    return select.select_screening(res_of(*cells), sanity)["contexts"]["32K"]


def test_screening_shortlist_is_the_two_best_eligible_and_never_the_stock():
    stock = cell("stock", [7.0, 7.1], profile="stock")
    cs = [cell("c", [9.0, 9.1]), cell("a", [8.0, 8.1]), cell("b", [8.5, 8.6]),
          cell("flagged", [7.5, 7.6], flagged=["s:0"]), cell("dnf", [7.4, 7.5], status="did_not_fit"),
          cell("insane", [7.6, 7.7])]  # fmt: skip
    r = screening(stock, *cs, sanity={"insane": "fail"})
    assert r["shortlist"] == ["a", "b"] and r["stock"] == "stock"
    assert r["ranking"] == ["a", "b", "c"]
    rows = {x["cell"]: x for x in r["rows"]}
    assert rows["stock"]["reference"] and rows["stock"]["eligible"]  # shown, but not shortlisted
    assert not rows["flagged"]["eligible"] and not rows["insane"]["eligible"]
    assert set(r["details"]) == {"a", "b"}  # VRAM and cache details for the shortlist


def test_too_close_to_call_uses_the_larger_range_of_the_two_cells():
    x = cell("x", [7.75, 8.25])  # mean 8.00, range 0.50
    y = cell("y", [8.25, 8.35])  # mean 8.30, range 0.10 -> |diff| 0.30 < 0.50: too close
    z = cell("z", [9.45, 9.55])  # mean 9.50, range 0.10 -> far from both
    r = screening(x, y, z)
    pairs = [tuple(p["cells"]) for p in r["too_close"]]
    assert pairs == [("x", "y")] and r["too_close"][0]["note"] == "too close to call at n = 2"
    assert r["too_close"][0]["mean_difference"] == pytest.approx(0.30)
    assert r["too_close"][0]["larger_range"] == pytest.approx(0.50)


def test_too_close_looks_only_at_the_top_four():
    cs = [cell(f"c{i}", [8.0 + i * 1.0, 8.0 + i * 1.0 + 0.01]) for i in range(4)]
    cs.append(cell("c4", [12.0, 14.0]))  # fifth place with a huge range: not compared
    cs.append(cell("c5", [12.1, 12.2]))
    assert screening(*cs)["too_close"] == []
    # exactly equal difference and range is not "less than"
    t1, t2 = cell("t1", [8.0, 8.5]), cell("t2", [8.25, 8.75])  # means 8.25 / 8.50, ranges 0.5/0.5
    assert screening(t1, t2)["too_close"][0]["mean_difference"] == pytest.approx(0.25)
    u1, u2 = cell("u1", [8.0, 8.5]), cell("u2", [8.5, 9.0])  # means 8.25 / 8.75: diff 0.5 == range
    assert screening(u1, u2)["too_close"] == []


def test_screening_with_only_one_eligible_cell_and_markdown():
    r = select.select_screening(
        res_of(cell("a", [8.0, 8.1]), cell("stock", [7.0, 7.1], profile="stock")), None
    )
    md = select.render_markdown(r, "screening")
    assert "SCREENING DATA" in md and "**Shortlist (32K):** `a` (only 1 eligible cell)" in md
    assert "reference (stock)" in md and "never shortlisted" in md


# ------------------------------------------------------------------------ the CLI end to end


def test_cli_prints_a_table_and_writes_json(tmp_path, capsys):
    d = build_session(tmp_path, "s", [
        CellSpec("stock-32K", "stock", pp=950),
        CellSpec("a-32K", pp=1000, reps=[RepSpec(0), RepSpec(1)]),
        CellSpec("b-32K", pp=980, reps=[RepSpec(0), RepSpec(1, flags=("paging",))]),
    ], canary=False)  # fmt: skip
    out_json, out_md = tmp_path / "x.json", tmp_path / "x.md"
    rc = select.main(["--mode", "screening", "--sessions", str(d), "--label", "functional-test",
                      "--out-json", str(out_json), "--out-md", str(out_md)])  # fmt: skip
    assert rc == 0
    text = capsys.readouterr().out
    assert "FUNCTIONAL-TEST DATA" in text and "| b-32K | candidate | 1/2 |" in text
    assert "flagged unit(s) s:1 (paging)" in text
    data = json.loads(out_json.read_text())
    assert (
        data["contexts"]["32K"]["shortlist"] == ["a-32K"]
        and out_md.read_text() == text.rstrip("\n") + "\n"
    )
