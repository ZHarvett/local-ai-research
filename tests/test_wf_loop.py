"""wf-loop.sh tests (T-017 S4): fake claude + fixture state, one test per stop condition.

Never runs the real claude CLI and never touches this repo's real state
(card S2/S5; decision E-004 change 2). Every test drives the loop through the
WF_LOOP_* env knobs with a fixture git repo, fixture state files and a fake
claude executable in a temporary directory.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import textwrap
from pathlib import Path

from conftest import REPO

LOOP = REPO / "scripts/wf-loop.sh"

GUARD_OK = "#!/usr/bin/env bash\nexit 0\n"
GUARD_FAIL_OTHER = (
    "#!/usr/bin/env bash\n"
    'echo "GUARD: PLAN.md does not match the approved hash"\n'
    'echo "guard: 1 problem(s)"\n'
    "exit 1\n"
)
GUARD_PLACEHOLDER = (
    "#!/usr/bin/env bash\n"
    'echo "GUARD: task T-001 is in the main state as ready AND in lane 3; '
    'run wf.sh merge-lanes 3"\n'
    'echo "guard: 1 problem(s) — see GUARD lines above"\n'
    "exit 1\n"
)
# Like the real guard: the placeholder line exists only while the lane mirror
# shows the task active; once it is done the guard passes.
GUARD_PLACEHOLDER_DYNAMIC = """#!/usr/bin/env bash
status=$(python3 -c 'import json, os; p = os.path.join(os.environ["WF_LOOP_LANES_DIR"], "3.json"); d = json.load(open(p)) if os.path.exists(p) else {}; print(d.get("tasks", {}).get("T-001", {}).get("status", ""))' 2>/dev/null)
if [ "$status" = "in-progress" ]; then
  echo "GUARD: task T-001 is in the main state as ready AND in lane 3; run wf.sh merge-lanes 3"
  echo "guard: 1 problem(s) — see GUARD lines above"
  exit 1
fi
exit 0
"""

# The fake claude: records its argv, optionally prints text, optionally runs a
# mutation script (which edits the fixture state), then exits with a chosen code.
FAKE_CLAUDE = """#!/usr/bin/env python3
import json
import os
import runpy
import sys

