from __future__ import annotations

from pathlib import Path

import pytest

from smallpc import flags
from smallpc.stats import summarize

FIX = Path(__file__).parent / "fixtures"


def samples(n, gpu_hits=0, tctl_hits=0, reason="reason_hw_thermal_slowdown", cap_hits=0):
    out = []
    for i in range(n):
        s = {"tctl_c": 80.0, "gpu_temp_c": 60.0, reason: i < gpu_hits}
        if i < tctl_hits:
            s["tctl_c"] = 95.0
        s["reason_sw_power_cap"] = i < cap_hits
        out.append(s)
    return out


# ---------------------------------------------------------------- thermal


@pytest.mark.parametrize(
    "n,hits,flagged",
    [
        (100, 0, False),
        (100, 1, False),
        (100, 2, True),
        (200, 2, False),
        (200, 3, True),
        (3, 1, True),
    ],
)
def test_thermal_gpu_threshold_is_strictly_above_one_percent(n, hits, flagged):
    r = flags.thermal(samples(n, gpu_hits=hits))
    assert (r["flag"] == "thermal") is flagged
    assert r["gpu_slowdown_samples"] == hits


@pytest.mark.parametrize(
    "reason",
    [
        "reason_hw_slowdown",
        "reason_hw_thermal_slowdown",
        "reason_sw_thermal_slowdown",
        "reason_hw_power_brake_slowdown",
    ],
)
def test_each_slowdown_reason_counts(reason):
    assert flags.thermal(samples(100, gpu_hits=5, reason=reason))["flag"] == "thermal"


@pytest.mark.parametrize("n,hits,flagged", [(100, 1, False), (100, 2, True), (200, 2, False)])
def test_thermal_tctl_threshold(n, hits, flagged):
    r = flags.thermal(samples(n, tctl_hits=hits))
    assert (r["flag"] == "thermal") is flagged
    assert r["tctl_ge_95_samples"] == hits


def test_tctl_just_below_95_is_not_counted():
    s = [{"tctl_c": 94.9} for _ in range(100)]
    assert flags.thermal(s)["flag"] is None
    s = [{"tctl_c": 95.0} for _ in range(100)]
    assert flags.thermal(s)["flag"] == "thermal"


def test_power_cap_is_recorded_not_flagged():
    r = flags.thermal(samples(100, cap_hits=100))
    assert r["flag"] is None and r["sw_power_cap_samples"] == 100


def test_thermal_empty_and_missing_values():
    assert flags.thermal([])["flag"] is None
    assert flags.thermal([{"tctl_c": None}] * 10)["flag"] is None


# ---------------------------------------------------------------- paging


def pg(maj, swp):
    return [{"majflt": a, "pswpin": b} for a, b in zip(maj, swp, strict=True)]


def test_paging_major_fault_threshold():
    assert flags.paging(pg([500, 1500], [10, 10]))["flag"] is None  # exactly 1,000
    assert flags.paging(pg([500, 1501], [10, 10]))["flag"] == "paging"  # 1,001
    assert flags.paging(pg([500, 1501], [10, 10]))["major_faults"] == 1001


def test_paging_any_swap_in():
    assert flags.paging(pg([0, 0], [100, 100]))["flag"] is None
    r = flags.paging(pg([0, 0], [100, 101]))
    assert r["flag"] == "paging" and r["swap_in_pages"] == 1
    assert flags.paging(pg([0, 0], [100, 105]), swap_in_tolerance_pages=5)["flag"] is None
    assert flags.paging(pg([0, 0], [100, 106]), swap_in_tolerance_pages=5)["flag"] == "paging"


def test_paging_skips_samples_without_process():
    rows = [{"majflt": None, "pswpin": 1}, {"majflt": 10, "pswpin": 1}, {"majflt": 20, "pswpin": 1}]
    r = flags.paging(rows)
    assert r["major_faults"] == 10 and r["flag"] is None
    assert flags.paging([{"majflt": None, "pswpin": None}])["flag"] is None


