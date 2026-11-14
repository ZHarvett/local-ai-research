"""Kit repair tests (T-018 S3): leaving blocked-decision after a review verdict.

Every test drives the real scripts/_wf.py against a throwaway fixture repo in
tmp_path (WF_REPO override) — never this repo's live .workflow/ state. The six
card scenarios reproduce the T-021 failure exactly: a review verdict of
blocked-decision recorded no blocked_from, and every kit path out of
blocked-decision then failed (docs/recon/T-018-kit-repair.md).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO

WF = REPO / "scripts" / "_wf.py"

BRIEF = """# Escalation E-NNN

## What happened
Fixture problem.

## Why it cannot proceed
Fixture reason.

## Options
A. Do the fixture thing.

## Recommendation
A.

## What is blocked and what can proceed
The fixture task is blocked; nothing else.

## The exact question
Which fixture option?
"""

REPORT = """# Review T-900 (cycle 1)

## Acceptance verdicts
Fixture.

## Task verdict

blocked-decision
"""

REPLY = "DECISION E-001\n\nOption A ratified.\n"


def task(status: str, **extra) -> dict:
    return {"title": "Fixture task", "status": status, "lane": 1, "review": "post", **extra}


def make_repo(tmp_path: Path, tasks: dict, *, escalations=None, review_cycles=None) -> Path:
    """A throwaway git repo with a fixture state (no checksum: kit writes add it)."""
    repo = tmp_path / "repo"
    (repo / ".workflow").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    state = {
        "tasks": tasks,
        "escalations": escalations or {},
        "review_cycles": review_cycles or {},
        "review_dispositions": {},
    }
    (repo / ".workflow" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return repo


def run_wf(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "WF_REPO": str(repo), "WF_SESSION_PID": "0"}
    return subprocess.run(
        [sys.executable, str(WF), *args], cwd=repo, env=env, capture_output=True, text=True
    )


def read_state(repo: Path) -> dict:
    return json.loads((repo / ".workflow" / "state.json").read_text(encoding="utf-8"))


def open_escalation(tid: str = "T-900") -> dict:
    return {
        "E-001": {
            "task": tid,
            "type": "decision",
            "status": "open",
            "created_utc": "2026-11-14T00:00:00Z",
        }
    }


# Scenario 1: unblock --to changes-requested works with no blocked_from (T-021's shape).
def test_unblock_to_changes_requested_without_blocked_from(tmp_path):
    repo = make_repo(tmp_path, {"T-900": task("blocked-decision")})
    # the old path still fails exactly as before: the todo fallback is illegal
    old = run_wf(repo, "unblock", "T-900")
    assert old.returncode != 0
    assert "invalid transition" in old.stderr
    assert read_state(repo)["tasks"]["T-900"]["status"] == "blocked-decision"
    # the new explicit target works
    proc = run_wf(repo, "unblock", "T-900", "--to", "changes-requested")
    assert proc.returncode == 0, proc.stderr
    t = read_state(repo)["tasks"]["T-900"]
    assert t["status"] == "changes-requested"
    assert t["blocked_from"] is None
    # the event names the old and the new status
    events = read_state(repo)["events"]
    assert events[-1]["event"] == "unblocked"
    assert events[-1]["detail"] == "blocked-decision -> changes-requested"


# Scenario 2: --to ready, todo and accepted are refused, with no state change.
@pytest.mark.parametrize("target", ["ready", "todo", "accepted"])
def test_unblock_to_refuses_illegal_targets(tmp_path, target):
    repo = make_repo(tmp_path, {"T-900": task("blocked-decision")})
    before = (repo / ".workflow" / "state.json").read_bytes()
    proc = run_wf(repo, "unblock", "T-900", "--to", target)
    assert proc.returncode != 0
    assert "not a legal unblock target" in proc.stderr
    assert (repo / ".workflow" / "state.json").read_bytes() == before


# Scenario 3: unblock without --to still returns to blocked_from, as before.
def test_unblock_without_to_restores_blocked_from(tmp_path):
    repo = make_repo(
        tmp_path,
        {
            "T-900": task(
                "blocked-decision", blocked_from="in-progress", blocked_reason="escalation E-001"
            )
        },
    )
    proc = run_wf(repo, "unblock", "T-900")
    assert proc.returncode == 0, proc.stderr
    t = read_state(repo)["tasks"]["T-900"]
    assert t["status"] == "in-progress"
    assert t["blocked_from"] is None
    assert t["blocked_reason"] is None
    events = read_state(repo)["events"]
    assert events[-1]["event"] == "unblocked"
    assert events[-1]["detail"] == "restored to in-progress"


# Scenario 4: a review verdict of blocked-decision records blocked_from.
def test_review_verdict_blocked_decision_records_blocked_from(tmp_path):
    repo = make_repo(tmp_path, {"T-900": task("in-review")}, review_cycles={"T-900": 1})
    report = tmp_path / "report.md"
    report.write_text(REPORT, encoding="utf-8")
    proc = run_wf(repo, "review-verdict", "T-900", "blocked-decision", "--report-file", str(report))
    assert proc.returncode == 0, proc.stderr
    t = read_state(repo)["tasks"]["T-900"]
    assert t["status"] == "blocked-decision"
    assert t["blocked_from"] == "changes-requested"
    # the normal recovery path now works without --to: back to changes-requested
    proc = run_wf(repo, "unblock", "T-900")
    assert proc.returncode == 0, proc.stderr
    assert read_state(repo)["tasks"]["T-900"]["status"] == "changes-requested"


# Scenario 5: escalate on an already blocked task keeps blocked_from.
def test_escalate_keeps_blocked_from_when_already_blocked(tmp_path):
    repo = make_repo(tmp_path, {"T-900": task("in-progress")})
    brief = tmp_path / "brief.md"
    brief.write_text(BRIEF, encoding="utf-8")
    # first escalation from a live status: blocked_from is that status (unchanged behaviour)
    proc = run_wf(
        repo, "escalate", "--task", "T-900", "--type", "decision", "--brief-file", str(brief)
    )
    assert proc.returncode == 0, proc.stderr
    t = read_state(repo)["tasks"]["T-900"]
    assert t["status"] == "blocked-decision"
    assert t["blocked_from"] == "in-progress"
    # second escalation while already blocked: the original return status survives
    proc = run_wf(
        repo, "escalate", "--task", "T-900", "--type", "decision", "--brief-file", str(brief)
    )
    assert proc.returncode == 0, proc.stderr
    t = read_state(repo)["tasks"]["T-900"]
    assert t["status"] == "blocked-decision"
    assert t["blocked_from"] == "in-progress"
    assert t["blocked_reason"] == "escalation E-002"
    # and unblock still restores it
    proc = run_wf(repo, "unblock", "T-900")
    assert proc.returncode == 0, proc.stderr
    assert read_state(repo)["tasks"]["T-900"]["status"] == "in-progress"


def test_escalate_keeps_missing_blocked_from_missing(tmp_path):
    # T-021's exact shape: blocked by a verdict with no blocked_from; escalating
    # must not invent "blocked-decision" as the return status (the --to flag is
    # the escape hatch for this case).
    repo = make_repo(tmp_path, {"T-900": task("blocked-decision")})
    brief = tmp_path / "brief.md"
    brief.write_text(BRIEF, encoding="utf-8")
    proc = run_wf(
        repo, "escalate", "--task", "T-900", "--type", "decision", "--brief-file", str(brief)
    )
    assert proc.returncode == 0, proc.stderr
    t = read_state(repo)["tasks"]["T-900"]
    assert t["status"] == "blocked-decision"
    assert t.get("blocked_from") is None


# Scenario 6: decision on a task that cannot be unblocked writes nothing.
@pytest.mark.parametrize("decisions_pre_exists", [False, True])
def test_decision_refuses_when_task_cannot_be_unblocked(tmp_path, decisions_pre_exists):
    repo = make_repo(tmp_path, {"T-900": task("blocked-decision")}, escalations=open_escalation())
    decisions = repo / "docs" / "decisions.md"
    sentinel = "# Decisions\n\nEarlier decision.\n"
    if decisions_pre_exists:
        decisions.parent.mkdir(parents=True)
        decisions.write_text(sentinel, encoding="utf-8")
    reply = tmp_path / "reply.md"
    reply.write_text(REPLY, encoding="utf-8")
    proc = run_wf(repo, "decision", "E-001", "--reply-file", str(reply))
    assert proc.returncode != 0
    assert "no legal unblock target" in proc.stderr
    assert "not recorded" in proc.stderr
    # docs/decisions.md untouched (absent stays absent, content stays byte-identical)
    if decisions_pre_exists:
        assert decisions.read_text(encoding="utf-8") == sentinel
    else:
        assert not decisions.exists()
    # the escalation is still open, the task still blocked, no events appended
    state = read_state(repo)
    assert state["escalations"]["E-001"]["status"] == "open"
    assert "decided_utc" not in state["escalations"]["E-001"]
    assert state["tasks"]["T-900"]["status"] == "blocked-decision"
    assert state.get("events", []) == []
    # after the documented remedy, the same decision records cleanly
    proc = run_wf(repo, "unblock", "T-900", "--to", "changes-requested")
    assert proc.returncode == 0, proc.stderr
    proc = run_wf(repo, "block", "T-900", "--reason", "re-block for the decision")
    assert proc.returncode == 0, proc.stderr
    proc = run_wf(repo, "decision", "E-001", "--reply-file", str(reply))
    assert proc.returncode == 0, proc.stderr
    assert read_state(repo)["tasks"]["T-900"]["status"] == "changes-requested"


def test_decision_records_and_unblocks_when_legal(tmp_path):
    # regression guard: the normal decision flow is unchanged
    repo = make_repo(
        tmp_path,
        {"T-900": task("blocked-decision", blocked_from="changes-requested")},
        escalations=open_escalation(),
    )
    reply = tmp_path / "reply.md"
    reply.write_text(REPLY, encoding="utf-8")
    proc = run_wf(repo, "decision", "E-001", "--reply-file", str(reply))
    assert proc.returncode == 0, proc.stderr
    assert "## DECISION E-001" in (repo / "docs" / "decisions.md").read_text(encoding="utf-8")
    state = read_state(repo)
    assert state["escalations"]["E-001"]["status"] == "decided"
    assert state["tasks"]["T-900"]["status"] == "changes-requested"


def test_decision_refuses_when_task_not_blocked(tmp_path):
    # a task that is not blocked-decision cannot be unblocked: refuse before writing
    repo = make_repo(tmp_path, {"T-900": task("in-progress")}, escalations=open_escalation())
    decisions = repo / "docs" / "decisions.md"
    decisions.parent.mkdir(parents=True)
    decisions.write_text("# Decisions\n", encoding="utf-8")
    reply = tmp_path / "reply.md"
    reply.write_text(REPLY, encoding="utf-8")
    proc = run_wf(repo, "decision", "E-001", "--reply-file", str(reply))
    assert proc.returncode != 0
    assert "not blocked-decision" in proc.stderr
    assert decisions.read_text(encoding="utf-8") == "# Decisions\n"
    assert read_state(repo)["escalations"]["E-001"]["status"] == "open"
