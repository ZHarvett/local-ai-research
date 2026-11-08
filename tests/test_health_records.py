"""Pure helpers of smallpc.health (no GPU, no server)."""

from __future__ import annotations

import json

import pytest

from smallpc import health
from smallpc.health import (
    Recorder,
    aggregate,
    aggregate_acceptance,
    chatml,
    draft_verdict,
    dump_toml,
    pack_to_tokens,
    template_hash,
    user_turn,
    variant_config,
)


def test_fail_without_explanation_is_a_bug():
    rec = Recorder("T")
    rec.add("x.ok", "fine", True)
    with pytest.raises(ValueError, match="needs an explanation"):
        rec.add("x.bad", "broken", False)
    rec.add("x.bad", "broken", False, explanation="because")
    assert [c["status"] for c in rec.checks] == ["PASS", "FAIL"]
    assert rec.failed()[0]["explanation"] == "because"


def test_record_truncates_long_evidence():
    rec = Recorder("T")
    rec.add("x", "n", True, response={"text": "a" * 5000, "items": list(range(100))})
    r = rec.checks[0]["response"]
    assert len(r["text"]) < 400 and r["text"].endswith("[5000 chars]")
    assert r["items"][-1] == "...[100 items]"


def test_acceptance_is_sum_over_sum_not_mean_of_ratios():
    runs = [
        {"draft_n": 100, "draft_n_accepted": 90, "predicted_n": 512},
        {"draft_n": 400, "draft_n_accepted": 100, "predicted_n": 512},
        {"predicted_n": 512},  # no draft fields at all (absent, not zero)
    ]
    agg = aggregate_acceptance(runs)
    assert agg["draft_n"] == 500 and agg["draft_n_accepted"] == 190
    assert agg["acceptance"] == pytest.approx(0.38)  # mean of ratios would be 0.575
    assert agg["per_prompt"][2]["acceptance"] is None
    assert aggregate_acceptance([{}])["acceptance"] is None


def test_template_hash_ignores_whitespace_only():
    a = "{%- if x %}\n   hello   {{ y }}\n{%- endif %}"
    b = "{%- if x %} hello {{ y }} {%- endif %}"
    assert template_hash(a) == template_hash(b)
    assert template_hash(a) != template_hash(a.replace("hello", "hallo"))
    assert len(template_hash(a)) == 64


def test_chatml_matches_the_template_example_format():
    # shape taken from the real startup log: "example_format" of the embedded template
    assert chatml("S", "U", thinking=True) == (
        "<|im_start|>system\nS<|im_end|>\n<|im_start|>user\nU<|im_end|>\n<|im_start|>assistant\n<think>\n"
    )
    assert chatml("S", "U", thinking=False).endswith(
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    assert user_turn("Q").startswith("<|im_start|>user\nQ<|im_end|>\n<|im_start|>assistant\n")


CTL = {"draft_n": 100, "draft_n_accepted": 70}
CTL2 = {"draft_n": 104, "draft_n_accepted": 71}


def test_draft_verdict_preserved_when_inside_control_variation():
    v = draft_verdict(CTL, CTL2, {"draft_n": 102, "draft_n_accepted": 70})
    assert v["verdict"] == "draft_state_preserved"
    assert draft_verdict(CTL, CTL, {"draft_n": 100, "draft_n_accepted": 70})["verdict"] == (
        "draft_state_preserved"
    )


def test_draft_verdict_detects_lower_acceptance_or_fewer_drafts():
    low = draft_verdict(CTL, CTL2, {"draft_n": 100, "draft_n_accepted": 30})
    assert low["verdict"] == "draft_state_lost_or_degraded"
    fewer = draft_verdict(CTL, CTL2, {"draft_n": 20, "draft_n_accepted": 14})
    assert fewer["verdict"] == "draft_state_lost_or_degraded"
    assert "acceptance arm" in low["detail"]


def test_draft_verdict_edge_cases():
    assert draft_verdict(CTL, CTL2, {})["verdict"] == "no_drafting"
    assert (
        draft_verdict({}, CTL2, {"draft_n": 5, "draft_n_accepted": 5})["verdict"] == "inconclusive"
    )


def test_pack_to_tokens_binary_search():
    lines = [f"line {i}\n" for i in range(1000)]
    count = lambda text: len(text.split())  # noqa: E731  (2 "tokens" per line)
    kept = pack_to_tokens(lines, count, 100)
    assert len(kept) == 50 and count("".join(kept)) <= 100
    assert len(pack_to_tokens(lines[:3], count, 1000)) == 3
    assert len(pack_to_tokens(lines, count, 0)) == 1  # never empty


def test_toml_roundtrip_and_none_removes_a_field():
    import tomllib

    cfg = variant_config(
        {"spec_type": "draft-mtp", "spec_draft_n_max": 2, "log_verbosity": None, "cache_ram": 0}
    )
    assert "log_verbosity" not in cfg and cfg["cache_ram"] == 0 and cfg["profile"] == "candidate"
    assert tomllib.loads(dump_toml(cfg)) == cfg
    # the generated variants are valid server configs (schema + stock rules intact)
    from smallpc.config import ServerConfig

    ServerConfig.model_validate(cfg)
    ServerConfig.model_validate(variant_config(health.cmoe_overrides(log_verbosity=4)))


def test_aggregate_collects_phase_files(tmp_path):
    for name, status in (("A", "PASS"), ("B", "FAIL")):
        (tmp_path / f"phase-{name}.json").write_text(
            json.dumps(
                {
                    "checks": [{"id": name, "status": status}],
                    "servers": [{"phase": name}],
                    f"phase_{name.lower()}": {"x": 1},
                    "s4a_pass": name == "A",
                }
            )
        )
    doc = aggregate(tmp_path, "2026-11-08", {"e": 1})
    assert doc["summary"]["counts"] == {"PASS": 1, "FAIL": 1}
    assert doc["summary"]["failed_checks"] == ["B"]
    assert len(doc["servers"]) == 2 and doc["phase_a"] == {"x": 1}


def test_committed_endpoints_files_are_complete():
    """Every committed data/health/endpoints-*.json: PASS/FAIL per check, FAILs explained."""
    from conftest import REPO

    files = sorted((REPO / "data/health").glob("endpoints-*.json"))
    for f in files:
        doc = json.loads(f.read_text())
        assert doc["checks"], f.name
        for c in doc["checks"]:
            assert c["status"] in ("PASS", "FAIL"), (f.name, c["id"])
            assert c["id"] and c["name"] and c["phase"]
            if c["status"] == "FAIL":
                assert c["explanation"], (f.name, c["id"])
        counts = doc["summary"]["counts"]
        assert counts["PASS"] + counts["FAIL"] == len(doc["checks"])
        assert doc["summary"]["failed_checks"] == [
            c["id"] for c in doc["checks"] if c["status"] == "FAIL"
        ]
