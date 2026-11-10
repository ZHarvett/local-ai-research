"""The session gate (Stage 1 gate with the two Stage 2 changes), on fixture sessions."""

from __future__ import annotations

import json

import pytest

from fixture_session import CellSpec, RepSpec, build_session
from smallpc.stage2 import cli, gate


def cells(flag_reps=(), flag="paging", **kw):
    """Two cells x five repetitions = 10 measured windows; ``flag_reps`` flags the first cell."""
    a = CellSpec(
        name="a", context=65536,
        reps=[RepSpec(i, flags=(flag,) if i in flag_reps else ()) for i in range(5)], **kw,
    )  # fmt: skip
    return [a, CellSpec(name="b", context=65536)]


def run(tmp_path, stage="2a", cs=None, **kw):
    d = build_session(tmp_path, "g", cs or cells(), **kw)
    return gate.gate(stage, d, logs_root=tmp_path / "logs"), d


def failed(g):
    return g["failed"]


def test_a_clean_session_passes_and_names_the_next_step(tmp_path):
    g, _ = run(tmp_path, "2a")
    assert g["pass"] and g["failed"] == [] and not g["stop_for_human"]
    assert [c["id"] for c in g["criteria"]] == list("abcdef")
    assert all(c["pass"] for c in g["criteria"]) and "decide --stage 2a" in g["next"]
    assert "0 of 10" in g["criteria"][-1]["detail"]


@pytest.mark.parametrize("stage", list(gate.NEXT))
def test_every_stage_has_a_next_step(tmp_path, stage):
    g, _ = run(tmp_path, stage)
    assert g["pass"] and g["next"] == gate.NEXT[stage]
    assert stage in g["next"] and "decide" in g["next"]


def test_a_not_complete_session_fails_a(tmp_path):
    g, _ = run(tmp_path, state="interrupted")
    assert failed(g) == ["a"] and g["stop_for_human"] and "STOP" in g["next"]


def test_the_detached_job_exit_code_is_checked_when_the_job_is_found(tmp_path):
    job = tmp_path / "logs/jobs/sweep-g-20261110T000000Z"
    job.mkdir(parents=True)
    (job / "status.json").write_text(json.dumps({"exit_code": 75, "state": "failed"}))
    g, _ = run(tmp_path)
    assert failed(g) == ["a"] and "exit code 75" in g["criteria"][0]["detail"]
    (job / "status.json").write_text(json.dumps({"exit_code": 0, "state": "done"}))
    g2 = gate.gate("2a", tmp_path / "g", logs_root=tmp_path / "logs")
    assert g2["pass"] and "exit code 0" in g2["criteria"][0]["detail"]


def test_a_cell_without_a_final_record_fails_b(tmp_path):
    cs = cells()
    cs[1].status = "interrupted"  # its cell record is not final
    g, _ = run(tmp_path, cs=cs)
    assert "b" in failed(g) and "missing ['b']" in g["criteria"][1]["detail"]


@pytest.mark.parametrize("flag", ["accounting", "warm_prefill", "cache_miss"])
def test_request_flags_fail_c(tmp_path, flag):
    g, _ = run(tmp_path, cs=cells(flag_reps=(2,), flag=flag))
    assert failed(g) == ["c"] and f"a r2 {flag}" in g["criteria"][2]["detail"]


def test_a_thermal_flag_fails_d(tmp_path):
    g, _ = run(tmp_path, cs=cells(flag_reps=(0,), flag="thermal"))
    assert failed(g) == ["d"]


def test_a_drift_flag_fails_d(tmp_path):
    g, _ = run(tmp_path, drift_main="drift")
    assert failed(g) == ["d"] and "drift" in g["criteria"][3]["detail"]


@pytest.mark.parametrize(
    "reason", ["startup_failure", "startup_timeout", "crash_mid_cell", "oom_runtime"]
)
def test_did_not_fit_for_the_listed_reasons_fails_e(tmp_path, reason):
    cs = cells() + [CellSpec(name="c", context=65536, status="did_not_fit", reason=reason)]
    g, _ = run(tmp_path, cs=cs)
    assert failed(g) == ["e"] and reason in g["criteria"][4]["detail"]


def test_did_not_fit_for_another_reason_is_a_result_not_a_stop(tmp_path):
    cs = cells() + [CellSpec(name="c", context=65536, status="did_not_fit", reason="oom_at_load")]
    g, _ = run(tmp_path, cs=cs)
    assert g["pass"] and "oom_at_load" in g["criteria"][4]["detail"]


def test_2f_reports_flagged_windows_per_cell_and_does_not_stop(tmp_path):
    g, _ = run(tmp_path, "2f", cs=cells(flag_reps=(0, 1, 2, 3)))  # 4 of 10 = 40% flagged
    assert g["pass"] is True and g["failed"] == [] and not g["stop_for_human"]
    f = g["criteria"][-1]
    assert f["applies"] is False and f["pass"] is None and "4 of 10" in f["detail"]
    assert g["paging_per_cell"]["a"] == {
        "windows": 5,
        "flagged": 4,
        "flagged_repetitions": [0, 1, 2, 3],
    }
    assert g["paging_per_cell"]["b"]["flagged"] == 0
    assert "decide --stage 2f" in g["next"] and "rerun-flagged" in g["next"]
    text = gate.format_gate(g)
    assert "a: 4 of 10" not in text and "a: 4 of 5" in text and "n/a" in text


def test_2f_still_stops_for_the_other_criteria(tmp_path):
    g, _ = run(tmp_path, "2f", cs=cells(flag_reps=(1,), flag="accounting"))
    assert failed(g) == ["c"] and g["stop_for_human"]


def test_from_2a_onward_more_than_20_percent_paging_stops(tmp_path):
    g, _ = run(tmp_path, "2a", cs=cells(flag_reps=(0, 1, 2)))  # 3 of 10 = 30%
    assert failed(g) == ["f"] and "2f choice did not hold" in g["next"] and g["stop_for_human"]


def test_exactly_20_percent_paging_passes(tmp_path):
    g, _ = run(tmp_path, "2b", cs=cells(flag_reps=(0, 1)))  # 2 of 10 = 20%: "no more than 20%"
    assert g["pass"] and "20.0%" in g["criteria"][-1]["detail"]


def test_paging_is_counted_from_attempt_1_even_after_a_rerun(tmp_path):
    a = CellSpec(
        name="a", context=65536,
        reps=[RepSpec(i, flags=("paging",) if i < 3 else ()) for i in range(5)]
        + [RepSpec(i, attempt=2) for i in range(3)],
    )  # fmt: skip
    g, _ = run(tmp_path, "2a", cs=[a, CellSpec(name="b", context=65536)])
    assert failed(g) == ["f"] and "3 of 10" in g["criteria"][-1]["detail"]  # the re-run is clean
    assert not [c for c in g["criteria"] if c["id"] == "c" and not c["pass"]]


def test_cli_gate_exit_codes_and_text(tmp_path, capsys):
    ok = build_session(tmp_path, "ok", cells())
    assert cli.main(["gate", "--stage", "2a", "--session", str(ok)]) == 0
    assert "PASS" in capsys.readouterr().out
    bad = build_session(tmp_path, "bad", cells(flag_reps=(0, 1, 2)))
    assert cli.main(["gate", "--stage", "2a", "--session", str(bad), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == ["f"]
    assert cli.main(["gate", "--stage", "2f", "--session", str(bad)]) == 0
    assert cli.main(["gate", "--stage", "2a", "--session", str(tmp_path / "nope")]) == 2
