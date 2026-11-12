"""`python -m smallpc.stage3 gate` on fixture sessions (WP13): criteria a to e as in Stage 2, and
criterion f over the tuned cells' and the canaries' windows only; stock windows are reported."""

from __future__ import annotations

import json

import pytest

from conftest import REPO
from fixture_session import CellSpec, RepSpec, build_session
from smallpc.stage3 import cli, gate


def stock(reps=None, **kw):
    return CellSpec(name="stock-32K", profile="stock", reps=reps, **kw)


def tuned(reps=None, **kw):
    return CellSpec(name="tuned-32K", profile="tuned", reps=reps, cache_mib=11520, **kw)


def paging(*flagged, swap=None, flag="paging"):
    """Five repetitions; the listed ones carry the flag (and ``swap`` MiB of swap growth)."""
    return [
        RepSpec(i, flags=(flag,) if i in flagged else (), swap_mib=swap if i in flagged else None,
                faults=2500 if i in flagged else None)
        for i in range(5)
    ]  # fmt: skip


def canary_summaries(d, flagged=(), swap=None):
    """Canary cell summaries with one window each (the fixture writes only the request records)."""
    for role, base in (("canary_start", 100), ("canary_end", 103)):
        wins = [
            {"window_id": f"c-{role}-{i}", "repetition": base + i, "attempt": 1,
             "flags": ["paging"] if (role, i) in flagged else [],
             **({"swap_activity_mib": swap} if (role, i) in flagged else {"swap_activity_mib": 0.0})}
            for i in range(3)
        ]  # fmt: skip
        name = role.replace("_", "-")
        (d / "cells" / f"{name}-deadbeef.json").write_text(
            json.dumps(
                {
                    "cell": name,
                    "role": role,
                    "profile": "candidate",
                    "config_hash": "deadbeef",
                    "instances": [{"windows": wins}],
                    "flags": [],
                }
            )  # fmt: skip
        )


def run(tmp_path, cells, **kw):
    d = build_session(tmp_path, "stage3-32K", cells, **kw)
    return gate.gate(d, logs_root=tmp_path / "logs"), d


def test_a_clean_session_passes_all_criteria(tmp_path):
    g, _ = run(tmp_path, [stock(), tuned()])
    assert g["pass"] and g["failed"] == [] and [c["id"] for c in g["criteria"]] == list("abcdef")
    assert "0 of 5" in g["criteria"][-1]["detail"] and "PASS" in g["next"]


def test_heavily_flagged_stock_windows_never_fail_the_gate_and_are_reported(tmp_path):
    g, _ = run(tmp_path, [stock(reps=paging(0, 1, 2, 3, swap=2500.0)), tuned()])
    assert g["pass"], g["criteria"]
    assert g["stock_paging"] == {
        "windows": 5,
        "flagged": 4,
        "note": "reported only; stock windows never fail the gate",
    }
    assert (
        g["paging_per_cell"]["stock-32K"]["flagged"] == 4
        and g["paging_per_cell"]["stock-32K"]["group"] == "stock"
    )
    assert g["paging_per_cell"]["stock-32K"]["max_swap_mib"] == 2500.0
    text = gate.format_gate(g)
    assert "stock-32K [stock]: 4 of 5" in text and "never fail the gate" in text


def test_more_than_40_percent_of_the_tuned_windows_flagged_fails_f(tmp_path):
    g, _ = run(tmp_path, [stock(), tuned(reps=paging(0, 1, 2, swap=10.0))])  # 3 of 5 = 60%
    assert g["failed"] == ["f"] and "3 of 5" in g["criteria"][-1]["detail"] and "STOP" in g["next"]
    assert g["stop_for_human"]


def test_exactly_40_percent_passes_and_the_limit_is_more_than(tmp_path):
    g, _ = run(tmp_path, [stock(), tuned(reps=paging(0, 1, swap=10.0))])  # 2 of 5 = 40%
    assert g["pass"]


def test_one_flagged_tuned_window_above_1024_mib_of_swap_fails_f(tmp_path):
    g, _ = run(tmp_path, [stock(), tuned(reps=paging(3, swap=1500.0))])
    assert g["failed"] == ["f"] and "tuned-32K r3 (1500 MiB)" in g["criteria"][-1]["detail"]
    ok, _ = run(tmp_path / "ok", [stock(), tuned(reps=paging(3, swap=1000.0))])
    assert ok["pass"]  # a flagged window at 1,000 MiB is within the rule


def test_a_canary_window_over_the_swap_rule_fails_f(tmp_path):
    d = build_session(tmp_path, "stage3-32K", [stock(), tuned()])
    canary_summaries(d, flagged={("canary_end", 1)}, swap=1800.0)
    g = gate.gate(d, logs_root=tmp_path / "logs")
    assert g["failed"] == ["f"] and "canary-end r104 (1800 MiB)" in g["criteria"][-1]["detail"]
    assert "1 of 11" in g["criteria"][-1]["detail"]  # five tuned windows and six canary windows


