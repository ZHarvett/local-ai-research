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


# --- S3: restore-status (done -> accepted, guarded by a verdict event) ---

OPENED = {
    "ts": "2026-11-14T10:00:00Z",
    "seq": 5,
    "event": "review-opened",
    "task": "T-900",
    "detail": "cycle 1",
}
VERDICT = {
    "ts": "2026-11-14T10:05:00Z",
    "seq": 6,
    "event": "review-verdict",
    "task": "T-900",
    "detail": "accepted (cycle 1, 3 findings)",
}


def add_events(repo: Path, events: list[dict]) -> None:
    state = read_state(repo)
    state["events"] = events
    (repo / ".workflow" / "state.json").write_text(json.dumps(state), encoding="utf-8")


def restore_repo(tmp_path: Path, status: str = "done", events: list | None = None) -> Path:
    repo = make_repo(tmp_path, {"T-900": task(status)})
    add_events(repo, [OPENED, VERDICT] if events is None else events)
    return repo


def assert_restore_refused(repo: Path, *args: str) -> subprocess.CompletedProcess:
    before = (repo / ".workflow" / "state.json").read_bytes()
    proc = run_wf(repo, "restore-status", *args)
    assert proc.returncode != 0
    assert (repo / ".workflow" / "state.json").read_bytes() == before
    return proc


def test_restore_status_done_to_accepted(tmp_path):
    repo = restore_repo(tmp_path)
    proc = run_wf(repo, "restore-status", "T-900", "--to", "accepted", "--verdict-seq", "6")
    assert proc.returncode == 0, proc.stderr
    state = read_state(repo)
    assert state["tasks"]["T-900"]["status"] == "accepted"
    ev = state["events"][-1]
    assert ev["event"] == "status-restored"
    assert ev["task"] == "T-900"
    assert ev["detail"] == "done -> accepted (review-verdict seq 6)"


@pytest.mark.parametrize("target", ["done", "in-review", "ready", "changes-requested"])
def test_restore_status_refuses_other_targets(tmp_path, target):
    repo = restore_repo(tmp_path)
    proc = assert_restore_refused(repo, "T-900", "--to", target, "--verdict-seq", "6")
    assert "not a legal restore target" in proc.stderr


@pytest.mark.parametrize("status", ["in-progress", "in-review", "accepted", "ready"])
def test_restore_status_refuses_non_done_tasks(tmp_path, status):
    repo = restore_repo(tmp_path, status=status)
    proc = assert_restore_refused(repo, "T-900", "--to", "accepted", "--verdict-seq", "6")
    assert "not done" in proc.stderr


def test_restore_status_refuses_wrong_seq(tmp_path):
    repo = restore_repo(tmp_path)
    proc = assert_restore_refused(repo, "T-900", "--to", "accepted", "--verdict-seq", "99")
    assert "no accepted review-verdict event" in proc.stderr


def test_restore_status_refuses_non_accepted_verdict(tmp_path):
    repo = restore_repo(
        tmp_path, events=[OPENED, {**VERDICT, "detail": "changes-requested (cycle 1, 2 findings)"}]
    )
    assert_restore_refused(repo, "T-900", "--to", "accepted", "--verdict-seq", "6")


def test_restore_status_refuses_verdict_of_another_task(tmp_path):
    repo = restore_repo(tmp_path, events=[OPENED, {**VERDICT, "task": "T-901"}])
    assert_restore_refused(repo, "T-900", "--to", "accepted", "--verdict-seq", "6")


@pytest.mark.parametrize("seq", [7, 4])
def test_restore_status_refuses_later_review_opened(tmp_path, seq):
    # canonical order is (ts, seq): a later ts counts even with a smaller seq
    opened = {**OPENED, "ts": "2026-11-14T10:10:00Z", "seq": seq}
    repo = restore_repo(tmp_path, events=[opened, VERDICT])
    proc = assert_restore_refused(repo, "T-900", "--to", "accepted", "--verdict-seq", "6")
    assert "review-opened later" in proc.stderr


def test_restore_status_refuses_unknown_task(tmp_path):
    repo = restore_repo(tmp_path)
    assert_restore_refused(repo, "T-999", "--to", "accepted", "--verdict-seq", "6")


def test_restore_status_requires_flags(tmp_path):
    repo = restore_repo(tmp_path)
    assert_restore_refused(repo, "T-900")


def test_restore_status_refuses_foreign_lane_from_worktree(tmp_path):
    repo = make_repo(tmp_path, {})
    commit(repo)
    git(repo, "branch", "lane-2")
    wt = repo / ".workflow" / "worktrees" / "lane-2"
    git(repo, "worktree", "add", str(wt), "lane-2")
    write_mirror(repo, 3, {"T-900": task("done", lane=3)}, [VERDICT])
    before = (repo / ".workflow" / "state.json").read_bytes()
    proc = run_wf(wt, "restore-status", "T-900", "--to", "accepted", "--verdict-seq", "6")
    assert proc.returncode != 0
    assert "worktree" in proc.stderr
    assert (repo / ".workflow" / "state.json").read_bytes() == before


# --- S4 (3): the verdict parser takes one trailing parenthetical ---


