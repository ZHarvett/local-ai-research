"""WP10: metric formulas, attempt resolution and the exclusion rules (no GPU)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fixture_session import CellSpec, RepSpec, build_session, standard_cells, unit_requests  # noqa: E402
from smallpc import analysis  # noqa: E402


def rec_a(**kw):
    base = {"cache_n": 0, "prompt_n": 8192, "prompt_ms": 8192.0, "prompt_per_second": 1000.0}
    return base | kw


def rec_b(**kw):
    base = {
        "cache_n": 8192, "prompt_n": 3000, "prompt_ms": 3000.0, "prompt_per_second": 1000.0,
        "predicted_n": 400, "predicted_ms": 5000.0, "predicted_per_second": 80.0,
        "timings": {"predicted_per_token_ms": 12.5}, "client": {"ttft_s": 3.1},
    }  # fmt: skip
    return base | kw


# ------------------------------------------------------------------ metric formulas, by hand


def test_metric_formulas_on_hand_computed_values():
    m = analysis.pair_metrics(8192, rec_a(prompt_per_second=1024.0), rec_b())
    assert m["pp_fresh"] == 1024.0  # Request A prompt_per_second
    assert m["pp_inc"] == pytest.approx(1000.0)  # 3000 tokens / 3.000 s
    assert m["tg"] == 80.0  # Request B predicted_per_second
    assert m["t_turn_400"] == pytest.approx((3000.0 + 400 * 12.5) / 1000)  # 8.0 s
    assert m["t_b"] == pytest.approx((3000.0 + 5000.0) / 1000)  # 8.0 s, measured
    assert m["predicted_n"] == 400
    assert m["t_reread"] == pytest.approx(8192 / 1024.0)  # d / PP_fresh = 8.0 s
    assert m["ttft"] == 3.1


def test_t_turn_400_is_an_estimate_and_t_b_the_measurement():
    # the model stopped at 384 tokens: T_B covers 384 tokens, T_turn_400 still extrapolates to 400
    b = rec_b(predicted_n=384, predicted_ms=4800.0, timings={"predicted_per_token_ms": 12.5})
    m = analysis.pair_metrics(8192, rec_a(), b)
    assert m["t_b"] == pytest.approx(7.8) and m["t_turn_400"] == pytest.approx(8.0)
    assert m["predicted_n"] == 384


def test_per_token_time_falls_back_to_predicted_ms_over_predicted_n():
    b = rec_b(timings={}, predicted_ms=4000.0, predicted_n=400)
    assert analysis.per_token_ms(b) == pytest.approx(10.0)
    m = analysis.pair_metrics(8192, rec_a(), b)
    assert m["t_turn_400"] == pytest.approx((3000.0 + 400 * 10.0) / 1000)


def test_short_gen_excludes_tg_and_t_turn_but_keeps_prefill():
    b = rec_b(predicted_n=40, predicted_ms=500.0)
    m = analysis.pair_metrics(8192, rec_a(), b)
    assert m["tg"] is None and m["t_turn_400"] is None
    assert m["pp_inc"] == pytest.approx(1000.0) and m["pp_fresh"] == 1000.0 and m["t_b"] is not None


def test_warm_prefill_excludes_pp_fresh_and_t_reread():
    m = analysis.pair_metrics(8192, rec_a(cache_n=500), rec_b())
    assert m["pp_fresh"] is None and m["t_reread"] is None and m["t_turn_400"] is not None


def test_context_label():
    assert analysis.context_label(32768) == "32K" and analysis.context_label(131072) == "128K"
    assert analysis.context_label(None) is None


# --------------------------------------------------------- a fixture session, end to end


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    root = tmp_path_factory.mktemp("fx")
    d = build_session(root, "fx-1", standard_cells())
    return d, analysis.analyse([d])


def test_attempt_2_replaces_attempt_1_in_headline_numbers(fx):
    _, res = fx
    c = res["cells"]["rerun-ok-32K"]
    assert c["n_total"] == 5 and c["n_clean"] == 5 and c["unit_flags"] == []
    # the value of repetition 2 is attempt 2's, computed independently from its raw requests
    cs = next(x for x in standard_cells() if x.name == "rerun-ok-32K")
    reqs = unit_requests("fx-1", cs, RepSpec(2, attempt=2), 7)
    by = {(r["kind"], r["depth"]): r for r in reqs}
    expected = [
        analysis.pair_metrics(d, by[("A", d)], by[("B", d)])["t_turn_400"]
        for d in (8192, 16384, 24576)
    ]
    assert c["rep_metrics"]["t_turn_400_mean"]["values"]["fx-1:2"] == pytest.approx(
        sum(expected) / 3
    )
    att1 = unit_requests("fx-1", cs, RepSpec(2, attempt=1, flags=("paging",)), 7)
    assert att1[0]["flags"] == ["paging"]  # attempt 1 was flagged and differs in its numbers
    units = [u for u in res["units"] if u["cell"] == "rerun-ok-32K" and u["repetition"] == 2]
    assert {u["attempt"]: u["superseded"] for u in units} == {1: True, 2: False}


def test_attempt_1_stays_in_the_diagnostics(fx):
    _, res = fx
    d = [x for x in res["diagnostics"] if x["cell"] == "rerun-ok-32K"]
    assert len(d) == 1 and d[0]["attempt"] == 1 and d[0]["flags"] == ["paging"]
    assert "attempt 1 of a unit re-run" in d[0]["why"]


def test_a_flagged_unit_after_attempt_2_is_excluded_and_listed(fx):
    _, res = fx
    c = res["cells"]["rerun-bad-32K"]
    assert c["n_total"] == 5 and c["n_clean"] == 4 and c["unit_flags"] == ["cache_miss"]
    assert c["flagged_units"] == ["fx-1:1"]
    assert "fx-1:1" not in c["rep_metrics"]["t_turn_400_mean"]["values"]
    why = {(x["attempt"], x["why"]) for x in res["diagnostics"] if x["cell"] == "rerun-bad-32K"}
    assert why == {(1, "attempt 1 of a unit re-run as attempt 2"), (2, "flagged unit")}


def test_short_gen_unit_is_not_clean_and_has_no_t_turn(fx):
    _, res = fx
    c = res["cells"]["shortgen-32K"]
    assert c["n_clean"] == 4 and c["unit_flags"] == ["short_gen"]
    u = next(u for u in res["units"] if u["cell"] == "shortgen-32K" and u["repetition"] == 1)
    assert u["rep"]["t_turn_400_mean"] is None and not u["clean"]
    assert u["metrics"]["8192"]["tg"] is None and u["metrics"]["8192"]["pp_inc"] is not None


def test_warmup_and_canary_records_never_enter_cell_statistics(fx):
    d, res = fx
    c = res["cells"]["stock-32K"]
    assert c["n_total"] == 5  # 5 measured repetitions, not 5 + 2 warm-up units
    for depth in ("8192", "16384", "24576"):
        # warm-up requests ran at 1.5 tokens/s: any leak would drag these far below 900
        assert c["depth_metrics"][depth]["pp_fresh"]["stats"]["min"] > 900
        assert len(c["depth_metrics"][depth]["pp_fresh"]["values"]) == 5
    assert not any(n.startswith("canary") for n in res["cells"])
    assert all(u["cell"] != "canary-start" for u in res["units"])
    can = res["sessions"][0]["canaries"]["main"]
    assert set(can) == {"canary_start", "canary_end"}
    assert len(can["canary_start"]["pp_fresh_16k"]["values"]) == 3


def test_did_not_fit_and_not_applicable_cells_are_reported_without_units(fx):
    _, res = fx
    for r in ("oom_at_load", "startup_failure", "startup_timeout", "context", "crash_mid_cell",
              "oom_runtime", "hung_server", "request_timeout"):  # fmt: skip
        c = res["cells"][f"dnf-{r}-32K"]
        assert c["status"] == "did_not_fit" and c["reason"] == r and c["n_total"] == 0
    na = res["cells"]["NA-32K"]
    assert na["status"] == "not_applicable" and "not applicable" in na["reason"]


def test_mtp_acceptance_per_repetition_and_pooled(fx):
    _, res = fx
    c = res["cells"]["MTP-32K"]
    assert c["mtp"] is True
    acc = c["rep_metrics"]["acceptance"]
    assert len(acc["values"]) == 5 and acc["stats"]["mean"] == pytest.approx(0.7, abs=0.01)
    p = c["acceptance_pooled"]
    # per repetition: 3 Request B x draft_n 280 -> 840 drafted, round(0.7*280) = 196 each -> 588 accepted
    assert p["counts"]["B"] == [5 * 588, 5 * 840] and p["B"] == pytest.approx(0.7)
    assert p["short"] == pytest.approx(0.7) and p["counts"]["short"] == [5 * 210, 5 * 300]
    assert "Request A" in p["note"]
    assert res["cells"]["stock-32K"]["rep_metrics"]["acceptance"]["values"] == {}  # no drafts


def test_cache_statistics_and_vram_parts(fx):
    _, res = fx
    c = res["cells"]["P4-32K-b2048"]
    assert c["cache"]["present"] and c["cache"]["decode_hit_rate_pct"] == pytest.approx(62.0)
    assert c["cache"]["large_batch_copies"] == {"experts": 4321, "mib": 8000.0}
    v = c["vram"]
    assert v["model_mib"] == 13000.0 and v["kv_mib"] == 340.0 and v["recurrent_mib"] == 62.81
    assert v["compute_mib"] == pytest.approx(318.02)  # CUDA0 only, not the host buffer
    assert c["min_free_vram_mib"] == 1200.0 and c["peak_vram_mib"] == pytest.approx(16311 - 1200)


def test_cell_record_server_instance_is_never_used(fx):
    import json

    _, res = fx
    # the fixture's cell records carry server_instance 98765 (wrong on purpose, like the mini data)
    assert "98765" not in json.dumps(res)


def test_units_pool_across_sessions_without_merging_repetitions(tmp_path):
    a = build_session(
        tmp_path, "s-a", [CellSpec("c-32K", reps=[RepSpec(0), RepSpec(1)])], canary=False
    )
    b = build_session(
        tmp_path, "s-b", [CellSpec("c-32K", reps=[RepSpec(0), RepSpec(1)])], canary=False, seed=8
    )
    res = analysis.analyse([a, b])
    c = res["cells"]["c-32K"]
    assert c["n_total"] == 4 and sorted(c["rep_metrics"]["t_turn_400_mean"]["values"]) == [
        "s-a:0", "s-a:1", "s-b:0", "s-b:1",
    ]  # fmt: skip


# ------------------------------------------------------------------------------------ drift


def test_a_drift_flag_excludes_the_sessions_attempt_1_units(tmp_path):
    d = build_session(tmp_path, "s-drift", [CellSpec("c-32K")], drift_main="drift")
    res = analysis.analyse([d])
    c = res["cells"]["c-32K"]
    assert c["n_total"] == 5 and c["n_clean"] == 0 and c["unit_flags"] == ["drift"]
    assert res["sessions"][0]["drift"]["main"]["flag"] == "drift"
    assert all("drift" in u["reasons"] for u in res["units"])
    assert len(res["diagnostics"]) == 5 and all(x["flags"] == ["drift"] for x in res["diagnostics"])


def test_attempt_2_unit_is_judged_by_the_rerun_drift_not_the_main_drift(tmp_path):
    cell = CellSpec(
        "c-32K", reps=[RepSpec(0), RepSpec(1, flags=("paging",)), RepSpec(1, attempt=2)]
    )
    # main drifted, the re-run's own canaries did not: only the replacement unit is usable
    d = build_session(tmp_path, "s-1", [cell], drift_main="drift", drift_rerun=None)
    c = analysis.analyse([d])["cells"]["c-32K"]
    assert (
        c["n_total"] == 2 and c["n_clean"] == 1
    )  # rep 0 (attempt 1) is drift-excluded, rep 1 clean
    assert list(c["rep_metrics"]["t_turn_400_mean"]["values"]) == ["s-1:1"]
    # and if the re-run drifted too, nothing is clean
    d2 = build_session(tmp_path, "s-2", [cell], drift_main=None, drift_rerun="drift")
    assert (
        analysis.analyse([d2])["cells"]["c-32K"]["n_clean"] == 1
    )  # rep 0 only (main did not drift)


def test_missing_rerun_drift_record_is_not_assessed_and_does_not_exclude(tmp_path):
    cell = CellSpec("c-32K", reps=[RepSpec(0, flags=("paging",)), RepSpec(0, attempt=2)])
    d = build_session(tmp_path, "s-3", [cell], drift_rerun=False)
    res = analysis.analyse([d])
    u = next(u for u in res["units"] if u["attempt"] == 2)
    assert u["drift"]["state"] == "not assessed" and u["clean"]


def test_incomplete_batches_are_ignored_via_store(tmp_path):
    d = build_session(tmp_path, "s-4", [CellSpec("c-32K")], canary=False)
    with open(
        d / "records.jsonl", "a"
    ) as fh:  # a repetition cut off mid-batch (batch of 3, 1 line)
        fh.write(
            '{"record_type":"request","batch_id":"zz","batch_index":0,"batch_size":3,'
            '"cell":"c-32K","role":"measured"}\n'
        )
    res = analysis.analyse([d])
    assert res["cells"]["c-32K"]["n_total"] == 5
    assert analysis.load_session(d).incomplete_batches == 1


def test_expert_cache_is_its_own_vram_part_and_not_in_other(tmp_path):
    d = build_session(
        tmp_path,
        "c",
        [
            CellSpec("P4-32K-b2048", cache_mib=2048, cache_hit_rate=0.6, placement="P4"),
            CellSpec("P1-32K-b2048", placement="P1"),
        ],
        canary=False,
    )
    res = analysis.analyse([d])
    with_cache, without = res["cells"]["P4-32K-b2048"]["vram"], res["cells"]["P1-32K-b2048"]["vram"]
    assert with_cache["expert_cache_mib"] == 2048.0 and without["expert_cache_mib"] == 0.0
    # peak used = the listed parts + other, with the cache no longer hidden in "other"
    for v in (with_cache, without):
        listed = sum(v[k] for k in ("model_mib", "kv_mib", "recurrent_mib", "compute_mib",
                                    "expert_cache_mib"))  # fmt: skip
        assert v["peak_used_mib"] == pytest.approx(listed + v["other_mib"], abs=0.1)
    assert with_cache["other_mib"] == pytest.approx(without["other_mib"] - 2048.0, abs=0.1)
