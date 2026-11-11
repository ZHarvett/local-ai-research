"""tools/merge_sanity.py (WP12 part 2g, step C.1)."""

from __future__ import annotations

import importlib.util
import json

import pytest

from conftest import REPO
from smallpc import select

spec = importlib.util.spec_from_file_location("merge_sanity", REPO / "tools" / "merge_sanity.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def write(tmp_path, name, cells):
    p = tmp_path / name
    p.write_text(json.dumps({"cells": cells}))
    return p


def cell(result, run_id, **kw):
    return {"result": result, "run_id": run_id, "config_sha256": "c" * 8, **kw}


def test_first_run_is_kept_and_repeats_are_listed(tmp_path):
    a = write(tmp_path, "a.json", {
        "ref": cell("pass", "r1", reference=True),
        "x": cell("fail", "x1", failed_prompts=["p0"],
                  prompts={"p0": {"tokens_sha256": "aa"}}),
    })  # fmt: skip
    b = write(tmp_path, "b.json", {"ref": cell("pass", "r2", reference=True),
                                   "x": cell("pass", "x2"), "y": cell("pass", "y1")})  # fmt: skip
    m = tool.merge([a, b])
    assert set(m["cells"]) == {"ref", "x", "y"} and m["sources"] == ["a.json", "b.json"]
    assert m["cells"]["x"]["result"] == "fail" and m["cells"]["x"]["run_id"] == "x1"
    assert m["cells"]["x"]["source"] == "a.json"
    assert m["cells"]["x"]["tokens_sha256"] == {"p0": "aa"}
    assert [r["run_id"] for r in m["repeats"]["x"]] == ["x2"]  # a disagreeing repeat stays visible
    assert m["repeats"]["x"][0]["result"] == "pass" and "y" not in m["repeats"]
    assert [r["run_id"] for r in m["repeats"]["ref"]] == ["r2"]


def test_the_result_is_what_select_reads(tmp_path):
    m = tool.merge([write(tmp_path, "a.json", {"x": cell("fail", "x1"), "y": cell("pass", "y1")})])
    assert select.sanity_state("x", m) == "fail" and select.sanity_state("y", m) == "pass"
    assert select.sanity_state("z", m) == "not run"


def test_main_writes_the_file_and_rejects_a_non_sanity_file(tmp_path, capsys):
    a = write(tmp_path, "a.json", {"x": cell("pass", "x1")})
    out = tmp_path / "o" / "all.json"
    assert tool.main([str(a), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["cells"]["x"]["result"] == "pass"
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert tool.main([str(bad), "--out", str(out)]) == 2
    with pytest.raises(ValueError, match="not a sanity file"):
        tool.merge([bad])