with open(os.environ["FAKE_CLAUDE_CALLS"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
text = os.environ.get("FAKE_CLAUDE_OUTPUT", "")
if text:
    print(text)
script = os.environ.get("FAKE_CLAUDE_SCRIPT")
if script:
    runpy.run_path(script)
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
"""


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def task(status="ready", lane=1, review="none", **extra):
    return {"status": status, "lane": lane, "review": review, **extra}


def make_fixture(
    tmp_path,
    tasks,
    *,
    escalations=None,
    review_cycles=None,
    mirrors=None,
    guard=None,
    accept=None,
):
    """A fixture repo + state + fake claude; returns (repo, env for the loop)."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("fixture\n")
    (repo / "scripts" / "wf-guard.sh").write_text(GUARD_OK if guard is None else guard)
    for tid, failures in (accept or {}).items():
        acc = repo / ".workflow" / "acceptance"
        acc.mkdir(parents=True, exist_ok=True)
        (acc / f"{tid}.json").write_text(json.dumps([{"failures": failures}]))
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(
        repo,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    state_dir = tmp_path / "state"
    (state_dir / "lanes").mkdir(parents=True)
    state = {
        "tasks": tasks,
        "escalations": escalations or {},
        "review_cycles": review_cycles or {},
        "review_dispositions": {},
    }
    (state_dir / "state.json").write_text(json.dumps(state))
    for lane, mirror in (mirrors or {}).items():
        (state_dir / "lanes" / f"{lane}.json").write_text(json.dumps(mirror))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(0o755)
    env = {
        **os.environ,
        "WF_LOOP_REPO": str(repo),
        "WF_LOOP_STATE_FILE": str(state_dir / "state.json"),
        "WF_LOOP_LANES_DIR": str(state_dir / "lanes"),
        "WF_LOOP_LOCK": str(tmp_path / "loop.lock"),
        "WF_LOOP_LOG": str(tmp_path / "loop.log"),
        "WF_LOOP_CLAUDE_BIN": str(fake),
        "WF_LOOP_CLAUDE_ARGS": "",
        "WF_LOOP_SESSION_TIMEOUT_MIN": "1",
        "FAKE_CLAUDE_CALLS": str(tmp_path / "calls.jsonl"),
    }
    env.pop("WF_CONFIG", None)
    return repo, env


def run_loop(env, hours="0.5", extra_env=None, timeout=60):
    merged = {**env, **(extra_env or {})}
    return subprocess.run(
        ["bash", str(LOOP), hours],
        capture_output=True,
        text=True,
        env=merged,
        timeout=timeout,
    )


def calls(env):
    path = Path(env["FAKE_CLAUDE_CALLS"])
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def prompts(env):
    return [c[1] for c in calls(env)]


def mutation(tmp_path, code):
    path = tmp_path / "mutate.py"
    path.write_text(textwrap.dedent(code))
    return str(path)


def set_status_code(tid, status, **fields):
    return f"""
        import json
        import os

        path = os.environ["WF_LOOP_STATE_FILE"]
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["tasks"]["{tid}"]["status"] = "{status}"
        state["tasks"]["{tid}"].update({fields!r})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    """


def accept_review_code(tid, verdict, cycle):
    return f"""
        import json
        import os

        path = os.environ["WF_LOOP_STATE_FILE"]
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["tasks"]["{tid}"]["status"] = "{verdict}"
        state["review_cycles"]["{tid}"] = {cycle}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    """


# ------------------------------------------------------------------ interface


def test_help_exits_zero():
    r = subprocess.run(["bash", str(LOOP), "--help"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert "Usage:" in r.stdout


def test_missing_hours_is_usage_error():
    r = subprocess.run(["bash", str(LOOP)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 2


def test_claude_args_come_only_from_env(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    env["WF_LOOP_CLAUDE_ARGS"] = "--foo bar"
    run_loop(env)
    assert calls(env)[0] == ["-p", "/continue", "--foo", "bar"]


def test_startup_prints_supervised_run_note(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    r = run_loop(env)
    assert "supervised" in r.stdout
    assert "1 hour" in r.stdout


# ------------------------------------------------- stop conditions (design §5)


def test_stop_1_deadline_before_any_session(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    r = run_loop(env, hours="0.000001")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "deadline" in r.stdout
    assert "(task: none)" in r.stdout
    assert calls(env) == []


def test_stop_2_open_gate(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task("awaiting-gate", gate_message="run the thing")})
    r = run_loop(env)
    assert r.returncode == 1
    assert "open gate T-001" in r.stdout
    assert "run the thing" in r.stdout
    assert calls(env) == []


def test_stop_3_open_escalation(tmp_path):
    _, env = make_fixture(
        tmp_path,
        {"T-001": task("in-progress")},
        escalations={"E-001": {"task": "T-001", "status": "open"}},
    )
    r = run_loop(env)
    assert r.returncode == 1
    assert "open escalation E-001" in r.stdout
    assert calls(env) == []


def test_stop_4_blocked_decision(tmp_path):
    _, env = make_fixture(
        tmp_path, {"T-001": task("blocked-decision", blocked_reason="escalation E-009")}
    )
    r = run_loop(env)
    assert r.returncode == 1
    assert "blocked-decision T-001" in r.stdout
    assert calls(env) == []


def test_stop_5_failed_acceptance(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()}, accept={"T-001": 2})
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, set_status_code("T-001", "in-progress"))
    r = run_loop(env)
    assert r.returncode == 1
    assert "acceptance failed (2 failures)" in r.stdout
    assert prompts(env) == ["/continue"]


def test_stop_6_no_progress_after_two_attempts(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    r = run_loop(env)  # fake claude changes nothing
    assert r.returncode == 1
    assert "no progress" in r.stdout
    assert prompts(env) == ["/continue", "/continue"]


def test_stop_7_nonzero_session_exit(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    env["FAKE_CLAUDE_EXIT"] = "3"
    r = run_loop(env)
    assert r.returncode == 1
    assert "session exit 3" in r.stdout
    assert len(calls(env)) == 1


def test_stop_7_usage_limit_message(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    env["FAKE_CLAUDE_OUTPUT"] = "Error: you have hit your usage limit"
    r = run_loop(env)
    assert r.returncode == 1
    assert "usage-limit" in r.stdout
    assert len(calls(env)) == 1


def test_stop_8_unexpected_dirty_tree(tmp_path):
    repo, env = make_fixture(tmp_path, {"T-001": task()})
    code = (
        set_status_code("T-001", "done")
        + """
        from pathlib import Path
        (Path(os.environ["WF_LOOP_REPO"]) / "stray.txt").write_text("x")
        """
    )
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, code)
    r = run_loop(env)
    assert r.returncode == 1
    assert "dirty tree" in r.stdout
    assert (repo / "stray.txt").exists()


def test_stop_8_kit_rendered_churn_is_expected(tmp_path):
    repo, env = make_fixture(tmp_path, {"T-001": task()})
    code = (
        set_status_code("T-001", "done")
        + """
        from pathlib import Path
        repo = Path(os.environ["WF_LOOP_REPO"])
        (repo / "PROGRESS.md").write_text("rendered")
        (repo / ".workflow" / "lanes").mkdir(parents=True, exist_ok=True)
        (repo / ".workflow" / "lanes" / "9.json").write_text("{}")
        """
    )
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, code)
    r = run_loop(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "idle" in r.stdout


def test_stop_9_second_loop_refused(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    lock = Path(env["WF_LOOP_LOCK"])
    lock.touch()
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = run_loop(env)
    assert r.returncode == 1
    assert "second loop" in r.stdout
    assert calls(env) == []


def test_stop_10_session_timeout(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, "import time\ntime.sleep(30)\n")
    r = run_loop(env, extra_env={"WF_LOOP_SESSION_TIMEOUT_MIN": "0.02"}, timeout=30)
    assert r.returncode == 1
    assert "session timeout" in r.stdout


# ------------------------------------- guard stops (E-004 change 3, E-005 rule)


def test_guard_failure_stops(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()}, guard=GUARD_FAIL_OTHER)
    r = run_loop(env)
    assert r.returncode == 1
    assert "guard failed" in r.stdout
    assert calls(env) == []


def test_guard_e005_placeholder_exception_continues(tmp_path):
    tasks = {"T-001": task(lane=3), "T-002": task(lane=1)}
    mirrors = {3: {"tasks": {"T-001": task("in-progress", lane=3)}}}
    _, env = make_fixture(tmp_path, tasks, mirrors=mirrors, guard=GUARD_PLACEHOLDER_DYNAMIC)
    # T-001's effective status lives in the lane-3 mirror (mirrors win), so the
    # fake session must finish it there, not in the main state.
    code = (
        set_status_code("T-002", "done")
        + """
        import json
        import os
        from pathlib import Path

        path = Path(os.environ["WF_LOOP_LANES_DIR"]) / "3.json"
        with open(path, encoding="utf-8") as fh:
            mirror = json.load(fh)
        mirror["tasks"]["T-001"]["status"] = "done"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(mirror, fh)
    """
    )
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, code)
    r = run_loop(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "E-005 placeholder exception applied" in r.stdout
    assert prompts(env) == ["/continue"]
    assert "idle" in r.stdout


def test_guard_placeholder_with_ready_status_stops(tmp_path):
    tasks = {"T-001": task(lane=3), "T-002": task(lane=1)}
    _, env = make_fixture(tmp_path, tasks, guard=GUARD_PLACEHOLDER)
    r = run_loop(env)
    assert r.returncode == 1
    assert "guard failed" in r.stdout
    assert "status is ready" in r.stdout
    assert calls(env) == []


# ----------------------------------------- task work and the lane answer (E-004)


def test_single_ready_lane_uses_continue(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, set_status_code("T-001", "done"))
    r = run_loop(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert prompts(env) == ["/continue"]
    assert "idle" in r.stdout


def test_multi_lane_uses_lowest_lane_then_continue(tmp_path):
    tasks = {"T-001": task(lane=1), "T-002": task(lane=2)}
    _, env = make_fixture(tmp_path, tasks)
    code = """
        import json
        import os

        n = sum(1 for _ in open(os.environ["FAKE_CLAUDE_CALLS"], encoding="utf-8"))
        path = os.environ["WF_LOOP_STATE_FILE"]
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["tasks"]["T-001" if n == 1 else "T-002"]["status"] = "done"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    """
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, code)
    r = run_loop(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert prompts(env) == ["/lane 1", "/continue"]


def test_lane_mirror_overlays_main_state(tmp_path):
    tasks = {"T-001": task(lane=1), "T-002": task(lane=2)}
    mirrors = {2: {"tasks": {"T-002": task("in-progress", lane=2)}}}
    _, env = make_fixture(tmp_path, tasks, mirrors=mirrors)
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, set_status_code("T-001", "done"))
    r = run_loop(env)
    # T-002 is effectively in-progress, so only lane 1 is ready: /continue, not /lane 1
    assert prompts(env) == ["/continue"]
    assert r.returncode == 1
    assert "T-002 left in-progress" in r.stdout


def test_partial_progress_stops_for_manual_resume(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    env["FAKE_CLAUDE_SCRIPT"] = mutation(
        tmp_path, set_status_code("T-001", "in-progress", steps_done=["S1"])
    )
    r = run_loop(env)
    assert r.returncode == 1
    assert "not finished cleanly" in r.stdout
    assert prompts(env) == ["/continue"]


def test_stranded_in_progress_stops(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task("in-progress")})
    r = run_loop(env)
    assert r.returncode == 1
    assert "resume manually" in r.stdout
    assert calls(env) == []


# ------------------------------------------------------------- review scheduling


def test_post_review_then_idle(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task("done", review="post")})
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, accept_review_code("T-001", "accepted", 1))
    r = run_loop(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert prompts(env) == ["/review T-001"]
    assert "idle" in r.stdout


def test_in_flight_review_finished(tmp_path):
    _, env = make_fixture(
        tmp_path, {"T-001": task("in-review", review="post")}, review_cycles={"T-001": 1}
    )
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, accept_review_code("T-001", "accepted", 2))
    r = run_loop(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert prompts(env) == ["/review T-001"]


def test_address_review_flow(tmp_path):
    _, env = make_fixture(
        tmp_path,
        {"T-001": task("changes-requested", review="post")},
        review_cycles={"T-001": 1},
    )
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, accept_review_code("T-001", "in-review", 2))
    r = run_loop(env)
    assert prompts(env) == ["/address-review T-001"]
    assert r.returncode == 1
    assert "review cycles exhausted" in r.stdout


def test_review_cycles_exhausted_stops(tmp_path):
    _, env = make_fixture(
        tmp_path, {"T-001": task("in-review", review="post")}, review_cycles={"T-001": 2}
    )
    r = run_loop(env)
    assert r.returncode == 1
    assert "review cycles exhausted" in r.stdout
    assert calls(env) == []


def test_review_retry_then_no_progress_stops(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task("done", review="post")})
    code = """
        import json
        import os

        n = sum(1 for _ in open(os.environ["FAKE_CLAUDE_CALLS"], encoding="utf-8"))
        if n == 1:
            path = os.environ["WF_LOOP_STATE_FILE"]
            with open(path, encoding="utf-8") as fh:
                state = json.load(fh)
            state["tasks"]["T-001"]["status"] = "in-review"
            state["review_cycles"]["T-001"] = 1
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(state, fh)
    """
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, code)
    r = run_loop(env)
    assert r.returncode == 1
    assert "no progress" in r.stdout
    # cycle 1 advanced; attempts 2 and 3 changed nothing -> stop
    assert prompts(env) == ["/review T-001"] * 3


def test_pre_review_while_gated(tmp_path):
    tasks = {
        "T-001": task("awaiting-gate", gate_message="go"),
        "T-002": task(review="pre+post"),
    }
    _, env = make_fixture(tmp_path, tasks)
    code = """
        import json
        import os

        path = os.environ["WF_LOOP_STATE_FILE"]
        with open(path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["review_cycles"]["T-002"] = 1
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
    """
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, code)
    r = run_loop(env)
    assert prompts(env) == ["/review T-002"]
    assert r.returncode == 1
    assert "open gate T-001" in r.stdout


def test_never_reviews_a_blocked_task(tmp_path):
    tasks = {
        "T-001": task("blocked-decision", review="post", blocked_reason="E-009"),
        "T-002": task("done", review="post"),
    }
    _, env = make_fixture(tmp_path, tasks)
    env["FAKE_CLAUDE_SCRIPT"] = mutation(tmp_path, accept_review_code("T-002", "accepted", 1))
    r = run_loop(env)
    assert prompts(env) == ["/review T-002"]
    assert r.returncode == 1
    assert "blocked-decision T-001" in r.stdout


def test_final_message_names_reason_and_task(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task("awaiting-gate", gate_message="run the thing")})
    r = run_loop(env)
    last = r.stdout.strip().splitlines()[-1]
    assert last.startswith("wf-loop: STOP — ")
    assert "open gate T-001" in last
    assert "(task: T-001)" in last


# ------------------------------------------------------------- S5: --dry-run


def dry_run(env, timeout=30):
    return subprocess.run(
        ["bash", str(LOOP), "--dry-run"], capture_output=True, text=True, env=env, timeout=timeout
    )


def test_dry_run_prints_next_action_without_session(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task()})
    r = dry_run(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "next action: continue" in r.stdout
    assert "task=T-001" in r.stdout
    assert "prompt=/continue" in r.stdout
    assert calls(env) == []
    assert not Path(env["WF_LOOP_LOG"]).exists()
    assert not Path(env["WF_LOOP_LOCK"]).exists()


def test_dry_run_multi_lane_prints_lane_prompt(tmp_path):
    tasks = {"T-001": task(lane=1), "T-002": task(lane=2)}
    _, env = make_fixture(tmp_path, tasks)
    r = dry_run(env)
    assert r.returncode == 0
    assert "next action: lane" in r.stdout
    assert "prompt=/lane 1" in r.stdout
    assert calls(env) == []


def test_dry_run_reads_lane_mirrors(tmp_path):
    tasks = {"T-001": task(lane=1), "T-002": task(lane=2)}
    mirrors = {2: {"tasks": {"T-002": task("in-progress", lane=2)}}}
    _, env = make_fixture(tmp_path, tasks, mirrors=mirrors)
    r = dry_run(env)
    assert r.returncode == 0
    # T-002 is effectively in-progress: one ready lane -> /continue, not /lane 1
    assert "prompt=/continue" in r.stdout


def test_dry_run_would_stop_names_reason_and_task(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task("awaiting-gate", gate_message="go")})
    r = dry_run(env)
    assert r.returncode == 0
    assert "would STOP" in r.stdout
    assert "open gate T-001" in r.stdout
    assert "(task: T-001)" in r.stdout
    assert calls(env) == []


def test_dry_run_review_due(tmp_path):
    _, env = make_fixture(tmp_path, {"T-001": task("done", review="post")})
    r = dry_run(env)
    assert r.returncode == 0
    assert "next action: review" in r.stdout
    assert "prompt=/review T-001" in r.stdout
    assert calls(env) == []
