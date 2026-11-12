"""add-task, supersede, escalate, decision, review-cycle and disposition flows."""

import json


def report_text(verdict, rows):
    lines = [
        "# Review",
        "",
        "## Task verdict",
        "",
        verdict,
        "",
        "| id | severity | action | evidence | required action |",
        "|---|---|---|---|---|",
    ]
    lines.extend(rows)
    return "\n".join(lines) + "\n"


def write_report(repo, verdict, rows, name="REVIEW_REPORT.md"):
    path = repo.path / name
    path.write_text(report_text(verdict, rows))
    return name


def finish_t001(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    (repo.path / "data").mkdir(exist_ok=True)
    (repo.path / "data" / "name.txt").write_text("world")
    repo.wf("accept", "T-001")
    repo.wf("done", "T-001")


# ------------------------------------------------------------- escalate/decision


def test_escalate_creates_brief_and_blocks(repo):
    finish_t001(repo)
    repo.wf("claim", "T-002")
    repo.wf("start", "T-002")
    brief = repo.path / "b.md"
    brief.write_text(
        "# Escalation E-NNN — subject\n\n## What happened\nfacts\n\n"
        "## Why it cannot proceed\nreason\n\n## Options\nA / B\n\n"
        "## Recommendation\nA (high)\n\n"
        "## What is blocked and what can proceed in parallel\nT-005\n\n"
        "## The exact question\nQ?\n"
    )
    out = repo.wf("escalate", "--task", "T-005", "--type", "decision", "--brief-file", "b.md")
    assert "E-001" in out.stdout
    brief_path = repo.path / "escalations" / "E-001.md"
    assert brief_path.is_file()
    assert "E-NNN" not in brief_path.read_text()  # the id was assigned
    state = repo.read_state()
    assert state["tasks"]["T-005"]["status"] == "blocked-decision"
    assert state["escalations"]["E-001"]["status"] == "open"


def test_escalate_rejects_incomplete_brief(repo):
    brief = repo.path / "b.md"
    brief.write_text("# Escalation E-NNN\n\n## What happened\nx\n")
    out = repo.wf_fail("escalate", "--type", "problem", "--brief-file", "b.md")
    assert "missing sections" in (out.stderr + out.stdout)


def test_decision_records_reply_and_unblocks(repo):
    finish_t001(repo)
    repo.wf("claim", "T-002")
    repo.wf("start", "T-002")
    brief = repo.path / "b.md"
    brief.write_text(
        "# Escalation E-NNN — subject\n\n## What happened\nfacts\n\n"
        "## Why it cannot proceed\nreason\n\n## Options\nA / B\n\n"
        "## Recommendation\nA (high)\n\n"
        "## What is blocked and what can proceed in parallel\nT-005\n\n"
        "## The exact question\nQ?\n"
    )
    repo.wf("escalate", "--task", "T-002", "--type", "decision", "--brief-file", "b.md")
    reply = repo.path / "r.md"
    reply.write_text(
        "DECISION E-001\nChosen option: A\nReason: cheap\nScope: this plan.\n"
        "Rule: standing rule text.\n"
    )
    out = repo.wf("decision", "E-001", "--reply-file", "r.md")
    assert "unblocked" in out.stdout
    decisions = (repo.path / "docs" / "decisions.md").read_text()
    assert "DECISION E-001" in decisions
    assert "standing rule text" in decisions
    # T-002 is a lane-2 task: the unblocked status lives in the lane mirror
    mirror = repo.run("git", "rev-parse", "--git-common-dir").stdout.strip()
    lane = json.loads((repo.path / mirror / "workflow" / "lanes" / "2.json").read_text())
    assert lane["tasks"]["T-002"]["status"] == "in-progress"
    assert repo.read_state()["escalations"]["E-001"]["status"] == "decided"


def test_decision_requires_matching_id(repo):
    reply = repo.path / "r.md"
    reply.write_text("DECISION E-999\nwhatever\n")
    out = repo.wf_fail("decision", "E-001", "--reply-file", "r.md")
    assert "unknown escalation" in (out.stderr + out.stdout)


# ------------------------------------------------------------- add-task / supersede


ADDED_CARD = """## Task cards

### T-050 — Extra check
id: T-050
title: Extra check
phase: P3
depends_on: T-001
lane: 1
resources: light
files_read: data/name.txt
files_write: out/extra.txt
gates: none
review: none
preconditions:
  - cmd: test -f data/name.txt
    expect: exit_code 0
steps:
  - S1: copy the name file to out/extra.txt (redo-safe)
acceptance:
  - cmd: cat out/extra.txt
    expect: stdout_regex ^world$
evidence: out/extra.txt
estimate: 5m
decision_rights:
  - may: choose the copy method
  - must_escalate: writing anywhere else
"""


def test_add_task_from_plan_added(repo):
    finish_t001(repo)
    (repo.path / "PLAN-ADDED.md").write_text(ADDED_CARD)
    out = repo.wf("add-task", "T-050", "--file", "PLAN-ADDED.md", "--reason", "test")
    assert "added T-050" in out.stdout
    state = repo.read_state()
    assert state["tasks"]["T-050"]["source"] == "added"
    assert state["tasks"]["T-050"]["status"] == "ready"  # dep T-001 done
    # wf-card prints it from PLAN-ADDED.md
    out = repo.wf("card", "T-050")
    assert "T-050" in out.stdout and "copy the name file" in out.stdout


def test_add_task_rejects_existing_id(repo):
    (repo.path / "PLAN-ADDED.md").write_text(ADDED_CARD)
    repo.wf("add-task", "T-050", "--file", "PLAN-ADDED.md")
    out = repo.wf_fail("add-task", "T-050", "--file", "PLAN-ADDED.md")
    assert "already exists" in (out.stderr + out.stdout)


def test_supersede_marks_and_never_deletes(repo):
    finish_t001(repo)
    repo.wf("supersede", "T-005", "--by", "T-050", "--reason", "E-001")
    state = repo.read_state()
    assert state["tasks"]["T-005"]["status"] == "superseded"
    assert state["tasks"]["T-005"]["superseded_by"] == "T-050"


def test_supersede_refuses_accepted(repo):
    repo.set_raw_status("T-003", "accepted")
    out = repo.wf_fail("supersede", "T-003")
    assert "accepted" in (out.stderr + out.stdout)


# ------------------------------------------------------------- review cycles


def rows(blocker=False):
    row = (
        "| F-1 | BLOCKER | RE-MEASURE | data/x | redo S1 (5 min) |\n"
        if blocker
        else "| F-1 | NOTE | FIX-DOC | x:1 | fix doc |\n"
    )
    return [row]


def test_review_cycle_limited_by_config(repo):
    repo.set_raw_status("T-004", "done")
    for _cycle in (1, 2):
        repo.wf("review-open", "T-004")
        write_report(repo, "changes-requested", rows())
        repo.wf("review-verdict", "T-004", "changes-requested", "--report-file", "REVIEW_REPORT.md")
    out = repo.wf_fail("review-open", "T-004")
    assert "escalate" in (out.stderr + out.stdout)


def test_review_verdict_must_match_report(repo):
    repo.set_raw_status("T-004", "done")
    repo.wf("review-open", "T-004")
    write_report(repo, "accepted", rows())
    out = repo.wf_fail(
        "review-verdict", "T-004", "changes-requested", "--report-file", "REVIEW_REPORT.md"
    )
    assert "Task verdict" in (out.stderr + out.stdout)


def test_review_verdict_archives_report(repo):
    repo.set_raw_status("T-004", "done")
    repo.wf("review-open", "T-004")
    write_report(repo, "changes-requested", rows())
    repo.wf("review-verdict", "T-004", "changes-requested", "--report-file", "REVIEW_REPORT.md")
    archived = repo.path / "reviews" / "T-004" / "r1-REVIEW_REPORT.md"
    assert archived.is_file()
    assert "F-1" in archived.read_text()


def test_blocker_cannot_be_rejected(repo):
    repo.set_raw_status("T-004", "done")
    repo.wf("review-open", "T-004")
    write_report(repo, "changes-requested", rows(blocker=True))
    repo.wf("review-verdict", "T-004", "changes-requested", "--report-file", "REVIEW_REPORT.md")
    out = repo.wf_fail("review-disposition", "T-004", "F-1", "reject", "--reason", "no")
    assert "BLOCKER" in (out.stderr + out.stdout)


def test_remeasure_finding_must_escalate(repo):
    repo.set_raw_status("T-004", "done")
    repo.wf("review-open", "T-004")
    write_report(repo, "changes-requested", rows(blocker=True))
    repo.wf("review-verdict", "T-004", "changes-requested", "--report-file", "REVIEW_REPORT.md")
    out = repo.wf_fail("review-disposition", "T-004", "F-1", "accept", "--reason", "redo it")
    assert "RE-MEASURE" in (out.stderr + out.stdout)
    out = repo.wf("review-disposition", "T-004", "F-1", "escalate", "--reason", "needs Zack")
    assert "recorded" in out.stdout
    state = repo.read_state()
    assert state["review_dispositions"]["T-004"][0]["action_taken"] == "escalate"


def test_disposition_requires_real_finding(repo):
    repo.set_raw_status("T-004", "done")
    repo.wf("review-open", "T-004")
    write_report(repo, "changes-requested", rows())
    repo.wf("review-verdict", "T-004", "changes-requested", "--report-file", "REVIEW_REPORT.md")
    out = repo.wf_fail("review-disposition", "T-004", "F-9", "accept", "--reason", "x")
    assert "not in the report" in (out.stderr + out.stdout)


# ------------------------------------------------------------- resume / steps


def test_step_done_and_resume(repo):
    repo.finish_t001()
    repo.wf("claim", "T-002")
    repo.wf("start", "T-002")
    repo.wf("step-done", "T-002", "S1")
    # lane 2: the record lives in the lane file's mirror
    mirror = repo.run("git", "rev-parse", "--git-common-dir").stdout.strip()
    lane = json.loads((repo.path / mirror / "workflow" / "lanes" / "2.json").read_text())
    assert lane["tasks"]["T-002"]["steps_done"] == ["S1"]
    # orphan the claim, then resume from S2
    claims_path = repo.path / mirror / "workflow" / "claims.json"
    claims = json.loads(claims_path.read_text())
    claims["T-002"]["pid"] = 999999  # dead
    claims_path.write_text(json.dumps(claims))
    out = repo.wf("resume", "T-002")
    assert "resumed T-002 at S2" in out.stdout


def test_resume_non_redo_safe_needs_confirm(repo):
    # T-004 S2 is 'not redo-safe'
    for tid, status in [("T-001", "done"), ("T-002", "done"), ("T-003", "done")]:
        repo.set_raw_status(tid, status)
    repo.wf("event", "recheck")
    repo.wf("claim", "T-004")
    repo.wf("start", "T-004")
    (repo.path / "out").mkdir(exist_ok=True)
    (repo.path / "out" / "message.txt").write_text("Hello, world!\n")
    repo.wf("step-done", "T-004", "S1")
    # orphan it and resume: the first incomplete step S2 is not redo-safe
    common = repo.run("git", "rev-parse", "--git-common-dir").stdout.strip()
    claims_path = repo.path / common / "workflow" / "claims.json"
    claims = json.loads(claims_path.read_text())
    claims["T-004"]["pid"] = 999999
    claims_path.write_text(json.dumps(claims))
    out = repo.wf_fail("resume", "T-004")
    assert "NOT redo-safe" in (out.stderr + out.stdout)
    out = repo.wf("resume", "T-004", "--confirm")
    assert "resumed T-004 at S2" in out.stdout


def test_step_done_rejects_unknown_step(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    out = repo.wf_fail("step-done", "T-001", "S9")
    assert "no step S9" in (out.stderr + out.stdout)


def test_calibration_record(repo):
    repo.wf(
        "calibration-record",
        "--caught",
        "F-1",
        "F-3",
        "--missed",
        "F-2",
        "--model-name",
        "test-model",
    )
    data = json.loads((repo.path / ".workflow" / "calibration.json").read_text())
    assert data[0]["caught"] == ["F-1", "F-3"]
    assert data[0]["missed"] == ["F-2"]
    assert data[0]["model_name"] == "test-model"
