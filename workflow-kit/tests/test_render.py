"""Render determinism and PROGRESS.md content."""


def test_render_is_deterministic(repo):
    first = (repo.path / "PROGRESS.md").read_text()
    repo.wf("render")
    second = (repo.path / "PROGRESS.md").read_text()
    repo.wf("render")
    third = (repo.path / "PROGRESS.md").read_text()
    assert first == second == third


def test_progress_header_and_sections(repo):
    text = (repo.path / "PROGRESS.md").read_text()
    assert "GENERATED, DO NOT EDIT BY HAND" in text
    for section in [
        "## Tasks",
        "## READY (grouped by lane)",
        "## Escalation queue",
        "## Review queue",
        "## Lanes",
        "## Last events",
    ]:
        assert section in text, section
    for tid in ["T-001", "T-002", "T-003", "T-004", "T-005"]:
        assert tid in text


def test_judgement_flag_appears_after_manual_accept(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    # T-001 has no manual item; run one that does (T-005 after its deps)
    for tid, status in [("T-001", "done"), ("T-002", "done"), ("T-003", "done")]:
        repo.set_raw_status(tid, status)
    repo.wf("event", "recheck")
    repo.set_raw_status("T-004", "accepted")
    repo.wf("event", "recheck")
    repo.wf("lane-release", "1")  # the raw-status surgery bypassed mutate's cleanup
    repo.wf("claim", "T-005")
    repo.wf("start", "T-005")
    (repo.path / "data").mkdir(exist_ok=True)
    (repo.path / "data" / "metrics.json").write_text('{"message_count": 2, "message_len": 14}')
    (repo.path / "REPORT.md").write_text("metrics: 2 / 14\n")
    repo.wf("accept", "T-005")
    repo.wf("done", "T-005")
    text = (repo.path / "PROGRESS.md").read_text()
    assert "(judgement)" in text


def test_ready_list_grouped_by_lane(repo):
    # T-001 done -> T-002 (lane 2) and T-003 (lane 3) ready
    repo.set_raw_status("T-001", "done")
    repo.wf("event", "recheck")
    repo.wf("render")
    text = (repo.path / "PROGRESS.md").read_text()
    assert "lane 2: **T-002**" in text
    assert "lane 3: **T-003**" in text


def test_last_five_events_shown(repo):
    for i in range(8):
        repo.wf("event", f"event {i}")
    text = (repo.path / "PROGRESS.md").read_text()
    assert "event 3" in text and "event 7" in text
    assert "event 0" not in text.split("## Last events")[1]


def test_escalation_queue_in_progress(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    brief = repo.path / "brief.md"
    brief.write_text(
        "# Escalation E-NNN\n\n## What happened\nx\n\n## Why it cannot proceed\nx\n"
        "## Options\nA/B\n\n## Recommendation\nA\n\n"
        "## What is blocked and what can proceed in parallel\nx\n"
        "## The exact question\nq\n"
    )
    repo.wf("escalate", "--task", "T-001", "--type", "decision", "--brief-file", "brief.md")
    text = (repo.path / "PROGRESS.md").read_text()
    assert "E-001" in text and "open" in text
