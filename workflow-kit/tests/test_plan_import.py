"""Plan-import validation: every mechanical error the importer must reject."""

import pytest

from conftest import EXAMPLE_PLAN, KIT, git_repo


def plan_with(tmp_path, old, new):
    text = EXAMPLE_PLAN.read_text()
    assert old in text
    return text.replace(old, new)


def check_fails(tmp_path, mutation):
    r = git_repo(tmp_path / "repo")
    (r.path / "PLAN.md").write_text(plan_with(tmp_path, *mutation))
    out = r.wf_fail("plan-check", "PLAN.md")
    return out.stderr + out.stdout


def test_missing_field_is_rejected(tmp_path):
    err = check_fails(tmp_path, ("estimate: 5m", "estimate:"))
    assert "missing fields" in err and "estimate" in err


def test_bad_resources_is_rejected(tmp_path):
    err = check_fails(tmp_path, ("resources: light", "resources: medium"))
    assert "resources" in err


def test_bad_review_policy_is_rejected(tmp_path):
    err = check_fails(tmp_path, ("review: post", "review: sometimes"))
    assert "review" in err


def test_step_without_redo_marker_is_rejected(tmp_path):
    r = git_repo(tmp_path / "repo2")
    text = EXAMPLE_PLAN.read_text().replace(
        '  - S1: create data/ if missing and write the single line "world" to '
        "data/name.txt (redo-safe)",
        '  - S1: create data/ if missing and write the single line "world" to data/name.txt',
    )
    (r.path / "PLAN.md").write_text(text)
    out = r.wf_fail("plan-check", "PLAN.md")
    assert "redo-safe" in (out.stderr + out.stdout)


def test_unknown_dependency_is_rejected(tmp_path):
    err = check_fails(tmp_path, ("depends_on: T-001", "depends_on: T-999"))
    assert "unknown task" in err


def test_dependency_cycle_is_rejected(tmp_path):
    # T-002 depends on T-001; make T-001 depend on T-002 -> cycle
    err = check_fails(
        tmp_path,
        (
            "depends_on: none\nlane: 1\nresources: light\nfiles_read: none",
            "depends_on: T-002\nlane: 1\nresources: light\nfiles_read: none",
        ),
    )
    assert "cycle" in err


def test_duplicate_card_id_is_rejected(tmp_path):
    r = git_repo(tmp_path / "repo")
    text = EXAMPLE_PLAN.read_text().replace(
        "### T-002 — Write the greeting builder", "### T-001 — Write the greeting builder"
    )
    (r.path / "PLAN.md").write_text(text)
    out = r.wf_fail("plan-check", "PLAN.md")
    assert "duplicate" in (out.stderr + out.stdout)


def test_lane_requires_reason(tmp_path):
    err = check_fails(
        tmp_path,
        (
            "lane_reason: independent of T-002 (different files, light, "
            "both under 10 minutes alone but more than 30 minutes together)",
            "lane_reason:",
        ),
    )
    assert "lane_reason" in err


def test_cmd_item_without_expect_is_rejected(tmp_path):
    r = git_repo(tmp_path / "repo")
    text = EXAMPLE_PLAN.read_text().replace(
        "  - cmd: cat data/name.txt\n    expect: stdout_regex ^world$",
        "  - cmd: cat data/name.txt",
    )
    (r.path / "PLAN.md").write_text(text)
    out = r.wf_fail("plan-check", "PLAN.md")
    assert "expect" in (out.stderr + out.stdout)


def test_missing_shared_rules_is_rejected(tmp_path):
    r = git_repo(tmp_path / "repo")
    text = EXAMPLE_PLAN.read_text().replace("## Shared rules", "## Old rules")
    (r.path / "PLAN.md").write_text(text)
    out = r.wf_fail("plan-check", "PLAN.md")
    assert "Shared rules" in (out.stderr + out.stdout)


def test_missing_assumption_register_is_rejected(tmp_path):
    r = git_repo(tmp_path / "repo")
    text = EXAMPLE_PLAN.read_text().replace("## Assumption register", "## Old register")
    (r.path / "PLAN.md").write_text(text)
    out = r.wf_fail("plan-check", "PLAN.md")
    assert "assumption" in (out.stderr + out.stdout).lower()


def test_assumption_referencing_unknown_task_is_rejected(tmp_path):
    err = check_fails(
        tmp_path,
        ("checked by T-001\n", "checked by T-099\n"),
    )
    assert "unknown task" in err


