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


def pg(maj, swp, vmswap=None):
    vmswap = vmswap if vmswap is not None else [0] * len(maj)
    return [
        {"majflt": a, "pswpin": b, "server_vmswap_kib": c}
        for a, b, c in zip(maj, swp, vmswap, strict=True)
    ]


def test_paging_major_fault_threshold():
    assert flags.paging(pg([500, 1500], [10, 10]))["flag"] is None  # exactly 1,000
    assert flags.paging(pg([500, 1501], [10, 10]))["flag"] == "paging"  # 1,001
    assert flags.paging(pg([500, 1501], [10, 10]))["major_faults"] == 1001


def test_paging_server_vmswap_above_zero_at_any_sample_flags():
    assert flags.paging(pg([0, 0, 0], [5, 5, 5], [0, 0, 0]))["flag"] is None
    r = flags.paging(pg([0, 0, 0], [5, 5, 5], [0, 4, 0]))  # swapped for one sample only
    assert r["flag"] == "paging"
    assert r["server_vmswap_max_kib"] == 4 and r["server_vmswap_samples"] == 1
    assert flags.paging(pg([0, 0], [5, 5], [128, 128]))["flag"] == "paging"


def test_system_swap_in_alone_does_not_flag():
    # zram swaps pages even on an idle machine: recorded, never a flag
    r = flags.paging(pg([0, 0], [100, 100_000], [0, 0]))
    assert r["flag"] is None and r["system_swap_in_pages"] == 99_900
    # ... and rows from before VmSwap was sampled (no column) behave the same
    rows = [{"majflt": 0, "pswpin": 1}, {"majflt": 0, "pswpin": 9999}]
    assert flags.paging(rows)["flag"] is None


def test_paging_skips_samples_without_process():
    rows = [
        {"majflt": None, "pswpin": 1, "server_vmswap_kib": None},
        {"majflt": 10, "pswpin": 1, "server_vmswap_kib": 0},
        {"majflt": 20, "pswpin": 1, "server_vmswap_kib": 0},
    ]
    r = flags.paging(rows)
    assert r["major_faults"] == 10 and r["flag"] is None and r["vmswap_samples_read"] == 2
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


@pytest.mark.parametrize(
    "prompt_n,cache_n,flagged",
    [(8192, 0, False), (8160, 32, False), (8191, 0, True), (8192, 1, True), (0, 8192, False)],
)
def test_accounting_request_a(prompt_n, cache_n, flagged):
    exp = {"processed_plus_cached": {"A": 8192, "B": 11192}}
    rec = {"prompt_n": prompt_n, "cache_n": cache_n}
    assert flags.accounting(rec, 8192) is flagged
    assert ("accounting" in flags.request_flags("A", rec, expected=exp)) is flagged


def test_accounting_request_b_uses_d_plus_3000():
    exp = {"processed_plus_cached": {"A": 8192, "B": 11192}}
    ok = {"prompt_n": 3000, "cache_n": 8192, "predicted_n": 400}
    assert "accounting" not in flags.request_flags("B", ok, depth=8192, expected=exp)
    # the cache hit is fine but the server processed a different number of tokens
    bad = {"prompt_n": 3000, "cache_n": 8191, "predicted_n": 400}
    assert flags.request_flags("B", bad, depth=8192, expected=exp) == ["accounting"]
    # a miss that re-processes everything keeps the total: cache_miss, not accounting
    miss = {"prompt_n": 11192, "cache_n": 0, "predicted_n": 400}
    assert flags.request_flags("B", miss, depth=8192, expected=exp) == ["cache_miss"]


def test_accounting_other_fresh_requests_use_their_own_length():
    exp = {"processed_plus_cached": {"request": 2048}}
    assert flags.request_flags("fresh", {"prompt_n": 2048, "cache_n": 0}, expected=exp) == []
    assert flags.request_flags("fresh", {"prompt_n": 2047, "cache_n": 0}, expected=exp) == [
        "accounting"
    ]
    # warm_prefill and accounting are independent
    both = {"prompt_n": 1900, "cache_n": 100}
    assert flags.request_flags("fresh", both, expected=exp) == ["warm_prefill", "accounting"]


def test_accounting_missing_counts_are_flagged_and_expected_is_optional():
    exp = {"processed_plus_cached": {"A": 100, "B": 3100}}
    assert flags.request_flags("A", {}, expected=exp) == ["accounting"]
    assert flags.accounting({"prompt_n": 100}, 100)
    assert flags.request_flags("A", {"prompt_n": 5, "cache_n": 0}) == []  # no expected: unchecked


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
