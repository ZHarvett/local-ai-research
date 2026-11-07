from __future__ import annotations

import pytest
from pydantic import ValidationError

from conftest import EXAMPLE_NAMES, EXAMPLES, REPO
from smallpc.config import (
    STOCK_ALLOWED_FIELDS,
    ServerConfig,
    load_machine,
    load_model,
    load_server,
    load_sweep,
)


def test_repo_configs_load():
    machine = load_machine(REPO / "configs/machine.toml")
    assert machine.paths.llama_server.endswith("third_party/llama.cpp/build/bin/llama-server")
    assert machine.server.port == 8080 and machine.server.host == "127.0.0.1"
    assert machine.paths.slot_save_dir == "/dev/shm/local-ai-research-slots"
    assert machine.bios.expo and machine.bios.igpu and machine.bios.pbo_eco_mode
    load_model(REPO / "configs/model.toml")


def test_machine_does_not_require_binary_to_exist():
    # The build does not exist until WP3; loading must not touch the file system.
    machine = load_machine(REPO / "configs/machine.toml")
    assert machine.paths.llama_server


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_load(name):
    assert load_server(EXAMPLES / f"{name}.toml").profile in {"stock", "candidate", "tuned"}


def test_model_fields_all_optional():
    from smallpc.config import ModelConfig

    assert ModelConfig().sha256 is None


# ------------------------------------------------------------------ validation errors


def test_unknown_field_rejected():
    with pytest.raises(ValidationError, match="bogus"):
        ServerConfig.model_validate({"profile": "candidate", "bogus": 1})


def test_unknown_field_rejected_in_machine(tmp_path):
    p = tmp_path / "m.toml"
    p.write_text(
        '[paths]\nllama_server="/a"\nmodels_dir="/b"\nslot_save_dir="/c"\nextra="x"\n'
        "[server]\nport=1\n"
    )
    with pytest.raises(ValidationError, match="extra"):
        load_machine(p)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cache_type_k", "q8_0"),
        ("cache_type_v", "q8_0"),
        ("flash_attn", "on"),
        ("parallel", 1),
        ("batch", 2048),
        ("ubatch", 512),
        ("spec_type", "draft-mtp"),
        ("fit", "on"),
        ("threads", 8),
    ],
)
def test_stock_cannot_set_forbidden_field(field, value):
    with pytest.raises(ValidationError, match="stock config may set only"):
        ServerConfig.model_validate({"profile": "stock", field: value})


def test_stock_may_set_allowed_fields():
    cfg = ServerConfig.model_validate(
        {
            "profile": "stock",
            "model": "m.gguf",
            "context": 32768,
            "host": "127.0.0.1",
            "port": 9000,
            "metrics": True,
            "log_verbosity": 3,
        }
    )
    assert cfg.model_fields_set - {"profile"} == STOCK_ALLOWED_FIELDS - {"profile"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "experimental"),
        ("flash_attn", "yes"),
        ("cache_type_k", "q9_9"),
        ("spec_type", "magic"),
        ("load_mode", "mlock-everything"),
        ("fit", "auto"),
    ],
)
def test_bad_enum_value_rejected(field, value):
    data = {"profile": "candidate"}
    data[field] = value
    with pytest.raises(ValidationError):
        ServerConfig.model_validate(data)


@pytest.mark.parametrize(
    "data",
    [
        {"cpu_moe": True, "n_cpu_moe": 10},
        {"fit": "off", "fit_target": 256},
        {"batch": 512, "ubatch": 1024},
        {"spec_draft_n_max": 2},
        {"slot_save_path": "relative/dir"},
        {"context": 0},
        {"port": 70000},
    ],
)
def test_inconsistent_values_rejected(data):
    with pytest.raises(ValidationError):
        ServerConfig.model_validate({"profile": "candidate", **data})


def test_model_sha256_must_be_hex():
    from smallpc.config import ModelConfig

    with pytest.raises(ValidationError):
        ModelConfig.model_validate({"sha256": "nothex"})


# ------------------------------------------------------------------ sweep defaults


def test_sweep_defaults_only_for_candidate_and_tuned():
    for profile in ("candidate", "tuned"):
        eff = ServerConfig(profile=profile).effective()
        assert (eff.cache_type_k, eff.cache_type_v) == ("q8_0", "q8_0")
        assert (eff.flash_attn, eff.parallel) == ("on", 1)
    stock = ServerConfig(profile="stock", context=65536).effective()
    assert stock.cache_type_k is None and stock.cache_type_v is None
    assert stock.flash_attn is None and stock.parallel is None


def test_explicit_values_beat_sweep_defaults():
    eff = ServerConfig(profile="candidate", cache_type_k="f16", parallel=2).effective()
    assert eff.cache_type_k == "f16" and eff.parallel == 2
    assert eff.cache_type_v == "q8_0"


# ------------------------------------------------------------------ sweep spec


def test_sweep_spec_loads(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text(
        'name = "mini"\nrepetitions = 2\n'
        '[[cells]]\nname = "stock-64k"\nconfig = "configs/server/examples/stock-64k.toml"\n'
        '[[cells]]\nname = "fit-64k"\nconfig = "configs/server/examples/fit-64k-q8.toml"\n'
    )
    spec = load_sweep(p)
    assert spec.repetitions == 2 and [c.name for c in spec.cells] == ["stock-64k", "fit-64k"]


@pytest.mark.parametrize(
    "text",
    [
        'name = "x"\nrepetitions = 0\n[[cells]]\nname = "a"\nconfig = "c.toml"\n',
        'name = "x"\nrepetitions = 1\n',
        'name = "x"\nrepetitions = 1\n[[cells]]\nname = "a"\nconfig = "c"\n'
        '[[cells]]\nname = "a"\nconfig = "d"\n',
        'name = "x"\nrepetitions = 1\nfoo = 1\n[[cells]]\nname = "a"\nconfig = "c"\n',
    ],
)
def test_sweep_spec_invalid(tmp_path, text):
    p = tmp_path / "s.toml"
    p.write_text(text)
    with pytest.raises(ValidationError):
        load_sweep(p)
