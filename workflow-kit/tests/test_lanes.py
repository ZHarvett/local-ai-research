"""Lanes: worktrees, mirrors, merge, release, cross-worktree visibility."""

import json
from pathlib import Path


def shared(repo) -> Path:
    common = repo.run("git", "rev-parse", "--git-common-dir").stdout.strip()
    return repo.path / common / "workflow"


def claim_lane2(repo):
    repo.finish_t001()
    repo.wf("claim", "T-002")
    return repo.path / ".workflow" / "worktrees" / "lane-2"


def commit_all(repo, path, msg):
    repo.run("git", "-C", str(path), "add", "-A")
    repo.run("git", "-C", str(path), "commit", "-m", msg)


def test_lane_claim_creates_worktree_and_branch(repo):
    worktree = claim_lane2(repo)
    assert worktree.is_dir()
    out = repo.run("git", "worktree", "list").stdout
    assert "lane-2" in out
    assert "lane-2" in repo.run("git", "branch").stdout


def test_lane_file_and_mirror_written(repo):
    worktree = claim_lane2(repo)
    lane_file = worktree / ".workflow" / "lanes" / "2.json"
    mirror = shared(repo) / "lanes" / "2.json"
    assert lane_file.is_file() and mirror.is_file()
    data = json.loads(mirror.read_text())
    assert data["tasks"]["T-002"]["status"] == "claimed"


def test_render_merges_lane_mirrors(repo):
    claim_lane2(repo)
    progress = (repo.path / "PROGRESS.md").read_text()
    assert "T-002" in progress and "claimed" in progress
    # the lane file's task overrides the main state's todo placeholder
    state = repo.read_state()
    assert state["tasks"]["T-002"]["status"] == "todo"


def test_lane_2_sees_lane_1_progress_after_branch_creation(repo):
    """Amendment 2: dependencies completed on MAIN after the lane branch was
    created are visible to the lane session."""
    repo.commit("init")  # a base commit: all tasks todo
    repo.set_raw_status("T-001", "done")  # uncommitted: only the working tree
    repo.wf("event", "recheck")
    repo.wf("claim", "T-002")  # worktree branches from HEAD; its state copy is stale
    worktree = repo.path / ".workflow" / "worktrees" / "lane-2"
    # main completes T-001 (commits it) AFTER the lane branch was created
    repo.commit("T-001 done")
    # the worktree's own state copy predates T-001's completion; commands
    # inside the worktree must see 'done' via the MAIN state
    env = {
        **repo.env,
        "WF_REPO": str(worktree),
    }
    import subprocess

    from conftest import SCRIPTS

    proc = subprocess.run(
        ["bash", str(SCRIPTS / "wf.sh"), "status"],
        cwd=worktree,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "T-001  done" in proc.stdout, (
        "the lane session must read dependency status from the MAIN checkout"
    )


def test_merge_lanes_folds_status_and_cleans_up(repo):
    worktree = claim_lane2(repo)
    repo.wf("start", "T-002")
    # do the work in the worktree
    (worktree / "src").mkdir(exist_ok=True)
    (worktree / "src" / "greet.py").write_text(
        "import json, sys\n"
        "name = open(sys.argv[1]).read().strip()\n"
        "style = json.load(sys.stdin if sys.argv[2] == '-' else open(sys.argv[2]))\n"
        "print(style['prefix'] + name + style['suffix'])\n"
    )
    (worktree / "data").mkdir(exist_ok=True)
    (worktree / "data" / "name.txt").write_text("world")
    repo.wf("step-done", "T-002", "S1")
    repo.wf("accept", "T-002")
    repo.wf("done", "T-002")
    commit_all(repo, worktree, "T-002")
    repo.wf("merge-lanes", "2")
    state = repo.read_state()
    assert state["tasks"]["T-002"]["status"] == "done"
    assert not (shared(repo) / "lanes" / "2.json").exists()
    assert not worktree.exists()
    assert "src/greet.py" in repo.run("git", "ls-files").stdout


def test_merge_refuses_with_active_tasks(repo):
    claim_lane2(repo)
    repo.wf("start", "T-002")
    out = repo.wf_fail("merge-lanes", "2")
    assert "active tasks" in (out.stderr + out.stdout)


def test_lane_release_reverts_active_tasks(repo):
    claim_lane2(repo)
    repo.wf("start", "T-002")
    repo.wf("lane-release", "2")
    mirror = json.loads((shared(repo) / "lanes" / "2.json").read_text())
    assert mirror["tasks"]["T-002"]["status"] == "ready"
    assert not (shared(repo) / "locks" / "lane-2.lock").exists()


def test_stale_lane_lock_removed_by_guard(repo):
    import subprocess

    from conftest import SCRIPTS

    repo.finish_t001()
    # a session that claims lane 2 and then DIES: the bash records its own $$,
    # which is gone once it exits
    proc = subprocess.run(
        ["bash", "-c", f"export WF_SESSION_PID=$$; exec bash {SCRIPTS / 'wf.sh'} claim T-002"],
        cwd=repo.path,
        env=repo.env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    lock = shared(repo) / "locks" / "lane-2.lock"
    info = json.loads(lock.read_text())
    dead_pid = info["pid"]
    assert not Path(f"/proc/{dead_pid}").exists(), "the claiming process must be gone"
    # simulate the crash cleanup: the dead session's claim entry is dropped
    claims = shared(repo) / "claims.json"
    data = json.loads(claims.read_text())
    data.pop("T-002", None)
    claims.write_text(json.dumps(data))
    # guard reports the removal (exit 1, one problem) and removes the lock
    out = repo.wf("guard", check=False)
    assert out.returncode == 1
    assert "removed stale lane-2 lock" in out.stderr
    assert not lock.exists()
    # and the tree is consistent again
    repo.wf("guard")


def test_lane_session_cannot_mutate_foreign_tasks(repo):
    worktree = claim_lane2(repo)
    env = {**repo.env, "WF_REPO": str(worktree)}
    import subprocess

    from conftest import SCRIPTS

    # T-004 lives in the main state; a lane-2 worktree session must not claim it
    proc = subprocess.run(
        ["bash", str(SCRIPTS / "wf.sh"), "claim", "T-004"],
        cwd=worktree,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


def test_lane_worktree_tasks_run_acceptance_there(repo):
    worktree = claim_lane2(repo)
    repo.wf("start", "T-002")
    (worktree / "src").mkdir(exist_ok=True)
    (worktree / "src" / "greet.py").write_text(
        "import json, sys\n"
        "name = open(sys.argv[1]).read().strip()\n"
        "style = json.load(sys.stdin if sys.argv[2] == '-' else open(sys.argv[2]))\n"
        "print(style['prefix'] + name + style['suffix'])\n"
    )
    (worktree / "data").mkdir(exist_ok=True)
    (worktree / "data" / "name.txt").write_text("world")
    out = repo.wf("accept", "T-002")
    record = worktree / ".workflow" / "acceptance" / "T-002.json"
    assert record.is_file(), "acceptance evidence must be recorded in the worktree"
    assert "PASS" in out.stdout
