"""Shell-script tests. Nothing here needs a GPU: llama-server is replaced by a fake."""

from __future__ import annotations

import fcntl
import json
import os
import shlex
import socket
import subprocess
import time

import pytest

from conftest import EXAMPLE_NAMES, EXAMPLES, FIXTURES, GOLDEN, REPO

LAUNCH = REPO / "scripts/launch-server.sh"
STOP = REPO / "scripts/stop-server.sh"
WITH_LOCK = REPO / "scripts/with-gpu-lock.sh"
FAKE = FIXTURES / "fake_llama_server.py"


def run(cmd, env=None, timeout=60, **kw):
    full_env = {**os.environ, **(env or {})}
    full_env.pop("SMALLPC_GPU_LOCK_HELD", None) if env is None else None
    return subprocess.run(
        [str(c) for c in cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=full_env,
        check=False,
        **kw,
    )


# ------------------------------------------------------------------ dry-run vs golden


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_dry_run_matches_golden(name):
    r = run(
        [
            LAUNCH,
            "--dry-run",
            "--machine",
            FIXTURES / "machine.toml",
            "--model-config",
            FIXTURES / "model.toml",
            EXAMPLES / f"{name}.toml",
        ]
    )
    assert r.returncode == 0, r.stderr
    assert shlex.split(r.stdout) == (GOLDEN / f"{name}.argv").read_text().splitlines()


def test_dry_run_needs_no_binary_lock_or_port(sandbox):
    # Missing binary, lock held by someone else, configured port busy: --dry-run still prints.
    lock = sandbox["tmp"] / "locks/gpu.lock"
    lock.parent.mkdir(parents=True)
    sandbox["tmp"].joinpath("machine.toml").write_text(
        f'[paths]\nllama_server="/nonexistent/llama-server"\nmodels_dir="{sandbox["tmp"]}"\n'
        f'slot_save_dir="/dev/shm/local-ai-research-slots"\n[server]\nport={sandbox["port"]}\n'
    )
    with open(lock, "w") as fh, socket.socket() as s:
        fcntl.flock(fh, fcntl.LOCK_EX)
        s.bind(("127.0.0.1", sandbox["port"]))
        s.listen()
        r = run([*sandbox["launch"], "--dry-run", sandbox["cfg"]], env=sandbox["env"])
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("/nonexistent/llama-server ")
    assert f"--port {sandbox['port']}" in r.stdout
    assert not sandbox["logs"].exists(), "--dry-run must not create run directories"


def test_dry_run_rejects_invalid_config(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('profile = "stock"\nflash_attn = "on"\n')
    r = run(
        [
            LAUNCH,
            "--dry-run",
            "--machine",
            FIXTURES / "machine.toml",
            "--model-config",
            FIXTURES / "model.toml",
            bad,
        ]
    )
    assert r.returncode != 0 and "stock config may set only" in r.stderr


# ------------------------------------------------------------------ launch / stop lifecycle


@pytest.fixture
def sandbox(tmp_path, free_port):
    """A machine config that points at the fake server, plus private lock and log dirs."""
    machine = tmp_path / "machine.toml"
    machine.write_text(
        f'[paths]\nllama_server="{FAKE}"\nmodels_dir="{tmp_path}"\n'
        f'slot_save_dir="/dev/shm/local-ai-research-slots"\n'
        f"[server]\nport={free_port}\n"
    )
    env = {
        "SMALLPC_GPU_LOCK_FILE": str(tmp_path / "locks/gpu.lock"),
        "SMALLPC_LOG_ROOT": str(tmp_path / "logs"),
    }
    cfg = tmp_path / "stock.toml"
    cfg.write_text('profile = "stock"\ncontext = 4096\nmetrics = true\n')
    launch = [
        LAUNCH,
        "--machine",
        machine,
        "--model-config",
        FIXTURES / "model.toml",
        "--health-timeout",
        "20",
    ]
    return {
        "env": env,
        "launch": launch,
        "cfg": cfg,
        "logs": tmp_path / "logs",
        "port": free_port,
        "tmp": tmp_path,
    }


def launch_ok(sb, run_id, extra_env=None, wrapper=False):
    cmd = [*sb["launch"], "--run-id", run_id, sb["cfg"]]
    if wrapper:
        cmd = [WITH_LOCK, *cmd]
    r = run(cmd, env={**sb["env"], **(extra_env or {})})
    assert r.returncode == 0, r.stdout + r.stderr
    return sb["logs"] / run_id


def test_launch_and_clean_stop(sandbox):
    run_dir = launch_ok(sandbox, "t1")
    assert (run_dir / "server.pid").read_text().strip().isdigit()
    assert "listening" in (run_dir / "server.log").read_text()
    assert f"--port\n{sandbox['port']}\n" in (run_dir / "argv.txt").read_text()
    assert (run_dir / "server.toml").exists()
    r = run([STOP, "--timeout", "10", run_dir], env=sandbox["env"])
    assert r.returncode == 0, r.stderr
    status = json.loads((run_dir / "stop-status.json").read_text())
    assert status["method"] == "sigint" and status["exit_code"] == 0
    assert (run_dir / "exit-code").read_text().strip() == "0"
    assert "SIGINT" in (run_dir / "server.log").read_text()


def test_stop_falls_back_to_sigkill(sandbox):
    run_dir = launch_ok(sandbox, "t2", {"FAKE_IGNORE_SIGINT": "1"})
    r = run([STOP, "--timeout", "1", run_dir], env=sandbox["env"])
    assert r.returncode == 0 and "SIGKILL" in r.stderr
    status = json.loads((run_dir / "stop-status.json").read_text())
    assert status["method"] == "sigkill" and status["exit_code"] == 137


def test_stop_by_run_id_and_when_already_exited(sandbox):
    run_dir = launch_ok(sandbox, "t3")
    assert run([STOP, "t3"], env=sandbox["env"]).returncode == 0
    r = run([STOP, "t3"], env=sandbox["env"])  # second stop: nothing running
    assert r.returncode == 0
    assert json.loads((run_dir / "stop-status.json").read_text())["method"] == "already_exited"


def test_waits_for_health(sandbox):
    t0 = time.monotonic()
    run_dir = launch_ok(sandbox, "t4", {"FAKE_LOAD_DELAY": "3"})
    assert time.monotonic() - t0 >= 2.5, "launch returned before /health answered 200"
    run([STOP, run_dir], env=sandbox["env"])


def test_health_timeout_stops_server(sandbox):
    cmd = [*sandbox["launch"][:-2], "--health-timeout", "2", "--run-id", "t5", sandbox["cfg"]]
    r = run(cmd, env={**sandbox["env"], "FAKE_LOAD_DELAY": "60"})
    assert r.returncode != 0 and "no healthy /health" in r.stderr
    status = json.loads((sandbox["logs"] / "t5/stop-status.json").read_text())
    assert status["method"] == "sigint"


def test_server_dying_at_start_is_reported(sandbox):
    r = run(
        [*sandbox["launch"], "--run-id", "t6", sandbox["cfg"]],
        env={**sandbox["env"], "FAKE_EXIT_AT_START": "7"},
    )
    assert r.returncode != 0 and "exited with code 7" in r.stderr


def test_refuses_busy_port(sandbox):
    with socket.socket() as s:
        s.bind(("127.0.0.1", sandbox["port"]))
        s.listen()
        r = run([*sandbox["launch"], "--run-id", "t7", sandbox["cfg"]], env=sandbox["env"])
    assert r.returncode != 0 and "already in use" in r.stderr
    assert not (sandbox["logs"] / "t7").exists()


def test_refuses_missing_binary(sandbox):
    sandbox["tmp"].joinpath("machine.toml").write_text(
        f'[paths]\nllama_server="{sandbox["tmp"]}/nope"\nmodels_dir="{sandbox["tmp"]}"\n'
        f'slot_save_dir="/dev/shm/local-ai-research-slots"\n[server]\nport={sandbox["port"]}\n'
    )
    r = run([*sandbox["launch"], "--run-id", "t8", sandbox["cfg"]], env=sandbox["env"])
    assert r.returncode != 0 and "not found or not executable" in r.stderr


# ------------------------------------------------------------------ GPU lock


def test_refuses_when_gpu_lock_held_by_another_job(sandbox):
    lock = sandbox["tmp"] / "locks/gpu.lock"
    lock.parent.mkdir(parents=True)
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        r = run([*sandbox["launch"], "--run-id", "t9", sandbox["cfg"]], env=sandbox["env"])
    assert r.returncode != 0 and "GPU lock is held by another job" in r.stderr
    assert not (sandbox["logs"] / "t9").exists()


def test_plain_launch_holds_the_lock_for_the_servers_lifetime(sandbox):
    run_dir = launch_ok(sandbox, "t10")
    lock = sandbox["tmp"] / "locks/gpu.lock"
    held = run(["flock", "-n", lock, "true"])
    assert held.returncode != 0, "lock should still be held by the running server"
    run([STOP, run_dir], env=sandbox["env"])
    deadline = time.monotonic() + 5
    while run(["flock", "-n", lock, "true"]).returncode != 0 and time.monotonic() < deadline:
        time.sleep(0.1)
    assert run(["flock", "-n", lock, "true"]).returncode == 0, "lock should be free after stop"


def test_with_gpu_lock_sets_variable_and_excludes_second_job(sandbox):
    env = sandbox["env"]
    r = run([WITH_LOCK, "bash", "-c", 'echo "held=$SMALLPC_GPU_LOCK_HELD"'], env=env)
    assert r.returncode == 0 and r.stdout.startswith("held=") and r.stdout.strip() != "held="
    r = run([WITH_LOCK, "bash", "-c", f"{WITH_LOCK} true; echo rc=$?"], env=env)
    assert "rc=75" in r.stdout


def test_launch_under_wrapper_uses_the_held_lock(sandbox):
    run_dir = launch_ok(sandbox, "t11", wrapper=True)
    # Another job cannot take the lock while the server runs, even though the wrapper exited.
    r = run([WITH_LOCK, "true"], env=sandbox["env"])
    assert r.returncode == 75
    run([STOP, run_dir], env=sandbox["env"])


def test_stale_lock_variable_is_refused(sandbox):
    # Variable set, but nothing holds the lock -> refuse.
    r = run(
        [*sandbox["launch"], "--run-id", "t12", sandbox["cfg"]],
        env={**sandbox["env"], "SMALLPC_GPU_LOCK_HELD": str(os.getpid())},
    )
    assert r.returncode != 0 and "stale variable" in r.stderr
    # Variable names a dead pid -> refuse.
    r = run(
        [*sandbox["launch"], "--run-id", "t13", sandbox["cfg"]],
        env={**sandbox["env"], "SMALLPC_GPU_LOCK_HELD": "999999999"},
    )
    assert r.returncode != 0 and "stale variable" in r.stderr


def test_lock_held_by_another_job_is_refused_even_with_a_live_variable(sandbox):
    # Documented limit: the variable is trusted when it names a live pid AND the lock is held,
    # because the holder cannot be identified. Without the variable the lock is always honoured.
    lock = sandbox["tmp"] / "locks/gpu.lock"
    lock.parent.mkdir(parents=True)
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        r = run([*sandbox["launch"], "--run-id", "t14", sandbox["cfg"]], env=sandbox["env"])
    assert r.returncode != 0 and "held by another job" in r.stderr
