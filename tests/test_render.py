from __future__ import annotations

import shlex
import subprocess
import sys

import pytest

from conftest import EXAMPLE_NAMES, EXAMPLES, FIXTURES, GOLDEN, REPO
from smallpc.config import ServerConfig, load_machine, load_model, load_server
from smallpc.render import FLAG_TABLE, render_argv

MACHINE = FIXTURES / "machine.toml"
MODEL = FIXTURES / "model.toml"
FORBIDDEN_IN_STOCK = ["-ctk", "-ctv", "-fa", "-np", "-b", "-ub", "--spec-type"]


def golden(name: str) -> list[str]:
    return (GOLDEN / f"{name}.argv").read_text().splitlines()


def render_example(name: str) -> list[str]:
    return render_argv(
        load_server(EXAMPLES / f"{name}.toml"), load_machine(MACHINE), load_model(MODEL)
    )


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_golden_argv(name):
    assert render_example(name) == golden(name)


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_rendering_is_deterministic(name):
    first = render_example(name)
    assert all(render_example(name) == first for _ in range(5))


def test_order_follows_table_not_toml_order(tmp_path):
    a = tmp_path / "a.toml"
    b = tmp_path / "b.toml"
    a.write_text('profile="candidate"\ncontext=1024\nthreads=4\nfit="on"\n')
    b.write_text('fit="on"\nthreads=4\ncontext=1024\nprofile="candidate"\n')
    machine, model = load_machine(MACHINE), load_model(MODEL)
    assert render_argv(load_server(a), machine, model) == render_argv(
        load_server(b), machine, model
    )


def test_flag_table_names_are_unique_and_known():
    fields = [f for f, _, _ in FLAG_TABLE]
    flags = [f for _, f, _ in FLAG_TABLE]
    assert len(set(fields)) == len(fields) and len(set(flags)) == len(flags)
    expected = {
        "-c",
        "--fit",
        "--fit-target",
        "-cmoe",
        "--n-cpu-moe",
        "--moe-cache-mib",
        "-b",
        "-ub",
        "-ctk",
        "-ctv",
        "-fa",
        "-np",
        "--spec-type",
        "--spec-draft-n-max",
        "-t",
        "--load-mode",
        "--metrics",
        "--slot-save-path",
        "-lv",
    }
    assert expected <= set(flags)
    # every ServerConfig field except profile/model is either in the table or a table alias
    server_fields = set(ServerConfig.model_fields) - {"profile", "model"}
    assert server_fields <= set(fields)


def test_stock_argv_has_no_sweep_flags():
    argv = render_example("stock-64k")
    for flag in FORBIDDEN_IN_STOCK:
        assert flag not in argv
    assert argv[1:] == [
        "-m",
        "/opt/smallpc/models/test-model-Q4_K_M.gguf",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "-c",
        "65536",
        "--metrics",
    ]


def test_candidate_gets_sweep_defaults_in_argv():
    argv = render_example("fit-64k-q8")
    for flag, value in [("-ctk", "q8_0"), ("-ctv", "q8_0"), ("-fa", "on"), ("-np", "1")]:
        assert argv[argv.index(flag) + 1] == value


def test_explicit_port_always_present():
    for name in EXAMPLE_NAMES:
        argv = render_example(name)
        assert argv[argv.index("--port") + 1] == "8080"


def test_server_overrides_and_absolute_model(tmp_path):
    cfg = ServerConfig(profile="stock", model="/abs/m.gguf", host="0.0.0.0", port=9000, context=8)
    argv = render_argv(cfg, load_machine(MACHINE), load_model(MODEL))
    assert argv[1:7] == ["-m", "/abs/m.gguf", "--host", "0.0.0.0", "--port", "9000"]


def test_missing_model_is_an_error():
    from smallpc.config import ModelConfig

    with pytest.raises(ValueError, match="no model file"):
        render_argv(ServerConfig(profile="stock"), load_machine(MACHINE), ModelConfig())


def test_real_configs_render_all_examples():
    machine = load_machine(REPO / "configs/machine.toml")
    model = load_model(REPO / "configs/model.toml")
    for name in EXAMPLE_NAMES:
        argv = render_argv(load_server(EXAMPLES / f"{name}.toml"), machine, model)
        assert argv[0] == machine.paths.llama_server and "--port" in argv


# ------------------------------------------------------------------ CLI


def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "smallpc.render", *args], capture_output=True, text=True, check=False
    )


def test_cli_default_output_is_one_quoted_line():
    r = cli("--machine", str(MACHINE), "--model-config", str(MODEL), str(EXAMPLES / "mtp-64k.toml"))
    assert r.returncode == 0
    assert shlex.split(r.stdout) == golden("mtp-64k")
    assert r.stdout.count("\n") == 1


def test_cli_nul_output():
    r = cli(
        "--nul",
        "--machine",
        str(MACHINE),
        "--model-config",
        str(MODEL),
        str(EXAMPLES / "fit-64k-q8.toml"),
    )
    assert r.returncode == 0
    assert r.stdout.endswith("\0")
    assert r.stdout.split("\0")[:-1] == golden("fit-64k-q8")


def test_cli_gpu_index():
    r = cli("--gpu-index", "--machine", str(MACHINE))
    assert (r.returncode, r.stdout.strip()) == (0, "0")


def test_cli_validation_error_exits_2(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('profile = "stock"\nparallel = 2\n')
    r = cli("--machine", str(MACHINE), "--model-config", str(MODEL), str(bad))
    assert r.returncode == 2 and "stock config may set only" in r.stderr
    assert r.stdout == ""
