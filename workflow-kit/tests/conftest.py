"""Shared fixtures: a temp git repo with the example plan imported.

wf() runs the real CLI (bash scripts/wf.sh) as a subprocess, the way an
installed kit would. WF_SESSION_PID is the live pytest process, so claims look
owned; the machine lock is a per-repo temp file.
"""

import os
import subprocess
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1]
SCRIPTS = KIT / "scripts"
EXAMPLE_PLAN = KIT / "templates" / "plan-example.md"


class Repo:
    def __init__(self, path: Path, machine_lock: Path):
        self.path = path
        self.env = {
            **os.environ,
            "WF_SESSION_PID": str(os.getpid()),
            "WF_MACHINE_LOCK": str(machine_lock),
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        }

    def wf(self, *args, check=True):
        proc = subprocess.run(
            ["bash", str(SCRIPTS / "wf.sh"), *args],
            cwd=self.path,
            env=self.env,
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise AssertionError(
                f"wf {' '.join(args)} failed (exit {proc.returncode}):\n"
                f"{proc.stdout}\n{proc.stderr}"
            )
        return proc

    def wf_fail(self, *args):
        proc = self.wf(*args, check=False)
        assert proc.returncode != 0, f"wf {' '.join(args)} unexpectedly succeeded"
        return proc

    def run(self, *args, check=True):
        proc = subprocess.run(
            list(args), cwd=self.path, env=self.env, capture_output=True, text=True
        )
        if check and proc.returncode != 0:
            raise AssertionError(f"{args} failed:\n{proc.stdout}\n{proc.stderr}")
        return proc

    def py(self, code: str):
        """Run python that imports the engine in-process (WF_REPO is set)."""
        env = {**self.env, "WF_REPO": str(self.path)}
        return subprocess.run(
            ["python3", "-c", code],
            cwd=self.path,
            env=env,
            capture_output=True,
            text=True,
        )

    def set_raw_status(self, tid: str, status: str):
        """Bypass the transition checks: set a task status directly in state."""
        code = (
            "import importlib.util, os\n"
            f"spec = importlib.util.spec_from_file_location('_wf', {str(SCRIPTS / '_wf.py')!r})\n"
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "from pathlib import Path\n"
            "repo = Path(os.environ['WF_REPO'])\n"
            "state = m.load_state(repo)\n"
            f"state['tasks'][{tid!r}]['status'] = {status!r}\n"
            "m.save_json(m.state_path(repo), state)\n"
        )
        proc = self.py(code)
        assert proc.returncode == 0, proc.stderr

    def read_state(self) -> dict:
        import json

        return json.loads((self.path / ".workflow" / "state.json").read_text())

    def finish_t001(self):
        """Run T-001 (the simple lane-1 task) to done, and commit."""
        self.wf("claim", "T-001")
        self.wf("start", "T-001")
        self.wf("precheck", "T-001")
        (self.path / "data").mkdir(exist_ok=True)
        (self.path / "data" / "name.txt").write_text("world")
        self.wf("step-done", "T-001", "S1")
        self.wf("accept", "T-001")
        self.wf("done", "T-001")
        self.run("git", "add", "-A")
        self.run("git", "commit", "-m", "T-001")

    def commit(self, msg):
        self.run("git", "add", "-A")
        self.run("git", "commit", "-m", msg)


def git_repo(path: Path) -> Repo:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    return Repo(path, path.parent / f"{path.name}-machine.lock")


@pytest.fixture
def repo(tmp_path):
    """A repo with the example plan imported (tasks exist, none claimed)."""
    r = git_repo(tmp_path / "repo")
    (r.path / "PLAN.md").write_text(EXAMPLE_PLAN.read_text())
    r.wf("init-from-plan", "PLAN.md")
    return r


@pytest.fixture
def repo_with_custom_plan():
    """Factory: a repo with a plan derived from the example by text surgery."""

    def make(tmp_path: Path, replacements: dict[str, str], name="repo") -> Repo:
        r = git_repo(tmp_path / name)
        text = EXAMPLE_PLAN.read_text()
        for old, new in replacements.items():
            assert old in text, f"fixture surgery: {old!r} not in the example plan"
            text = text.replace(old, new)
        (r.path / "PLAN.md").write_text(text)
        r.wf("init-from-plan", "PLAN.md")
        return r

    return make
