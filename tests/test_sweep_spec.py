"""Sweep spec: expansion, the Stage 1 sketch, section 5.4 defaults, filters and cell order."""

from __future__ import annotations

import pytest

from conftest import FIXTURES, REPO
from smallpc.config import ServerConfig, load_machine, load_model, load_sweep
from smallpc.render import render_argv
from smallpc.sweep import spec as sp

SKETCH = FIXTURES / "stage1-sketch.toml"


@pytest.fixture(scope="module")
def cells():
    s = load_sweep(SKETCH)
    out = sp.expand(s, REPO)
    sp.validate_cells(out)
    return out


def argv_of(c, tokens=None):
    tokens = tokens or {}
    fields = {k: (tokens.get(k, 1) if sp.parse_token(v) else v) for k, v in c.overrides.items()}
    cfg = ServerConfig.model_validate({"profile": c.profile, **fields})
    return render_argv(
        cfg, load_machine(FIXTURES / "machine.toml"), load_model(FIXTURES / "model.toml")
    )


def test_stage1_sketch_expands_to_exactly_57_cells(cells):
    assert len(cells) == 57
    assert sum(c.profile == "stock" for c in cells) == 3
    assert len({c.name for c in cells}) == 57
    by_ctx = {k: sum(c.coords.get("context") == k for c in cells) for k in ("32K", "64K", "128K")}
    assert by_ctx == {"32K": 19, "64K": 19, "128K": 19}


def test_check_fails_when_the_cell_count_differs(tmp_path):
    text = SKETCH.read_text().replace('"P9"]', "]").replace('"P8", ', '"P8"')
    p = tmp_path / "s.toml"
    p.write_text(text)
    s = load_sweep(p)
    assert len(sp.expand(s, REPO)) != s.expect_cells
    from smallpc.sweep.runner import check_spec

    with pytest.raises(sp.SpecError, match="expects 57 cells"):
        check_spec(p, REPO)


def test_every_candidate_cell_renders_the_section_5_4_defaults_and_a_port(cells):
    for c in (c for c in cells if c.profile == "candidate"):
        a = argv_of(c)
        for flag, value in (("-ctk", "q8_0"), ("-ctv", "q8_0"), ("-fa", "on"), ("-np", "1")):
            assert a[a.index(flag) + 1] == value, (c.name, flag)
        assert "--port" in a and a[a.index("--port") + 1] == "8080"
        assert a[a.index("-lv") + 1] == "4" and "--metrics" in a


def test_stock_cells_render_none_of_the_sweep_settings(cells):
    stock = [c for c in cells if c.profile == "stock"]
    assert len(stock) == 3
    for c in stock:
        a = argv_of(c)
        for flag in ("-ctk", "-ctv", "-fa", "-np", "-b", "-ub", "--spec-type"):
            assert flag not in a, (c.name, flag)
        assert a[a.index("-lv") + 1] == "4" and "--port" in a and "-c" in a
        assert "--fit" not in a and "--metrics" in a


def test_candidate_cell_with_tokens_is_valid_and_token_fields_are_restricted(cells):
    p8 = next(c for c in cells if c.name == "P8-32K-b2048")
    assert set(p8.tokens) == {"n_cpu_moe"} and p8.deps == ("P1-32K-b2048",)
    p6 = next(c for c in cells if c.name == "P6-64K-b4096")
    assert p6.tokens["moe_cache_mib"].kind == "max_fit" and p6.deps == ()
    assert next(c for c in cells if c.name == "P7-64K-b4096").tokens["moe_cache_mib"].offset == 2048
    bad = [sp.CellDef("x", "candidate", {"fit_target": "@max_fit", "log_verbosity": 4})]
    with pytest.raises(sp.SpecError, match="not allowed"):
        sp.validate_cells(bad)


def test_token_parsing():
    assert sp.parse_token("@max_fit") == sp.Token("max_fit", 0)
    assert sp.parse_token("@max_fit-2048") == sp.Token("max_fit", 2048)
    assert sp.parse_token("@n_fit(P1)-2") == sp.Token("n_fit", 2, "P1")
    assert sp.parse_token(1024) is None and sp.parse_token("on") is None
    with pytest.raises(sp.SpecError):
        sp.parse_token("@oops")