def test_review_with_all_manual_acceptance_warns(tmp_path):
    r = git_repo(tmp_path / "repo")
    text = EXAMPLE_PLAN.read_text()
    for old in [
        "  - expect: json_eq data/metrics.json message_count 2\n",
        "  - cmd: test -s REPORT.md\n    expect: exit_code 0\n",
        "  - expect: file_exists REPORT.md\n",
    ]:
        assert old in text
        text = text.replace(old, "")
    text = text.replace(
        '  - expect: manual "REPORT.md states the metric values plainly, no adjectives"',
        '  - expect: manual "REPORT.md looks sensible"\n  - expect: manual "metrics look sensible"',
    )
    (r.path / "PLAN.md").write_text(text)
    out = r.wf("plan-check", "PLAN.md")
    assert "WARNING" in out.stderr
    assert "T-005" in out.stderr


def test_import_refuses_over_in_progress(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    out = repo.wf_fail("plan-import", "PLAN.md")
    assert "in-progress" in (out.stderr + out.stdout)


def test_import_refuses_without_amend_when_state_exists(repo):
    out = repo.wf_fail("plan-import", "PLAN.md")
    assert "--amend" in (out.stderr + out.stdout)


def test_amend_keeps_unchanged_cards_and_flags_changed(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    (repo.path / "data").mkdir(exist_ok=True)
    (repo.path / "data" / "name.txt").write_text("world")
    repo.wf("accept", "T-001")
    repo.wf("done", "T-001")
    text = (repo.path / "PLAN.md").read_text()
    # change T-003's card (untouched status: ready) and leave the rest alone
    text = text.replace(
        '  - S1: create config/ and write style.json with prefix "Hello, " and '
        'suffix "!" (redo-safe)',
        '  - S1: create config/ and write style.json with prefix "Hi, " and suffix "!" (redo-safe)',
    )
    text = text.replace("*Version 1.0 · 12 November 2026*", "*Version 1.1 · 12 November 2026*")
    (repo.path / "PLAN.md").write_text(text)
    repo.wf("plan-import", "PLAN.md", "--amend")
    state = repo.read_state()
    assert state["tasks"]["T-001"]["status"] == "done"  # unchanged card keeps status
    assert state["tasks"]["T-003"]["status"] in ("todo", "ready")  # reset + re-derived
    assert state["tasks"]["T-003"].get("plan_changed") is True
    # re-acknowledgement is visible in PROGRESS.md
    progress = (repo.path / "PROGRESS.md").read_text()
    assert "re-acknowledge" in progress


def test_amend_refuses_when_changed_card_is_active(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    text = (
        (repo.path / "PLAN.md")
        .read_text()
        .replace('write the single line "world"', 'write the single line "earth"')
    )
    (repo.path / "PLAN.md").write_text(text)
    out = repo.wf_fail("plan-import", "PLAN.md", "--amend")
    assert "amend refused" in (out.stderr + out.stdout)


def test_amend_unchanged_plan_is_a_no_op(repo):
    out = repo.wf_fail("plan-import", "PLAN.md", "--amend")
    assert "nothing to amend" in (out.stderr + out.stdout)


def test_init_writes_gitignore_entry(repo):
    gi = (repo.path / ".gitignore").read_text()
    assert ".workflow/worktrees/" in gi


def test_import_records_plan_hash(repo):
    import hashlib

    state = repo.read_state()
    digest = hashlib.sha256((repo.path / "PLAN.md").read_bytes()).hexdigest()
    assert state["plan_sha256"] == digest


@pytest.mark.parametrize(
    "expect_line",
    ["exit_code 0", "stdout_regex ^world$", "file_exists REPORT.md", "json_eq x y 1"],
)
def test_expect_types_parse(tmp_path, expect_line):
    r = git_repo(tmp_path / "repo")
    text = EXAMPLE_PLAN.read_text().replace(
        "  - cmd: cat data/name.txt\n    expect: stdout_regex ^world$",
        f"  - expect: {expect_line}",
    )
    (r.path / "PLAN.md").write_text(text)
    out = r.wf("plan-check", "PLAN.md")
    assert "OK: 5 cards" in out.stdout


def test_kit_scripts_are_the_installed_names():
    for name in [
        "wf.sh",
        "wf-card.sh",
        "wf-plan-import.sh",
        "wf-guard.sh",
        "wf-progress.sh",
        "wf-escalate.sh",
        "wf-decision.sh",
        "wf-merge-lanes.sh",
    ]:
        assert (KIT / "scripts" / name).is_file(), name
