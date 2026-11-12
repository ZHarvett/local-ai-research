"""The six released config files (WP13): golden argument lists, `launch-server.sh --dry-run`, and
the tuned files against the resolved configs of their Stage 2 winning cells."""

from __future__ import annotations

import shlex
import subprocess

import pytest
from conftest import FIXTURES, REPO

from smallpc.config import ServerConfig, load_machine, load_model, load_server
from smallpc.render import render_argv

SERVER = REPO / "configs/server"
LAUNCH = REPO / "scripts/launch-server.sh"
BIN = "/opt/smallpc/llama.cpp/build/bin/llama-server"  # tests/fixtures/machine.toml
MODEL = "/opt/smallpc/models/test-model-Q4_K_M.gguf"  # tests/fixtures/model.toml
HEAD = [BIN, "-m", MODEL, "--host", "127.0.0.1", "--port", "8080"]

GOLDEN = {
    "stock-32k": HEAD + ["-c", "32768"],
    "stock-64k": HEAD + ["-c", "65536"],
    "stock-128k": HEAD + ["-c", "131072"],
    "tuned-32k": HEAD
    + "-c 32768 -cmoe --moe-cache-mib 11520 -b 4096 -ub 4096 -ctk q8_0 -ctv q8_0 -fa on -np 1"
    " --cache-ram 2048".split(),
    "tuned-64k": HEAD
    + "-c 65536 -cmoe --moe-cache-mib 9472 -b 4096 -ub 4096 -ctk f16 -ctv f16 -fa on -np 1"
    " --spec-type draft-mtp --spec-draft-n-max 1 --cache-ram 2048".split(),
    "tuned-128k": HEAD
    + "-c 131072 -cmoe --moe-cache-mib 8704 -b 4096 -ub 4096 -ctk f16 -ctv f16 -fa on -np 1"
    " --cache-ram 2048".split(),
}

# tuned file -> (session, winning cell) of the Stage 2 outcome (docs/stage2-summary.md)
WINNERS = {
    "tuned-32k": ("s2a-32K", "s2a-P6-32K-b4096-mtp0"),
    "tuned-64k": ("s2b", "s2b-P6-64K-b4096-mtp1-kvf16"),
    "tuned-128k": ("s2b-128K", "s2b-P6-128K-b4096-mtp0-kvf16"),
}


@pytest.fixture(scope="module")
def machine():
    return load_machine(FIXTURES / "machine.toml"), load_model(FIXTURES / "model.toml")


@pytest.mark.parametrize("name", list(GOLDEN))
def test_rendered_argument_list_is_golden(name, machine):
    m, mdl = machine
    assert render_argv(load_server(SERVER / f"{name}.toml"), m, mdl) == GOLDEN[name]


@pytest.mark.parametrize("name", list(GOLDEN))
def test_launch_server_dry_run_prints_the_golden_list(name):
    r = subprocess.run(
        [
            LAUNCH,
            "--dry-run",
            "--machine",
            FIXTURES / "machine.toml",
            "--model-config",
            FIXTURES / "model.toml",
            SERVER / f"{name}.toml",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert shlex.split(r.stdout) == GOLDEN[name]


@pytest.mark.parametrize("name", ["stock-32k", "stock-64k", "stock-128k"])
def test_stock_files_set_only_the_profile_and_the_context(name):
    cfg = load_server(SERVER / f"{name}.toml")
    assert cfg.profile == "stock"
    assert cfg.model_fields_set == {"profile", "context"}
    argv = " ".join(GOLDEN[name])
    for flag in ("-ctk", "-ctv", "-fa", "-np", "-b ", "-ub", "--spec-type", "--cache-ram", "--fit"):
        assert flag not in argv


@pytest.mark.parametrize("name", ["tuned-32k", "tuned-64k", "tuned-128k"])
def test_tuned_file_equals_its_winners_argument_list_but_for_metrics_and_lv(name, machine):
    m, mdl = machine
    sess, cell = WINNERS[name]
    winner = load_server(REPO / "data/raw" / sess / "resolved" / f"{cell}.toml")
    tuned = load_server(SERVER / f"{name}.toml")
    assert tuned.profile == "tuned"
    a, b = render_argv(winner, m, mdl), render_argv(tuned, m, mdl)
    # the difference is exactly --metrics and -lv 4, which the table puts at the end
    assert a == b + ["--metrics", "-lv", "4"]


@pytest.mark.parametrize("name", list(GOLDEN))
def test_every_file_is_a_valid_server_config_without_logging_flags(name):
    cfg = load_server(SERVER / f"{name}.toml")
    assert isinstance(cfg, ServerConfig)
    assert cfg.metrics is None and cfg.log_verbosity is None
