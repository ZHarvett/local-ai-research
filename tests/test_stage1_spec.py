"""The real Stage 1 and pre-flight specs (configs/sweeps/): the expansion of step plan 5.4, exactly."""

from __future__ import annotations

import pytest

from conftest import FIXTURES, REPO
from smallpc.config import ServerConfig, load_machine, load_model, load_sweep
from smallpc.render import render_argv
from smallpc.sweep import spec as sp
from smallpc.sweep.runner import check_spec

STAGE1 = REPO / "configs/sweeps/stage1.toml"
PREFLIGHT = REPO / "configs/sweeps/preflight.toml"
SKETCH = FIXTURES / "stage1-sketch.toml"
TOKEN_VALUE = {"moe_cache_mib": 3072, "n_cpu_moe": 7}  # stand-ins for the run-time token values


@pytest.fixture(scope="module")
def cells():
    out = sp.expand(load_sweep(STAGE1), REPO)
    sp.validate_cells(out)
    return out


def argv_of(c):
    fields = {k: (TOKEN_VALUE[k] if sp.parse_token(v) else v) for k, v in c.overrides.items()}
    cfg = ServerConfig.model_validate({"profile": c.profile, **fields})
    return render_argv(
        cfg, load_machine(FIXTURES / "machine.toml"), load_model(FIXTURES / "model.toml")
    )


def opt(a, flag):
    return a[a.index(flag) + 1]


def test_stage1_is_57_cells_and_19_per_context(cells):
    assert len(cells) == 57 and len({c.name for c in cells}) == 57
    assert sum(c.profile == "stock" for c in cells) == 3
    for k in ("32K", "64K", "128K"):
        kept = sp.apply_filter(cells, {"context": k})
        assert len(kept) == 19, k
        assert sum(c.profile == "stock" for c in kept) == 1
        assert len({c.coords.get("batch") for c in kept if c.profile != "stock"}) == 2


def test_check_output_counts(capsys):
    full = check_spec(STAGE1, REPO)
    assert full["cells"] == 57 and full["by_context"] == {"32K": 19, "64K": 19, "128K": 19}
    assert full["by_axis"]["batch"] == {"b2048": 27, "b4096": 27}
    assert full["by_axis"]["placement"] == {f"P{i}": 6 for i in range(1, 10)}
    assert full["by_axis"]["profile"] == {"candidate": 54, "stock": 3}
    assert full["estimate"]["total_h"] > 0
    for k in ("32K", "64K", "128K"):
        part = check_spec(STAGE1, REPO, {"context": k})
        assert part["cells"] == 19 and part["cells_in_spec"] == 57 and part["by_context"] == {k: 19}
    assert 6 < full["estimate"]["total_h"] < 9  # plan 5.4: "about 8 hours of GPU time"


def test_stage1_axes_and_defaults_are_those_of_the_reviewed_sketch():
    a, b = load_sweep(STAGE1), load_sweep(SKETCH)
    assert a.axes == b.axes and a.defaults == b.defaults and a.stock_defaults == b.stock_defaults
    assert a.cells == b.cells and a.canary == b.canary
    assert (a.repetitions, a.expect_cells, a.shuffle_seed) == (2, 57, b.shuffle_seed)


def test_stock_cells_render_none_of_the_sweep_settings(cells):
    for c in (c for c in cells if c.profile == "stock"):
        a = argv_of(c)
        for flag in ("-ctk", "-ctv", "-fa", "-np", "-b", "-ub", "--spec-type"):
            assert flag not in a, (c.name, flag)
        for flag in ("--fit", "-cmoe", "--n-cpu-moe", "--moe-cache-mib"):
            assert flag not in a, (c.name, flag)


