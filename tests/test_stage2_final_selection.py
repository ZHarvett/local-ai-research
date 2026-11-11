"""tools/stage2_final_selection.py: provenance around the final selection (WP12 part 2g)."""

from __future__ import annotations

import importlib.util

from conftest import REPO

spec = importlib.util.spec_from_file_location(
    "stage2_final_selection", REPO / "tools" / "stage2_final_selection.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

RESULT = {"mode": "final", "min_clean": 5, "contexts": {}}
PROV = {
    "sessions": [{"session_id": "s", "spec_path": "a.toml", "spec_sha256": "ab" * 32,
                  "session_git_commit": "c" * 40}],
    "plan_version": "1.6", "code": {"commit": "d" * 40, "dirty": False},
    "llama_cpp_commit": "e" * 40, "rule_text": ["line one\n\nline two"],
}  # fmt: skip


def test_build_adds_provenance_sanity_and_rule_text():
    san = {"cells": {"x": {"result": "pass"}, "y": {"result": "fail"}}}
    obj, md = tool.build(RESULT, PROV, "data/sanity/all.json", "f" * 64, san)
    assert obj["sanity_file"]["results"] == {"x": "pass", "y": "fail"}
    assert obj["sanity_file"]["sha256"] == "f" * 64 and obj["provenance"] is PROV
    assert obj["mode"] == "final"
    assert "## Provenance" in md and "data/sanity/all.json" in md and "| s | a.toml |" in md
    assert "> line one" in md and "> line two" in md and "plan version: 1.6" in md
