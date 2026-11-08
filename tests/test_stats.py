from __future__ import annotations

import math

import pytest

from smallpc import stats


def test_known_values_n5():
    s = stats.summarize([1, 2, 3, 4, 5])
    assert (s["n"], s["mean"], s["min"], s["max"]) == (5, 3.0, 1.0, 5.0)
    half = 2.776 * math.sqrt(2.5) / math.sqrt(5)  # t(0.975, df 4) * s / sqrt(n)
    assert s["t_ci"] == pytest.approx([3 - half, 3 + half])
    lo, hi = s["bootstrap_ci"]
    assert 1.0 <= lo < 3 < hi <= 5.0
    assert hi - lo < 2 * half  # the bootstrap interval is the narrower one at n = 5
    assert s["ci_method"] == "t"
    assert s["ci"] == s["t_ci"]  # the wider of the two is the CI to use


def test_ci_is_the_wider_interval():
    for vals in ([10, 12, 11, 13, 9], [1.0, 1.0, 1.0, 50.0], list(range(40))):
        s = stats.summarize(vals)
        widths = {
            "t": s["t_ci"][1] - s["t_ci"][0],
            "bootstrap": s["bootstrap_ci"][1] - s["bootstrap_ci"][0],
        }
        assert s["ci"][1] - s["ci"][0] == pytest.approx(max(widths.values()))


def test_n1_ci_unavailable():
    s = stats.summarize([7.5])
    assert (s["n"], s["mean"], s["min"], s["max"]) == (1, 7.5, 7.5, 7.5)
    assert s["ci"] is None and s["bootstrap_ci"] is None and s["t_ci"] is None
    assert "unavailable" in s["ci_method"]
    assert stats.ci_halfwidth(s) is None


def test_n2_has_a_ci_using_df1():
    s = stats.summarize([10.0, 12.0])
    assert s["mean"] == 11.0
    # sample sd = sqrt(2); half = 12.706 * sqrt(2) / sqrt(2)
    assert s["t_ci"] == pytest.approx([11 - 12.706, 11 + 12.706])
    assert s["bootstrap_ci"][0] >= 10.0 and s["bootstrap_ci"][1] <= 12.0
    assert s["ci_method"] == "t"
    assert stats.ci_halfwidth(s) == pytest.approx(12.706)


def test_constant_values_have_zero_width():
    s = stats.summarize([4.0] * 5)
    assert s["ci"] == [4.0, 4.0]


def test_deterministic_with_fixed_seed():
    vals = [3.1, 4.1, 5.9, 2.6, 5.3]
    assert stats.summarize(vals) == stats.summarize(list(vals))
    assert stats.bootstrap_ci(vals) == stats.bootstrap_ci(vals)
    many = [float(i * i % 17) for i in range(20)]
    assert stats.bootstrap_ci(many, seed=1) != stats.bootstrap_ci(many, seed=2)


def test_t_table_edges():
    assert stats.t_critical(1) == 12.706
    assert stats.t_critical(4) == 2.776
    assert stats.t_critical(30) == 2.042
    assert stats.t_critical(31) == 1.96
    assert stats.t_critical(500) == 1.96
    assert len(stats.T_CRIT_95) == 30
    with pytest.raises(ValueError):
        stats.t_critical(0)


def test_empty_raises():
    with pytest.raises(ValueError):
        stats.summarize([])