# ---------------------------------------------------------------- drift


def canary(mean, half_rel=0.001):
    return {"mean": mean, "ci": [mean * (1 - half_rel), mean * (1 + half_rel)]}


def test_drift_exactly_five_percent_is_not_flagged():
    r = flags.drift(canary(100.0), canary(105.0))
    assert r["relative_difference"] == 0.05 and r["flag"] is None


def test_drift_just_over_five_percent_is_flagged():
    assert flags.drift(canary(100.0), canary(105.01))["flag"] == "drift"
    assert flags.drift(canary(100.0), canary(94.9))["flag"] == "drift"


def test_drift_uses_the_wider_ci_when_it_exceeds_five_percent():
    wide = canary(100.0, half_rel=0.10)
    assert flags.drift(wide, canary(108.0))["flag"] is None  # 8% < 10% CI
    r = flags.drift(wide, canary(111.0))
    assert r["threshold"] == pytest.approx(0.10) and r["flag"] == "drift"


def test_drift_with_summarize_results_and_missing_ci():
    a, b = summarize([100, 101, 99, 100, 100]), summarize([100, 100, 101, 99, 100])
    assert flags.drift(a, b)["flag"] is None
    one = summarize([100.0])
    assert flags.drift(one, summarize([106.0]))["flag"] == "drift"


# ---------------------------------------------------------------- request flags


def test_warm_prefill_threshold():
    assert not flags.warm_prefill({"cache_n": 32})
    assert flags.warm_prefill({"cache_n": 33})
    assert not flags.warm_prefill({"cache_n": 0, "prompt_n": 8000})
    assert not flags.warm_prefill({})


def test_cache_miss_threshold():
    d = 2000
    assert not flags.cache_miss({"cache_n": 1900}, d)  # exactly 0.95 d
    assert flags.cache_miss({"cache_n": 1899}, d)
    assert not flags.cache_miss({"cache_n": 2000}, d)
    assert flags.cache_miss({"cache_n": 0}, d)


def test_short_gen_threshold():
    assert not flags.short_gen({"predicted_n": 100})
    assert flags.short_gen({"predicted_n": 99})
    assert flags.short_gen({})


def test_request_flags_by_kind():
    a = {"cache_n": 40, "prompt_n": 8000, "predicted_n": 0}
    assert flags.request_flags("A", a) == ["warm_prefill"]
    b = {"cache_n": 100, "prompt_n": 3000, "predicted_n": 50}
    assert flags.request_flags("B", b, depth=1000) == ["cache_miss", "short_gen"]
    ok = {"cache_n": 1000, "prompt_n": 3000, "predicted_n": 400}
    assert flags.request_flags("B", ok, depth=1000) == []
    assert flags.request_flags("A", ok) == ["warm_prefill"]  # cache_n 1000 on a fresh request


# ---------------------------------------------------------------- did_not_fit


def test_did_not_fit_exit_code_and_log():
    assert flags.did_not_fit(None, "all good")["flag"] is None
    assert flags.did_not_fit(0, "all good")["flag"] is None
    assert flags.did_not_fit(1, "")["flag"] == "did_not_fit"
    assert flags.did_not_fit(134, "")["startup_exit_code"] == 134
    r = flags.did_not_fit(None, "ggml_backend_cuda_buffer_type_alloc_buffer: CUDA out of memory")
    assert r["flag"] == "did_not_fit" and r["log_matches"]
    assert flags.did_not_fit(None, "cudaMalloc failed: out of memory")["flag"] == "did_not_fit"


@pytest.mark.parametrize("name", sorted(p.name for p in (FIX / "logs").glob("startup-*.txt")))
def test_real_startup_logs_are_not_flagged(name):
    assert flags.did_not_fit(None, (FIX / "logs" / name).read_text())["flag"] is None
