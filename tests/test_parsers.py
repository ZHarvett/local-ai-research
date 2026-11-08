"""Log parsers against real (scrubbed) llama-server b12208 excerpts in tests/fixtures/logs/."""

from __future__ import annotations

import getpass
import socket

import pytest

from conftest import FIXTURES
from smallpc import parsers

LOGS = FIXTURES / "logs"


def fixture(name: str) -> str:
    return (LOGS / name).read_text()


# ------------------------------------------------------------------ startup / placement


def test_fit_placement_from_real_startup_log():
    p = parsers.parse_fit_placement(fixture("startup-health64k.txt"))
    assert p["fit_attempted"] and p["fit_succeeded"]
    assert p["n_ctx"] == 65536 and p["n_slots"] == 1 and p["n_ctx_slot"] == 65536
    assert p["fit_context_note"].endswith("no change")
    # --fit moved sparse experts of 15 of the 41 layers to the CPU; the first partial layer keeps
    # attention, up and gate on the GPU (overflow type GATE)
    assert (p["n_layer"], p["expert_layers_on_cpu"]) == (41, 15)
    assert p["first_partial_layer_overflow"] == "GATE"
    assert p["fit_layers"] == 41 and p["fit_overflowing_layers"] == 15
    assert p["fit_device_used_mib"] == pytest.approx(14709, abs=300)
    assert p["offloaded_layers"] == [42, 42] and p["load_mode"] == "mmap"
    assert p["model_buffers"]["CUDA0"]["mib"] == pytest.approx(13614.34, abs=0.1)
    assert p["model_buffers"]["CPU_Mapped"]["count"] == 41
    assert p["kv"] | {} == p["kv"] and p["kv"]["k_type"] == p["kv"]["v_type"] == "q8_0"
    assert p["kv"]["cells"] == 65536 and p["kv"]["mib"] == pytest.approx(680.0)
    assert p["recurrent_state_buffers"][0]["mib"] == pytest.approx(62.81)
    assert p["compute_buffers"][0] == {"device": "CUDA0", "mib": pytest.approx(350.02)}
    assert p["contexts"][0]["flash_attn"] == "enabled" and p["contexts"][0]["n_seq_max"] == 1
    assert p["prompt_cache"] == "8192 MiB"
    assert p["checkpoints"] == {"max": 32, "min_spacing": 8192}
    assert any("tensor overrides to CPU" in w for w in p["warnings"])


def test_mtp_startup_has_a_second_context():
    p = parsers.parse_fit_placement(fixture("startup-mtp-d2.txt"))
    assert len(p["contexts"]) >= 2  # target context and the MTP draft context
    assert p["n_slots"] == 1 and p["n_ctx"] == 65536
    assert any(b["mib"] == pytest.approx(259.54) for b in p["compute_buffers"])
    assert p["expert_layers_on_cpu"] > 15  # the draft context takes VRAM, so fit moves more


def test_empty_and_irrelevant_logs_parse_to_defaults():
    p = parsers.parse_fit_placement("")
    assert p["fit_attempted"] is False and p["contexts"] == [] and p["model_buffers"] == {}
    assert "n_slots" not in p
    assert parsers.parse_fit_placement("some other text\n")["fit_succeeded"] is False


# --------------------------------------------------------------------- expert cache


def test_moe_cache_stats_from_real_log():
    s = parsers.parse_moe_cache_stats(fixture("moe-cache-stats.txt"))
    assert s["present"] and s["classes"]
    c = s["classes"][0]
    assert c["name"] == "ubatch <= 8"
    assert c["hits"] > 0 and c["misses"] > 0
    assert c["hit_rate_pct"] == pytest.approx(100 * c["hits"] / (c["hits"] + c["misses"]), abs=0.01)
    hits = sum(x["hits"] for x in s["classes"])
    total = hits + sum(x["misses"] for x in s["classes"])
    assert s["overall_hit_rate_pct"] == pytest.approx(100 * hits / total, abs=0.01)
    assert s["large_batch_copies"]["experts"] > 0
    assert s["config"]["cache_mib"] == pytest.approx(4094, abs=2)
    assert s["config"]["host_expert_mib"] == pytest.approx(18600, abs=1)