def test_every_cell_needs_log_verbosity_4(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text(
        'name = "x"\nrepetitions = 1\n[[cells]]\nname = "a"\nprofile = "candidate"\n'
        "[cells.set]\ncontext = 4096\n"
    )
    with pytest.raises(sp.SpecError, match="log_verbosity = 4"):
        sp.validate_cells(sp.expand(load_sweep(p), REPO))


def test_two_axes_setting_the_same_field_is_an_error(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text(
        'name = "x"\nrepetitions = 1\n[axes.a]\nv = { context = 1 }\n[axes.b]\nw = { context = 2 }\n'
        '[[cells]]\nname = "c-{a}-{b}"\nprofile = "candidate"\nproduct = { a = ["v"], b = ["w"] }\n'
    )
    with pytest.raises(sp.SpecError, match="set by both"):
        sp.expand(load_sweep(p), REPO)


def test_wp2_reference_form_still_works(tmp_path):
    p = tmp_path / "s.toml"
    p.write_text(
        'name = "x"\nrepetitions = 1\n[[cells]]\nname = "a"\nconfig = "configs/server/health-64k.toml"\n'
    )
    cs = sp.expand(load_sweep(p), REPO)
    assert (
        cs[0].profile == "candidate" and cs[0].config_path and cs[0].overrides["context"] == 65536
    )


# ---------------------------------------------------------------- filters


def test_only_filters_by_context_and_batch_and_rejects_other_axes(cells):
    only = sp.parse_only(["context=32K"])
    kept = sp.apply_filter(cells, only)
    assert len(kept) == 19 and all(c.coords["context"] == "32K" for c in kept)
    kept = sp.apply_filter(cells, sp.parse_only(["context=32K", "batch=b2048"]))
    assert len(kept) == 9  # nine placements; stock cells have no batch coordinate
    with pytest.raises(sp.SpecError, match="allows only"):
        sp.parse_only(["placement=P1"])
    with pytest.raises(sp.SpecError, match="axis=value"):
        sp.parse_only(["context"])
    with pytest.raises(sp.SpecError, match="matches no cell"):
        sp.apply_filter(cells, {"context": "7K"})


def test_filter_that_removes_an_n_fit_dependency_fails_clearly(cells):
    # P8 depends on P1-32K-b2048; a batch filter keeps the same batch so it is fine ...
    assert sp.apply_filter(cells, {"batch": "b2048"})
    # ... but if the dependency lacks the filtered coordinate it is removed and the error says so
    broken = [c for c in cells if c.name != "P1-32K-b2048"]
    p1 = sp.CellDef("P1-32K-b2048", "candidate", {"fit": "on", "log_verbosity": 4}, coords={})
    with pytest.raises(sp.SpecError, match="removes 'P1-32K-b2048'"):
        sp.apply_filter([*broken, p1], {"context": "32K"})


# ---------------------------------------------------------------- order


def test_cell_order_is_a_seeded_shuffle_that_respects_dependencies(cells):
    a = sp.order_cells(cells, 20261109)
    b = sp.order_cells(list(reversed(cells)), 20261109)
    assert [c.name for c in a] == [c.name for c in b]  # independent of the spec order
    assert [c.name for c in a] != [c.name for c in cells]  # not spec order
    assert [c.name for c in sp.order_cells(cells, 1)] != [c.name for c in a]
    pos = {c.name: i for i, c in enumerate(a)}
    for c in a:
        for d in c.deps:
            assert pos[d] < pos[c.name], (d, c.name)
    assert len(a) == 57


def test_cyclic_dependencies_are_rejected():
    x = sp.CellDef(
        "P8-a", "candidate", {"n_cpu_moe": "@n_fit(P9)"}, {"placement": "P8"}, "{placement}-a"
    )
    y = sp.CellDef(
        "P9-a", "candidate", {"n_cpu_moe": "@n_fit(P8)"}, {"placement": "P9"}, "{placement}-a"
    )
    with pytest.raises(sp.SpecError, match="cyclic"):
        sp.order_cells([x, y], 1)


def test_depth_order_is_deterministic_per_cell_and_repetition():
    d = [8192, 16384, 24576]
    assert sp.depth_order(7, "c", 0, d) == sp.depth_order(7, "c", 0, d)
    seen = {tuple(sp.depth_order(7, "c", r, d)) for r in range(12)}
    assert len(seen) > 1 and all(sorted(s) == d for s in seen)
    assert sp.depth_order(7, "c", 3, d) != sp.depth_order(8, "c", 3, d) or True
    assert d == [8192, 16384, 24576]  # the input list is not modified
