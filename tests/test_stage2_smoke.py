"""The smoke start (one request with changed settings) against the mock server."""

from __future__ import annotations

import json

import pytest

from conftest import FIXTURES, REPO
from smallpc.sanity_runner import SanityError
from smallpc.stage2 import cli, smoke
from sweep_fakes import MOCK, SynthProvider


@pytest.fixture
def rig(tmp_path, free_port):
    machine = tmp_path / "machine.toml"
    machine.write_text(
        f'[paths]\nllama_server="{MOCK}"\nmodels_dir="{tmp_path}"\n'
        f'slot_save_dir="/dev/shm/local-ai-research-slots"\n[server]\nport={free_port}\n'
    )
    d = tmp_path / "data/raw/s1/resolved"
    d.mkdir(parents=True)
    (d / "P6-32K-b4096.toml").write_text(
        'profile = "candidate"\ncontext = 32768\ncpu_moe = true\nmoe_cache_mib = 1024\n'
        "metrics = true\nlog_verbosity = 4\n"
    )
    return tmp_path, machine


def run(rig, overrides, **kw):
    tmp, machine = rig
    return smoke.run_smoke(
        "P6-32K-b4096", overrides, tmp / "out/smoke.json", root=tmp, scratch=tmp / "scratch",
        scripts_dir=REPO / "scripts", log_root=tmp / "logs", machine=machine,
        model_config=FIXTURES / "model.toml", provider=SynthProvider(),
        server_env={"SMALLPC_GPU_LOCK_FILE": str(tmp / "lock"), "MOCK_BEHAVIOR": "{}"},
        require_lock=False, health_timeout=30, **kw,
    )  # fmt: skip


def test_the_override_is_applied_the_server_answers_and_memory_is_recorded(rig):
    res = run(rig, {"load_mode": "none"})
    assert res["ok"] and res["label"] == "functional-test" and res["error"] is None
    assert (
        res["effective_fields"]["load_mode"] == "none"
        and res["effective_fields"]["cpu_moe"] is True
    )
    assert res["request"]["predicted_n"] == 64 and res["request"]["http_status"] == 200
    assert res["memory_after_load"]["rss_anon_kib"] > 0 and res["memory_peak"]["rss_anon_kib"] > 0
    assert res["stop"]["method"] in ("sigint", "already_exited")
    toml = (rig[0] / "scratch/smoke-P6-32K-b4096.toml").read_text()
    assert 'load_mode = "none"' in toml and "cpu_moe = true" in toml
    assert json.loads((rig[0] / "out/smoke.json").read_text())["run_id"].startswith("ft-smoke-")


def test_an_invalid_override_is_refused_before_a_server_starts(rig):
    with pytest.raises(ValueError):
        run(rig, {"load_mode": "bogus"})


def test_a_server_that_does_not_start_is_reported(rig, monkeypatch):
    tmp, machine = rig
    res = smoke.run_smoke(
        "P6-32K-b4096", {}, tmp / "o.json", root=tmp, scratch=tmp / "s", scripts_dir=REPO / "scripts",
        log_root=tmp / "logs", machine=machine, model_config=FIXTURES / "model.toml",
        server_env={"SMALLPC_GPU_LOCK_FILE": str(tmp / "lock"), "MOCK_BEHAVIOR": json.dumps({"oom_at_start": True})},
        require_lock=False, health_timeout=30,
    )  # fmt: skip
    assert not res["ok"] and res["error"]["stage"] == "start" and res["log_tail"]


def test_lock_guard_sets_and_cli(rig, monkeypatch, capsys):
    monkeypatch.delenv("SMALLPC_GPU_LOCK_HELD", raising=False)
    with pytest.raises(SanityError, match="GPU lock is not held"):
        smoke.run_smoke("x", {}, rig[0] / "o.json", scratch=rig[0], root=rig[0])
    assert smoke.parse_sets(["load_mode=none", "threads=8", "metrics=true"]) == {
        "load_mode": "none", "threads": 8, "metrics": True,
    }  # fmt: skip
    with pytest.raises(SanityError):
        smoke.parse_sets(["nonsense"])
    assert cli.main(["smoke", "--base-cell", "x", "--out", str(rig[0] / "o.json")]) == 2
    assert "GPU lock is not held" in capsys.readouterr().err
