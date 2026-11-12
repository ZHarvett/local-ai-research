"""Guard failures: plan edited, state hand-edited, PROGRESS.md hand-edited, stale locks."""

import json
from pathlib import Path


def test_guard_ok_on_fresh_repo(repo):
    out = repo.wf("guard")
    assert "guard: OK" in out.stdout


def test_guard_fails_when_plan_edited(repo):
    plan = repo.path / "PLAN.md"
    plan.write_text(plan.read_text() + "\n<!-- sneaky edit -->\n")
    out = repo.wf_fail("guard")
    assert "PLAN.md does not match the approved hash" in out.stderr
    assert "git checkout -- PLAN.md" in out.stderr
    # restore
    plan.write_text(plan.read_text().replace("\n<!-- sneaky edit -->\n", ""))
    repo.wf("guard")


def test_guard_fails_when_state_hand_edited(repo):
    state_path = repo.path / ".workflow" / "state.json"
    state = json.loads(state_path.read_text())
    state["tasks"]["T-001"]["status"] = "done"  # hand edit, no checksum update
    state_path.write_text(json.dumps(state, indent=2))
    out = repo.wf_fail("status")
    assert "modified outside the workflow scripts" in out.stderr
    assert "git checkout -- " in out.stderr


def test_guard_fails_when_progress_hand_edited(repo):
    progress = repo.path / "PROGRESS.md"
    progress.write_text(progress.read_text().replace("T-001 |", "T-XXX |"))
    out = repo.wf_fail("guard")
    assert "PROGRESS.md differs from the render" in out.stderr
    assert "wf-progress.sh render" in out.stderr
    repo.wf("render")
    repo.wf("guard")


def test_guard_reports_stale_machine_lock(repo):
    lock = Path(repo.env["WF_MACHINE_LOCK"])
    lock.write_text(json.dumps({"pid": 999999, "repo": "x", "task": "T-009", "ts": "t"}))
    out = repo.wf("guard", check=False)
    assert out.returncode == 1
    assert "machine lock" in out.stderr and "dead holder pid" in out.stderr
    repo.wf("machine-release")  # pid dead -> release allowed without --force
    assert not lock.exists()


def test_machine_release_refuses_live_holder(repo):
    lock = Path(repo.env["WF_MACHINE_LOCK"])
    lock.write_text(json.dumps({"pid": 1, "repo": "x", "task": "T-009", "ts": "t"}))
    out = repo.wf_fail("machine-release")
    assert "alive" in (out.stderr + out.stdout)
    assert lock.exists()


def test_guard_fails_without_state(tmp_path):
    from conftest import git_repo

    r = git_repo(tmp_path / "repo")
    out = r.wf_fail("guard")
    assert "init-from-plan" in (out.stderr + out.stdout)
