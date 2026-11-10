"""tools/repair_rerun_summaries.py on a throw-away git repository (WP12 part 2d, B3)."""

from __future__ import annotations

import importlib.util
import json
import subprocess

from conftest import REPO

spec = importlib.util.spec_from_file_location(
    "repair_rerun_summaries", REPO / "tools" / "repair_rerun_summaries.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

COORDS = {"placement": "P6", "context": "32K", "batch": "b4096"}
RES = {"moe_cache_mib": {"token": "max_fit", "base": 9000, "value": 9000}}


def git(repo, *a):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True,
        capture_output=True,
    )  # fmt: skip


def write(p, obj):
    p.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n")


def make_repo(tmp_path, res_in_jsonl=RES):
    s = tmp_path / "data" / "raw" / "sess"
    (s / "cells").mkdir(parents=True)
    (s / "resolved").mkdir()
    (s / "resolved" / "P6-32K-b4096.toml").write_text(
        'profile = "candidate"\ncontext = 32768\nbatch = 4096\nmoe_cache_mib = 9000\n'
    )
    (s / "resolutions.jsonl").write_text(
        json.dumps({"cell": "P6-32K-b4096", "resolution": res_in_jsonl}) + "\n"
    )
    cell = s / "cells" / "P6-32K-b4096-abcd1234.json"
    first = {"cell": "P6-32K-b4096", "coords": COORDS, "resolution": RES, "instances": [{"i": 0}]}
    write(cell, first)
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "first")
    blank = {**first, "coords": {}, "resolution": {}, "instances": [{"i": 0}, {"i": 1}]}
    write(cell, blank)
    git(tmp_path, "commit", "-qam", "rerun")
    return s, cell


def test_repairs_only_coords_and_resolution_and_audits(tmp_path, monkeypatch):
    s, cell = make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    rel = s.relative_to(tmp_path)
    before = cell.read_bytes()
    assert tool.main([str(rel), "--apply"]) == 0
    after = json.loads(cell.read_text())
    assert after["coords"] == COORDS and after["resolution"] == RES
    assert after["instances"] == [{"i": 0}, {"i": 1}]  # the re-run's instance is kept
    assert list(after) == ["cell", "coords", "resolution", "instances"]  # key order unchanged
    audit = [json.loads(x) for x in (s / "repairs.jsonl").read_text().splitlines()]
    assert len(audit) == 1 and audit[0]["keys"] == ["coords", "resolution"]
    assert audit[0]["sha256_before"] == tool.sha256(before)
    assert audit[0]["sha256_after"] == tool.sha256(cell.read_bytes())
    assert tool.main([str(rel), "--apply"]) == 0  # nothing left to repair
    assert len((s / "repairs.jsonl").read_text().splitlines()) == 1


def test_an_inconsistent_cell_is_reported_and_left_alone(tmp_path, monkeypatch):
    s, cell = make_repo(tmp_path, res_in_jsonl={"moe_cache_mib": {"value": 1}})
    monkeypatch.chdir(tmp_path)
    before = cell.read_bytes()
    assert tool.main([str(s.relative_to(tmp_path)), "--apply"]) == 1
    assert cell.read_bytes() == before and not (s / "repairs.jsonl").exists()
