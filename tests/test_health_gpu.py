"""Tests that need the GPU and the real model. Excluded in CI with -m "not gpu"; run by hand:

uv run pytest -m gpu tests/test_health_gpu.py
"""

from __future__ import annotations

import json
import subprocess

import pytest

from conftest import REPO


@pytest.mark.gpu
def test_phase_a_against_the_real_server(tmp_path):
    p = subprocess.run(
        [
            str(REPO / "scripts/healthcheck.sh"),
            "--phases",
            "A",
            "--run-dir",
            str(tmp_path),
            "--no-aggregate",
        ],
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    assert p.returncode == 0, p.stderr[-2000:]
    doc = json.loads((tmp_path / "phase-A.json").read_text())
    failed = [c["id"] for c in doc["checks"] if c["status"] == "FAIL"]
    assert not failed, failed