def test_moe_cache_stats_synthetic_two_classes_and_absent():
    log = (
        "0.1 I llama_moe_cache: ubatch <= 8: hits = 90, misses = 10 (0 on the CPU), "
        "hit rate = 90.00%, uploaded = 5.00 MiB\n"
        "0.2 I llama_moe_cache: ubatch  > 8: hits = 10, misses = 90 (3 on the CPU), "
        "hit rate = 10.00%, uploaded = 7.50 MiB\n"
    )
    s = parsers.parse_moe_cache_stats(log)
    assert [c["name"] for c in s["classes"]] == ["ubatch <= 8", "ubatch > 8"]
    assert s["classes"][1]["cpu"] == 3 and s["overall_hit_rate_pct"] == 50.0
    none = parsers.parse_moe_cache_stats("nothing here\n")
    assert none == {"present": False, "classes": [], "overall_hit_rate_pct": None}


# ----------------------------------------------------- checkpoints, speculation, sources


def test_checkpoints_from_real_log():
    c = parsers.parse_checkpoints(fixture("cache-source-prompt-cache.txt"))
    assert c["created"] >= 1 and len(c["created_detail"]) == c["created"]
    d = c["created_detail"][0]
    assert d["max"] == 32 and d["pos_min"] == d["pos_max"] and d["n_tokens"] == d["pos_max"] + 1
    assert parsers.parse_checkpoints("")["created"] == 0


def test_spec_stats_from_real_log():
    stats = parsers.parse_spec_stats(fixture("cache-source-slot-restore.txt"))
    assert stats
    for s in stats:
        assert s["ratio"] == pytest.approx(s["accepted"] / s["generated"], abs=1e-4)
        assert s["mean_len"] >= 1.0


def test_cache_source_slot_restore():
    action = fixture("cache-source-slot-restore.txt")
    src = parsers.parse_cache_source(action, "no prompt cache lines", 180, 181)
    assert src["verdict"] == "slot_restore" and src["restored_tokens"] == 181
    assert src["draft_state_restored_from_slot_file"] and src["draft_state_mib"] > 0


def test_cache_source_prompt_cache_wins_over_a_restore():
    seg = "0.1 I srv  load: - found better prompt with f_keep = 0.250, f_sim = 0.900\n"
    src = parsers.parse_cache_source("", seg, 180)
    assert src["verdict"] == "prompt_cache" and src["prompt_cache_f_sim"] == 0.9
    both = parsers.parse_cache_source("", seg, 180, restored_tokens=181)
    assert both["verdict"] == "prompt_cache"


def test_cache_source_slot_memory_and_none():
    assert parsers.parse_cache_source("", "", 100)["verdict"] == "slot_memory"
    assert parsers.parse_cache_source("", "", 0)["verdict"] == "none"
    assert parsers.parse_cache_source("", "", None, restored_tokens=5)["verdict"] == "none"


# ------------------------------------------------------------------------- privacy


def test_scrub_log():
    text = "load /home/someone/models/m.gguf and /home/someone/x; user someone\n"
    out = parsers.scrub_log(text, "/home/someone/", extra=("someone",))
    assert "/home/someone" not in out and "~/models/m.gguf" in out
    assert parsers.scrub_log("abc", "") == "abc"


@pytest.mark.parametrize("path", sorted(LOGS.glob("*.txt")), ids=lambda p: p.name)
def test_fixtures_contain_no_personal_data(path):
    text = path.read_text()
    for needle in ("/home/", getpass.getuser(), socket.gethostname()):
        if len(needle) > 3:
            assert needle not in text, f"{needle!r} in {path.name}"
