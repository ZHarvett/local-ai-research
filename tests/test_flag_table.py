"""Drift check: every flag in render.FLAG_TABLE must exist in the recorded llama-server --help.

data/env/llama-server-help.txt is saved from the pinned build in WP3 (no GPU needed here).
"""

from __future__ import annotations

import re

import pytest

from conftest import REPO
from smallpc.render import FLAG_TABLE

HELP = REPO / "data/env/llama-server-help.txt"


@pytest.fixture(scope="module")
def help_text() -> str:
    assert HELP.exists(), "run WP3 (scripts/build-llama.sh) to record llama-server --help"
    return HELP.read_text()


def has_flag(text: str, flag: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", text) is not None


@pytest.mark.parametrize(("field", "flag", "kind"), FLAG_TABLE, ids=[f[0] for f in FLAG_TABLE])
def test_flag_in_help(help_text, field, flag, kind):
    assert has_flag(help_text, flag), f"{flag} ({field}) not found in {HELP.name}"


def test_table_has_no_duplicate_flags():
    flags = [f for _, f, _ in FLAG_TABLE]
    assert len(flags) == len(set(flags))


# ---------------------------------------------------------------- accepted values vs --help


def _values_after(text: str, flag: str) -> list[str]:
    m = re.search(rf"^{re.escape(flag)}\s+(\S+)", text, re.M)
    assert m, flag
    return m.group(1).split(",")


def test_spec_type_enum_matches_help(help_text):
    from typing import get_args

    from smallpc.config import SpecType

    assert set(get_args(SpecType)) == set(_values_after(help_text, "--spec-type"))
    assert "draft-mtp" in get_args(SpecType)


def test_load_mode_enum_matches_help(help_text):
    from typing import get_args

    from smallpc.config import LoadMode

    block = re.search(r"--load-mode MODE.*?\(env: LLAMA_ARG_LOAD_MODE\)", help_text, re.S)
    assert block
    listed = set(re.findall(r"^\s+- ([\w+]+):", block.group(0), re.M))
    assert set(get_args(LoadMode)) == listed


def test_kv_types_flash_attn_and_fit_match_help(help_text):
    from typing import get_args

    from smallpc.config import KvType, OnOff, OnOffAuto

    m = re.search(r"-ctk, .*?allowed values: ([\w, ]+)", help_text, re.S)
    assert m
    assert set(get_args(KvType)) == {v.strip() for v in m.group(1).split(",")}
    assert "[on|off|auto]" in re.search(r"--flash-attn .*", help_text).group(0)
    assert set(get_args(OnOffAuto)) == {"on", "off", "auto"}
    assert "--fit [on|off]" in help_text
    assert set(get_args(OnOff)) == {"on", "off"}


def test_log_verbosity_range_matches_help(help_text):
    from smallpc.config import ServerConfig

    block = re.search(r"--log-verbosity N.*?\(default", help_text, re.S)
    assert block
    levels = [int(n) for n in re.findall(r"^\s+- (\d+):", block.group(0), re.M)]
    assert levels == list(range(max(levels) + 1))
    ServerConfig.model_validate({"profile": "candidate", "log_verbosity": max(levels)})
    with pytest.raises(ValueError):
        ServerConfig.model_validate({"profile": "candidate", "log_verbosity": max(levels) + 1})


def test_server_defaults_json_agrees_with_help(help_text):
    import json

    d = json.loads((REPO / "data/env/server-defaults.json").read_text())["defaults"]
    expect = {
        "port": r"--port PORT.*\(default: 9931\)",
        "fit_target": r"default: 1024\s",
        "ctx_size": r"--ctx-size N.*\(default: 0,",
        "batch": r"--batch-size N.*\(default: 2048\)",
        "ubatch": r"--ubatch-size N.*\(default: 512\)",
        "parallel_slots": r"--parallel N.*\(default: -1,",
        "flash_attn": r"'auto', default: 'auto'\)",
        "ctx_checkpoints": r"\(default:\s+32\)",
        "checkpoint_min_step": r"\(default: 8192,",
        "cache_ram": r"--cache-ram N.*\(default: 8192,",
        "spec_draft_n_max": r"--spec-draft-n-max N.*\(default: 3\)",
        "reasoning_budget": r"\(default: -1\)",
    }
    for key, pat in expect.items():
        assert key in d
        assert re.search(pat, help_text), f"{key}: help no longer matches {pat}"
    assert d["spec_type"]["value"] == "none" and d["load_mode"]["value"] == "auto"
    assert d["cache_type_k"]["value"] == d["cache_type_v"]["value"] == "f16"
