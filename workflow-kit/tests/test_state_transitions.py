"""Every valid and invalid transition, driven through the real engine."""

import importlib.util

from conftest import SCRIPTS

spec = importlib.util.spec_from_file_location("_wf", SCRIPTS / "_wf.py")
_wf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_wf)

ACTIVE = _wf.ACTIVE_STATUSES


def attempt(repo, tid, new_status):
    """Try a transition in-process; return (ok, message)."""
    code = (
        "import importlib.util, os\n"
        f"spec = importlib.util.spec_from_file_location('_wf', {str(SCRIPTS / '_wf.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "from pathlib import Path\n"
        "repo = Path(os.environ['WF_REPO'])\n"
        "try:\n"
        f"    m.mutate(repo, {tid!r}, {new_status!r})\n"
        "    print('OK')\n"
        "except SystemExit:\n"
        "    raise\n"
        "except Exception as e:\n"
        "    print('ERR', e)\n"
    )
    proc = repo.py(code)
    return proc.returncode == 0 and "OK" in proc.stdout, proc.stdout + proc.stderr


def test_all_valid_transitions_allowed(repo):
    # T-001 walks its whole legal lifecycle
    repo.wf("claim", "T-001")  # todo->ready->claimed
    repo.wf("start", "T-001")  # ->in-progress
    repo.wf("gate-wait", "T-001", "--message", "x")  # ->awaiting-gate
    repo.wf("gate-release", "T-001")  # ->in-progress
    (repo.path / "data").mkdir(exist_ok=True)
    (repo.path / "data" / "name.txt").write_text("world")
    repo.wf("accept", "T-001")
    repo.wf("done", "T-001")  # ->done
    repo.wf("review-open", "T-001")
    repo.wf(
        "review-verdict",
        "T-001",
        "changes-requested",
        "--report-file",
        str(_write_report(repo.path, "changes-requested")),
    )
    repo.wf("start", "T-001")  # changes-requested -> in-progress
    repo.wf("done", "T-001")
    repo.wf("review-open", "T-001")
    repo.wf(
        "review-verdict",
        "T-001",
        "accepted",
        "--report-file",
        str(_write_report(repo.path, "accepted")),
    )
    assert repo.read_state()["tasks"]["T-001"]["status"] == "accepted"


def _write_report(root, verdict, findings=1):

    text = (
        "# Review\n\n## Task verdict\n\n" + verdict + "\n\n"
        "| id | severity | action | evidence | required action |\n"
        "|---|---|---|---|---|\n" + ("| F-1 | NOTE | FIX-DOC | x:1 | fix it |\n" * findings)
    )
    f = _tmp_file(root)
    f.write_text(text)
    return f


def _tmp_file(root):
    import tempfile
    from pathlib import Path

    fd, name = tempfile.mkstemp(dir=root, suffix=".md")
    import os

    os.close(fd)
    return Path(name)


def test_blocked_roundtrip_restores_status(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    repo.wf("block", "T-001", "--reason", "need a decision")
    assert repo.read_state()["tasks"]["T-001"]["status"] == "blocked-decision"
    repo.wf("unblock", "T-001")
    assert repo.read_state()["tasks"]["T-001"]["status"] == "in-progress"


def test_invalid_transitions_rejected(repo):
    # a fresh task is 'ready' (deps satisfied: none)
    for bad in [
        "done",
        "in-progress",
        "awaiting-gate",
        "in-review",
        "accepted",
        "changes-requested",
    ]:
        ok, msg = attempt(repo, "T-001", bad)
        assert not ok, f"ready -> {bad} was allowed"
        assert "invalid transition" in msg
    assert repo.read_state()["tasks"]["T-001"]["status"] == "ready"


def test_terminal_states_are_frozen(repo):
    repo.set_raw_status("T-001", "superseded")
    for bad in ["ready", "claimed", "in-progress", "done"]:
        ok, _ = attempt(repo, "T-001", bad)
        assert not ok, f"superseded -> {bad} was allowed"
    repo.set_raw_status("T-002", "cancelled")
    ok, _ = attempt(repo, "T-002", "ready")
    assert not ok
    repo.set_raw_status("T-003", "accepted")
    ok, _ = attempt(repo, "T-003", "superseded")
    assert not ok, "accepted -> superseded was allowed"


def test_transition_table_is_total():
    for status in _wf.ALL_STATUSES:
        assert status in _wf.TRANSITIONS
    unknown = set(_wf.TRANSITIONS) - set(_wf.ALL_STATUSES)
    assert not unknown


def test_ready_derivation_requires_accepted_reviewed_deps(repo):
    # T-005 depends on T-004 which has review: post -> only 'accepted' satisfies
    repo.set_raw_status("T-004", "done")
    # force the recompute that a normal mutation triggers
    repo.wf("event", "recompute")
    state = repo.read_state()
    assert state["tasks"]["T-005"]["status"] == "todo", (
        "done-with-review must NOT satisfy a dependent; only accepted does"
    )
    repo.set_raw_status("T-004", "accepted")
    repo.wf("event", "recompute")
    assert repo.read_state()["tasks"]["T-005"]["status"] == "ready"


def test_done_requires_acceptance_record(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    (repo.path / "data").mkdir(exist_ok=True)
    (repo.path / "data" / "name.txt").write_text("world")
    out = repo.wf_fail("done", "T-001")
    assert "acceptance record" in (out.stderr + out.stdout)


def test_done_refuses_after_a_failing_accept(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    (repo.path / "data").mkdir(exist_ok=True)
    (repo.path / "data" / "name.txt").write_text("earth")  # wrong content
    repo.wf("accept", "T-001")
    out = repo.wf_fail("done", "T-001")
    assert "FAILED" in (out.stderr + out.stdout)


def test_done_refuses_when_evidence_file_is_empty(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    (repo.path / "data").mkdir(exist_ok=True)
    (repo.path / "data" / "name.txt").write_text("world")
    repo.wf("accept", "T-001")
    (repo.path / "data" / "name.txt").write_text("")  # evidence emptied afterwards
    repo.wf("accept", "T-001")  # re-run records the failure
    out = repo.wf_fail("done", "T-001")
    assert "FAILED" in (out.stderr + out.stdout) or "missing or empty" in (out.stderr + out.stdout)
