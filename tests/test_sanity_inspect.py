"""tools/sanity_inspect.py: counts and indices of repeated 8-grams, no text (WP12 part 2g)."""

from __future__ import annotations

import importlib.util
import json

import pytest

from conftest import REPO
from smallpc import sanity

spec = importlib.util.spec_from_file_location(
    "sanity_inspect", REPO / "tools" / "sanity_inspect.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

PHRASE = [101, 102, 103, 104, 105, 106, 107, 108]


def filler(n, start=1000):
    return list(range(start, start + n))


def test_a_loop_is_found_with_its_indices_and_equal_gaps():
    toks = filler(5) + PHRASE + filler(2, 2000) + PHRASE + filler(2, 3000) + PHRASE
    toks += filler(2, 4000) + PHRASE + filler(20, 5000)
    c = tool.characterise(toks, filler(60))
    assert c["distinct_8grams_repeating_4_or_more"] == 1
    top = c["top_8gram"]
    assert top["count"] == 4 and top["start_indices"] == [5, 15, 25, 35]
    assert top["gaps"] == [10, 10, 10] and top["pattern"] == "loop"
    assert c["max_8gram_repeat"] == 4 == sanity.max_ngram_repeat(toks)
    assert c["first_divergence"] == 5 and top["first_occurrence_after_divergence"] is True


def test_clustered_and_scattered_and_nothing_repeating():
    toks = PHRASE + filler(3) + PHRASE + filler(9, 2000) + PHRASE + filler(4, 3000) + PHRASE
    c = tool.characterise(toks, toks)
    assert c["top_8gram"]["pattern"] == "clustered" and c["first_divergence"] is None
    assert c["top_8gram"]["first_occurrence_after_divergence"] is None
    far = PHRASE + filler(100) + PHRASE + filler(150, 2000) + PHRASE + filler(100, 3000) + PHRASE
    assert tool.characterise(far, far[:1])["top_8gram"]["pattern"] == "scattered"
    clean = tool.characterise(filler(200), filler(200))
    assert clean["distinct_8grams_repeating_4_or_more"] == 0
    assert clean["top_8gram"]["count"] == 1


def test_overlapping_runs_count_once_like_the_sanity_metric():
    toks = [7] * 40  # one 8-gram, non-overlapping: 5 occurrences
    c = tool.characterise(toks, filler(40))
    assert c["max_8gram_repeat"] == 5 == sanity.max_ngram_repeat(toks)
    assert c["top_8gram"]["start_indices"] == [0, 8, 16, 24, 32]


def test_inspect_writes_no_text_or_token_ids(tmp_path):
    ref = {f"sanity-v5-2048-r{i}": filler(300, 10 * i) for i in range(3)}
    bad = PHRASE * 5 + filler(260, 9000)

    def fake_run_cell(cell, **kw):
        toks = {k: list(v) for k, v in ref.items()}
        if cell["name"] == "bad":
            toks["sanity-v5-2048-r0"] = bad
        return {"run_id": "x", "tokens": toks, "stop_types": {}, "timings": {}, "error": None}

    for name in ("ref", "bad"):
        d = tmp_path / "data" / "raw" / "s" / "resolved"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.toml").write_text("profile = 'candidate'\n")
    res = tool.inspect(
        ["bad"], "ref", root=tmp_path, run_cell=fake_run_cell, require_lock=False,
        provider=object(),
    )  # fmt: skip
    r0 = res["cells"]["bad"]["prompts"]["sanity-v5-2048-r0"]
    assert r0["top_8gram"]["count"] == 5 and r0["top_8gram"]["pattern"] == "loop"
    assert res["cells"]["bad"]["prompts"]["sanity-v5-2048-r1"]["first_divergence"] is None
    blob = json.dumps(res)
    assert "tokens" not in blob.replace("no generated text and no token ids", "")
    for p in res["cells"]["bad"]["prompts"].values():
        assert set(p) == {"length", "distinct_8grams_repeating_4_or_more", "max_8gram_repeat",
                          "first_divergence", "top_8gram"}  # fmt: skip
    assert "bad" in tool.format_table(res)


def test_a_failed_reference_is_an_error(tmp_path):
    d = tmp_path / "data" / "raw" / "s" / "resolved"
    d.mkdir(parents=True)
    (d / "ref.toml").write_text("x = 1\n")
    (d / "c.toml").write_text("x = 1\n")

    def failing(cell, **kw):
        return {"run_id": "x", "tokens": {}, "error": {"stage": "start"}}

    with pytest.raises(tool.sanity_runner.SanityError, match="reference run failed"):
        tool.inspect(["c"], "ref", root=tmp_path, run_cell=failing, require_lock=False,
                     provider=object())  # fmt: skip