def test_canary_windows_count_in_the_paging_share_with_the_tuned_windows(tmp_path):
    d = build_session(tmp_path, "stage3-32K", [stock(), tuned(reps=paging(0, swap=5.0))])
    canary_summaries(
        d, flagged={("canary_start", 0), ("canary_start", 1), ("canary_end", 0)}, swap=5.0
    )
    g = gate.gate(d, logs_root=tmp_path / "logs")  # 4 of 11 = 36%
    assert g["pass"]
    canary_summaries(
        d, flagged={(r, i) for r in ("canary_start", "canary_end") for i in range(2)}, swap=5.0
    )
    g = gate.gate(d, logs_root=tmp_path / "logs")  # 5 of 11 = 45%
    assert g["failed"] == ["f"]


def test_the_spec_classifies_the_cells_when_given(tmp_path):
    cs = [
        CellSpec(name="stock-32K", reps=paging(0, 1, 2, 3, swap=2500.0)),
        CellSpec(name="tuned-32K"),
    ]
    d = build_session(tmp_path, "stage3-32K", cs)  # both recorded as "candidate"
    plain = gate.gate(d, logs_root=tmp_path / "logs")
    assert plain["failed"] == ["f"]  # without the spec the flagged cell is taken as tuned
    g = gate.gate(d, REPO / "configs/sweeps/stage3.toml", logs_root=tmp_path / "logs")
    assert g["pass"] and g["paging_per_cell"]["stock-32K"]["group"] == "stock"


# ---------------------------------------------------------------- every other criterion fails once


def test_a_not_complete_session_fails_a(tmp_path):
    g, _ = run(tmp_path, [stock(), tuned()], state="interrupted")
    assert g["failed"] == ["a"]


def test_a_failed_detached_job_fails_a(tmp_path):
    job = tmp_path / "logs/jobs/sweep-stage3-32K-20261112T000000Z"
    job.mkdir(parents=True)
    (job / "status.json").write_text(json.dumps({"exit_code": 75, "state": "failed"}))
    g, _ = run(tmp_path, [stock(), tuned()])
    assert g["failed"] == ["a"] and "exit code 75" in g["criteria"][0]["detail"]


def test_a_cell_without_a_final_record_fails_b(tmp_path):
    t = tuned()
    t.status = "interrupted"
    g, _ = run(tmp_path, [stock(), t])
    assert "b" in g["failed"] and "missing ['tuned-32K']" in g["criteria"][1]["detail"]


@pytest.mark.parametrize("flag", ["accounting", "warm_prefill", "cache_miss"])
@pytest.mark.parametrize("which", ["stock", "tuned"])
def test_request_flags_in_either_cell_fail_c(tmp_path, flag, which):
    reps = [RepSpec(i, flags=(flag,) if i == 2 else ()) for i in range(5)]
    cells = [stock(reps=reps), tuned()] if which == "stock" else [stock(), tuned(reps=reps)]
    g, _ = run(tmp_path, cells)
    assert g["failed"] == ["c"] and flag in g["criteria"][2]["detail"]


def test_a_thermal_flag_fails_d(tmp_path):
    reps = [RepSpec(i, flags=("thermal",) if i == 0 else ()) for i in range(5)]
    g, _ = run(tmp_path, [stock(), tuned(reps=reps)])
    assert g["failed"] == ["d"]


def test_a_drift_flag_fails_d(tmp_path):
    g, _ = run(tmp_path, [stock(), tuned()], drift_main="drift")
    assert g["failed"] == ["d"]


@pytest.mark.parametrize(
    "reason", ["startup_failure", "startup_timeout", "crash_mid_cell", "oom_runtime"]
)
def test_did_not_fit_for_the_listed_reasons_fails_e(tmp_path, reason):
    g, _ = run(
        tmp_path, [stock(), tuned(), CellSpec(name="x", status="did_not_fit", reason=reason)]
    )
    assert g["failed"] == ["e"]


def test_did_not_fit_by_oom_at_load_is_not_a_gate_failure(tmp_path):
    g, _ = run(
        tmp_path, [stock(), tuned(), CellSpec(name="x", status="did_not_fit", reason="oom_at_load")]
    )
    assert g["pass"]


def test_the_command_line_exit_codes_and_json(tmp_path, capsys):
    d = build_session(tmp_path, "stage3-32K", [stock(), tuned()])
    assert cli.main(["gate", "--session", str(d)]) == 0
    assert "PASS" in capsys.readouterr().out
    d2 = build_session(tmp_path, "stage3-64K", [stock(), tuned(reps=paging(0, 1, 2, swap=10.0))])
    assert cli.main(["gate", "--session", str(d2), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["failed"] == ["f"]
    assert cli.main(["gate", "--session", str(tmp_path / "nonexistent")]) == 2
