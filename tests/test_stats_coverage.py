"""Coverage of the section 5.5 intervals on simulated data (fixed seeds, CI-safe, about 3 s).

What is asserted, and why it is not "93% everywhere": the reported interval is the wider of the
bootstrap and t intervals. In 100% of the simulated samples the t interval was the wider one, so the
reported interval covers exactly as often as the t interval does. That is about 95% for symmetric
and mildly skewed data (the step-0 timings have a 1 to 2% spread, far below the mild case), and it
falls to 88 to 92% for strongly skewed data, which no t-based interval fixes at n = 5 or 10. The
declared floor of 93% is asserted for the symmetric and the mild-skew scenarios; the two stress
scenarios assert only a regression floor (85%) and their numbers are reported, not hidden. The full
table (20,000 experiments per row) is in docs/decisions.md; reproduce it with
``python -m smallpc.stats coverage``.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from smallpc import stats

EXPERIMENTS = 6000
RESAMPLES = 500
FLOOR = 0.93
STRESS_FLOOR = 0.85
OVER = 0.98  # coverage above this would mean the interval is conservative


@pytest.mark.parametrize("n", [5, 10])
@pytest.mark.parametrize("dist", ["normal", "lognormal-0.1"])
def test_reported_interval_covers_at_least_93_percent(n, dist):
    r = stats.simulate_coverage(n, dist, EXPERIMENTS, RESAMPLES, seed=11)
    cov = r["coverage"]
    print(f"coverage n={n} {dist}: " + ", ".join(f"{k} {v:.3f}" for k, v in cov.items()))
    assert cov["wider"] >= FLOOR
    assert cov["wider"] <= OVER  # not conservative either
    assert cov["wider"] >= cov["bootstrap"] and cov["wider"] >= cov["t"]  # wider never covers less
    assert cov["bootstrap"] < cov["t"]  # the bootstrap interval alone is too narrow (the reason
    # the plan reports the wider one)


@pytest.mark.parametrize("n", [5, 10])
@pytest.mark.parametrize("dist", ["lognormal-0.5", "exponential"])
def test_stress_cases_are_reported_with_a_regression_floor_only(n, dist):
    r = stats.simulate_coverage(n, dist, EXPERIMENTS, RESAMPLES, seed=12)
    cov = r["coverage"]
    print(f"coverage n={n} {dist}: " + ", ".join(f"{k} {v:.3f}" for k, v in cov.items()))
    assert cov["wider"] >= STRESS_FLOOR


def test_wider_interval_is_in_practice_the_t_interval():
    r = stats.simulate_coverage(5, "normal", 2000, 300, seed=3)
    assert r["bootstrap_was_wider_fraction"] == 0.0
    assert r["coverage"]["wider"] == r["coverage"]["t"]


def test_simulation_is_deterministic_and_fast():
    t0 = time.perf_counter()
    a = stats.simulate_coverage(5, "normal", 1000, 200, seed=5)
    b = stats.simulate_coverage(5, "normal", 1000, 200, seed=5)
    assert a == b and time.perf_counter() - t0 < 5
    assert stats.simulate_coverage(5, "normal", 1000, 200, seed=6) != a


def test_unknown_distribution_is_rejected():
    with pytest.raises(ValueError, match="unknown distribution"):
        stats.simulate_coverage(5, "cauchy", 10, 10)


def test_vectorised_bootstrap_matches_the_production_formula():
    """The simulation's t and bootstrap intervals are those of summarize() on the same sample."""
    rng = np.random.default_rng(4)
    x = rng.normal(10, 1, size=7)
    s = stats.summarize(x)
    n = x.size
    half = stats.t_critical(n - 1) * x.std(ddof=1) / np.sqrt(n)
    assert s["t_ci"] == pytest.approx([x.mean() - half, x.mean() + half])
    # same random stream and the same percentile rule as bootstrap_ci
    gen = np.random.default_rng(stats.BOOTSTRAP_SEED)
    idx = gen.integers(0, n, size=(1, stats.BOOTSTRAP_RESAMPLES, n))
    means = np.take_along_axis(x[None, None, :], idx, axis=2).mean(axis=2)
    lo, hi = np.percentile(means, [2.5, 97.5], axis=1)
    assert s["bootstrap_ci"] == pytest.approx([lo[0], hi[0]])


def test_cli_prints_the_table(capsys):
    assert stats.main(["coverage", "--experiments", "200", "--resamples", "50"]) == 0
    out = capsys.readouterr().out
    assert "| normal | 5 |" in out and "| exponential | 10 |" in out
