"""Render a server config plus the machine config into a llama-server argv.

The field-to-flag mapping lives in one table, ``FLAG_TABLE``. The order of that table IS the
order of the rendered argv, so rendering is deterministic. Flag names are the current upstream
names, verified in WP3 against ``llama-server --help`` of build b12208
(``data/env/llama-server-help.txt``; ``tests/test_flag_table.py`` guards against drift).

CLI::

    python -m smallpc.render [--machine M.toml] [--model-config MODEL.toml] [--nul] SERVER.toml
    python -m smallpc.render [--machine M.toml] --gpu-index
"""

from __future__ import annotations

import argparse
import posixpath
import shlex
import sys
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .config import (
    MachineConfig,
    ModelConfig,
    ServerConfig,
    load_machine,
    load_model,
    load_server,
    repo_root,
)

Kind = Literal["value", "switch"]

# (resolved field name, flag, kind). "value": emit ``flag value`` when the field is set.
# "switch": emit the bare flag when the field is True.
# The first three entries are resolved from server config -> machine/model config (see
# ``resolved_values``); the rest come straight from the (effective) server config.
FLAG_TABLE: tuple[tuple[str, str, Kind], ...] = (
    ("model_path", "-m", "value"),
    ("host", "--host", "value"),
    ("port", "--port", "value"),
    ("context", "-c", "value"),
    ("fit", "--fit", "value"),
    ("fit_target", "--fit-target", "value"),
    ("cpu_moe", "-cmoe", "switch"),
    ("n_cpu_moe", "--n-cpu-moe", "value"),
    ("moe_cache_mib", "--moe-cache-mib", "value"),
    ("batch", "-b", "value"),
    ("ubatch", "-ub", "value"),
    ("cache_type_k", "-ctk", "value"),
    ("cache_type_v", "-ctv", "value"),
    ("flash_attn", "-fa", "value"),
    ("parallel", "-np", "value"),
    ("spec_type", "--spec-type", "value"),
    ("spec_draft_n_max", "--spec-draft-n-max", "value"),
    ("threads", "-t", "value"),
    ("load_mode", "--load-mode", "value"),
    ("metrics", "--metrics", "switch"),
    ("slot_save_path", "--slot-save-path", "value"),
    ("log_verbosity", "-lv", "value"),
)


def resolve_model_path(server: ServerConfig, machine: MachineConfig, model: ModelConfig) -> str:
    name = server.model or model.file
    if not name:
        raise ValueError(
            "no model file: set `model` in the server config or `file` in configs/model.toml"
        )
    if posixpath.isabs(name):
        return name
    return posixpath.join(machine.paths.models_dir, name)


def resolved_values(
    server: ServerConfig, machine: MachineConfig, model: ModelConfig
) -> dict[str, object]:
    """Effective value of every field in ``FLAG_TABLE`` (None = not set, not rendered)."""
    eff = server.effective()
    values: dict[str, object] = {
        name: getattr(eff, name) for name, _, _ in FLAG_TABLE if hasattr(eff, name)
    }
    values["model_path"] = resolve_model_path(eff, machine, model)
    values["host"] = eff.host or machine.server.host
    values["port"] = eff.port or machine.server.port
    return values


def render_argv(
    server: ServerConfig, machine: MachineConfig, model: ModelConfig | None = None
) -> list[str]:
    """Return ``[llama-server path, flags...]`` in fixed table order."""
    values = resolved_values(server, machine, model or ModelConfig())
    argv = [machine.paths.llama_server]
    for name, flag, kind in FLAG_TABLE:
        value = values.get(name)
        if value is None:
            continue
        if kind == "switch":
            if value:
                argv.append(flag)
        else:
            argv += [flag, str(value)]
    return argv


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    ap = argparse.ArgumentParser(
        prog="python -m smallpc.render", description=__doc__.split("\n")[0]
    )
    ap.add_argument(
        "server_toml", nargs="?", type=Path, help="server config (configs/server/*.toml)"
    )
    ap.add_argument("--machine", type=Path, default=root / "configs/machine.toml")
    ap.add_argument("--model-config", type=Path, default=root / "configs/model.toml")
    ap.add_argument("--nul", action="store_true", help="NUL-separated output (for shell scripts)")
    ap.add_argument("--gpu-index", action="store_true", help="print the machine's GPU index only")
    args = ap.parse_args(argv)

    try:
        machine = load_machine(args.machine)
        if args.gpu_index:
            print(machine.gpu.index)
            return 0
        if args.server_toml is None:
            ap.error("server_toml is required")
        server = load_server(args.server_toml)
        model = load_model(args.model_config)
        out = render_argv(server, machine, model)
    except (ValidationError, ValueError, OSError) as exc:
        print(f"smallpc.render: {exc}", file=sys.stderr)
        return 2

    if args.nul:
        sys.stdout.write("".join(a + "\0" for a in out))
    else:
        print(shlex.join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
