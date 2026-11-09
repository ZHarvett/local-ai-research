"""sweep-status, session discovery, and the run-sweep.sh / sweep-status.sh scripts."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess

import pytest

from conftest import FIXTURES, REPO
from smallpc.sweep import status
from test_sweep_session import run_session

RUN = REPO / "scripts/run-sweep.sh"
STATUS = REPO / "scripts/sweep-status.sh"
SKETCH = FIXTURES / "stage1-sketch.toml"


# ------------------------------------------------------------------ status


def test_status_report_of_a_finished_session(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, canary=True, reps=1)
    r = status.report(sess.dir)
    assert r["state"] == "complete" and r["cells_total"] == 3 and r["cells_done"] == 3
    assert r["cells_remaining"] == 0 and r["eta_s"] == 0 and r["pid"] == os.getpid()
    assert r["records"]["torn_lines"] == 0 and r["records"]["requests"] > 40
    assert r["last_error"] is None and r["drift"]["main"]["flag"] is None
    text = status.format_report(r)
    for word in ("session", "cells", "3/3", "ETA", "flags", "drift", "last error"):
        assert word in text


def test_status_mid_run_shows_remaining_cells_current_cell_and_flags(tmp_path, free_port):
    sess, _, _ = run_session(tmp_path, free_port, {"cache_miss_B": {"on": [1]}}, reps=1)
    # make it look like an unfinished run: drop the last cell's final record and mark it running
    lines = sess.store.path.read_text().splitlines()
    keep = [ln for ln in lines if not (json.loads(ln)["record_type"] == "cell"
                                       and json.loads(ln)["cell"] == sess.order[-1])]  # fmt: skip
    sess.store.path.write_text("\n".join(keep) + "\n")
    sj = json.loads((sess.dir / "session.json").read_text())
    sj["state"] = "running"
    (sess.dir / "session.json").write_text(json.dumps(sj))
    prog = json.loads((sess.dir / "progress.json").read_text())
    prog.update(cell=sess.order[-1], phase="measure", repetition=0, depth=2000)
    (sess.dir / "progress.json").write_text(json.dumps(prog))
    r = status.report(sess.dir)
    assert r["cells_done"] == 2 and r["cells_remaining"] == 1 and r["eta_s"] > 0
    assert r["current_cell"] == sess.order[-1] and r["phase"] == "measure"
    assert r["request_flags_so_far"] == {"cache_miss": 3}
    assert "cache_miss" in status.format_report(r)


def test_latest_session_filters_by_spec_and_state(tmp_path, free_port):
    sess, _, env = run_session(tmp_path, free_port, reps=1)
    assert status.latest_session(env.out_root, "t") is None  # complete: nothing to resume
    assert status.latest_session(env.out_root, "t", unfinished_only=False) == "s1"
    assert status.latest_session(env.out_root, "other", unfinished_only=False) is None
    assert status.latest_session(env.out_root, "t", {"context": "32K"}, False) is None
    sj = json.loads((sess.dir / "session.json").read_text())
    sj["state"] = "interrupted"
    (sess.dir / "session.json").write_text(json.dumps(sj))
    assert status.latest_session(env.out_root, "t") == "s1"


def test_fmt_duration():
    assert status.fmt_duration(59) == "0m59s" and status.fmt_duration(3725) == "1h02m"
    assert status.fmt_duration(None) == "?"


# ------------------------------------------------------------------ scripts


def test_scripts_are_shellcheck_clean():
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed")
    r = subprocess.run(["shellcheck", str(RUN), str(STATUS)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def fake_tool(path, body):
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def repo_copy(tmp_path):
    """A scratch git repo with a copy of the scripts, a fake `uv` and a fake `systemd-inhibit`,
    so run-sweep.sh can be exercised without starting a GPU job."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for f in ("run-sweep.sh", "_common.sh", "run-detached.sh"):
        shutil.copy(REPO / "scripts" / f, repo / "scripts" / f)
    for d in ("src", "configs"):
        (repo / d).mkdir()
        (repo / d / "keep").write_text("x\n")
    spec = repo / "spec.toml"
    shutil.copy(SKETCH, spec)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_tool(bindir / "uv", 'if [[ "$*" == *" latest "* ]]; then echo prev-session; fi\nexit 0\n')
    fake_tool(
        bindir / "systemd-inhibit",
        'echo "$@" >>"$FAKE_INHIBIT_LOG"\nexit "${FAKE_INHIBIT_RC:-0}"\n',
    )
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "SMALLPC_SWEEP_DRY_RUN": "1",
           "FAKE_INHIBIT_LOG": str(tmp_path / "inhibit.log")}  # fmt: skip

    def sh(*cmd, **kw):
        return subprocess.run(cmd, cwd=repo, env={**env, **kw.pop("env", {})}, capture_output=True,
                              text=True, **kw)  # fmt: skip

    sh("git", "init", "-q")
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    sh("git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return repo, sh


def test_run_sweep_starts_a_new_session_on_a_clean_tree(repo_copy):
    repo, sh = repo_copy
    (repo / "data/raw").mkdir(parents=True)
    r = sh("scripts/run-sweep.sh", "spec.toml", "--only", "context=32K")
    assert r.returncode == 0, r.stderr
    assert "DRY RUN: mode=sweep session=spec-context32K-" in r.stdout
    assert "--only context=32K" in r.stdout and "--allow-dirty" not in r.stdout
    assert "smallpc-sweep-spec-context32K-" in r.stdout  # the inhibit tag the runner looks for


def test_run_sweep_refuses_uncommitted_changes_unless_allowed(repo_copy):
    repo, sh = repo_copy
    (repo / "src/keep").write_text("changed\n")
    r = sh("scripts/run-sweep.sh", "spec.toml")
    assert r.returncode != 0 and "uncommitted changes" in r.stderr and "--allow-dirty" in r.stderr
    ok = sh("scripts/run-sweep.sh", "spec.toml", "--allow-dirty")
    assert ok.returncode == 0 and "--allow-dirty" in ok.stdout
    # data/ is not one of the guarded directories
    (repo / "src/keep").write_text("x\n")
    (repo / "data").mkdir(exist_ok=True)
    (repo / "data/x").write_text("y\n")
    assert sh("scripts/run-sweep.sh", "spec.toml").returncode == 0


def test_run_sweep_stops_if_systemd_inhibit_is_refused(repo_copy):
    repo, sh = repo_copy
    r = sh("scripts/run-sweep.sh", "spec.toml", env={"FAKE_INHIBIT_RC": "1"})
    assert r.returncode != 0 and "systemd-inhibit was refused" in r.stderr
    assert "DRY RUN" not in r.stdout  # nothing was started


def test_run_sweep_resume_and_rerun_pick_the_session(repo_copy):
    repo, sh = repo_copy
    (repo / "data/raw/old-sess").mkdir(parents=True)
    r = sh("scripts/run-sweep.sh", "spec.toml", "--resume")
    assert (
        r.returncode == 0
        and "mode=resume session=prev-session" in r.stdout
        or "no such" in r.stderr
    )
    (repo / "data/raw/prev-session").mkdir()
    r = sh("scripts/run-sweep.sh", "spec.toml", "--resume")
    assert r.returncode == 0 and "mode=resume session=prev-session" in r.stdout
    assert "--resume" in r.stdout
    r = sh("scripts/run-sweep.sh", "spec.toml", "--rerun-flagged", "old-sess")
    assert r.returncode == 0 and "mode=rerun session=old-sess" in r.stdout
    assert "--rerun-flagged" in r.stdout
    # (dirty trees are allowed for resume and re-run: only the code commit is recorded)
    (repo / "src/keep").write_text("changed\n")
    assert sh("scripts/run-sweep.sh", "spec.toml", "--resume").returncode == 0


def test_run_sweep_argument_errors(repo_copy):
    repo, sh = repo_copy
    assert sh("scripts/run-sweep.sh").returncode == 2
    assert "no such spec" in sh("scripts/run-sweep.sh", "nope.toml").stderr
    assert (
        "exclusive"
        in sh("scripts/run-sweep.sh", "spec.toml", "--resume", "--rerun-flagged", "x").stderr
    )
    assert "unknown option" in sh("scripts/run-sweep.sh", "spec.toml", "--bogus").stderr
    (repo / "data/raw/exists").mkdir(parents=True)
    assert (
        "already exists" in sh("scripts/run-sweep.sh", "spec.toml", "--session-id", "exists").stderr
    )


def test_the_real_check_command_rejects_a_spec_with_the_wrong_cell_count(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(SKETCH.read_text().replace("expect_cells = 57", "expect_cells = 56"))
    r = subprocess.run(["uv", "run", "--frozen", "--quiet", "python", "-m", "smallpc.sweep",
                        "check", str(bad)], cwd=REPO, capture_output=True, text=True)  # fmt: skip
    assert r.returncode == 2 and "expects 56 cells but expands to 57" in r.stderr
    ok = subprocess.run(["uv", "run", "--frozen", "--quiet", "python", "-m", "smallpc.sweep",
                         "check", str(SKETCH)], cwd=REPO, capture_output=True, text=True)  # fmt: skip
    assert ok.returncode == 0 and json.loads(ok.stdout)["cells"] == 57
