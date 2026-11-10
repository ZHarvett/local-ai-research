"""The Stage 2 spec generator (WP12): cell counts, names, rendered argv, determinism, inputs."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import tomllib
from pathlib import Path

import pytest

from conftest import FIXTURES, REPO
from smallpc.config import ServerConfig, load_machine, load_model, load_sweep
from smallpc.render import render_argv
from smallpc.stage2 import cli, rules, specgen
from smallpc.stage2.shortlist import Entry, ShortlistError, load_shortlist
from smallpc.sweep import spec as sp
from smallpc.sweep.runner import check_spec

TOKEN_VALUE = {"moe_cache_mib": 3072, "n_cpu_moe": 7}  # stand-ins for the run-time token values
STAGE1 = REPO / "configs/sweeps/stage1.toml"


@pytest.fixture(scope="module")
def sl():
    return load_shortlist(REPO)


@pytest.fixture(scope="module")
def stage1_names():
    return {c.name for c in sp.expand(load_sweep(STAGE1), REPO)}


def argv_of(c):
    fields = {k: (TOKEN_VALUE[k] if sp.parse_token(v) else v) for k, v in c.overrides.items()}
    cfg = ServerConfig.model_validate({"profile": c.profile, **fields})
    return render_argv(
        cfg, load_machine(FIXTURES / "machine.toml"), load_model(FIXTURES / "model.toml")
    )


def opt(a, flag):
    return a[a.index(flag) + 1]


def build(tmp_path: Path, stage: str, name: str | None = None, **kw):
    """Generate, write, check, expand: ``(text, check result, {cell name: argv}, cells)``."""
    text = specgen.generate(stage, root=REPO, **kw)
    path = tmp_path / f"{name or stage}.toml"
    path.write_text(text)
    res = check_spec(path, REPO)
    cells = sp.expand(load_sweep(path), REPO)
    sp.validate_cells(cells)
    return text, res, {c.name: argv_of(c) for c in cells}, cells


def fake_2a(sl, second_mtp=2, top_mtp=1, drop=()):
    out = {}
    for ctx in sl.contexts:
        if ctx in drop:
            continue
        top, second = sl.top(ctx), sl.second(ctx)
        out[ctx] = {
            "input_2a2": {
                "top_cell": top.cell,
                "second_cell": second.cell,
                "top_mtp": top_mtp,
                "second_mtp": second_mtp,
            }
        }
    return {"stage": "2a", "contexts": out}


def write_json(tmp_path: Path, name: str, obj) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return p


def winner_json(tmp_path, sl, mtp=0, ctx="64K"):
    e = sl.top(ctx)
    obj = {
        "stage": "2a2",
        "winners": {
            ctx: {
                "cell": f"s2a2-{e.placement}-{ctx}-{e.batch}-mtp{mtp}",
                "placement": e.placement,
                "batch": e.batch,
                "mtp": mtp,
            }  # fmt: skip
        },
    }
    return write_json(tmp_path, "2a2.json", obj)


def candidate_defaults_ok(a):
    assert (opt(a, "-ctk"), opt(a, "-ctv"), opt(a, "-fa"), opt(a, "-np")) == (
        "q8_0", "q8_0", "on", "1",
    )  # fmt: skip
    assert opt(a, "-lv") == "4" and "--metrics" in a and "--port" in a


# ------------------------------------------------------------------ the shortlist


def test_the_shortlist_is_read_from_the_json_and_the_stage1_spec(sl):
    top = {c: (e[0].cell, e[0].placement, e[0].batch) for c, e in sl.contexts.items()}
    assert top == {
        "32K": ("P6-32K-b4096", "P6", "b4096"),
        "64K": ("P6-64K-b4096", "P6", "b4096"),
        "128K": ("P2-128K-b4096", "P2", "b4096"),
    }
    assert [sl.second(c).cell for c in ("32K", "64K", "128K")] == [
        "P2-32K-b4096", "P2-64K-b4096", "P6-128K-b4096",
    ]  # fmt: skip
    assert (
        sl.sha256
        == hashlib.sha256((REPO / "data/analysis/select-screening.json").read_bytes()).hexdigest()
    )


def test_a_shortlist_needing_n_fit_or_unknown_cells_is_refused(tmp_path):
    root = tmp_path / "repo"
    (root / "data/analysis").mkdir(parents=True)
    (root / "configs/sweeps").mkdir(parents=True)
    (root / "configs/sweeps/stage1.toml").write_text(STAGE1.read_text())
    for name, why in (("P8-32K-b4096", "@n_fit"), ("Z9-32K-b4096", "not in")):
        sel = {"mode": "screening", "contexts": {"32K": {"shortlist": [name, "P2-32K-b4096"]}}}
        (root / "data/analysis/select-screening.json").write_text(json.dumps(sel))
        with pytest.raises(ShortlistError, match=why):
            load_shortlist(root)


# ------------------------------------------------------------------ 2f


def test_2f_cells_values_and_argv(tmp_path, stage1_names):
    text, res, argvs, cells = build(tmp_path, "2f")
    assert res["cells"] == 6 and res["by_context"] == {"128K": 4, "64K": 2}
    assert sorted(argvs) == sorted(
        [f"s2f-P2-128K-b4096-mtp0-cram{v}" for v in (8192, 4096, 2048, 0)]
        + [f"s2f-P6-64K-b4096-mtp0-cram{v}" for v in (8192, 2048)]
    )
    for name, a in argvs.items():
        candidate_defaults_ok(a)
        assert opt(a, "--cache-ram") == name.rsplit("cram", 1)[1]  # explicit, "0" included
        assert "--spec-type" not in a and "--spec-draft-n-max" not in a
        assert opt(a, "-b") == opt(a, "-ub") == "4096"
        assert opt(a, "-c") == ("131072" if "128K" in name else "65536")
    assert all(
        "--fit" in a and opt(a, "--fit-target") == "256" for n, a in argvs.items() if "P2" in n
    )
    assert all("-cmoe" in a for n, a in argvs.items() if "P6" in n)
    assert not set(argvs) & stage1_names
    assert [c for c in cells if c.tokens] and all("P6" in c.name for c in cells if c.tokens)


# ------------------------------------------------------------------ 2a and 2a2


def test_2a_has_five_cells_per_context_with_the_mtp_flags(tmp_path, stage1_names, sl):
    _, res, argvs, _ = build(tmp_path, "2a", cache_ram="2048")
    assert res["cells"] == 15 and res["by_context"] == {"32K": 5, "64K": 5, "128K": 5}
    for ctx in ("32K", "64K", "128K"):
        t, s = sl.top(ctx), sl.second(ctx)
        want = {f"s2a-{t.placement}-{ctx}-{t.batch}-mtp{n}" for n in (0, 1, 2, 3)}
        want.add(f"s2a-{s.placement}-{ctx}-{s.batch}-mtp0")
        assert {n for n in argvs if f"-{ctx}-" in n} == want
    for name, a in argvs.items():
        candidate_defaults_ok(a)
        assert opt(a, "--cache-ram") == "2048"
        n = int(name[-1])
        if n == 0:
            assert "--spec-type" not in a and "--spec-draft-n-max" not in a
        else:
            assert opt(a, "--spec-type") == "draft-mtp" and opt(a, "--spec-draft-n-max") == str(n)
    assert not set(argvs) & stage1_names


def test_2a_with_the_default_cache_sets_no_cache_flag(tmp_path):
    _, _, argvs, _ = build(tmp_path, "2a", cache_ram="default")
    assert all("--cache-ram" not in a for a in argvs.values())
    _, _, zero, _ = build(tmp_path, "2a", name="2a0", cache_ram="0")
    assert all(opt(a, "--cache-ram") == "0" for a in zero.values())


def test_2a2_has_the_second_placement_and_the_anchor(tmp_path, sl):
    p = write_json(tmp_path, "2a.json", fake_2a(sl, second_mtp=2, top_mtp=1))
    _, res, argvs, _ = build(tmp_path, "2a2", cache_ram="2048", from_2a=p)
    assert res["cells"] == 9 and res["by_context"] == {"32K": 3, "64K": 3, "128K": 3}
    for ctx in ("32K", "64K", "128K"):
        t, s = sl.top(ctx), sl.second(ctx)
        assert {n for n in argvs if f"-{ctx}-" in n} == {
            f"s2a2-{s.placement}-{ctx}-{s.batch}-mtp0",
            f"s2a2-{s.placement}-{ctx}-{s.batch}-mtp2",
            f"s2a2-{t.placement}-{ctx}-{t.batch}-mtp1",  # the anchor
        }
    for name, a in argvs.items():
        candidate_defaults_ok(a)
        n = int(name[-1])
        assert ("--spec-type" in a) == (n > 0)
    _, res2, argvs2, _ = build(
        tmp_path, "2a2", name="noanchor", cache_ram="2048", from_2a=p, anchor=False
    )
    assert res2["cells"] == 6 and not any("mtp1" in n and "P6-32K" in n for n in argvs2)


def test_2a2_without_an_mtp_cell_for_the_second_placement(tmp_path, sl):
    p = write_json(tmp_path, "2a.json", fake_2a(sl, second_mtp=None, top_mtp=0))
    _, res, argvs, _ = build(tmp_path, "2a2", cache_ram="default", from_2a=p)
    assert res["cells"] == 6 and all(n.endswith("mtp0") for n in argvs)


def test_2a2_refuses_a_2a_result_for_another_shortlist(tmp_path, sl):
    bad = fake_2a(sl)
    bad["contexts"]["32K"]["input_2a2"]["top_cell"] = "P1-32K-b2048"
    with pytest.raises(specgen.SpecGenError, match="shortlist now says"):
        specgen.generate(
            "2a2", root=REPO, cache_ram="default", from_2a=write_json(tmp_path, "b.json", bad)
        )
    with pytest.raises(specgen.SpecGenError, match="needs --from-2a"):
        specgen.generate("2a2", root=REPO, cache_ram="default")
    with pytest.raises(specgen.SpecGenError, match="not a 2a decision"):
        specgen.generate(
            "2a2",
            root=REPO,
            cache_ram="default",
            from_2a=write_json(tmp_path, "c.json", {"stage": "2f"}),
        )


# ------------------------------------------------------------------ 2b, 2c, 2d


@pytest.mark.parametrize("mtp", [0, 2])
def test_2b_compares_8bit_and_fp16_kv(tmp_path, sl, mtp):
    w = winner_json(tmp_path, sl, mtp=mtp)
    _, res, argvs, _ = build(tmp_path, "2b", cache_ram="2048", winner_from=w)
    assert res["cells"] == 2 and res["by_context"] == {"64K": 2}
    q8 = next(a for n, a in argvs.items() if n.endswith("kvq8"))
    f16 = next(a for n, a in argvs.items() if n.endswith("kvf16"))
    assert (opt(q8, "-ctk"), opt(q8, "-ctv")) == ("q8_0", "q8_0")
    # the FP16 cell states -ctk f16 -ctv f16 explicitly (it does not just omit the flags)
    assert (opt(f16, "-ctk"), opt(f16, "-ctv")) == ("f16", "f16")
    for a in (q8, f16):
        assert opt(a, "-fa") == "on" and opt(a, "-np") == "1" and opt(a, "--cache-ram") == "2048"
        assert ("--spec-type" in a) == (mtp > 0)
    assert all(f"mtp{mtp}" in n for n in argvs)


def test_2c_compares_auto_with_the_chosen_alternative(tmp_path, sl):
    _, res, argvs, _ = build(
        tmp_path, "2c", cache_ram="default", winner_from=winner_json(tmp_path, sl)
    )
    assert res["cells"] == 2
    modes = {n.rsplit("-", 1)[1]: opt(a, "--load-mode") for n, a in argvs.items()}
    assert modes == {"lmauto": "auto", f"lm{specgen.LOAD_MODE_ALT}": specgen.LOAD_MODE_ALT}
    # no memlock (the limit is 8 MiB) and a real alternative to auto; the WP12 choice is pinned
    assert specgen.LOAD_MODE_ALT not in ("mlock", "mmap+mlock", "auto", "mmap")
    assert specgen.LOAD_MODE_ALT == "dio" and "lmdio" in modes


def test_2d_threads_only_when_the_default_differs(tmp_path, sl):
    w = winner_json(tmp_path, sl)
    _, res, argvs, _ = build(tmp_path, "2d", cache_ram="default", winner_from=w, default_threads=16)
    assert res["cells"] == 2
    t8 = next(a for n, a in argvs.items() if n.endswith("-t8"))
    tdef = next(a for n, a in argvs.items() if n.endswith("-tdef"))
    assert opt(t8, "-t") == "8" and "-t" not in tdef
    with pytest.raises(specgen.NotNeeded, match="not needed"):
        specgen.generate("2d", root=REPO, cache_ram="default", winner_from=w, default_threads=8)
    with pytest.raises(specgen.SpecGenError, match="--default-threads"):
        specgen.generate("2d", root=REPO, cache_ram="default", winner_from=w)


# ------------------------------------------------------------------ the cache_ram input


def test_the_chosen_cache_ram_is_never_guessed(tmp_path, sl):
    with pytest.raises(specgen.SpecGenError, match="chosen cache_ram is needed"):
        specgen.generate("2a", root=REPO)
    with pytest.raises(specgen.SpecGenError, match="integer or 'default'"):
        specgen.generate("2a", root=REPO, cache_ram="lots")
    with pytest.raises(specgen.SpecGenError, match="not both"):
        specgen.generate("2a", root=REPO, cache_ram="0", from_2f=tmp_path / "x.json")
    for status in ("stop", "needs_human", "no_automatic_decision"):
        p = write_json(
            tmp_path, "2f.json", {"stage": "2f", "status": status, "chosen_cache_ram": 2048}
        )
        with pytest.raises(specgen.SpecGenError, match="a human decides"):
            specgen.generate("2a", root=REPO, from_2f=p)
    ok = write_json(
        tmp_path, "2f.json", {"stage": "2f", "status": "decided", "chosen_cache_ram": 4096}
    )
    _, _, argvs, _ = build(tmp_path, "2a", from_2f=ok)
    assert all(opt(a, "--cache-ram") == "4096" for a in argvs.values())
    keep = write_json(
        tmp_path, "2f2.json", {"stage": "2f", "status": "decided", "chosen_cache_ram": None}
    )
    _, _, argvs, _ = build(tmp_path, "2a", name="2akeep", from_2f=keep)
    assert all("--cache-ram" not in a for a in argvs.values())


# ------------------------------------------------------------------ determinism, provenance, structure


def test_generation_is_deterministic_and_carries_the_provenance(tmp_path, sl):
    for stage, kw in (("2f", {}), ("2a", {"cache_ram": "2048"})):
        a = specgen.generate(stage, root=REPO, **kw)
        assert a == specgen.generate(stage, root=REPO, **kw)
        head = "\n".join(line for line in a.splitlines() if line.startswith("#"))
        assert sl.sha256 in head and sl.spec_sha256 in head
        assert f"plan v{rules.plan_version(REPO)}" in head
        for text in rules.RULES_BY_STAGE[stage]:
            for line in text.split("\n"):
                assert (f"#   {line}" if line else "#") in head.splitlines()
        assert head.index("Rules applied") < a.index("\nname =")  # all of it above the spec body


@pytest.mark.parametrize(
    ("stage", "kw", "count"),
    [("2f", {}, 6), ("2a", {"cache_ram": "default"}, 15)],
)
def test_the_spec_is_a_plain_sweep_spec(tmp_path, stage, kw, count):
    text = specgen.generate(stage, root=REPO, **kw)
    data = tomllib.loads(text)
    assert data["expect_cells"] == count and data["repetitions"] == 5
    s1 = load_sweep(STAGE1)
    assert data["canary"] == {
        "cell": dict(s1.canary.cell),
        "repetitions": 3,
        "points": ["short", "16K"],
    }
    assert data["shuffle_seed"] == s1.shuffle_seed and data["max_restarts"] == s1.max_restarts
    for axis in ("context", "batch", "placement"):  # copied from Stage 1, value by value
        assert all(data["axes"][axis][k] == s1.axes[axis][k] for k in data["axes"][axis])
    assert data["defaults"]["metrics"] is True and data["defaults"]["log_verbosity"] == 4


def test_stage1_stock_cells_still_render_as_before(tmp_path):
    cells = sp.expand(load_sweep(STAGE1), REPO)
    for c in (c for c in cells if c.profile == "stock"):
        a = argv_of(c)
        assert all(f not in a for f in ("-ctk", "--cache-ram", "--spec-type", "--load-mode", "-t"))


# ------------------------------------------------------------------ the functional-test preset


def test_the_functional_test_presets(tmp_path, sl):
    text, res, argvs, _ = build(tmp_path, "2f", name="ft-2f", preset="functional-test")
    data = tomllib.loads(text)
    assert data["name"] == "ft-2f" and data["name"].startswith(specgen.FT_PREFIX)
    assert data["repetitions"] == 1 and "canary" not in data and res["cells"] == 2
    assert specgen.FT_LINE in text.split("\nname =")[0]
    assert sorted(argvs) == [
        f"s2f-{sl.top('32K').placement}-32K-b4096-mtp0-cram{v}" for v in (0, 8192)
    ]
    assert sorted(opt(a, "--cache-ram") for a in argvs.values()) == ["0", "8192"]
    text, res, argvs, _ = build(tmp_path, "2a", name="ft-2a", preset="functional-test")
    assert tomllib.loads(text)["name"] == "ft-2a" and res["cells"] == 2
    assert sorted(opt(a, "--spec-draft-n-max") for a in argvs.values()) == ["1", "3"]


def test_the_functional_2a_preset_adds_a_p6_cell_when_the_top_placement_is_not_p6(tmp_path, sl):
    p2 = Entry("P2-32K-b4096", "P2", "32K", "b4096")
    p6 = Entry("P6-32K-b4096", "P6", "32K", "b4096")
    fake = dataclasses.replace(sl, contexts={**sl.contexts, "32K": (p2, p6)})
    plan = specgen.build_2a(fake, REPO, specgen.CachePolicy(None, "test"), "cmd", ft=True)
    text = specgen.emit(plan)
    path = tmp_path / "ft2a.toml"
    path.write_text(text)
    names = [c.name for c in sp.expand(load_sweep(path), REPO)]
    assert sorted(names) == [
        "s2a-P2-32K-b4096-mtp1", "s2a-P2-32K-b4096-mtp3", "s2a-P6-32K-b4096-mtp2",
    ]  # fmt: skip
    assert plan.expect_cells == 3


def test_presets_exist_for_2f_and_2a_only():
    with pytest.raises(specgen.SpecGenError, match="2f and 2a only"):
        specgen.generate("2b", root=REPO, preset="functional-test", cache_ram="default")


# ------------------------------------------------------------------ the command line


def test_cli_writes_the_spec_and_uses_exit_codes(tmp_path, sl, capsys):
    out = tmp_path / "x/stage2-2f.toml"
    assert cli.main(["spec", "--stage", "2f", "--out", str(out)]) == 0
    assert out.read_text() == specgen.generate(
        "2f", root=REPO, command=out.read_text().split("`")[1]
    )
    assert cli.main(["spec", "--stage", "2a", "--out", str(tmp_path / "a.toml")]) == 2
    assert "chosen cache_ram is needed" in capsys.readouterr().err
    w = winner_json(tmp_path, sl)
    args = ["spec", "--stage", "2d", "--out", str(tmp_path / "d.toml"), "--cache-ram", "default",
            "--winner-from", str(w), "--default-threads", "8"]  # fmt: skip
    assert cli.main(args) == 3
    assert "not needed" in capsys.readouterr().err and not (tmp_path / "d.toml").exists()