@pytest.mark.parametrize("verdict_line", ["accepted", "accepted (cycle 1, 3 findings)"])
def test_review_verdict_parses_bare_and_parenthetical(tmp_path, verdict_line):
    repo = make_repo(tmp_path, {"T-900": task("in-review")}, review_cycles={"T-900": 1})
    report = tmp_path / "report.md"
    report.write_text(f"# Review T-900\n\n## Task verdict\n\n{verdict_line}\n", encoding="utf-8")
    proc = run_wf(repo, "review-verdict", "T-900", "accepted", "--report-file", str(report))
    assert proc.returncode == 0, proc.stderr
    assert read_state(repo)["tasks"]["T-900"]["status"] == "accepted"


@pytest.mark.parametrize("verdict_line", ["accepted extra words", "accepted (cycle 1) trailing"])
def test_review_verdict_still_rejects_trailing_junk(tmp_path, verdict_line):
    repo = make_repo(tmp_path, {"T-900": task("in-review")}, review_cycles={"T-900": 1})
    report = tmp_path / "report.md"
    report.write_text(f"# Review T-900\n\n## Task verdict\n\n{verdict_line}\n", encoding="utf-8")
    before = (repo / ".workflow" / "state.json").read_bytes()
    proc = run_wf(repo, "review-verdict", "T-900", "accepted", "--report-file", str(report))
    assert proc.returncode != 0
    assert (repo / ".workflow" / "state.json").read_bytes() == before


# --- S4 (4): stale lane worktrees refresh from main on start ---


def worktree_repo(tmp_path: Path) -> Path:
    repo = make_repo(
        tmp_path, {"T-900": task("claimed", lane=2, claimed_by_lane=2, resources="light")}
    )
    git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    commit(repo)
    git(repo, "branch", "lane-2")
    return repo


def test_start_refreshes_existing_stale_worktree(tmp_path):
    repo = worktree_repo(tmp_path)
    wt = repo / ".workflow" / "worktrees" / "lane-2"
    git(repo, "worktree", "add", str(wt), "lane-2")
    (repo / "main-update.txt").write_text("from main\n", encoding="utf-8")
    commit(repo, "main advances")
    proc = run_wf(repo, "start", "T-900")
    assert proc.returncode == 0, proc.stderr
    assert (wt / "main-update.txt").is_file()
    assert git(wt, "rev-list", "--count", "HEAD..main") == "0"


def test_start_refreshes_recreated_worktree_from_old_branch_tip(tmp_path):
    # T-018 recon §5: the worktree was recreated from the old lane branch tip
    repo = worktree_repo(tmp_path)
    (repo / "main-update.txt").write_text("from main\n", encoding="utf-8")
    commit(repo, "main advances")
    proc = run_wf(repo, "start", "T-900")
    assert proc.returncode == 0, proc.stderr
    wt = repo / ".workflow" / "worktrees" / "lane-2"
    assert (wt / "main-update.txt").is_file()


def test_start_leaves_worktree_as_is_on_merge_conflict(tmp_path):
    repo = worktree_repo(tmp_path)
    wt = repo / ".workflow" / "worktrees" / "lane-2"
    git(repo, "worktree", "add", str(wt), "lane-2")
    (repo / "shared.txt").write_text("main version\n", encoding="utf-8")
    commit(repo, "main change")
    (wt / "shared.txt").write_text("lane version\n", encoding="utf-8")
    commit(wt, "lane change")
    tip = git(wt, "rev-parse", "HEAD")
    proc = run_wf(repo, "start", "T-900")
    assert proc.returncode == 0, proc.stderr
    assert "merge main by hand" in proc.stdout
    assert git(wt, "rev-parse", "HEAD") == tip
    assert (wt / "shared.txt").read_text(encoding="utf-8") == "lane version\n"
    assert not (Path(git(wt, "rev-parse", "--absolute-git-dir")) / "MERGE_HEAD").exists()


# --- S4 (5): recompute_ready leaves lane-owned placeholders alone (E-005) ---


def test_event_does_not_promote_lane_owned_placeholders(tmp_path):
    repo = make_repo(
        tmp_path, {"T-900": task("todo"), "T-901": task("todo"), "T-902": task("todo")}
    )
    write_mirror(repo, 2, {"T-900": task("claimed", lane=2)})
    write_mirror(repo, 3, {"T-902": task("todo", lane=3)})
    proc = run_wf(repo, "event", "fixture", "note")
    assert proc.returncode == 0, proc.stderr
    tasks = read_state(repo)["tasks"]
    assert tasks["T-900"]["status"] == "todo"  # lane 2 owns it
    assert tasks["T-902"]["status"] == "todo"  # lane 3 owns it
    assert tasks["T-901"]["status"] == "ready"  # unowned: promoted as before


def test_lane_owner_still_promotes_its_own_todo_tasks(tmp_path):
    repo = make_repo(tmp_path, {"T-900": task("todo")})
    write_mirror(repo, 2, {"T-900": task("claimed", lane=2), "T-903": task("todo", lane=2)})
    proc = run_wf(repo, "block", "T-900", "--reason", "fixture")
    assert proc.returncode == 0, proc.stderr
    mirror = json.loads(
        (repo / ".git" / "workflow" / "lanes" / "2.json").read_text(encoding="utf-8")
    )
    assert mirror["tasks"]["T-900"]["status"] == "blocked-decision"
    assert mirror["tasks"]["T-903"]["status"] == "ready"
    assert read_state(repo)["tasks"]["T-900"]["status"] == "todo"  # placeholder untouched
