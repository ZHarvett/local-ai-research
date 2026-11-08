"""scripts/_sandbox.sh: bubblewrap + isolation environment. No GPU, no network, no harness."""

from __future__ import annotations

import os
import socket
import subprocess

import pytest

from conftest import REPO

SANDBOX = REPO / "scripts/_sandbox.sh"


def _bwrap_works() -> bool:
    try:
        return (
            subprocess.run(
                ["bwrap", "--ro-bind", "/", "/", "--unshare-pid", "true"],
                capture_output=True,
                check=False,
                timeout=20,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


needs_bwrap = pytest.mark.skipif(not _bwrap_works(), reason="bubblewrap unavailable here")


def sandbox(*args, env=None):
    return subprocess.run(
        [str(SANDBOX), "--kind", "pytest", *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ, **(env or {})},
    )


def test_print_shows_isolation_environment():
    r = sandbox("--print", "--npm", "--proxy", "4321", "--", "true")
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    state = str(REPO / "third_party/harness-state/pytest")
    for want in (
        "--tmpfs",
        "/home",
        "--unshare-pid",
        "--new-session",
        f"HOME={state}/home",
        f"XDG_CONFIG_HOME={state}/config",
        f"XDG_DATA_HOME={state}/data",
        f"XDG_CACHE_HOME={state}/cache",
        f"XDG_STATE_HOME={state}/state",
        f"TMPDIR={state}/tmp",
        "HTTPS_PROXY=http://127.0.0.1:4321",
        f"npm_config_cache={REPO}/third_party/npm-cache",
    ):
        assert want in lines, want
    assert "env" in lines and "-i" in lines  # environment is built from scratch
    assert "--unshare-net" not in lines
    assert "--unshare-net" in sandbox("--print", "--no-net", "--", "true").stdout.splitlines()


def test_rw_outside_repo_and_scratch_is_refused(tmp_path):
    r = sandbox("--print", "--rw", str(tmp_path), "--", "true")
    assert r.returncode != 0 and "outside the repo" in r.stderr


@needs_bwrap
def test_environment_is_not_inherited_and_home_is_hidden():
    r = sandbox(
        "--",
        "/usr/bin/sh",
        "-c",
        'echo "${LEAK_ME:-unset}"; ls /home | wc -l; echo "$HOME"',
        env={"LEAK_ME": "secret"},
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout.split("\n")
    assert out[0] == "unset"
    assert out[1].strip() == "0"  # /home is an empty tmpfs
    assert out[2] == f"{REPO}/third_party/harness-state/pytest/home"


@needs_bwrap
def test_repo_is_read_only_but_state_and_rw_paths_are_writable():
    scratch = REPO / "third_party/harness-state/pytest-rw"
    scratch.mkdir(parents=True, exist_ok=True)
    r = sandbox(
        "--rw",
        str(scratch),
        "--",
        "/usr/bin/sh",
        "-c",
        f"touch {REPO}/should-not-exist 2>/dev/null && echo repo-writable; "
        f"touch {scratch}/ok && echo rw-ok; touch $HOME/ok && echo state-ok",
    )
    assert "repo-writable" not in r.stdout
    assert "rw-ok" in r.stdout and "state-ok" in r.stdout
    assert not (REPO / "should-not-exist").exists()


@needs_bwrap
def test_no_net_blocks_loopback():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        code = (
            "import socket,sys\n"
            "c=socket.socket(); c.settimeout(2)\n"
            f"try: c.connect(('127.0.0.1',{port})); print('connected')\n"
            "except OSError: print('blocked')\n"
        )
        with_net = sandbox("--", "/usr/bin/python3", "-c", code)
        no_net = sandbox("--no-net", "--", "/usr/bin/python3", "-c", code)
    assert with_net.stdout.strip() == "connected"
    assert no_net.stdout.strip() == "blocked"


def _userns_net_works() -> bool:
    try:
        r = subprocess.run(
            ["unshare", "-Urn", "true"], capture_output=True, check=False, timeout=20
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


needs_netns = pytest.mark.skipif(
    not (_bwrap_works() and _userns_net_works()), reason="user+network namespaces unavailable"
)


@needs_netns
def test_bridge_reaches_only_the_bridged_port_and_nothing_else():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(5)
        port = srv.getsockname()[1]

        def serve():
            while True:
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                c.sendall(b"hello-from-host")
                c.close()

        import threading

        threading.Thread(target=serve, daemon=True).start()
        other = port + 1 if port < 65000 else port - 1
        code = (
            "import socket\n"
            f"c = socket.create_connection(('127.0.0.1', {port}), timeout=5)\n"
            "print(c.recv(100).decode())\n"
            "for host, p in (('1.1.1.1', 443), ('127.0.0.1', %d)):\n"
            "    try:\n"
            "        socket.create_connection((host, p), timeout=2)\n"
            "        print('REACHABLE', host, p)\n"
            "    except OSError:\n"
            "        print('blocked', host, p)\n" % other
        )
        r = sandbox("--bridge", str(port), "--", "/usr/bin/python3", "-c", code)
    assert r.returncode == 0, r.stderr
    out = r.stdout.split("\n")
    assert out[0] == "hello-from-host"
    assert "REACHABLE" not in r.stdout
    assert "blocked 1.1.1.1 443" in out and f"blocked 127.0.0.1 {other}" in out


def test_bridge_rejects_a_non_port_and_the_no_net_combination():
    assert sandbox("--bridge", "abc", "--print", "--", "true").returncode != 0
    r = sandbox("--bridge", "8080", "--no-net", "--print", "--", "true")
    assert r.returncode != 0 and "exclude each other" in r.stderr
    printed = sandbox("--bridge", "8080", "--print", "--", "true").stdout.splitlines()
    assert printed[0] == "unshare" and "-Urn" in printed and "smallpc.netbridge" in printed