def test_candidate_cells_render_the_defaults_batch_and_an_explicit_port(cells):
    for c in (c for c in cells if c.profile == "candidate"):
        a = argv_of(c)
        assert (opt(a, "-ctk"), opt(a, "-ctv"), opt(a, "-fa"), opt(a, "-np")) == (
            "q8_0", "q8_0", "on", "1",
        )  # fmt: skip
        assert "--port" in a
        batch = {"b2048": "2048", "b4096": "4096"}[c.coords["batch"]]
        assert opt(a, "-b") == batch and opt(a, "-ub") == batch, c.name
        assert opt(a, "-c") == str(
            {"32K": 32768, "64K": 65536, "128K": 131072}[c.coords["context"]]
        )


def test_placements_render_as_section_5_4_says(cells):
    for c in (c for c in cells if c.profile == "candidate"):
        a, p = argv_of(c), c.coords["placement"]
        if p in ("P1", "P2", "P3", "P4", "P5"):
            assert opt(a, "--fit") == "on" and "-cmoe" not in a and "--n-cpu-moe" not in a
        if p == "P2":
            assert opt(a, "--fit-target") == "256"
        else:
            assert "--fit-target" not in a
        if p in ("P3", "P4", "P5"):
            assert opt(a, "--moe-cache-mib") == {"P3": "1024", "P4": "2048", "P5": "4096"}[p]
        elif p not in ("P6", "P7"):
            assert "--moe-cache-mib" not in a
        if p in ("P6", "P7"):
            assert "-cmoe" in a and opt(a, "--moe-cache-mib") == "3072"
            assert "--n-cpu-moe" not in a and "--fit" not in a  # fit left at the server default
            assert c.tokens["moe_cache_mib"].kind == "max_fit"
            assert c.tokens["moe_cache_mib"].offset == (0 if p == "P6" else 2048)
        if p in ("P8", "P9"):
            assert opt(a, "--fit") == "off" and opt(a, "--n-cpu-moe") == "7" and "-cmoe" not in a
            t = c.tokens["n_cpu_moe"]
            assert (t.kind, t.ref, t.offset) == ("n_fit", "P1", 0 if p == "P8" else 2)
            assert c.deps == (c.name.replace(p, "P1"),)


def test_every_cell_has_lv_4_and_metrics_and_no_mtp(cells):
    for c in cells:
        a = argv_of(c)
        assert opt(a, "-lv") == "4" and "--metrics" in a and "--spec-type" not in a, c.name


# ------------------------------------------------------------------------------ pre-flight


def test_preflight_cells_are_a_subset_of_stage1_with_identical_settings(cells):
    pre = sp.expand(load_sweep(PREFLIGHT), REPO)
    sp.validate_cells(pre)
    by_name = {c.name: c for c in cells}
    assert sorted(c.name for c in pre) == sorted(
        [f"{p}-32K-b2048" for p in ("P1", "P3", "P6", "P7", "P8", "P9")]
        + [f"{p}-128K-b2048" for p in ("P1", "P6", "P8")]
        + ["P1-32K-b4096"]
    )
    for c in pre:
        s1 = by_name[c.name]
        assert (c.profile, c.overrides, c.coords) == (s1.profile, s1.overrides, s1.coords), c.name
        assert argv_of(c) == argv_of(s1)
    # the n_fit dependencies resolve inside the pre-flight (P1 of the same context and batch)
    names = {c.name for c in pre}
    for c in pre:
        assert set(c.deps) <= names


def test_preflight_spec_header_and_shape():
    s, st = load_sweep(PREFLIGHT), load_sweep(STAGE1)
    assert (s.repetitions, s.expect_cells, s.canary) == (1, 10, None)
    assert s.axes == st.axes and s.defaults == st.defaults and s.stock_defaults == st.stock_defaults
    out = check_spec(PREFLIGHT, REPO)
    assert out["cells"] == 10 and out["by_context"] == {"32K": 7, "128K": 3}
    assert out["by_axis"]["batch"] == {"b2048": 9, "b4096": 1} and out["canary"] is False
