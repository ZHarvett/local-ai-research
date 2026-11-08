"""run-detached.sh / job-status.sh tests (no GPU needed)."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time

from conftest import REPO

RUN = REPO / "scripts/run-detached.sh"
STATUS = REPO / "scripts/job-status.sh"


def start(tmp_path, *args, lock=None):
    env = {**os.environ, "SMALLPC_JOBS_ROOT": str(tmp_path / "jobs")}
    env["SMALLPC_GPU_LOCK_FILE"] = str(lock or tmp_path / "gpu.lock")
    env.pop("SMALLPC_GPU_LOCK_HELD", None)
    return subprocess.run(
        [str(RUN), *map(str, args)], capture_output=True, text=True, env=env, timeout=30
    )


def wait_done(jobdir, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = json.loads((jobdir / "status.json").read_text())
        if s["state"] != "running":
            return s
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_exit_code_is_recorded(tmp_path):
    t0 = time.time()
    r = start(tmp_path, "failing", "--", "bash", "-c", "echo out; echo err >&2; sleep 1; exit 3")
    assert r.returncode == 0, r.stderr
    assert time.time() - t0 < 0.9, "must return immediately"
    jobdir = tmp_path / "jobs"
    (d,) = list(jobdir.iterdir())
    assert d.name.startswith("failing-") and r.stdout.strip() == str(d)
    assert json.loads((d / "status.json").read_text())["state"] == "running"
    s = wait_done(d)
    assert (s["state"], s["exit_code"]) == ("failed", 3)
    assert s["command"] == ["bash", "-c", "echo out; echo err >&2; sleep 1; exit 3"]
    assert s["start"] and s["end"]
    log = (d / "job.log").read_text()
    assert "out" in log and "err" in log
    assert int((d / "pid").read_text()) > 0


def test_success_state_done(tmp_path):
    r = start(tmp_path, "ok", "--", "true")
    assert r.returncode == 0
    (d,) = list((tmp_path / "jobs").iterdir())
    s = wait_done(d)
    assert (s["state"], s["exit_code"]) == ("done", 0)


def test_arguments_with_spaces_survive(tmp_path):
    start(tmp_path, "args", "--", "bash", "-c", 'printf "%s|" "$@"', "_", "a b", "c")
    (d,) = list((tmp_path / "jobs").iterdir())
    wait_done(d)
    assert (d / "job.log").read_text() == "a b|c|"


def test_gpu_job_refused_when_lock_held(tmp_path):
    lock = tmp_path / "gpu.lock"
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        r = start(tmp_path, "--gpu", "g", "--", "true", lock=lock)
    assert r.returncode == 75
    assert "GPU lock is held" in r.stderr
    assert not (tmp_path / "jobs").exists()


def test_gpu_job_runs_under_lock_when_free(tmp_path):
    r = start(tmp_path, "--gpu", "g", "--", "bash", "-c", 'echo "held=$SMALLPC_GPU_LOCK_HELD"')
    assert r.returncode == 0, r.stderr
    (d,) = list((tmp_path / "jobs").iterdir())
    s = wait_done(d)
    assert s["gpu"] is True and s["state"] == "done"
    assert (d / "job.log").read_text().startswith("held=")


def test_bad_usage(tmp_path):
    assert start(tmp_path, "nodashes", "true").returncode == 2
    assert start(tmp_path).returncode == 2


def test_job_status_prints_status_and_log_tail(tmp_path):
    start(tmp_path, "st", "--", "bash", "-c", "seq 1 30")
    (d,) = list((tmp_path / "jobs").iterdir())
    wait_done(d)
    out = subprocess.run([str(STATUS), str(d)], capture_output=True, text=True).stdout
    assert '"state": "done"' in out
    assert "\n30\n" in out and "\n11\n" in out and "\n10\n" not in out
