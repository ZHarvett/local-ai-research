"""configs/sweeps/stage3.toml, stage4.toml and ft-stage3.toml (WP13): the cells reference the released
config files and add --metrics -lv 4 and nothing else; `check` passes; `--only context=` selects a context.
Also the spec-format additions this needs (reference cells with `coords` and `apply_defaults`)."""

from __future__ import annotations

import pytest
from conftest import FIXTURES, REPO

from smallpc.config import ServerConfig, load_machine, load_model, load_server, load_sweep
from smallpc.render import render_argv
from smallpc.stage2 import eligibility
from smallpc.sweep import runner
from smallpc.sweep import spec as sp

SPECS = REPO / "configs/sweeps"
FILES = {
    "stock-32K": "stock-32k",
    "tuned-32K": "tuned-32k",
    "stock-64K": "stock-64k",
    "tuned-64K": "tuned-64k",
    "stock-128K": "stock-128k",
    "tuned-128K": "tuned-128k",
}
MACHINE = load_machine(FIXTURES / "machine.toml")
MODEL = load_model(FIXTURES / "model.toml")
NOT_IN_STOCK = ("-ctk", "-ctv", "-fa", "-np", "-b", "-ub", "--spec-type", "--cache-ram")


def cell_argv(cell: sp.CellDef) -> list[str]:
    return render_argv(
        ServerConfig.model_validate({"profile": cell.profile, **cell.overrides}), MACHINE, MODEL
    )


def file_argv(name: str) -> list[str]:
    return render_argv(load_server(REPO / "configs/server" / f"{FILES[name]}.toml"), MACHINE, MODEL)


@pytest.mark.parametrize(
    ("spec", "cells", "contexts"),
    [
        ("stage3", 6, {"32K": 2, "64K": 2, "128K": 2}),
        ("stage4", 2, {"64K": 2}),
        ("ft-stage3", 2, {"32K": 2}),
    ],
)
def test_check_passes_with_the_declared_number_of_cells(spec, cells, contexts):
    r = runner.check_spec(SPECS / f"{spec}.toml", REPO)
    assert r["cells"] == cells and r["by_context"] == contexts and r["canary"] is True
    assert load_sweep(SPECS / f"{spec}.toml").expect_cells == cells


@pytest.mark.parametrize("ctx", ["32K", "64K", "128K"])
def test_stage3_only_context_selects_stock_and_tuned_of_that_context(ctx):
    r = runner.check_spec(SPECS / "stage3.toml", REPO, only={"context": ctx})
    assert r["cells"] == 2 and r["stock_cells"] == 1 and r["cells_in_spec"] == 6
    names = [
        c.name
        for c in sp.apply_filter(
            sp.expand(load_sweep(SPECS / "stage3.toml"), REPO), {"context": ctx}
        )
    ]
    assert sorted(names) == [f"stock-{ctx}", f"tuned-{ctx}"]


@pytest.mark.parametrize("spec", ["stage3", "stage4", "ft-stage3"])
def test_every_cell_is_its_config_file_plus_metrics_and_lv4(spec):
    cells = sp.expand(load_sweep(SPECS / f"{spec}.toml"), REPO)
    assert cells and all(c.config_path for c in cells)
    for c in cells:
        assert c.config_path == f"configs/server/{FILES[c.name]}.toml"
        assert cell_argv(c) == file_argv(c.name) + ["--metrics", "-lv", "4"]
        assert c.profile == ("stock" if c.name.startswith("stock") else "tuned")


@pytest.mark.parametrize("spec", ["stage3", "stage4", "ft-stage3"])
def test_stock_cells_render_no_candidate_flags(spec):
    stock = [c for c in sp.expand(load_sweep(SPECS / f"{spec}.toml"), REPO) if c.profile == "stock"]
    assert stock
    for c in stock:
        argv = cell_argv(c)
        assert not [a for a in argv if a in NOT_IN_STOCK], argv
        assert set(c.overrides) == {"context", "metrics", "log_verbosity"}


