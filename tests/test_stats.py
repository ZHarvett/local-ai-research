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


# ------------------------------------------------------------------------------ paired (WP10)


def test_paired_difference_known_values():
    b = {0: 9.0, 1: 11.0, 2: 11.5, 3: 12.0, 4: 12.5}
    a = {k: v + dv for (k, v), dv in zip(b.items(), [1.0, 1.2, 0.9, 1.1, 0.8], strict=True)}
    d = stats.paired_difference(a, b)
    assert d["n"] == 5 and d["keys"] == [0, 1, 2, 3, 4]
    assert d["differences"] == pytest.approx([1.0, 1.2, 0.9, 1.1, 0.8])
    assert d["mean"] == pytest.approx(1.0)
    # by hand: deviations 0, .2, -.1, .1, -.2 -> variance .025 -> half = 2.776 * sqrt(.025 / 5)
    half = 2.776 * math.sqrt(0.025 / 5)
    assert d["t_ci"] == pytest.approx([1.0 - half, 1.0 + half])
    s = stats.summarize(d["differences"])
    assert d["bootstrap_ci"] == s["bootstrap_ci"] and d["ci"] == s["ci"]
    assert d["ci"] == d["t_ci"] and d["ci_method"] == "t"  # the wider of the two at n = 5
    assert d["excludes_zero"] is True


def test_paired_difference_matches_on_keys_not_position():
    a = {("s", 0): 5.0, ("s", 1): 6.0, ("s", 2): 7.0}
    b = {("s", 2): 5.0, ("s", 0): 4.0, ("s", 9): 100.0}  # only 0 and 2 are in both
    d = stats.paired_difference(a, b)
    assert d["n"] == 2 and d["keys"] == [("s", 0), ("s", 2)]
    assert d["differences"] == [1.0, 2.0]


def test_paired_difference_that_includes_zero():
    d = stats.paired_difference([5.0, 6.0, 7.0, 8.0, 9.0], [5.5, 5.5, 7.5, 7.5, 9.5])
    assert d["excludes_zero"] is False and d["ci"][0] < 0 < d["ci"][1]


def test_paired_difference_small_and_empty_inputs():
    one = stats.paired_difference({0: 2.0}, {0: 1.0})
    assert one["n"] == 1 and one["mean"] == 1.0 and one["ci"] is None
    assert one["excludes_zero"] is None  # no CI for n = 1: no claim either way
    none = stats.paired_difference({0: 1.0}, {1: 1.0})
    assert none["n"] == 0 and none["mean"] is None and none["excludes_zero"] is None


def test_paired_difference_rejects_mismatched_inputs():
    with pytest.raises(ValueError, match="different length"):
        stats.paired_difference([1.0, 2.0], [1.0])
    with pytest.raises(TypeError, match="mappings"):
        stats.paired_difference({0: 1.0}, [1.0])


def test_paired_ratio_is_the_geometric_mean_of_ratios():
    r = stats.paired_ratio([2.0, 8.0, 4.0], [1.0, 2.0, 2.0])  # ratios 2, 4, 2
    assert r["n"] == 3 and r["ratios"] == pytest.approx([2.0, 4.0, 2.0])
    assert r["geomean"] == pytest.approx((2 * 4 * 2) ** (1 / 3))
    lo, hi = r["ci"]
    assert 2.0 <= lo <= r["geomean"] <= hi <= 4.0
    assert r["ci_method"] == "bootstrap"
    again = stats.paired_ratio([2.0, 8.0, 4.0], [1.0, 2.0, 2.0])
    assert again["ci"] == r["ci"]  # fixed seed: reproducible


def test_paired_ratio_of_equal_series_is_one():
    r = stats.paired_ratio({0: 3.0, 1: 5.0}, {0: 3.0, 1: 5.0})
    assert r["geomean"] == pytest.approx(1.0) and r["ci"] == pytest.approx([1.0, 1.0])


def test_paired_ratio_rejects_non_positive_values_with_a_clear_error():
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError, match="positive values; a has"):
            stats.paired_ratio([1.0, bad], [1.0, 1.0])
        with pytest.raises(ValueError, match="positive values; b has"):
            stats.paired_ratio([1.0, 1.0], [1.0, bad])


def test_paired_ratio_small_inputs():
    one = stats.paired_ratio([4.0], [2.0])
    assert one["geomean"] == pytest.approx(2.0) and one["ci"] is None
    assert "unavailable" in one["ci_method"]
    assert stats.paired_ratio({0: 1.0}, {1: 1.0})["n"] == 0
