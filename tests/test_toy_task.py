"""The harness smoke task: fails on the pristine code, passes with the reference fix."""

from __future__ import annotations

import shutil
import subprocess
import sys

from conftest import FIXTURES

TOY = FIXTURES / "toy-task"
PATCH = FIXTURES / "toy-task-solution.patch"
TEST_ID = "test_moving_average_covers_every_window"


def pytest_in(path):
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(path),
        ],
        cwd=path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def copy_toy(tmp_path):
    dest = tmp_path / "toy"
    shutil.copytree(TOY, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def test_pristine_task_fails_on_exactly_the_named_test(tmp_path):
    r = pytest_in(copy_toy(tmp_path))
    assert r.returncode == 1, r.stdout
    assert f"FAILED test_movavg.py::{TEST_ID}" in r.stdout and "1 failed" in r.stdout


def test_reference_fix_makes_it_pass_and_touches_only_the_module(tmp_path):
    dest = copy_toy(tmp_path)
    p = subprocess.run(
        ["patch", "-p1", "--no-backup-if-mismatch", "-i", str(PATCH)],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "movavg.py" in p.stdout and "test_movavg.py" not in p.stdout
    r = pytest_in(dest)
    assert r.returncode == 0 and "1 passed" in r.stdout, r.stdout
    assert (dest / "test_movavg.py").read_bytes() == (TOY / "test_movavg.py").read_bytes()


def test_prompt_names_the_test_file_and_the_rules():
    text = (TOY / "PROMPT.txt").read_text()
    assert TEST_ID in text and "test_movavg.py" in text and "movavg.py" in text
    assert "Do not edit the test" in text and "pytest" in text


def test_toy_task_is_small_and_licensed_as_ours():
    lines = sum(len(f.read_text().splitlines()) for f in TOY.glob("*.py"))
    assert lines <= 30
    for f in TOY.glob("*.py"):
        assert "MIT" in f.read_text().splitlines()[0]
