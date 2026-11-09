"""WP10: the output sanity check (pure functions; thresholds from decisions.md, decision 5)."""

from __future__ import annotations

import random

import pytest

from smallpc import sanity


def healthy(n: int = 512, seed: int = 1) -> list[int]:
    rng = random.Random(seed)
    return [rng.randrange(0, 5000) for _ in range(n)]


def test_metric_formulas_by_hand():
    assert sanity.distinct_ngram_ratio([1, 2, 3, 4, 5], 4) == 1.0  # 2 four-grams, both distinct
    assert sanity.distinct_ngram_ratio([7] * 6, 4) == pytest.approx(
        1 / 3
    )  # 3 four-grams, 1 distinct
    assert sanity.distinct_ngram_ratio([1, 2, 3], 4) == 0.0  # shorter than n
    assert sanity.longest_run([1, 1, 2, 2, 2, 2, 1]) == 4 and sanity.longest_run([]) == 0
    seq = [1, 2, 3, 4, 5, 6, 7, 8] * 3  # the 8-gram 1..8 occurs 3 times (shifts give others)
    assert sanity.max_ngram_repeat(seq, 8) == 3
    assert sanity.max_ngram_repeat([1, 2, 3], 8) == 0
    assert sanity.first_divergence([1, 2, 3], [1, 2, 9]) == 2
    assert sanity.first_divergence([1, 2], [1, 2, 3, 4]) == 2  # a prefix diverges at its end
    assert sanity.first_divergence([5, 6], [5, 6]) is None


def test_healthy_output_passes():
    ref, cand = healthy(512, 1), healthy(512, 2)
    p = sanity.check_prompt(cand, ref)
    assert p["ok"] and p["reasons"] == []
    assert p["first_divergence"] == 0 or p["first_divergence"] > 0  # information only
    assert p["candidate"]["distinct_4gram_ratio"] > 0.99


def test_identical_output_passes_with_no_divergence():
    ref = healthy()
    p = sanity.check_prompt(list(ref), ref)
    assert p["ok"] and p["first_divergence"] is None


def test_repetition_loop_fails_on_ngram_ratio_and_repeat_count():
    ref = healthy()
    loop = healthy(40, 3) + [11, 12, 13, 14, 15, 16, 17, 18] * 60  # 8-gram repeated 60 times
    p = sanity.check_prompt(loop[:512], ref)
    assert not p["ok"]
    text = " ".join(p["reasons"])
    assert "distinct 4-gram ratio" in text and "8-gram repeats" in text


def test_too_short_output_fails_on_length():
    ref = healthy(512)
    p = sanity.check_prompt(healthy(99, 4), ref)  # min(100, 256) = 100
    assert not p["ok"] and "length 99 is below 100" in p["reasons"][0]
    assert sanity.check_prompt(healthy(100, 4), ref)["ok"]  # exactly 100 is fine


def test_length_floor_is_half_of_a_short_reference():
    ref = healthy(120)  # half is 60
    assert not sanity.check_prompt(healthy(59, 5), ref)["ok"]
    assert sanity.check_prompt(healthy(60, 5), ref)["ok"]


def test_run_of_one_token_fails_unless_the_reference_has_it_too():
    ref = healthy()
    run16 = healthy(200, 6) + [42] * 16 + healthy(200, 7)
    p = sanity.check_prompt(run16, ref)
    assert not p["ok"] and any("one token repeated 16 times" in r for r in p["reasons"])
    run15 = healthy(200, 6) + [42] * 15 + healthy(200, 7)
    assert sanity.check_prompt(run15, ref)["ok"]  # 15 is below the limit
    ref_run = healthy(200, 8) + [9] * 20 + healthy(200, 9)
    assert sanity.check_prompt(run16, ref_run)["ok"]  # the reference has such a run: not a failure


def test_repeated_8gram_rule_on_its_own():
    ref = healthy()
    gram = [101, 102, 103, 104, 105, 106, 107, 108]
    body = healthy(300, 10)
    cand = body[:100] + gram * 8 + body[100:]  # 8 repeats, but the 4-gram ratio stays high enough
    p = sanity.check_prompt(cand, ref)
    assert not p["ok"] and any("8-gram repeats" in r for r in p["reasons"])
    cand7 = body[:100] + gram * 7 + body[100:]
    assert not any("8-gram" in r for r in sanity.check_prompt(cand7, ref)["reasons"])


def test_distinct_4gram_rule_on_its_own():
    ref = healthy()
    # 4-gram ratio about 0.4 with no long run and no 8-gram repeated 8 times
    pat = healthy(5, 11)
    cand = (pat * 4 + healthy(3, 12)) * 12  # period 23, repeats 12 times: 8-gram repeats 12 -> also
    p = sanity.check_prompt(cand[:512], ref)
    assert not p["ok"] and any("distinct 4-gram ratio" in r for r in p["reasons"])


def test_candidate_passes_only_if_no_prompt_fails():
    ref = {f"p{i}": healthy(512, i) for i in range(3)}
    good = {k: healthy(512, 50 + i) for i, k in enumerate(ref)}
    assert sanity.check_candidate(good, ref)["result"] == "pass"
    bad = dict(good, p1=[7] * 512)
    r = sanity.check_candidate(bad, ref)
    assert r["result"] == "fail" and r["failed_prompts"] == ["p1"]
    missing = {k: v for k, v in good.items() if k != "p2"}
    assert sanity.check_candidate(missing, ref)["result"] == "not run"
    assert sanity.check_candidate({}, {})["result"] == "not run"