def test_the_specs_hold_nothing_but_the_logging_defaults_and_the_canary():
    for spec in ("stage3", "stage4", "ft-stage3"):
        s = load_sweep(SPECS / f"{spec}.toml")
        assert s.defaults == s.stock_defaults == {"metrics": True, "log_verbosity": 4}
        assert not s.axes and all(c.config and not c.set for c in s.cells)
        assert s.canary is not None and s.canary.cell["context"] == 65536
    assert load_sweep(SPECS / "stage3.toml").repetitions == 5
    assert load_sweep(SPECS / "stage4.toml").repetitions == 5
    assert load_sweep(SPECS / "ft-stage3.toml").repetitions == 1


def test_the_functional_test_spec_says_so_and_the_real_specs_do_not():
    assert "functional-test" in eligibility.spec_header(SPECS / "ft-stage3.toml").lower()
    for spec in ("stage3", "stage4"):
        assert "functional-test" not in eligibility.spec_header(SPECS / f"{spec}.toml").lower()


# ---------------------------------------------------------------- the spec-format additions


def write(tmp_path, body: str):
    p = tmp_path / "s.toml"
    p.write_text('name = "x"\nrepetitions = 1\n' + body)
    return p


REF = '[[cells]]\nname = "a"\nconfig = "configs/server/tuned-32k.toml"\n'


def test_reference_cell_without_the_new_fields_behaves_as_before(tmp_path):
    p = write(tmp_path, "[defaults]\nmetrics = true\n" + REF)
    (c,) = sp.expand(load_sweep(p), REPO)
    assert c.coords == {} and "metrics" not in c.overrides  # defaults are not applied unasked


def test_apply_defaults_merges_the_profile_defaults_under_the_file(tmp_path):
    body = "[defaults]\nmetrics = true\nlog_verbosity = 4\n[stock_defaults]\nmetrics = true\n"
    p = write(tmp_path, body + REF + "apply_defaults = true\ncoords = { context = '32K' }\n")
    (c,) = sp.expand(load_sweep(p), REPO)
    assert c.coords == {"context": "32K"} and c.overrides["log_verbosity"] == 4
    assert c.overrides["cache_ram"] == 2048  # the file's own fields stay
    q = write(
        tmp_path,
        body
        + '[[cells]]\nname = "s"\nconfig = "configs/server/stock-32k.toml"\napply_defaults = true\n',
    )
    (s,) = sp.expand(load_sweep(q), REPO)
    assert s.overrides == {"context": 32768, "metrics": True}  # stock gets stock_defaults only


def test_apply_defaults_refuses_a_value_that_clashes_with_the_file(tmp_path):
    p = write(tmp_path, "[defaults]\ncache_ram = 8192\n" + REF + "apply_defaults = true\n")
    with pytest.raises(sp.SpecError, match="cache_ram"):
        sp.expand(load_sweep(p), REPO)
    ok = write(tmp_path, "[defaults]\ncache_ram = 2048\n" + REF + "apply_defaults = true\n")
    assert sp.expand(load_sweep(ok), REPO)[0].overrides["cache_ram"] == 2048  # same value: fine


def test_coords_and_apply_defaults_belong_to_reference_cells(tmp_path):
    for field in ("apply_defaults = true", "coords = { context = '32K' }"):
        p = write(tmp_path, f'[[cells]]\nname = "a"\nprofile = "candidate"\n{field}\n')
        with pytest.raises(ValueError, match="reference cells"):
            load_sweep(p)


def test_only_matches_a_reference_cell_by_its_coords(tmp_path):
    two = (
        REF
        + "coords = { context = '32K' }\n"
        + REF.replace('"a"', '"b"')
        + "coords = { context = '64K' }\n"
    )
    cells = sp.expand(load_sweep(write(tmp_path, two)), REPO)
    assert [c.name for c in sp.apply_filter(cells, {"context": "64K"})] == ["b"]
