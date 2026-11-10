"""The output sanity runner against the mock server (WP12): healthy, looping, early-stopping and
diverging cells, the reference itself, failures to start, and the shape ``smallpc.select`` reads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FIXTURES, REPO
from smallpc import sanity, sanity_runner, select
from smallpc.sanity_runner import SanityError, run_sanity
from sweep_fakes import MOCK, SynthProvider

CONFIG = 'profile = "candidate"\ncontext = 32768\nfit = "on"\nmetrics = true\nlog_verbosity = 4\n'


class Rig:
    """Resolved configs and a machine config for the mock server; one behaviour per cell."""

    def __init__(self, tmp_path: Path, port: int):
        self.tmp = tmp_path
        self.machine = tmp_path / "machine.toml"
        self.machine.write_text(
            f'[paths]\nllama_server="{MOCK}"\nmodels_dir="{tmp_path}"\n'
            f'slot_save_dir="/dev/shm/local-ai-research-slots"\n[server]\nport={port}\n'
        )
        self.model = FIXTURES / "model.toml"
        self.behavior: dict[str, dict] = {}
        self.sessions = tmp_path / "data/raw"
        self.started: list[str] = []

    def cell(self, name: str, behavior: dict | None = None, session: str = "s1") -> str:
        d = self.sessions / session / "resolved"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.toml").write_text(CONFIG + f"# {name}\n")
        self.behavior[name] = behavior or {}
        return name

    def env(self, name: str) -> dict:
        self.started.append(name)
        return {
            "SMALLPC_GPU_LOCK_FILE": str(self.tmp / "locks/gpu.lock"),
            "MOCK_BEHAVIOR": json.dumps(self.behavior.get(name, {})),
        }

    def run(self, cells, reference, **kw):
        return run_sanity(
            cells, reference, root=self.tmp, provider=SynthProvider(), scripts_dir=REPO / "scripts",
            log_root=self.tmp / "logs", machine=self.machine, model_config=self.model,
            server_env=self.env, require_lock=False, health_timeout=30, **kw,
        )  # fmt: skip


@pytest.fixture
def rig(tmp_path, free_port):
    return Rig(tmp_path, free_port)


def test_a_healthy_cell_passes_against_the_reference(rig):
    ref, cand = rig.cell("P1-32K-b2048"), rig.cell("P6-32K-b4096")
    res = rig.run([cand], ref, label="functional-test")
    c = res["cells"][cand]
    assert c["result"] == "pass" and c["failed_prompts"] == [] and not c["reference"]
    assert len(c["prompts"]) == 3 and all(
        p["ok"] and p["reasons"] == [] for p in c["prompts"].values()
    )
    for p in c["prompts"].values():
        assert p["n_tokens"] == 512 and p["first_divergence"] is None  # identical greedy outputs
        assert p["candidate"]["length"] == 512 and p["reference"]["length"] == 512
        assert p["candidate"]["distinct_4gram_ratio"] > 0.9 and p["stop_type"] == "limit"
        assert len(p["tokens_sha256"]) == 64
    assert res["label"] == "functional-test" and "FUNCTIONAL-TEST" in res["banner"]
    assert rig.started == [ref, cand]  # the reference first, one server at a time, each stopped
    assert (
        res["reference"]["cell"] == ref
        and res["reference"]["ok"]
        and res["reference"]["warnings"] == []
    )
    # the same data in the shape smallpc.select reads
    assert select.sanity_state(cand, res) == "pass" and select.sanity_state(ref, res) == "pass"
    assert select.sanity_state("other", res) == "not run"


def test_a_healthy_cell_that_diverges_from_the_reference_still_passes(rig):
    ref = rig.cell("P1-32K-b2048")
    cand = rig.cell("P6-32K-b4096", {"output": {"mode": "diverge", "at": 200}})
    c = rig.run([cand], ref)["cells"][cand]
    assert c["result"] == "pass"
    assert {p["first_divergence"] for p in c["prompts"].values()} == {200}  # information only


def test_a_cell_whose_output_loops_fails(rig):
    ref, cand = rig.cell("P1-32K-b2048"), rig.cell("P4-32K-b4096", {"output": {"mode": "loop"}})
    res = rig.run([cand], ref)
    c = res["cells"][cand]
    assert c["result"] == "fail" and sorted(c["failed_prompts"]) == sorted(c["prompts"])
    reasons = " ".join(r for p in c["prompts"].values() for r in p["reasons"])
    assert "repeated 512 times in a row" in reasons and "distinct 4-gram ratio" in reasons
    assert "8-gram repeats" in reasons
    assert all(not p["ok"] for p in c["prompts"].values())
    # select treats it as ineligible
    cell = {"name": cand, "status": "complete", "min_free_vram_mib": 1500.0, "flagged_units": [],
            "n_clean": 5, "n_total": 5, "reason": None}  # fmt: skip
    el = select.eligibility(cell, "final", res)
    assert not el["eligible"] and "failed the output sanity check" in el["reasons"]
    table = sanity_runner.format_table(res)
    assert f"{cand}: FAIL" in table and "first divergence" in table


def test_a_cell_that_stops_early_fails_the_length_rule(rig):
    ref = rig.cell("P1-32K-b2048")
    cand = rig.cell("P2-32K-b4096", {"output": {"mode": "short", "n": 30}})
    c = rig.run([cand], ref)["cells"][cand]
    assert c["result"] == "fail"
    for p in c["prompts"].values():
        assert p["candidate"]["length"] == 30 and p["stop_type"] == "eos"
        assert any("length 30 is below 100" in r for r in p["reasons"])


def test_the_reference_listed_among_the_cells_is_handled_once(rig):
    ref, cand = rig.cell("P1-32K-b2048"), rig.cell("P6-32K-b4096")
    res = rig.run([ref, cand, cand], ref)
    assert rig.started == [ref, cand]  # not started a second time, not compared with itself
    assert res["cells"][ref]["reference"] is True and res["cells"][ref]["result"] == "pass"
    assert "prompts" not in res["cells"][ref] and res["cells"][cand]["result"] == "pass"


def test_a_degenerate_reference_is_flagged_because_relative_thresholds_would_pass_anything(rig):
    ref = rig.cell("P1-32K-b2048", {"output": {"mode": "loop"}})
    cand = rig.cell("P6-32K-b4096", {"output": {"mode": "loop"}})
    res = rig.run([cand], ref)
    assert res["cells"][cand]["result"] == "pass"  # as bad as the reference: relative rule
    w = res["reference"]["warnings"]
    assert (
        w and any("repeats one token 512 times" in x for x in w) and any("8-gram" in x for x in w)
    )


def test_a_candidate_that_does_not_start_is_not_run(rig):
    ref = rig.cell("P1-32K-b2048")
    cand = rig.cell("P7-32K-b4096", {"oom_at_start": True})
    res = rig.run([cand], ref)
    c = res["cells"][cand]
    assert c["result"] == "not run" and c["prompts"] == {} and c["error"]["stage"] == "start"
    assert c["error"]["reason"] == "oom_at_load"
    assert select.sanity_state(cand, res) == "not run"
    other = rig.cell("P2-32K-b4096")  # the rest of the run is not affected
    assert rig.run([cand, other], ref)["cells"][other]["result"] == "pass"


def test_a_failed_reference_makes_every_cell_not_run(rig):
    ref = rig.cell("P1-32K-b2048", {"oom_at_start": True})
    cand = rig.cell("P6-32K-b4096")
    res = rig.run([cand], ref)
    assert res["reference"]["ok"] is False and res["cells"][ref]["result"] == "not run"
    assert (
        res["cells"][cand]["result"] == "not run"
        and "reference run failed" in res["cells"][cand]["error"]
    )


def test_the_output_has_no_prompt_text_and_no_token_arrays(rig):
    ref, cand = rig.cell("P1-32K-b2048"), rig.cell("P6-32K-b4096")
    res = rig.run([cand], ref)
    text = json.dumps(res)
    # none of the generated ids (the mock's 512 pseudo-random ids per prompt) is stored as a list
    first = sanity_runner.run_cell
    assert "tokens" not in {k for p in res["cells"][cand]["prompts"].values() for k in p}
    assert '"content"' not in text and '"prompt"' not in text
    run = first(
        {"name": ref, "toml": next((rig.sessions / "s1/resolved").glob(f"{ref}.toml"))},
        provider=SynthProvider(), scripts_dir=REPO / "scripts", log_root=rig.tmp / "logs",
        machine=rig.machine, model_config=rig.model, server_env=rig.env(ref), health_timeout=30,
    )  # fmt: skip
    assert run["error"] is None, run["error"]
    ids = next(iter(run["tokens"].values()))
    assert (
        len(ids) == 512 and json.dumps(ids[:8])[1:-1] not in text
    )  # the ids themselves are not in it
    assert sanity_runner.ids_sha256(ids) in text  # but their hash is


def test_the_prompts_are_the_three_sanity_prompts_of_the_manifest(rig):
    prov = SynthProvider()
    ref = rig.cell("P1-32K-b2048")
    res = run_sanity([], ref, root=rig.tmp, provider=prov, scripts_dir=REPO / "scripts",
                     log_root=rig.tmp / "logs", machine=rig.machine, model_config=rig.model,
                     server_env=rig.env, require_lock=False, health_timeout=30)  # fmt: skip
    assert prov.calls == [("sanity", 2048, 0), ("sanity", 2048, 1), ("sanity", 2048, 2)]
    assert res["prompts"]["n_predict"] == 512 and len(res["prompts"]["ids"]) == 3
    assert res["thresholds"]["run_limit"] == sanity.RUN_LIMIT == 16


def test_cells_resolve_from_sessions_newest_first_and_skip_functional_test_sessions(tmp_path):
    raw = tmp_path / "data/raw"
    for sid, mtime in (("old", 1000), ("ft-x", 3000), ("new", 2000)):
        d = raw / sid / "resolved"
        d.mkdir(parents=True)
        (d / "c.toml").write_text(CONFIG)
        import os

        os.utime(raw / sid, (mtime, mtime))
    got = sanity_runner.resolve_cell("c", tmp_path)
    assert got["resolved_from"] == "new" and got["name"] == "c"
    assert sanity_runner.resolve_cell("c", tmp_path, [raw / "ft-x"])["resolved_from"] == "ft-x"
    p = tmp_path / "x/my-cell.toml"
    p.parent.mkdir()
    p.write_text(CONFIG)
    assert sanity_runner.resolve_cell(str(p), tmp_path)["name"] == "my-cell"
    with pytest.raises(SanityError, match="no resolved config"):
        sanity_runner.resolve_cell("nope", tmp_path)


def test_it_refuses_to_run_without_the_gpu_lock(rig, monkeypatch):
    monkeypatch.delenv("SMALLPC_GPU_LOCK_HELD", raising=False)
    ref = rig.cell("P1-32K-b2048")
    with pytest.raises(SanityError, match="GPU lock is not held"):
        run_sanity([], ref, root=rig.tmp, provider=SynthProvider(), require_lock=True)
    monkeypatch.setenv("SMALLPC_GPU_LOCK_HELD", "123")  # run-detached.sh --gpu sets this
    with pytest.raises(SanityError, match="no resolved config"):  # past the lock check
        run_sanity([], "missing", root=rig.tmp, provider=SynthProvider(), require_lock=True)


def test_cli_writes_the_json_and_exit_codes(tmp_path, monkeypatch, capsys):
    fake = {
        "label": "results", "banner": "x", "reference": {"cell": "R"},
        "cells": {
            "R": {"result": "pass", "reference": True},
            "C": {"result": "pass", "reference": False, "prompts": {}},
        },
    }  # fmt: skip
    monkeypatch.setattr(sanity_runner, "run_sanity", lambda *a, **k: fake)
    out = tmp_path / "o/s.json"
    args = ["--cells", "C", "--reference", "R", "--out", str(out)]
    assert (
        sanity.main(["run", *args]) == 0
        and json.loads(out.read_text())["cells"]["C"]["result"] == "pass"
    )
    fake["cells"]["C"]["result"] = "fail"
    assert sanity.main(["run", *args]) == 1
    monkeypatch.setattr(
        sanity_runner, "run_sanity", lambda *a, **k: (_ for _ in ()).throw(SanityError("boom"))
    )
    assert sanity.main(["run", *args]) == 2 and "boom" in capsys.readouterr().err
    assert sanity.main(["nothing"]) == 2
