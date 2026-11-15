"""Lane-merge and state-rider tests (T-022): the fold keeps advanced main statuses,
restore-status repairs a bug-regressed done -> accepted, the verdict parser takes a
parenthetical, stale lane worktrees refresh from main, and recompute_ready leaves
lane-owned placeholders alone (E-005).

Every test drives the real scripts/_wf.py against a throwaway fixture repo in
tmp_path (WF_REPO override) — never this repo's live .workflow/ state.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from test_wf_unblock import make_repo, read_state, run_wf, task


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def commit(repo: Path, msg: str = "fixture") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)


def write_mirror(repo: Path, lane: int, tasks: dict, events: list | None = None) -> None:
    mirror = repo / ".git" / "workflow" / "lanes" / f"{lane}.json"
    mirror.parent.mkdir(parents=True, exist_ok=True)
    mirror.write_text(
        json.dumps({"version": 1, "lane": lane, "tasks": tasks, "events": events or []}),
        encoding="utf-8",
    )


def merge_repo(tmp_path: Path, main_tasks: dict, mirror_tasks: dict) -> Path:
    """Fixture repo with a lane-2 branch at main HEAD and a lane-2 mirror."""
    repo = make_repo(tmp_path, main_tasks)
    commit(repo)
    git(repo, "branch", "lane-2")
    write_mirror(repo, 2, mirror_tasks)
    return repo


# S2: the T-005 / T-018 regression (15 November): reviews ran from main and set
# accepted, the lane mirrors still said done, and the fold regressed both to done.
def test_merge_keeps_accepted_main_status_over_stale_done_mirror(tmp_path):
    repo = merge_repo(
        tmp_path,
        {"T-005": task("accepted"), "T-018": task("accepted")},
        {"T-005": task("done"), "T-018": task("done")},
    )
    proc = run_wf(repo, "merge-lanes", "2")
    assert proc.returncode == 0, proc.stderr
    tasks = read_state(repo)["tasks"]
    assert tasks["T-005"]["status"] == "accepted"
    assert tasks["T-018"]["status"] == "accepted"


@pytest.mark.parametrize(
    "status", ["accepted", "in-review", "changes-requested", "superseded", "cancelled"]
)
def test_merge_keeps_every_main_wins_status_and_folds_other_fields(tmp_path, status):
    repo = merge_repo(tmp_path, {"T-900": task(status)}, {"T-900": task("done", note="lane field")})
    proc = run_wf(repo, "merge-lanes", "2")
    assert proc.returncode == 0, proc.stderr
    t = read_state(repo)["tasks"]["T-900"]
    assert t["status"] == status
    assert t["note"] == "lane field"


def test_merge_still_takes_lane_status_over_todo_placeholder(tmp_path):
    # the normal lane-completion flow is unchanged: the mirror wins over todo
    repo = merge_repo(tmp_path, {"T-900": task("todo")}, {"T-900": task("done")})
    proc = run_wf(repo, "merge-lanes", "2")
    assert proc.returncode == 0, proc.stderr
    assert read_state(repo)["tasks"]["T-900"]["status"] == "done"
