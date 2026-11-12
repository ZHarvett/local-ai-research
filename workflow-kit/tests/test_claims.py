"""Claim conflicts: files_write overlap, resource conflicts, machine lock."""

import json
import subprocess
from pathlib import Path

from conftest import EXAMPLE_PLAN, SCRIPTS, git_repo


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def shared(repo) -> Path:
    common = repo.run("git", "rev-parse", "--git-common-dir").stdout.strip()
    return repo.path / common / "workflow"


def gpu_plan(tmp_path, name="repo") -> "object":
    """Example plan where T-004 is gpu with no dependencies."""
    r = git_repo(tmp_path / name)
    text = EXAMPLE_PLAN.read_text().replace(
        "phase: P2\ndepends_on: T-002, T-003\nlane: 1\nresources: light",
        "phase: P2\ndepends_on: none\nlane: 1\nresources: gpu",
    )
    (r.path / "PLAN.md").write_text(text)
    r.wf("init-from-plan", "PLAN.md")
    return r


def test_claim_requires_ready(repo):
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    out = repo.wf_fail("claim", "T-004")  # todo: deps not satisfied
    assert "not ready" in (out.stderr + out.stdout)


def test_claim_refuses_wrong_lane(repo):
    out = repo.wf_fail("claim", "T-001", "--lane", "2")
    assert "planned for lane 1" in (out.stderr + out.stdout)


def test_files_write_overlap_refused(tmp_path):
    r = git_repo(tmp_path / "repo")
    # T-005 gains a file that T-002 (in progress) writes
    text = EXAMPLE_PLAN.read_text().replace(
        "files_write: data/metrics.json, REPORT.md",
        "files_write: src/greet.py, data/metrics.json, REPORT.md",
    )
    (r.path / "PLAN.md").write_text(text)
    r.wf("init-from-plan", "PLAN.md")
    r.set_raw_status("T-001", "done")  # T-002 becomes ready
    r.wf("event", "recheck")
    r.wf("claim", "T-002")
    r.wf("start", "T-002")
    r.set_raw_status("T-004", "accepted")
    r.set_raw_status("T-005", "ready")
    r.wf("event", "recheck")
    out = r.wf_fail("claim", "T-005")
    assert "overlaps the in-progress task T-002" in (out.stderr + out.stdout)


def test_gpu_task_refuses_beside_cpu_heavy_task(tmp_path):
    r = gpu_plan(tmp_path)
    r.py(
        "import importlib.util, os\n"
        f"spec = importlib.util.spec_from_file_location('_wf', {str(SCRIPTS / '_wf.py')!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "from pathlib import Path\n"
        "repo = Path(os.environ['WF_REPO'])\n"
        "state = m.load_state(repo)\n"
        "state['tasks']['T-002']['resources'] = 'cpu-heavy'\n"
        "state['tasks']['T-002']['status'] = 'in-progress'\n"
        "m.save_json(m.state_path(repo), state)\n"
    )
    # register a live claim for T-002 so the conflict check sees it
    claims_path = shared(r) / "claims.json"
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims = read_json(claims_path) if claims_path.is_file() else {}
    claims["T-002"] = {
        "lane": 2,
        "pid": int(r.env["WF_SESSION_PID"]),
        "ts": "t",
        "resources": "cpu-heavy",
    }
    claims_path.write_text(json.dumps(claims))
    out = r.wf_fail("claim", "T-004")
    assert "'gpu'" in (out.stderr + out.stdout) and "cpu-heavy" in (out.stderr + out.stdout)


def test_light_task_beside_in_progress_task_is_allowed(repo):
    repo.set_raw_status("T-002", "in-progress")
    out = repo.wf("claim", "T-001")  # light, disjoint files
    assert out.returncode == 0


def test_machine_lock_taken_by_heavy_start(tmp_path):
    r = gpu_plan(tmp_path)
    r.wf("claim", "T-004")
    r.wf("start", "T-004")
    info = read_json(Path(r.env["WF_MACHINE_LOCK"]))
    assert info["task"] == "T-004"
    assert info["repo"] == str(r.path)


def test_machine_lock_released_by_done(tmp_path):
    r = gpu_plan(tmp_path)
    r.wf("claim", "T-004")
    r.wf("start", "T-004")
    # satisfy acceptance: T-004 writes out/message.txt; heavy item is deferred
    (r.path / "out").mkdir(exist_ok=True)
    (r.path / "out" / "message.txt").write_text("Hello, world!\n")
    (r.path / "data").mkdir(exist_ok=True)
    (r.path / "data" / "name.txt").write_text("world")
    r.wf("accept", "T-004")
    r.wf("done", "T-004")
    assert not Path(r.env["WF_MACHINE_LOCK"]).exists()


def test_machine_lock_blocks_a_second_repo(tmp_path):
    """Two temp repos, one shared machine lock: the second heavy claim refuses."""
    lock = tmp_path / "shared-machine.lock"
    repos = []
    for name in ("a", "b"):
        path = tmp_path / name
        path.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=path, check=True)
        r = git_repo(path)
        r.env["WF_MACHINE_LOCK"] = str(lock)
        text = EXAMPLE_PLAN.read_text().replace(
            "phase: P2\ndepends_on: T-002, T-003\nlane: 1\nresources: light",
            "phase: P2\ndepends_on: none\nlane: 1\nresources: gpu",
        )
        (r.path / "PLAN.md").write_text(text)
        r.wf("init-from-plan", "PLAN.md")
        repos.append(r)
    first, second = repos
    first.wf("claim", "T-004")
    first.wf("start", "T-004")
    out = second.wf_fail("claim", "T-004")
    assert "machine lock" in (out.stderr + out.stdout)
    # release (crash recovery path) and the second repo can claim
    second.wf("machine-release", "--force")
    out = second.wf("claim", "T-004")
    assert out.returncode == 0


def test_claim_records_session_pid(repo):
    repo.wf("claim", "T-001")
    claims = read_json(shared(repo) / "claims.json")
    assert claims["T-001"]["pid"] == int(repo.env["WF_SESSION_PID"])
    assert claims["T-001"]["lane"] == 1


def test_lane_lock_blocks_a_foreign_live_session(repo):
    repo.wf("claim", "T-001")
    lock = shared(repo) / "locks" / "lane-1.lock"
    info = read_json(lock)
    info["pid"] = 1  # init: alive and definitely not us
    lock.write_text(json.dumps(info))
    # a second claim of another lane-1 task is refused while the lock is held
    for tid in ("T-001", "T-002", "T-003"):
        repo.set_raw_status(tid, "done")
    repo.wf("event", "recheck")  # T-004 becomes ready (lane 1)
    out = repo.wf_fail("claim", "T-004")
    assert "locked by pid 1" in (out.stderr + out.stdout)
    repo.wf("lane-release", "1")
    out = repo.wf("claim", "T-004")
    assert out.returncode == 0
