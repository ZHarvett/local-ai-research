"""Near-tie logic on synthetic data (no GPU)."""

from __future__ import annotations

import math

import pytest

from smallpc import neartie
from smallpc.neartie import NEAR_TIE_NATS, classify, first_divergence, gaps_of, top2_gap


def item(*logprobs: float) -> dict:
    return {
        "id": 1,
        "logprob": logprobs[0],
        "top_logprobs": [{"id": i, "logprob": lp} for i, lp in enumerate(logprobs)],
    }


def test_threshold_is_half_a_nat():
    assert NEAR_TIE_NATS == 0.5


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ([1, 2, 3], [1, 2, 3], None),
        ([1, 2, 3], [1, 9, 3], 1),
        ([5], [6], 0),
        ([1, 2], [1, 2, 3], 2),  # one run stopped earlier
        ([], [], None),
        ([], [1], 0),
    ],
)
def test_first_divergence(a, b, expected):
    assert first_divergence(a, b) == expected


def test_top2_gap_logprob_format():
    assert top2_gap(item(-0.1, -0.4, -3.0)) == pytest.approx(0.3)
    # order of alternatives does not matter
    unordered = {"top_logprobs": [{"logprob": -2.0}, {"logprob": -0.5}, {"logprob": -1.0}]}
    assert top2_gap(unordered) == pytest.approx(0.5)


def test_top2_gap_post_sampling_probs_format():
    it = {"prob": 0.6, "top_probs": [{"id": 1, "prob": 0.6}, {"id": 2, "prob": 0.3}]}
    assert top2_gap(it) == pytest.approx(math.log(2))


def test_top2_gap_nested_probs_layout():
    assert top2_gap({"probs": [item(-0.2, -0.3)]}) == pytest.approx(0.1)


@pytest.mark.parametrize("bad", [None, {}, {"top_logprobs": []}, item(-0.1)])
def test_top2_gap_unavailable(bad):
    assert top2_gap(bad) is None


def test_identical_runs():
    d = classify([1, 2, 3], [1, 2, 3])
    assert d.identical and d.ok and d.verdict == "identical" and d.position is None


@pytest.mark.parametrize(
    ("gap", "verdict"),
    [
        (0.0, "near_tie"),
        (0.1, "near_tie"),
        (0.49, "near_tie"),
        (0.5, "real_divergence"),
        (2.0, "real_divergence"),
    ],
)
def test_gap_boundaries(gap, verdict):
    gaps = [5.0, gap, 5.0]
    d = classify([1, 2, 3], [1, 9, 3], gaps, gaps)
    assert d.verdict == verdict and d.position == 1 and d.gap_nats == pytest.approx(gap)
    assert d.ok == (verdict == "near_tie")


def test_only_the_first_divergence_counts():
    # later positions diverge too, but only position 1 matters; its gap is tiny
    d = classify([1, 2, 3, 4], [1, 9, 8, 7], [9, 0.1, 0.1, 0.1], [9, 0.1, 9.0, 9.0])
    assert d.position == 1 and d.verdict == "near_tie"


def test_gap_source_prefers_run_b_then_falls_back_to_run_a():
    d = classify([1, 2], [1, 9], gaps_a=[9, 0.2], gaps_b=[9, None])
    assert d.gap_source == "run_a" and d.verdict == "near_tie"
    d = classify([1, 2], [1, 9], gaps_a=[9, 0.2], gaps_b=[9, 0.4])
    assert d.gap_source == "run_b" and d.gap_nats == pytest.approx(0.4)
    d = classify([1, 2], [1, 9], gaps_a=[9, 0.2], gaps_b=[9, 0.4], prefer="a")
    assert d.gap_source == "run_a"


def test_missing_gap_is_not_a_near_tie():
    d = classify([1, 2], [1, 9], gaps_a=[], gaps_b=[])
    assert d.verdict == "unclassified" and not d.ok and d.gap_nats is None
    assert "no top-2 gap" in d.reason


def test_length_difference_uses_gap_at_the_shorter_length():
    d = classify([1, 2], [1, 2, 3], gaps_a=[0, 0], gaps_b=[0, 0, 0.3])
    assert d.position == 2 and d.verdict == "near_tie"


def test_gaps_of_and_as_dict():
    gaps = gaps_of([item(-0.1, -0.2), {}, item(-1.0, -4.0)])
    assert gaps == [pytest.approx(0.1), None, pytest.approx(3.0)]
    assert gaps_of(None) == []
    assert classify([1], [2], [0.1], [0.1]).as_dict()["verdict"] == "near_tie"
    assert neartie.classify([1], [1]).as_dict()["identical"] is True
