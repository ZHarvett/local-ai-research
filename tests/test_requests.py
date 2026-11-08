"""smallpc.requests: server-log request parser and main/auxiliary classifier."""

from __future__ import annotations

import json

from conftest import FIXTURES
from smallpc import requests as rq

LOG = (FIXTURES / "logs/requests-opencode.txt").read_text()
OC = (FIXTURES / "logs/opencode-debug.txt").read_text()


def test_parse_server_requests_in_task_order_with_cache_n():
    r = rq.parse_server_requests(LOG)
    assert [x["task"] for x in r] == [0, 2, 105]
    assert (r[0]["prompt_n"], r[0]["cache_n"], r[0]["predicted_n"]) == (410, 0, 20)
    assert (r[2]["prompt_n"], r[2]["cache_n"], r[2]["prompt_total"]) == (379, 9021, 9400)
    assert r[0]["time_ms"] == 700.0 and r[0]["prompt_ms"] == 300.0 and r[0]["predicted_ms"] == 400
    assert [x["truncated"] for x in r] == [False, False, True]


def test_unfinished_and_internal_tasks_are_skipped():
    unfinished = "slot   operator(): id  1 | task 200 | new prompt, n_ctx_slot = 1, n_keep = 0, "
    log = LOG + f"0.14.0 I {unfinished}task.n_tokens = 5\n"
    assert [x["task"] for x in rq.parse_server_requests(log)] == [0, 2, 105]


def test_opencode_calls_classify_the_title_request_and_cross_check_by_size():
    calls = rq.opencode_calls(OC)
    assert [(c["small"], c["agent"]) for c in calls] == [
        (True, "title"),
        (False, "build"),
        (False, "build"),
    ]
    p = rq.build_pattern("r1", "opencode", LOG, OC)
    assert [r["kind"] for r in p["requests"]] == ["auxiliary", "main", "main"]
    assert p["per_turn"]["requests_per_turn"] == 3 and p["per_turn"]["main_requests_per_turn"] == 2
    assert p["per_turn"]["totals"]["auxiliary"]["prompt_n"] == 410
    assert p["classification"]["classes_separate_by_prompt_size"] is True
    assert p["any_request_truncated"] is True
    assert p["label"] == "smoke-task data, not representative of real agent turns"
    assert "step plan 3.4" not in json.dumps(p)  # the label lives in the file, the citation in code


def test_count_mismatch_leaves_requests_unclassified_and_says_so():
    p = rq.build_pattern("r2", "opencode", LOG, "")
    assert {r["kind"] for r in p["requests"]} == {"unclassified"}
    assert p["per_turn"]["totals"]["unclassified"]["requests"] == 3
    assert p["classification"]["classes_separate_by_prompt_size"] is None


def test_dsh_main_steps_pick_the_largest_prompts():
    p = rq.build_pattern("r3", "dsh", LOG, "", main_steps=2)
    assert [r["kind"] for r in p["requests"]] == ["auxiliary", "main", "main"]
    assert "2 main-loop steps" in p["requests"][0]["classified_by"]
