#!/usr/bin/env python3
"""workflow-kit engine: state machine, plan import, lanes, gates, reviews, escalations.

Invoked as `wf.sh <subcommand> ...` (bash wrappers live beside this file) or directly:
`python3 _wf.py <subcommand> ...`. Python standard library only.

Repository layout (relative to the repo the session works in):
  PLAN.md               frozen plan (hash recorded in state)      [tracked]
  PLAN-ADDED.md         cards appended by sessions                [tracked, hand-writable]
  PROGRESS.md           GENERATED; do not edit by hand            [tracked]
  .workflow/state.json  written ONLY by these scripts             [tracked]
  .workflow/lanes/N.json  lane-local task statuses                [tracked]
  .workflow/acceptance/T-xxx.json  wf accept evidence records     [tracked]
  .workflow/config.toml repo copy of the kit config               [tracked]
  escalations/E-NNN.md  escalation briefs                         [tracked]
  reviews/, REVIEW_REPORT.md                                       [tracked]
Shared runtime (untracked, visible from every worktree of the repo):
  <git-common-dir>/workflow/locks/lane-N.lock
  <git-common-dir>/workflow/claims.json
  <git-common-dir>/workflow/lanes/N.json   mirrors of the lane files
Machine-wide lock (cross-repo, for gpu / exclusive-machine / cpu-heavy tasks):
  $WF_MACHINE_LOCK, default /dev/shm/local-ai-research-machine.lock

Ownership rules:
  - The main state file always lives in the MAIN checkout (parent of the git common
    dir); every session reads it there, so lanes never see a stale copy.
  - A task claimed into lane 1 is mutated in the main state; a task claimed into
    lane 2+ migrates into .workflow/lanes/N.json (tracked on the lane branch, mirrored
    in the shared dir). render merges main state + mirrors, so PROGRESS.md never
    conflicts between branches.
  - Sessions run in the main checkout; lane 2/3 file work happens inside the lane
    worktree at .workflow/worktrees/lane-N (created at claim time).
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

KIT_VERSION = "0.1.0"

ACTIVE_STATUSES = ("claimed", "in-progress", "awaiting-gate")
TERMINAL_STATUSES = ("accepted", "superseded", "cancelled")
ALL_STATUSES = (
    "todo",
    "ready",
    "claimed",
    "in-progress",
    "awaiting-gate",
    "done",
    "in-review",
    "changes-requested",
    "accepted",
    "blocked-decision",
    "superseded",
    "cancelled",
)
RESOURCES = ("light", "cpu-heavy", "gpu", "exclusive-machine")
REVIEW_POLICIES = ("none", "post", "pre+post")
EXPECT_TYPES = ("exit_code", "stdout_regex", "file_exists", "json_eq", "manual")
REVIEW_VERDICTS = ("accepted", "changes-requested", "blocked-decision")
ESCALATION_TYPES = (
    "decision",
    "problem",
    "assumption-mismatch",
    "review-disagreement",
)
PLAN_ADDED_NAME = "PLAN-ADDED.md"

# fields that must be present on every card, and those that may be empty/none
CARD_FIELDS_REQUIRED = (
    "id",
    "title",
    "phase",
    "depends_on",
    "lane",
    "resources",
    "files_read",
    "files_write",
    "gates",
    "review",
    "preconditions",
    "steps",
    "acceptance",
    "estimate",
    "decision_rights",
)
CARD_FIELDS_NONEMPTY = ("steps", "acceptance", "decision_rights")
CARD_FIELDS_LIST = ("depends_on", "files_read", "files_write", "gates", "evidence")
STEP_MARKER_RE = re.compile(r"\((redo-safe|not redo-safe)\)\s*$")
CHECK_ITEM_KEYS = ("cmd", "expect", "value", "id", "heavy")

TRANSITIONS: dict[str, set[str]] = {
    "todo": {"ready", "blocked-decision", "superseded", "cancelled"},
    "ready": {"claimed", "blocked-decision", "superseded", "cancelled", "todo"},
    "claimed": {"ready", "in-progress", "blocked-decision", "superseded", "cancelled"},
    "in-progress": {
        "awaiting-gate",
        "done",
        "blocked-decision",
        "superseded",
        "cancelled",
    },
    "awaiting-gate": {"in-progress", "blocked-decision", "superseded", "cancelled"},
    "done": {"in-review", "blocked-decision", "superseded", "cancelled"},
    "in-review": {
        "accepted",
        "changes-requested",
        "blocked-decision",
        "superseded",
        "cancelled",
    },
    "changes-requested": {
        "in-progress",
        "in-review",
        "blocked-decision",
        "superseded",
        "cancelled",
    },
    "accepted": set(),
    "blocked-decision": {
        "ready",
        "claimed",
        "in-progress",
        "awaiting-gate",
        "done",
        "in-review",
        "changes-requested",
        "superseded",
        "cancelled",
    },
    "superseded": set(),
    "cancelled": set(),
}

# Explicit targets for `wf.sh unblock --to` (T-018): the review-flow return statuses,
# each a legal transition out of blocked-decision in TRANSITIONS above.
UNBLOCK_TO_TARGETS = ("done", "in-review", "changes-requested")

# T-022: statuses only the main state advances (terminal or review-flow); a lane
# mirror can be stale against them, so merge-lanes keeps main's value.
MAIN_WINS_STATUSES = ("accepted", "in-review", "changes-requested", "superseded", "cancelled")

BRIEF_REQUIRED_SECTIONS = (
    "## What happened",
    "## Why it cannot proceed",
    "## Options",
    "## Recommendation",
    "## What is blocked and what can proceed",
    "## The exact question",
)

DEFAULT_CONFIG = {
    "model_note": "single model for executor, subagent and reviewer",
    "workflow": {
        "max_parallel_sessions": 3,
        "max_review_cycles": 2,
        "parallel_value_threshold_min": 30,
    },
    "locks": {
        "machine_lock": "/dev/shm/local-ai-research-machine.lock",
    },
}


class WfError(Exception):
    """A user-facing error: message is printed verbatim, exit code 1."""


def die(msg: str) -> None:
    raise WfError(msg)


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def deep_default_config() -> dict:
    return json.loads(json.dumps(DEFAULT_CONFIG))


# ---------------------------------------------------------------- repo paths


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        die(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def repo_root() -> Path:
    env = os.environ.get("WF_REPO")
    if env:
        return Path(env).resolve()
    proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if proc.returncode != 0:
        die("not inside a git repository (and WF_REPO is unset)")
    return Path(proc.stdout.strip()).resolve()


def git_common_dir(repo: Path) -> Path:
    out = _git(repo, "rev-parse", "--git-common-dir")
    path = Path(out)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def main_root(repo: Path) -> Path:
    """The main checkout: parent of the git common dir (== repo outside worktrees)."""
    return git_common_dir(repo).parent


def shared_dir(repo: Path) -> Path:
    return git_common_dir(repo) / "workflow"


def in_main(repo: Path) -> bool:
    return repo == main_root(repo)


def worktree_for_lane(repo: Path, lane: int) -> Path:
    return main_root(repo) / ".workflow" / "worktrees" / f"lane-{lane}"


def session_pid() -> int:
    """Pid of the long-lived session process (Claude Code), 0 if unknown.

    Walks the parent chain for a process whose comm starts with 'claude';
    WF_SESSION_PID overrides (tests, non-claude drivers). 0 means "assume alive".
    """
    env = os.environ.get("WF_SESSION_PID")
    if env:
        try:
            return int(env)
        except ValueError:
            return 0
    pid = os.getpid()
    for _ in range(20):
        try:
            with open(f"/proc/{pid}/comm") as fh:
                comm = fh.read().strip()
        except OSError:
            return 0
        if comm.startswith("claude"):
            return pid
        try:
            with open(f"/proc/{pid}/stat") as fh:
                stat = fh.read()
        except OSError:
            return 0
        rest = stat.rsplit(")", 1)[1].split()
        pid = int(rest[1])
        if pid <= 1:
            return 0
    return 0


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return True  # unknown owner: never auto-stale
    return Path(f"/proc/{pid}").exists()


# ------------------------------------------------------------------- config


def load_config(repo: Path) -> dict:
    import tomllib

    cfg = deep_default_config()
    path = os.environ.get("WF_CONFIG") or (repo / ".workflow" / "config.toml")
    path = Path(path)
    if path.is_file():
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except (OSError, ValueError) as exc:
            die(f"cannot read config {path}: {exc}")
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    return cfg


def machine_lock_path(repo: Path) -> Path:
    env = os.environ.get("WF_MACHINE_LOCK")
    return Path(env if env else load_config(repo)["locks"]["machine_lock"])


# -------------------------------------------------------------------- state


def state_path(repo: Path) -> Path:
    """The state file ALWAYS lives in the main checkout (fresh across worktrees)."""
    return main_root(repo) / ".workflow" / "state.json"


def lane_file(repo: Path, lane: int) -> Path:
    return repo / ".workflow" / "lanes" / f"{lane}.json"


def lane_mirror(repo: Path, lane: int) -> Path:
    return shared_dir(repo) / "lanes" / f"{lane}.json"


def _payload_checksum(payload: dict) -> str:
    body = {k: v for k, v in payload.items() if k != "checksum"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_json_checked(path: Path, label: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        die(f"{label} at {path} is unreadable: {exc}")
    if not isinstance(data, dict):
        die(f"{label} at {path} is not a JSON object")
    if "checksum" in data and data["checksum"] != _payload_checksum(data):
        die(
            f"{label} at {path} was modified outside the workflow scripts "
            f"(checksum mismatch). Restore it with: git checkout -- {path}"
        )
    return data


def load_state(repo: Path) -> dict:
    return _load_json_checked(state_path(repo), "state.json")


def lane_numbers(repo: Path) -> list[int]:
    numbers = []
    shared = shared_dir(repo) / "lanes"
    if shared.is_dir():
        for entry in sorted(shared.iterdir()):
            m = re.fullmatch(r"(\d+)\.json", entry.name)
            if m:
                numbers.append(int(m.group(1)))
    return numbers


def load_lane(repo: Path, lane: int, from_mirror: bool = False) -> dict | None:
    path = lane_mirror(repo, lane) if from_mirror else lane_file(repo, lane)
    if not path.is_file():
        return None
    return _load_json_checked(path, f"lane file {lane}")


def save_json(path: Path, data: dict) -> None:
    data = dict(data)
    data["checksum"] = _payload_checksum(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def save_owner(repo: Path, owner: dict, owner_lane: int | None) -> None:
    """Persist the owning file: main state (renders PROGRESS.md) or the lane file
    (worktree copy when it exists, plus the shared mirror). PROGRESS.md merges
    the mirrors, so lane mutations re-render it on the main checkout too."""
    if owner_lane is None:
        save_json(state_path(repo), owner)
        render_progress(repo)
        return
    if lane_of_worktree(repo) == owner_lane:
        save_json(lane_file(repo, owner_lane), owner)
    else:
        wt = worktree_for_lane(repo, owner_lane)
        if wt.is_dir():
            save_json(lane_file(wt, owner_lane), owner)
    save_json(lane_mirror(repo, owner_lane), owner)
    render_progress(repo)


def lane_of_worktree(repo: Path) -> int | None:
    main = main_root(repo)
    try:
        rel = repo.relative_to(main / ".workflow" / "worktrees")
    except ValueError:
        return None
    if not rel.parts:
        return None
    m = re.fullmatch(r"lane-(\d+)", rel.parts[0])
    return int(m.group(1)) if m else None


def effective_tasks(repo: Path, state: dict) -> dict[str, dict]:
    """Main state tasks overlaid by every lane mirror (mirrors win)."""
    tasks = {tid: dict(t) for tid, t in state.get("tasks", {}).items()}
    for lane in lane_numbers(repo):
        mirror = load_lane(repo, lane, from_mirror=True)
        if mirror:
            for tid, task in mirror.get("tasks", {}).items():
                merged = dict(tasks.get(tid, {}))
                merged.update(task)
                tasks[tid] = merged
    return tasks


def all_events(repo: Path, state: dict) -> list[dict]:
    events = list(state.get("events", []))
    for lane in lane_numbers(repo):
        mirror = load_lane(repo, lane, from_mirror=True)
        if mirror:
            events.extend(mirror.get("events", []))
    events.sort(key=lambda e: (e.get("ts", ""), e.get("seq", 0)))
    return events


def append_event(owner: dict, event: str, task: str | None, detail: str = "") -> None:
    events = owner.setdefault("events", [])
    events.append(
        {
            "ts": now_utc(),
            "seq": len(events),
            "event": event,
            "task": task,
            "detail": detail,
        }
    )


def task_deps_satisfied(eff: dict[str, dict], task: dict) -> bool:
    for dep in task.get("depends_on", []):
        dep_task = eff.get(dep)
        if dep_task is None:
            return False
        if dep_task["status"] == "done" and dep_task.get("review") == "none":
            continue
        if dep_task["status"] != "accepted":
            return False
    return True


def recompute_ready(owner: dict, repo: Path, owner_lane: int | None) -> bool:
    """todo -> ready for tasks in `owner` whose dependencies are satisfied, judged
    against the effective view (main state from disk + this owner's overlay)."""
    changed = False
    for _ in range(3):
        if owner_lane is None:
            eff = effective_tasks(repo, owner)
        else:
            base = _try_load_state(repo) or {"tasks": {}}
            tasks = {tid: dict(t) for tid, t in base.get("tasks", {}).items()}
            for tid, task in owner.get("tasks", {}).items():
                merged = dict(tasks.get(tid, {}))
                merged.update(task)
                tasks[tid] = merged
            eff = tasks
        round_changed = False
        for tid, task in owner.get("tasks", {}).items():
            if task["status"] == "todo" and task_deps_satisfied(eff, task):
                task["status"] = "ready"
                append_event(owner, "ready", tid, "dependencies satisfied")
                round_changed = True
        changed = changed or round_changed
        if not round_changed:
            break
    return changed


def _try_load_state(repo: Path) -> dict | None:
    try:
        return load_state(repo)
    except WfError:
        return None


def find_task(repo: Path, task_id: str) -> tuple[dict, int | None, dict]:
    """Locate task_id in its OWNING file: lane mirrors first (they win over the
    main state), then the main state. Returns (owner, lane, task)."""
    for lane in lane_numbers(repo):
        mirror = load_lane(repo, lane, from_mirror=True)
        if mirror and task_id in mirror.get("tasks", {}):
            owner = load_or_init_lane(repo, lane)
            return owner, lane, owner["tasks"][task_id]
    state = _try_load_state(repo)
    if state is not None and task_id in state.get("tasks", {}):
        return state, None, state["tasks"][task_id]
    die(f"task {task_id} is not in the state or any lane file")


def load_or_init_lane(repo: Path, lane: int) -> dict:
    """The writeable lane dict: this session's worktree file if it is the lane
    session, else the worktree copy under the main checkout, else the mirror."""
    if lane_of_worktree(repo) == lane:
        path = lane_file(repo, lane)
        if path.is_file():
            return _load_json_checked(path, f"lane file {lane}")
        return {"version": 1, "lane": lane, "tasks": {}, "events": []}
    wt = worktree_for_lane(repo, lane)
    path = lane_file(wt, lane)
    if path.is_file():
        return _load_json_checked(path, f"lane file {lane}")
    mirror = load_lane(repo, lane, from_mirror=True)
    if mirror is not None:
        return mirror
    return {"version": 1, "lane": lane, "tasks": {}, "events": []}


def transition(repo: Path, task_id: str, new_status: str) -> None:
    if new_status not in ALL_STATUSES:
        die(f"'{new_status}' is not a task status")
    _, _, task = find_task(repo, task_id)
    old = task["status"]
    if old == new_status:
        return
    if new_status not in TRANSITIONS[old]:
        die(
            f"invalid transition for {task_id}: {old} -> {new_status} "
            f"(allowed: {', '.join(sorted(TRANSITIONS[old])) or 'none'})"
        )


def mutate(
    repo: Path,
    task_id: str,
    new_status: str | None = None,
    extra: dict | None = None,
    event: str | None = None,
    detail: str = "",
) -> dict:
    """Apply one mutation to task_id in its owning file, then re-derive readiness."""
    if new_status is not None:
        transition(repo, task_id, new_status)
    owner, owner_lane, task = find_task(repo, task_id)
    foreign_lane = new_status is not None and owner_lane is not None and not in_main(repo)
    if foreign_lane and lane_of_worktree(repo) != owner_lane:
        die("this session runs in a worktree; only tasks owned by this lane may be changed here")
    if extra:
        task.update(extra)
    if new_status is not None:
        task["status"] = new_status
    if event:
        append_event(owner, event, task_id, detail)
    if recompute_ready(owner, repo, owner_lane):
        save_owner(repo, owner, owner_lane)
    else:
        save_owner(repo, owner, owner_lane)
    if new_status is not None and new_status not in ACTIVE_STATUSES:
        lane = task.get("claimed_by_lane") or task.get("lane")
        release_lane_lock_if_idle(repo, lane)
    return task


def _task_record_anywhere(repo: Path, task_id: str) -> dict | None:
    try:
        state = load_state(repo)
    except WfError:
        return None
    eff = effective_tasks(repo, state)
    return eff.get(task_id)


# --------------------------------------------------------------------- guard


def plan_file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan_hash(repo: Path) -> str | None:
    return plan_file_hash(repo / "PLAN.md")


def guard(repo: Path, quiet: bool = False) -> list[str]:
    """Consistency checks; dies on hard failures, returns warning strings."""
    problems: list[str] = []
    if not state_path(repo).is_file():
        die("no .workflow/state.json: run wf.sh init-from-plan PLAN.md first")
    state = load_state(repo)  # checksum verified inside
    if in_main(repo):
        recorded = state.get("plan_sha256")
        actual = plan_hash(repo)
        if actual != recorded:
            problems.append(
                f"PLAN.md does not match the approved hash (recorded {recorded}, "
                f"found {actual}). Restore PLAN.md with: git checkout -- PLAN.md  "
                f"(or re-issue the plan: wf.sh plan-import PLAN.md --amend)"
            )
        rendered = progress_markdown(repo, state)
        current = None
        progress = repo / "PROGRESS.md"
        if progress.is_file():
            current = progress.read_text(encoding="utf-8")
        if current != rendered:
            problems.append(
                "PROGRESS.md differs from the render of state.json + lane files "
                "(hand edit, or a command failed before rendering). Restore with: "
                "bash scripts/wf-progress.sh render"
            )
    for lane in lane_numbers(repo):
        mirror = load_lane(repo, lane, from_mirror=True)
        if mirror is None:
            continue
        for tid in mirror.get("tasks", {}):
            if tid in state.get("tasks", {}):
                base = state["tasks"][tid]["status"]
                if base not in TERMINAL_STATUSES and base != "todo":
                    problems.append(
                        f"task {tid} is in the main state as {base} AND in lane "
                        f"{lane}; run wf.sh merge-lanes {lane}"
                    )
    active = {
        tid for tid, t in effective_tasks(repo, state).items() if t["status"] in ACTIVE_STATUSES
    }
    locks = shared_dir(repo) / "locks"
    if locks.is_dir():
        for entry in sorted(locks.iterdir()):
            m = re.fullmatch(r"lane-(\d+)\.lock", entry.name)
            if not m:
                continue
            lane = int(m.group(1))
            info = _read_lock(entry)
            if info and not pid_alive(info.get("pid", 0)):
                lane_active = any(
                    tid in active and _claims(repo).get(tid, {}).get("lane") == lane
                    for tid in _claims(repo)
                )
                if not lane_active:
                    entry.unlink()
                    problems.append(
                        f"removed stale lane-{lane} lock (holder pid {info.get('pid')} is gone)"
                    )
                    render_progress(repo)
    machine = machine_lock_path(repo)
    if machine.is_file():
        info = _read_lock(machine)
        if info and not pid_alive(info.get("pid", 0)):
            problems.append(
                f"machine lock at {machine} has a dead holder pid "
                f"({info.get('pid')}, repo {info.get('repo')}); if no heavy work "
                f"is running there, release it with: wf.sh machine-release"
            )
    if problems and not quiet:
        for problem in problems:
            print(f"GUARD: {problem}", file=sys.stderr)
    return problems


def cmd_guard(repo: Path, args: argparse.Namespace) -> None:
    problems = guard(repo, args.quiet)
    if problems:
        print(f"guard: {len(problems)} problem(s) — see GUARD lines above", file=sys.stderr)
        sys.exit(1)
    print("guard: OK")


# ------------------------------------------------------------ locks / claims


def _read_lock(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_lock(path: Path, info: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(info).encode())
    except OSError as exc:
        die(f"cannot take lock {path}: {exc}")
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class _Mutex:
    """flock-held mutex around shared-registry mutations."""

    def __init__(self, repo: Path):
        self.path = shared_dir(repo) / "registry.lock"
        self.fd: int | None = None

    def __enter__(self) -> _Mutex:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc) -> None:
        if self.fd is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


def _claims(repo: Path) -> dict:
    path = shared_dir(repo) / "claims.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_claims(repo: Path, claims: dict) -> None:
    with _Mutex(repo):
        path = shared_dir(repo) / "claims.json"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(claims, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)


def update_claim(repo: Path, task: str, mutate_fn) -> None:
    with _Mutex(repo):
        claims = _claims(repo)
        mutate_fn(claims)
        path = shared_dir(repo) / "claims.json"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(claims, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)


def take_lane_lock(repo: Path, lane: int, task: str) -> None:
    path = shared_dir(repo) / "locks" / f"lane-{lane}.lock"
    if path.is_file():
        info = _read_lock(path)
        if info and pid_alive(info.get("pid", 0)):
            die(
                f"lane {lane} is locked by pid {info.get('pid')} (task "
                f"{info.get('task')}); if that session is gone, run "
                f"wf.sh lane-release {lane}"
            )
    _write_lock(path, {"pid": session_pid(), "task": task, "ts": now_utc()})


def release_lane_lock(repo: Path, lane: int) -> None:
    path = shared_dir(repo) / "locks" / f"lane-{lane}.lock"
    if path.is_file():
        path.unlink()


def release_lane_lock_if_idle(repo: Path, lane: int | None) -> None:
    """Drop a lane lock once no active task is left in that lane (claim re-takes it)."""
    if lane is None or lane < 1:
        return
    try:
        state = load_state(repo)
        eff = effective_tasks(repo, state)
    except WfError:
        return
    for tid, task in eff.items():
        if task.get("claimed_by_lane", task.get("lane")) == lane and (
            task["status"] in ACTIVE_STATUSES or _claims(repo).get(tid, {}).get("lane") == lane
        ):
            return
    release_lane_lock(repo, lane)
    render_progress(repo)


def machine_lock_free(repo: Path) -> str | None:
    """Return a human reason when the machine lock is taken, else None."""
    path = machine_lock_path(repo)
    if not path.is_file():
        return None
    info = _read_lock(path)
    if info is None:
        return f"machine lock {path} exists but is unreadable; wf.sh machine-release"
    return (
        f"machine lock {path} is taken (repo {info.get('repo')}, task "
        f"{info.get('task')}, pid {info.get('pid')}, at {info.get('ts')}); heavy "
        f"work is running or crashed elsewhere. If nothing runs: wf.sh machine-release"
    )


def take_machine_lock(repo: Path, task: str) -> None:
    reason = machine_lock_free(repo)
    if reason:
        die(f"cannot start {task}: {reason}")
    _write_lock(
        machine_lock_path(repo),
        {"pid": session_pid(), "repo": str(repo), "task": task, "ts": now_utc()},
    )


def release_machine_lock(repo: Path, task: str | None = None) -> None:
    path = machine_lock_path(repo)
    if path.is_file():
        info = _read_lock(path)
        if task is not None and info and info.get("task") != task:
            return  # not ours
        path.unlink()


def normalize_paths(paths: list[str]) -> list[str]:
    return [p.strip().strip("/") for p in paths if p.strip()]


def files_overlap(a: set[str], b: set[str]) -> set[str]:
    hits = set()
    for x in a:
        for y in b:
            if x == y or x.startswith(y + "/") or y.startswith(x + "/"):
                hits.add(x if len(x) <= len(y) else y)
    return hits


def check_claim_conflicts(repo: Path, task_id: str, task: dict) -> None:
    """files_write overlap and resource conflicts against every active task."""
    my_files = set(normalize_paths(task.get("files_write", [])))
    for other_id, claim in sorted(_claims(repo).items()):
        if other_id == task_id:
            continue
        other = _task_record_anywhere(repo, other_id)
        if other is None or other["status"] not in ACTIVE_STATUSES:
            continue
        if not pid_alive(claim.get("pid", 0)):
            continue  # orphaned claim; the resume/release path handles it
        overlap = files_overlap(my_files, set(normalize_paths(other.get("files_write", []))))
        if overlap:
            die(
                f"claim refused: {task_id} writes {sorted(overlap)[0]}, which "
                f"overlaps the in-progress task {other_id} (lane "
                f"{claim.get('lane')}, pid {claim.get('pid')})"
            )
        mine, theirs = task.get("resources"), other.get("resources")
        heavy = {"gpu", "exclusive-machine"}
        if (mine in heavy and theirs != "light") or (theirs in heavy and mine != "light"):
            die(
                f"claim refused: {task_id} is '{mine}' and the active task "
                f"{other_id} is '{theirs}' (lane {claim.get('lane')}); only 'light' "
                f"tasks may run beside heavy resources"
            )


# ------------------------------------------------------------- plan parsing


CARD_HEADING_RE = r"^### (T-\d+)\b"


def _card_slice(text: str, tid: str) -> str | None:
    m = re.search(rf"^### {re.escape(tid)}\b.*?(?=^### T-|^## |\Z)", text, re.M | re.S)
    return m.group(0) if m else None


def parse_plan(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        die(f"cannot read plan {path}: {exc}")
    lines = text.splitlines()
    title = ""
    version = ""
    section = ""
    shared_rules: list[str] = []
    assumptions: list[dict] = []
    phases: list[str] = []
    cards: dict[str, dict] = {}
    order: list[str] = []
    current: dict | None = None
    for i, line in enumerate(lines, 1):
        if line.startswith("### "):
            if current is not None:
                _finish_card(current, path, i)
            heading = line[4:].strip()
            m = re.match(r"^(T-\d+)\s*[-—]\s*(.+)$", heading)
            if not m:
                die(f"{path}:{i}: task heading must be '### T-NNN — title', got {heading!r}")
            current = _new_card(m.group(1), m.group(2))
            if current["id"] in cards:
                die(f"{path}:{i}: duplicate card id {current['id']}")
            cards[current["id"]] = current
            order.append(current["id"])
            section = "task cards"
            continue
        if line.startswith("## "):
            if current is not None:
                _finish_card(current, path, i)
                current = None
            section = line[3:].strip().lower()
            continue
        if current is not None:
            _card_line(current, line, path, i)
            continue
        if section == "shared rules" and line.strip():
            shared_rules.append(line)
        elif section == "assumption register":
            m = re.match(r"^\s*-\s*(A-?\d+):\s*(.+?)\s*(?:—|--)\s*checked by\s*(T-\d+)\s*$", line)
            if m:
                assumptions.append({"id": m.group(1), "text": m.group(2), "task": m.group(3)})
            elif line.strip() and not line.startswith("#"):
                die(
                    f"{path}:{i}: assumption lines must be "
                    f"'- A-N: text — checked by T-NNN', got {line.strip()!r}"
                )
        elif section == "phases":
            m = re.match(r"^\s*-\s*(P-?\d+)\s*:\s*(.+)$", line)
            if m:
                phases.append(m.group(1))
        elif not section and not title and line.startswith("# "):
            title = line[2:].strip()
        elif not section and line.startswith("*Version"):
            version = line.strip()
    if current is not None:
        _finish_card(current, path, len(lines))
    return {
        "title": title,
        "version": version,
        "shared_rules": "\n".join(shared_rules).strip(),
        "assumptions": assumptions,
        "phases": phases,
        "cards": cards,
        "order": order,
    }


def _new_card(tid: str, title: str) -> dict:
    return {
        "id": tid,
        "title": title,
        "steps": [],
        "preconditions": [],
        "acceptance": [],
        "decision_rights": {},
        "depends_on": [],
        "files_read": [],
        "files_write": [],
        "gates": [],
        "evidence": [],
        "lane_reason": "",
    }


def _card_line(card: dict, line: str, path: Path, lineno: int) -> None:
    if not line.strip():
        return
    stripped = line.strip()
    m = re.match(r"^([a-z_]+):\s*(.*)$", line)
    if m and not line.startswith((" ", "-")):
        key, value = m.group(1), m.group(2).strip()
        if key in ("steps", "preconditions", "acceptance", "decision_rights"):
            if value:
                die(f"{path}:{lineno}: '{key}:' starts a list; put items on next lines")
            card["_in_list"] = key
            return
        if key in CARD_FIELDS_LIST:
            if value.lower() == "none":
                value = ""
            card[key] = [v.strip() for v in value.split(",") if v.strip()]
        elif key == "lane":
            try:
                card[key] = int(value)
            except ValueError:
                die(f"{path}:{lineno}: lane must be a number, got {value!r}")
        else:
            card[key] = value
        return
    if stripped.startswith("- "):
        item = stripped[2:]
        where = card.get("_in_list")
        if where == "steps":
            marker = STEP_MARKER_RE.search(item)
            if not marker:
                die(
                    f"{path}:{lineno}: every step must end with '(redo-safe)' or "
                    f"'(not redo-safe)': {item!r}"
                )
            text = STEP_MARKER_RE.sub("", item).strip()
            text = re.sub(r"^S\d+:\s*", "", text)
            card["steps"].append(
                {
                    "id": f"S{len(card['steps']) + 1}",
                    "text": text,
                    "redo_safe": marker.group(1) == "redo-safe",
                }
            )
        elif where in ("preconditions", "acceptance"):
            entry = _parse_check_item(item, path, lineno)
            card[where].append(entry)
            card["_last_item"] = entry
        elif where == "decision_rights":
            dm = re.match(r"^(may|must_escalate):\s*(.*)$", item)
            if not dm:
                die(
                    f"{path}:{lineno}: decision_rights items must be 'may: ...' or "
                    f"'must_escalate: ...', got {item!r}"
                )
            card["decision_rights"][dm.group(1)] = dm.group(2)
        else:
            die(f"{path}:{lineno}: list item outside a list field: {item!r}")
        return
    cm = re.match(r"^(cmd|expect|value|id|heavy):\s*(.*)$", stripped)
    if cm and card.get("_last_item") is not None:
        item = card["_last_item"]
        key, value = cm.group(1), cm.group(2).strip()
        if key == "heavy":
            item["heavy"] = value.lower() in ("true", "yes", "1")
        elif key == "id":
            item["id"] = value
        elif key == "expect":
            em = re.match(r"^(exit_code|stdout_regex|file_exists|json_eq|manual)\b\s*(.*)$", value)
            if em:
                item["expect"] = em.group(1)
                rest = em.group(2).strip()
                if em.group(1) == "manual":
                    item["description"] = rest.strip('"')
                else:
                    item["args"] = rest
            else:
                item["expect"] = value
        else:
            item[key] = value
        return
    if stripped and not line.startswith(" "):
        die(f"{path}:{lineno}: unrecognized card line: {line!r}")


def _parse_check_item(item: str, path: Path, lineno: int) -> dict:
    m = re.match(r"^(cmd|expect):\s*(.*)$", item)
    if not m:
        die(f"{path}:{lineno}: check items must start with 'cmd:' or 'expect:', got {item!r}")
    kind, rest = m.group(1), m.group(2).strip()
    entry: dict = {"id": "", "heavy": False}
    if kind == "cmd":
        entry["cmd"] = rest
        return entry
    em = re.match(r"^(exit_code|stdout_regex|file_exists|json_eq|manual)\b\s*(.*)$", rest)
    if not em:
        die(f"{path}:{lineno}: expect type must be one of {', '.join(EXPECT_TYPES)}, got {rest!r}")
    entry["expect"] = em.group(1)
    args = em.group(2).strip()
    if entry["expect"] == "manual":
        entry["description"] = args.strip('"')
    else:
        entry["args"] = args
    return entry


def _finish_card(card: dict, path: Path, lineno: int) -> None:
    card.pop("_in_list", None)
    card.pop("_last_item", None)
    missing = [f for f in CARD_FIELDS_REQUIRED if f not in card]
    missing += [
        f
        for f in ("title", "phase", "resources", "review", "estimate")
        if f in card and not card[f]
    ]
    if missing:
        die(f"{path}:{lineno}: card {card['id']} is missing fields: {', '.join(missing)}")
    empty = [
        f
        for f in CARD_FIELDS_NONEMPTY
        if not card.get(f) or (f == "decision_rights" and "may" not in card[f])
    ]
    if empty:
        die(f"{path}:{lineno}: card {card['id']}: empty required list(s): {', '.join(empty)}")
    if card["resources"] not in RESOURCES:
        die(
            f"{path}:{lineno}: card {card['id']}: resources must be one of "
            f"{', '.join(RESOURCES)}, got {card['resources']!r}"
        )
    if card["review"] not in REVIEW_POLICIES:
        die(
            f"{path}:{lineno}: card {card['id']}: review must be one of "
            f"{', '.join(REVIEW_POLICIES)}, got {card['review']!r}"
        )
    if card["lane"] > 1 and not card.get("lane_reason"):
        die(
            f"{path}:{lineno}: card {card['id']}: lane {card['lane']} requires a "
            f"lane_reason (why parallel work saves more than about "
            f"{DEFAULT_CONFIG['workflow']['parallel_value_threshold_min']} minutes)"
        )
    for item in card["preconditions"] + card["acceptance"]:
        if item.get("cmd") and not item.get("expect"):
            die(
                f"{path}:{lineno}: card {card['id']}: a cmd item needs an indented 'expect: …' line"
            )
        if not item.get("cmd") and not item.get("expect"):
            die(f"{path}:{lineno}: card {card['id']}: check item needs cmd or expect")


def validate_plan(plan: dict, path: Path) -> list[str]:
    """Cross-card checks. Returns warnings; dies on hard errors."""
    warnings: list[str] = []
    cards = plan["cards"]
    for assumption in plan["assumptions"]:
        if assumption["task"] not in cards:
            die(
                f"{path}: assumption {assumption['id']} references unknown task "
                f"{assumption['task']}"
            )
    if not plan["shared_rules"]:
        die(f"{path}: a '## Shared rules' section with content is required")
    if not plan["assumptions"]:
        die(f"{path}: an '## Assumption register' with at least one entry is required")
    if not plan["phases"]:
        die(f"{path}: a '## Phases' section is required")
    for tid, card in cards.items():
        for dep in card["depends_on"]:
            if dep not in cards:
                die(f"{path}: card {tid} depends on unknown task {dep}")
        if card["phase"] not in plan["phases"]:
            die(
                f"{path}: card {tid} uses phase {card['phase']}, which is not "
                f"declared in '## Phases'"
            )
    colour: dict[str, int] = {tid: 0 for tid in cards}

    def visit(tid: str) -> None:
        if colour[tid] == 1:
            die(f"{path}: dependency cycle through {tid}")
        if colour[tid] == 2:
            return
        colour[tid] = 1
        for dep in cards[tid]["depends_on"]:
            visit(dep)
        colour[tid] = 2

    for tid in plan["order"]:
        visit(tid)
    for tid, card in cards.items():
        manual = [i for i in card["acceptance"] if i.get("expect") == "manual"]
        mechanical = [i for i in card["acceptance"] if i.get("expect") != "manual"]
        if card["review"] != "none" and len(manual) > len(mechanical):
            warnings.append(
                f"card {tid} requires review but its acceptance is mostly manual "
                f"({len(manual)} manual vs {len(mechanical)} machine-checkable); "
                f"the same model executes and reviews, so add machine-checkable "
                f"expectations where possible"
            )
    return warnings


# ------------------------------------------------------------------- import


def cmd_plan_import(repo: Path, args: argparse.Namespace) -> None:
    path = Path(args.plan)
    if not path.is_absolute():
        path = repo / path
    plan = parse_plan(path)
    warnings = validate_plan(plan, path)
    existing = state_path(repo).is_file()
    amend = args.amend
    if existing:
        state = load_state(repo)
        eff = effective_tasks(repo, state)
        active = [t for t, rec in eff.items() if rec["status"] in ACTIVE_STATUSES]
        if active and not amend:
            die(
                f"refusing to import over in-progress work ({', '.join(active)}); "
                f"re-issue with --amend if this is a re-issued plan"
            )
        if amend:
            _amend_state(repo, state, plan, path)
        else:
            die("state already exists; use --amend to re-issue a plan")
    else:
        state = _fresh_state(plan, path)
        recompute_ready(state, repo, None)
        save_json(state_path(repo), state)
        _ensure_gitignore(repo)
        render_progress(repo)
    print(f"plan imported: {len(plan['cards'])} cards, sha256 {state['plan_sha256'][:12]}…")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def _fresh_state(plan: dict, path: Path) -> dict:
    tasks = {}
    for tid in plan["order"]:
        card = plan["cards"][tid]
        tasks[tid] = {
            "title": card["title"],
            "phase": card["phase"],
            "lane": card["lane"],
            "depends_on": card["depends_on"],
            "resources": card["resources"],
            "files_write": card.get("files_write", []),
            "review": card["review"],
            "status": "todo",
            "source": "plan",
            "card_sha256": _card_hash(card),
        }
    state = {
        "version": 1,
        "kit_version": KIT_VERSION,
        "plan_file": Path(path).name,
        "plan_sha256": plan_file_hash(Path(path)),
        "phases": plan["phases"],
        "title": plan["title"],
        "created_utc": now_utc(),
        "tasks": tasks,
        "events": [],
        "escalations": {},
        "review_cycles": {},
        "review_dispositions": {},
    }
    append_event(state, "plan-imported", None, f"{len(tasks)} cards")
    return state


def _card_hash(card: dict) -> str:
    body = {k: v for k, v in card.items() if not k.startswith("_")}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _amend_state(repo: Path, state: dict, plan: dict, path: Path) -> None:
    new_hash = plan_file_hash(Path(path))
    if new_hash == state.get("plan_sha256"):
        die("plan unchanged; nothing to amend")
    old_tasks = state.get("tasks", {})
    for tid in plan["order"]:
        card = plan["cards"][tid]
        new_card_hash = _card_hash(card)
        old = old_tasks.get(tid)
        if old is None:
            state["tasks"][tid] = _task_from_card(card, new_card_hash)
            append_event(state, "plan-added", tid, "new card in amended plan")
        elif old.get("card_sha256") == new_card_hash:
            continue  # unchanged card: keep its status
        else:
            if old["status"] in ACTIVE_STATUSES + ("in-review", "changes-requested"):
                die(
                    f"amend refused: card {tid} changed while it is "
                    f"{old['status']}; finish or cancel it before re-issuing"
                )
            state["tasks"][tid] = {
                **_task_from_card(card, new_card_hash),
                "status": "todo",
                "plan_changed": True,
            }
            append_event(state, "plan-changed", tid, "card changed; re-acknowledgement required")
    for tid in [t for t in old_tasks if t not in plan["cards"]]:
        if old_tasks[tid]["status"] not in TERMINAL_STATUSES:
            append_event(state, "plan-removed", tid, "card no longer in plan")
        del state["tasks"][tid]
    state["plan_sha256"] = new_hash
    state["phases"] = plan["phases"]
    append_event(state, "plan-amended", None, f"sha256 {new_hash[:12]}…")
    recompute_ready(state, repo, None)
    save_json(state_path(repo), state)
    _ensure_gitignore(repo)
    render_progress(repo)


def _task_from_card(card: dict, card_hash: str) -> dict:
    return {
        "title": card["title"],
        "phase": card["phase"],
        "lane": card["lane"],
        "depends_on": card["depends_on"],
        "resources": card["resources"],
        "files_write": card.get("files_write", []),
        "review": card["review"],
        "status": "todo",
        "source": "plan",
        "card_sha256": card_hash,
    }


def _ensure_gitignore(repo: Path) -> None:
    gi = repo / ".gitignore"
    current = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    if ".workflow/worktrees" not in current:
        with open(gi, "a", encoding="utf-8") as fh:
            if current and not current.endswith("\n"):
                fh.write("\n")
            fh.write("# workflow-kit lane worktrees\n.workflow/worktrees/\n")


# ---------------------------------------------------------------------- card


def cmd_card(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    state = load_state(repo)
    eff = effective_tasks(repo, state)
    if tid not in eff:
        die(f"unknown task {tid}")
    task = eff[tid]
    source = repo / (PLAN_ADDED_NAME if task.get("source") == "added" else "PLAN.md")
    if not source.is_file():
        die(f"card source file {source} is missing")
    text = source.read_text(encoding="utf-8")
    card_text = _card_slice(text, tid)
    if card_text is None:
        die(f"card {tid} not found in {source}")
    plan = parse_plan(repo / "PLAN.md") if (repo / "PLAN.md").is_file() else {}
    print("# Shared rules (frozen with the plan)\n")
    print(plan.get("shared_rules", "(none)"))
    print(f"\n---\n\n# Card {tid}\n")
    print(card_text.strip())
    print(f"\n---\nstatus: {task['status']}  lane: {task['lane']}  review: {task['review']}")


# ------------------------------------------------------------ status / ready


def cmd_status(repo: Path, args: argparse.Namespace) -> None:
    state = load_state(repo)
    eff = effective_tasks(repo, state)
    print(f"plan: {state.get('title', '')} ({state.get('plan_file', 'PLAN.md')})")
    print(f"phase: {current_phase(state, eff) or '-'}")
    for tid in sorted(eff):
        task = eff[tid]
        print(f"{tid}  {task['status']:<18} lane {task['lane']}  {task['title']}")
    blocked = sorted(t for t, r in eff.items() if r["status"] == "blocked-decision")
    if blocked:
        print(f"\nblocked-decision (escalations): {', '.join(blocked)}")
    ready = sorted(t for t, r in eff.items() if r["status"] == "ready")
    if ready:
        print(f"READY: {', '.join(ready)}")


def current_phase(state: dict, eff: dict[str, dict]) -> str | None:
    for tid in state.get("tasks", {}):
        task = eff.get(tid, {})
        status = task.get("status")
        complete = status in ("accepted", "superseded", "cancelled") or (
            status == "done" and task.get("review") == "none"
        )
        if not complete:
            return task.get("phase")
    return None


def cmd_ready(repo: Path, args: argparse.Namespace) -> None:
    state = load_state(repo)
    eff = effective_tasks(repo, state)
    by_lane: dict[int, list[str]] = {}
    for tid, task in eff.items():
        if task["status"] == "ready":
            by_lane.setdefault(task["lane"], []).append(tid)
    if not by_lane:
        print("no ready tasks")
        return
    for lane in sorted(by_lane):
        for tid in sorted(by_lane[lane]):
            print(f"lane {lane}  {tid}  {eff[tid]['title']}")
            reason = _lane_reason_line(repo, tid)
            if reason:
                print(f"    lane reason: {reason}")


def _lane_reason_line(repo: Path, tid: str) -> str:
    for name in ("PLAN.md", PLAN_ADDED_NAME):
        path = repo / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        card = _card_slice(text, tid)
        if card:
            m = re.search(r"^lane_reason:\s*(.+)$", card, re.M)
            if m:
                return m.group(1).strip()
    return ""


# -------------------------------------------------------------- claim / runs


def cmd_claim(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    state = load_state(repo)
    eff = effective_tasks(repo, state)
    if tid not in eff:
        die(f"unknown task {tid}")
    task = eff[tid]
    if task["status"] not in ("ready",):
        die(f"task {tid} is {task['status']}, not ready")
    lane = args.lane if args.lane is not None else task["lane"]
    if lane != task["lane"]:
        die(
            f"task {tid} is planned for lane {task['lane']}; claiming it into lane "
            f"{lane} is not allowed (the plan fixes the lane)"
        )
    check_claim_conflicts(repo, tid, task)
    if task["resources"] != "light":
        reason = machine_lock_free(repo)
        if reason:
            die(f"claim refused: {reason}")
    take_lane_lock(repo, lane, tid)
    update_claim(
        repo,
        tid,
        lambda claims: claims.update(
            {
                tid: {
                    "lane": lane,
                    "pid": session_pid(),
                    "ts": now_utc(),
                    "resources": task["resources"],
                }
            }
        ),
    )
    if lane == 1:
        mutate(
            repo,
            tid,
            "claimed",
            {"claimed_by_lane": 1, "steps_done": []},
            event="claimed",
            detail=f"lane 1, pid {session_pid()}",
        )
    else:
        worktree = ensure_lane_worktree(repo, lane)
        owner = load_or_init_lane(repo, lane)
        record = dict(task)
        record.update(
            {
                "status": "claimed",
                "claimed_by_lane": lane,
                "steps_done": [],
                "source": task.get("source", "plan"),
            }
        )
        owner.setdefault("tasks", {})[tid] = record
        append_event(owner, "claimed", tid, f"lane {lane}, pid {session_pid()}")
        save_owner(repo, owner, lane)
        # the main state keeps only a 'todo' placeholder; the lane file is authoritative
        if tid in state.get("tasks", {}):
            main_rec = state["tasks"][tid]
            if main_rec["status"] in ("ready", "todo"):
                main_rec["status"] = "todo"
                append_event(state, "migrated-to-lane", tid, f"lane {lane}")
                save_json(state_path(repo), state)
                render_progress(repo)
        print(f"claimed {tid} (lane {lane}); worktree: {worktree}")
        print(f"next: wf.sh start {tid}   (file work happens inside {worktree})")
        return
    print(f"claimed {tid} (lane 1); next: wf.sh start {tid}")


def ensure_lane_worktree(repo: Path, lane: int) -> Path:
    """Lanes 2+ work in their own worktree + branch (created from main HEAD)."""
    if lane == 1:
        return repo
    worktree = worktree_for_lane(repo, lane)
    if worktree.is_dir():
        return worktree
    branch = f"lane-{lane}"
    branches = _git(repo, "branch", "--format=%(refname:short)").splitlines()
    if branch in branches:
        _git(repo, "worktree", "add", str(worktree), branch)
    else:
        _git(repo, "worktree", "add", "-b", branch, str(worktree))
    return worktree


def cmd_start(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    eff = effective_tasks(repo, load_state(repo))
    if tid not in eff:
        die(f"unknown task {tid}")
    task = eff[tid]
    claim = _claims(repo).get(tid)
    if claim and claim.get("pid") and not pid_alive(claim["pid"]):
        die(
            f"task {tid} looks orphaned (claim pid {claim['pid']} is gone); run "
            f"wf.sh resume {tid} instead of start"
        )
    if task["resources"] != "light":
        take_machine_lock(repo, tid)
    lane = task.get("claimed_by_lane", task["lane"])
    if lane > 1:
        worktree = ensure_lane_worktree(repo, lane)
        print(f"lane {lane} worktree: {worktree} (all file work and commits go there)")
    mutate(repo, tid, "in-progress", event="started", detail=f"lane {lane}")
    steps = card_steps(repo, tid)
    print(f"started {tid} (in-progress, lane {lane})")
    if steps:
        print(f"first step: {steps[0]['id']} — {steps[0]['text']}")


def card_steps(repo: Path, tid: str) -> list[dict]:
    card = card_of_task(repo, tid)
    return card.get("steps", []) if card else []


def card_of_task(repo: Path, tid: str) -> dict | None:
    task = _task_record_anywhere(repo, tid) or {}
    for name in (
        ("PLAN.md", PLAN_ADDED_NAME)
        if task.get("source") != "added"
        else (
            PLAN_ADDED_NAME,
            "PLAN.md",
        )
    ):
        path = repo / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _card_slice(text, tid):
            plan = parse_plan(path)
            if tid in plan["cards"]:
                return plan["cards"][tid]
    return None


def work_dir_for_task(repo: Path, tid: str) -> Path:
    """Where a task's commands run: its lane worktree for lanes 2+, else the repo."""
    task = _task_record_anywhere(repo, tid) or {}
    lane = task.get("claimed_by_lane", task.get("lane", 1))
    if lane and lane > 1:
        worktree = worktree_for_lane(repo, lane)
        if worktree.is_dir():
            return worktree
    return repo


def cmd_resume(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    eff = effective_tasks(repo, load_state(repo))
    if tid not in eff:
        die(f"unknown task {tid}")
    task = eff[tid]
    if task["status"] not in ACTIVE_STATUSES:
        die(f"task {tid} is {task['status']}; only active tasks can be resumed")
    claim = _claims(repo).get(tid, {})
    if claim.get("pid") and pid_alive(claim["pid"]) and claim["pid"] != session_pid():
        die(f"task {tid} is still owned by a live session (pid {claim['pid']}); resume refused")
    steps = card_steps(repo, tid)
    done = set(task.get("steps_done") or [])
    pending = [s for s in steps if s["id"] not in done]
    if not pending:
        die(f"task {tid} has no incomplete steps; run the acceptance and wf.sh done")
    first = pending[0]
    if not first["redo_safe"] and not args.confirm:
        die(
            f"step {first['id']} is NOT redo-safe and may already have run; confirm "
            f"it must be repeated with: wf.sh resume {tid} --confirm"
        )
    if task["resources"] != "light":
        take_machine_lock(repo, tid)
    update_claim(
        repo,
        tid,
        lambda claims: claims.update(
            {
                tid: {
                    "lane": task.get("claimed_by_lane", task["lane"]),
                    "pid": session_pid(),
                    "ts": now_utc(),
                    "resources": task["resources"],
                }
            }
        ),
    )
    mutate(repo, tid, "in-progress", event="resumed", detail=f"from {first['id']}")
    print(f"resumed {tid} at {first['id']}: {first['text']}")
    print(f"steps done: {', '.join(sorted(done)) if done else 'none'}")


def cmd_step_done(repo: Path, args: argparse.Namespace) -> None:
    tid, step = args.task, args.step
    task = _task_record_anywhere(repo, tid)
    if task is None or task["status"] not in ACTIVE_STATUSES:
        current = task["status"] if task else "unknown"
        die(f"task {tid} is {current}; steps are recorded only for active tasks")
    steps = {s["id"] for s in card_steps(repo, tid)}
    if not steps:
        die(f"no steps found for {tid}")
    if step not in steps:
        die(f"task {tid} has no step {step} (steps: {', '.join(sorted(steps))})")
    _, _, task = find_task(repo, tid)
    done = list(task.get("steps_done") or [])
    if step in done:
        print(f"{step} already recorded")
        return
    done.append(step)
    remaining = [s["id"] for s in card_steps(repo, tid) if s["id"] not in done]
    mutate(
        repo,
        tid,
        extra={"steps_done": done},
        event="step-done",
        detail=step + (f": {args.note}" if args.note else ""),
    )
    print(f"{tid} {step} recorded; next: {remaining[0] if remaining else 'acceptance'}")


def cmd_gate_wait(repo: Path, args: argparse.Namespace) -> None:
    mutate(
        repo,
        args.task,
        "awaiting-gate",
        {"gate_message": args.message},
        event="gate-wait",
        detail=args.message,
    )
    print(f"{args.task} is awaiting-gate. Zack must do: {args.message}")
    print(f"then: wf.sh gate-release {args.task}")


def cmd_gate_release(repo: Path, args: argparse.Namespace) -> None:
    mutate(repo, args.task, "in-progress", event="gate-release", detail="Zack said go")
    print(f"{args.task} gate released; continue with the next step")


# ------------------------------------------------------------- preconditions


def run_check(workdir: Path, item: dict) -> dict:
    cmd = item["cmd"]
    expect = item.get("expect", "")
    args = item.get("args", "")
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=workdir, capture_output=True, text=True, timeout=900
        )
        stdout, code = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return {"verdict": "fail", "cmd": cmd, "reason": "timeout after 900 s"}
    elapsed = round(time.monotonic() - started, 1)
    entry = {
        "cmd": cmd,
        "exit_code": code,
        "output_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
        "output_bytes": len(stdout),
        "elapsed_s": elapsed,
    }
    if expect == "exit_code":
        try:
            wanted = int(args)
        except ValueError:
            return {**entry, "verdict": "fail", "reason": f"bad exit_code arg {args!r}"}
        entry["verdict"] = "pass" if code == wanted else "fail"
        if entry["verdict"] == "fail":
            entry["reason"] = f"exit code {code}, wanted {wanted}"
    elif expect == "stdout_regex":
        entry["verdict"] = "pass" if re.search(args, stdout) else "fail"
        if entry["verdict"] == "fail":
            entry["reason"] = f"no match for /{args}/"
    else:
        entry["verdict"] = "fail"
        entry["reason"] = f"unknown expectation {expect!r} for a cmd item"
    return entry


def check_file_exists(workdir: Path, item: dict) -> dict:
    path = workdir / item["args"].strip()
    if path.is_file() and path.stat().st_size > 0:
        return {
            "verdict": "pass",
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {"verdict": "fail", "path": str(path), "reason": "missing or empty"}


def check_json_eq(workdir: Path, item: dict) -> dict:
    parts = item["args"].split()
    if len(parts) < 2:
        return {"verdict": "fail", "reason": "json_eq needs <file> <path> <value>"}
    file_arg, dotted = parts[0], parts[1]
    value = " ".join(parts[2:])
    path = workdir / file_arg
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"verdict": "fail", "reason": f"cannot read {path}: {exc}"}
    node = data
    for key in dotted.split("."):
        if isinstance(node, list):
            try:
                node = node[int(key)]
            except (ValueError, IndexError):
                return {"verdict": "fail", "reason": f"bad index {key} in {dotted}"}
        elif isinstance(node, dict):
            if key not in node:
                return {"verdict": "fail", "reason": f"no key {key} in {dotted}"}
            node = node[key]
        else:
            return {"verdict": "fail", "reason": f"cannot descend into {key}"}
    try:
        wanted = json.loads(value)
    except ValueError:
        wanted = value.strip('"')
    if node == wanted or str(node) == str(wanted):
        return {"verdict": "pass", "path": dotted, "value": node}
    return {"verdict": "fail", "path": dotted, "reason": f"{node!r} != {wanted!r}"}


def evaluate_item(workdir: Path, item: dict, defer_heavy: bool) -> dict:
    if item.get("heavy") and defer_heavy:
        return {"verdict": "deferred", "reason": "marked heavy; reviewer decides"}
    if item.get("expect") == "manual":
        return {"verdict": "judgement", "description": item.get("description", "")}
    if item.get("cmd"):
        return run_check(workdir, item)
    if item.get("expect") == "file_exists":
        return check_file_exists(workdir, item)
    if item.get("expect") == "json_eq":
        return check_json_eq(workdir, item)
    return {"verdict": "fail", "reason": "unparsable check item"}


def cmd_precheck(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    card = card_of_task(repo, tid)
    if card is None:
        die(f"card {tid} not found")
    workdir = work_dir_for_task(repo, tid)
    items = card["preconditions"]
    if not items:
        print(f"{tid}: no preconditions declared")
        return
    failures = 0
    for index, item in enumerate(items):
        item_id = item.get("id") or f"P{index + 1}"
        entry = evaluate_item(workdir, item, defer_heavy=True)
        print(
            f"{item_id} {entry['verdict'].upper():<10} "
            f"{entry.get('reason', entry.get('description', ''))}"
        )
        if entry["verdict"] == "fail":
            failures += 1
    if failures:
        die(f"{tid}: {failures} precondition(s) FAILED — STOP and report, never work around")
    print(f"{tid}: all preconditions pass")


# ------------------------------------------------------------------- accept


def cmd_accept(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    card = card_of_task(repo, tid)
    if card is None:
        die(f"card {tid} not found")
    workdir = work_dir_for_task(repo, tid)
    record = {
        "task": tid,
        "started_utc": now_utc(),
        "git_commit": git_head(workdir),
        "items": [],
    }
    failures = 0
    for index, item in enumerate(card["acceptance"]):
        item_id = item.get("id") or f"A{index + 1}"
        entry = evaluate_item(workdir, item, defer_heavy=True)
        entry = {"id": item_id, **entry}
        record["items"].append(entry)
        if entry["verdict"] == "fail":
            failures += 1
    record["evidence_files"] = {}
    for ev in card.get("evidence", []):
        path = workdir / ev
        entry = {"exists": path.is_file()}
        if entry["exists"]:
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            entry["bytes"] = path.stat().st_size
        record["evidence_files"][ev] = entry
        if not entry["exists"]:
            failures += 1
    record["finished_utc"] = now_utc()
    record["failures"] = failures
    out = workdir / ".workflow" / "acceptance" / f"{tid}.json"
    runs = []
    if out.is_file():
        try:
            runs = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            runs = []
    runs.append(record)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(runs, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, out)
    for entry in record["items"]:
        print(
            f"{entry['id']:>6} {entry['verdict'].upper():<10} "
            f"{entry.get('reason', entry.get('description', ''))}"
        )
    for ev, entry in record["evidence_files"].items():
        print(
            f"      evidence {ev}: {'ok' if entry['exists'] else 'MISSING'} "
            f"({entry.get('sha256', '')[:12]})"
        )
    print(f"record: {out} (run {len(runs)}), failures: {failures}")


def git_head(repo: Path) -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    return proc.stdout.strip() or "(no commits)"


def latest_accept_record(repo: Path, tid: str) -> dict | None:
    for base in (work_dir_for_task(repo, tid), repo):
        path = base / ".workflow" / "acceptance" / f"{tid}.json"
        if not path.is_file():
            continue
        try:
            runs = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if runs:
            return runs[-1]
    return None


def cmd_done(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    eff = effective_tasks(repo, load_state(repo))
    if tid not in eff:
        die(f"unknown task {tid}")
    if eff[tid]["status"] not in ("in-progress", "awaiting-gate"):
        die(f"task {tid} is {eff[tid]['status']}; done needs in-progress")
    record = latest_accept_record(repo, tid)
    if record is None:
        die(
            f"task {tid} has no acceptance record; run wf.sh accept {tid} first "
            f"(evidence is required before done)"
        )
    for entry in record.get("items", []):
        if entry["verdict"] == "fail":
            die(
                f"task {tid} acceptance item {entry['id']} FAILED: "
                f"{entry.get('reason', '')}; fix and re-run wf.sh accept {tid}"
            )
    card = card_of_task(repo, tid)
    for ev in card.get("evidence", []):
        entry = record.get("evidence_files", {}).get(ev)
        if not entry or not entry.get("exists"):
            die(f"task {tid} evidence file {ev} is missing or empty")
    update_claim(repo, tid, lambda claims: claims.pop(tid, None))
    release_machine_lock(repo, tid)
    mutate(
        repo,
        tid,
        "done",
        event="done",
        detail=f"accept run at {record['started_utc']}",
    )
    manual = [e["id"] for e in record.get("items", []) if e["verdict"] == "judgement"]
    review_line = (
        "review: required, run /review in a fresh session"
        if card["review"] != "none"
        else "review: none"
    )
    suffix = " | next ready: (run wf.sh ready)"  # commands replace this
    print(
        f"TASK {tid} DONE | {review_line} | judgement items: "
        f"{', '.join(manual) if manual else 'none'}{suffix}"
    )


# -------------------------------------------------------------------- review


def review_cycles(repo: Path, tid: str) -> int:
    return int(load_state(repo).get("review_cycles", {}).get(tid, 0))


def set_review_cycles(repo: Path, tid: str, cycles: int) -> None:
    state = load_state(repo)
    state.setdefault("review_cycles", {})[tid] = cycles
    save_json(state_path(repo), state)
    render_progress(repo)


def cmd_review_open(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    eff = effective_tasks(repo, load_state(repo))
    if tid not in eff:
        die(f"unknown task {tid}")
    if eff[tid]["status"] not in ("done", "changes-requested"):
        die(f"task {tid} is {eff[tid]['status']}; review-open needs done")
    cfg = load_config(repo)
    cycles = review_cycles(repo, tid) + 1
    if cycles > cfg["workflow"]["max_review_cycles"]:
        die(
            f"task {tid} already used {cfg['workflow']['max_review_cycles']} review "
            f"cycles; escalate with wf-escalate.sh (type review-disagreement)"
        )
    set_review_cycles(repo, tid, cycles)
    mutate(repo, tid, "in-review", event="review-opened", detail=f"cycle {cycles}")
    print(
        f"{tid} in-review (cycle {cycles}); report: REVIEW_REPORT.md + "
        f"reviews/{tid}/r{cycles}-REVIEW_REPORT.md"
    )


def parse_review_report(path: Path) -> tuple[dict, list[dict]]:
    """Parse the report's task-verdict line and findings table rows."""
    text = path.read_text(encoding="utf-8")
    verdict = ""
    m = re.search(r"^## Task verdict\s*\n+\s*(\S+)\s*$", text, re.M)
    if m:
        verdict = m.group(1)
    findings = []
    for line in text.splitlines():
        m = re.match(r"^\|\s*(F-\d+)\s*\|\s*([A-Z]+)\s*\|\s*([A-Z-]+)\s*\|", line)
        if m:
            findings.append({"id": m.group(1), "severity": m.group(2), "action": m.group(3)})
    return {"verdict": verdict}, findings


def cmd_review_verdict(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    verdict = args.verdict
    report = Path(args.report_file)
    if not report.is_absolute():
        report = repo / report
    if not report.is_file():
        die(f"report file {report} does not exist")
    parsed, findings = parse_review_report(report)
    if parsed["verdict"] != verdict:
        die(f"the report's 'Task verdict' says {parsed['verdict']!r} but you passed {verdict!r}")
    cycle = review_cycles(repo, tid)
    archive = repo / "reviews" / tid / f"r{cycle}-REVIEW_REPORT.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(report, archive)
    # T-018: a blocked-decision verdict returns to changes-requested when unblocked
    # (the status /address-review works from); record it so unblock has a target.
    extra = {"blocked_from": "changes-requested"} if verdict == "blocked-decision" else None
    mutate(
        repo,
        tid,
        verdict,
        extra,
        event="review-verdict",
        detail=f"{verdict} (cycle {cycle}, {len(findings)} findings)",
    )
    print(f"{tid} -> {verdict}; archived to {archive}")
    if verdict == "changes-requested":
        print(f"next: /address-review {tid}")


def cmd_review_disposition(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    finding_id = args.finding
    action = args.action
    if not args.reason:
        die("--reason is required for every disposition")
    cycle = review_cycles(repo, tid)
    report = repo / "reviews" / tid / f"r{cycle}-REVIEW_REPORT.md"
    if not report.is_file():
        die(f"no archived review report for {tid} cycle {cycle}")
    _, findings = parse_review_report(report)
    finding = next((f for f in findings if f["id"] == finding_id), None)
    if finding is None:
        known = ", ".join(f["id"] for f in findings) or "none"
        die(f"finding {finding_id} is not in the report (findings: {known})")
    if finding["severity"] == "BLOCKER" and action == "reject":
        die("a BLOCKER finding may not be rejected; only fixed or escalated")
    if finding["action"] in ("RE-MEASURE", "DECIDE") and action != "escalate":
        die(
            f"{finding['action']} findings are never resolved inline; escalate "
            f"(wf-escalate.sh) and, if Zack approves, add a gated task"
        )
    state = load_state(repo)
    dispositions = state.setdefault("review_dispositions", {}).setdefault(tid, [])
    dispositions.append(
        {
            "cycle": cycle,
            "finding": finding_id,
            "severity": finding["severity"],
            "action_taken": action,
            "reason": args.reason,
        }
    )
    save_json(state_path(repo), state)
    render_progress(repo)
    append_event_note(repo, tid, f"disposition {finding_id}: {action}")
    print(f"recorded: {tid} {finding_id} -> {action}")
    if action == "escalate":
        kind = "review-disagreement" if finding["action"] == "DECIDE" else "decision"
        print(f"next: wf-escalate.sh --task {tid} --type {kind}")


def append_event_note(repo: Path, tid: str, note: str) -> None:
    owner, lane, _ = find_task(repo, tid)
    append_event(owner, "note", tid, note)
    save_owner(repo, owner, lane)


# ---------------------------------------------------------- block / escalate


def cmd_block(repo: Path, args: argparse.Namespace) -> None:
    _, _, task = find_task(repo, args.task)
    if task["status"] in TERMINAL_STATUSES:
        die(f"task {args.task} is {task['status']}; cannot block")
    mutate(
        repo,
        args.task,
        "blocked-decision",
        {"blocked_from": task["status"], "blocked_reason": args.reason},
        event="blocked",
        detail=args.reason,
    )
    print(f"{args.task} blocked-decision: {args.reason}")


def cmd_unblock(repo: Path, args: argparse.Namespace) -> None:
    _, _, task = find_task(repo, args.task)
    if task["status"] != "blocked-decision":
        die(f"task {args.task} is {task['status']}, not blocked-decision")
    old = task["status"]
    to = getattr(args, "to", None)
    if to is not None:
        # T-018: explicit target for tasks whose blocked_from is missing or illegal
        if to not in UNBLOCK_TO_TARGETS or to not in TRANSITIONS["blocked-decision"]:
            die(
                f"--to {to} is not a legal unblock target "
                f"(allowed: {', '.join(UNBLOCK_TO_TARGETS)})"
            )
        restore = to
        detail = f"{old} -> {restore}"
    else:
        restore = task.get("blocked_from", "todo")
        if restore not in TRANSITIONS["blocked-decision"]:
            restore = "todo"
        detail = f"restored to {restore}"
    mutate(
        repo,
        args.task,
        restore,
        {"blocked_from": None, "blocked_reason": None},
        event="unblocked",
        detail=detail,
    )
    print(f"{args.task} unblocked -> {restore}")


def cmd_restore_status(repo: Path, args: argparse.Namespace) -> None:
    """T-022: repair a status a kit bug regressed (done -> accepted only), guarded
    by the task's own accepted review-verdict event. Writes the status directly:
    done -> accepted is deliberately outside TRANSITIONS, so no existing
    transition changes."""
    tid = args.task
    if args.to != "accepted":
        die(f"--to {args.to} is not a legal restore target (allowed: accepted)")
    owner, owner_lane, task = find_task(repo, tid)
    foreign_lane = owner_lane is not None and not in_main(repo)
    if foreign_lane and lane_of_worktree(repo) != owner_lane:
        die("this session runs in a worktree; only tasks owned by this lane may be changed here")
    if task["status"] != "done":
        die(f"task {tid} is {task['status']}, not done (restore-status repairs done -> accepted)")
    events = all_events(repo, load_state(repo))
    verdict = next(
        (
            e
            for e in events
            if e.get("event") == "review-verdict"
            and e.get("task") == tid
            and e.get("seq") == args.verdict_seq
            and str(e.get("detail", "")).startswith("accepted")
        ),
        None,
    )
    if verdict is None:
        die(f"no accepted review-verdict event with seq {args.verdict_seq} for {tid}")
    # canonical event order is (ts, seq): merged logs duplicate lane events and
    # lane/main seq spaces collide, so seq alone is not a safe ordering
    vkey = (verdict.get("ts", ""), verdict.get("seq", 0))
    if any(
        e.get("event") == "review-opened"
        and e.get("task") == tid
        and (e.get("ts", ""), e.get("seq", 0)) > vkey
        for e in events
    ):
        die(f"task {tid} has a review-opened later than verdict seq {args.verdict_seq}")
    old = task["status"]
    task["status"] = "accepted"
    detail = f"{old} -> accepted (review-verdict seq {args.verdict_seq})"
    append_event(owner, "status-restored", tid, detail)
    recompute_ready(owner, repo, owner_lane)
    save_owner(repo, owner, owner_lane)
    print(f"{tid} restored: {detail}")


def next_escalation_id(repo: Path) -> str:
    state = load_state(repo)
    ids = [int(k.split("-")[1]) for k in state.get("escalations", {}) if k.startswith("E-")]
    return f"E-{(max(ids) + 1) if ids else 1:03d}"


def read_brief(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    try:
        return Path(source).read_text(encoding="utf-8")
    except OSError as exc:
        die(f"cannot read brief: {exc}")
    return ""


def check_brief_sections(brief: str) -> None:
    missing = [s for s in BRIEF_REQUIRED_SECTIONS if s not in brief]
    if missing:
        die(
            "escalation brief is missing sections: "
            + ", ".join(s.removeprefix("## ") for s in missing)
        )
    if "E-NNN" not in brief:
        die("the brief must carry the placeholder id E-NNN (the script assigns the real id)")


def cmd_escalate(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    if args.type not in ESCALATION_TYPES:
        die(f"escalation type must be one of {', '.join(ESCALATION_TYPES)}")
    if tid:
        task = _task_record_anywhere(repo, tid)
        if task is None:
            die(f"unknown task {tid}")
        if task["status"] in TERMINAL_STATUSES:
            die(f"task {tid} is {task['status']}; cannot escalate")
    brief = read_brief(args.brief_file)
    check_brief_sections(brief)
    eid = next_escalation_id(repo)
    out = repo / "escalations" / f"{eid}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(brief.replace("E-NNN", eid))
    state = load_state(repo)
    state.setdefault("escalations", {})[eid] = {
        "task": tid,
        "type": args.type,
        "status": "open",
        "created_utc": now_utc(),
    }
    save_json(state_path(repo), state)
    render_progress(repo)
    if tid:
        task = _task_record_anywhere(repo, tid)
        blocked_from = task["status"]
        if task["status"] == "blocked-decision":
            # T-018: already blocked — keep the original return status instead of
            # overwriting it with blocked-decision (which can never be restored to)
            blocked_from = task.get("blocked_from")
        mutate(
            repo,
            tid,
            "blocked-decision",
            {
                "blocked_from": blocked_from,
                "blocked_reason": f"escalation {eid}",
            },
            event="escalated",
            detail=f"{eid} ({args.type})",
        )
    print(f"escalation {eid} written to {out}; task {tid or '-'} is blocked-decision")
    print("bring the brief to the planning chat; record the reply with wf-decision.sh")


def cmd_decision(repo: Path, args: argparse.Namespace) -> None:
    eid = args.escalation
    state = load_state(repo)
    info = state.get("escalations", {}).get(eid)
    if info is None:
        known = ", ".join(sorted(state.get("escalations", {}))) or "none"
        die(f"unknown escalation {eid} (known: {known})")
    if info["status"] != "open":
        die(f"escalation {eid} is already {info['status']}")
    reply = read_brief(args.reply_file)
    if not re.search(rf"^DECISION {re.escape(eid)}\b", reply, re.M):
        die(f"the reply must start with a 'DECISION {eid}' line")
    tid = info.get("task")
    task = _task_record_anywhere(repo, tid) if tid and tid != "-" else None
    if task is not None:
        # T-018: work out the unblock target BEFORE writing anything — otherwise a
        # failed unblock leaves docs/decisions.md and a decided escalation behind
        if task["status"] != "blocked-decision":
            die(
                f"task {tid} is {task['status']}, not blocked-decision; cannot "
                f"unblock — decision {eid} not recorded"
            )
        restore = task.get("blocked_from", "todo")
        if restore not in TRANSITIONS["blocked-decision"]:
            die(
                f"task {tid} has no legal unblock target (blocked_from="
                f"{task.get('blocked_from')!r}); run wf.sh unblock {tid} --to STATUS "
                f"first — decision {eid} not recorded"
            )
    decisions = repo / "docs" / "decisions.md"
    decisions.parent.mkdir(parents=True, exist_ok=True)
    with open(decisions, "a", encoding="utf-8") as fh:
        fh.write(f"\n---\n\n## DECISION {eid} ({now_utc()})\n\n{reply.strip()}\n")
    state["escalations"][eid]["status"] = "decided"
    state["escalations"][eid]["decided_utc"] = now_utc()
    save_json(state_path(repo), state)
    if task is not None:
        cmd_unblock(repo, argparse.Namespace(task=tid))
    append_event_note(repo, tid or "-", f"decision {eid} recorded")
    print(f"decision {eid} recorded in {decisions}; task {tid or '-'} unblocked")


# ------------------------------------------------------------ add / supersede


def cmd_add_task(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    source = Path(args.file)
    if not source.is_absolute():
        source = repo / source
    if not source.is_file():
        die(f"card file {source} does not exist")
    text = source.read_text(encoding="utf-8")
    if _card_slice(text, tid) is None:
        die(f"card {tid} not found in {source}")
    plan = parse_plan(source)
    card = plan["cards"][tid]
    state = load_state(repo)
    eff = effective_tasks(repo, state)
    if tid in eff:
        die(f"task id {tid} already exists")
    for dep in card["depends_on"]:
        if dep not in eff:
            die(f"card {tid} depends on unknown task {dep}")
    if card["phase"] not in state.get("phases", []) + ["P-9"]:
        die(
            f"card {tid} uses phase {card['phase']}, not declared in the plan "
            f"({', '.join(state.get('phases', []))})"
        )
    record = _task_from_card(card, _card_hash(card))
    record["source"] = "added"
    record["added_reason"] = args.reason
    if in_main(repo):
        owner, owner_lane = state, None
    else:
        lane = lane_of_worktree(repo)
        if lane is None:
            die("a worktree session may only add tasks to its own lane file")
        owner, owner_lane = load_or_init_lane(repo, lane), lane
    owner.setdefault("tasks", {})[tid] = record
    append_event(owner, "task-added", tid, f"from {source.name}: {args.reason or ''}")
    recompute_ready(owner, repo, owner_lane)
    save_owner(repo, owner, owner_lane)
    print(f"added {tid} (status {record['status']}); card source {source.name}")
    print(f"I added task {tid}; run /continue")


def cmd_supersede(repo: Path, args: argparse.Namespace) -> None:
    tid = args.task
    eff = effective_tasks(repo, load_state(repo))
    if tid not in eff:
        die(f"unknown task {tid}")
    if eff[tid]["status"] == "accepted":
        die(f"task {tid} is accepted; accepted work is never superseded")
    update_claim(repo, tid, lambda claims: claims.pop(tid, None))
    release_machine_lock(repo, tid)
    mutate(
        repo,
        tid,
        "superseded",
        {"superseded_by": args.by},
        event="superseded",
        detail=f"by {args.by or 'nothing'}" + (f": {args.reason}" if args.reason else ""),
    )
    print(f"{tid} superseded" + (f" by {args.by}" if args.by else ""))


# --------------------------------------------------------------------- lanes


def cmd_lane_status(repo: Path, args: argparse.Namespace) -> None:
    lanes = [args.lane] if args.lane else sorted(set([1, *lane_numbers(repo)]))
    for lane in lanes:
        lock = shared_dir(repo) / "locks" / f"lane-{lane}.lock"
        info = _read_lock(lock) if lock.is_file() else None
        mirror = load_lane(repo, lane, from_mirror=True)
        worktree = worktree_for_lane(repo, lane)
        state = "no file"
        if mirror:
            active = [
                tid for tid, t in mirror.get("tasks", {}).items() if t["status"] in ACTIVE_STATUSES
            ]
            state = f"{len(mirror['tasks'])} task(s), active: {', '.join(active) or '-'}"
        head = f"ACTIVE pid {info['pid']} ({info.get('task')})" if info else "no lock"
        print(f"lane {lane}: {head} | worktree {'yes' if worktree.is_dir() else '-'} | {state}")


def cmd_lane_release(repo: Path, args: argparse.Namespace) -> None:
    lane = args.lane
    release_lane_lock(repo, lane)
    mirror = load_lane(repo, lane, from_mirror=True)
    released = []
    if mirror is not None:
        for tid, task in mirror.get("tasks", {}).items():
            if task["status"] in ACTIVE_STATUSES:
                task["status"] = "ready"
                released.append(tid)
        append_event(
            mirror, "lane-released", None, f"lane {lane}; reverted: {', '.join(released) or 'none'}"
        )
        save_owner(repo, mirror, lane)
    update_claim(
        repo,
        "",
        lambda claims: claims.update({t: None for t, c in claims.items() if c.get("lane") == lane}),
    )
    # remove the None entries just inserted
    update_claim(
        repo,
        "",
        lambda claims: [claims.pop(t) for t in [k for k, v in claims.items() if v is None]],
    )
    print(
        f"lane {lane} released; "
        f"{'reverted to ready: ' + ', '.join(released) if released else 'no active tasks'}"
    )


def cmd_merge_lanes(repo: Path, args: argparse.Namespace) -> None:
    lane = args.lane
    if not in_main(repo):
        die("merge-lanes runs in the main checkout")
    branch = f"lane-{lane}"
    branches = _git(repo, "branch", "--format=%(refname:short)").splitlines()
    if branch not in branches:
        die(f"no branch {branch} to merge")
    mirror = load_lane(repo, lane, from_mirror=True)
    if mirror is None:
        die(f"lane {lane} has no lane file; nothing to merge")
    active = [tid for tid, t in mirror.get("tasks", {}).items() if t["status"] in ACTIVE_STATUSES]
    if active and not args.force:
        die(
            f"lane {lane} still has active tasks ({', '.join(active)}); finish them "
            f"or wf.sh lane-release {lane} first"
        )
    proc = subprocess.run(
        ["git", "merge", "--no-edit", branch], cwd=repo, capture_output=True, text=True
    )
    if proc.returncode != 0:
        subprocess.run(["git", "merge", "--abort"], cwd=repo, capture_output=True)
        die(
            f"git merge {branch} conflicted; merge aborted. Resolve manually "
            f"(git merge {branch}), commit, then re-run wf.sh merge-lanes {lane}"
        )
    state = load_state(repo)
    for tid, task in mirror.get("tasks", {}).items():
        base = state["tasks"].get(tid, {})
        merged = {**base, **task}
        if base.get("status") in MAIN_WINS_STATUSES:
            merged["status"] = base["status"]
        merged.pop("claimed_by_lane", None)
        merged.pop("steps_done", None)
        state["tasks"][tid] = merged
    state["events"] = list(state.get("events", [])) + list(mirror.get("events", []))
    state["events"].sort(key=lambda e: (e.get("ts", ""), e.get("seq", 0)))
    append_event(state, "lane-merged", None, f"lane {lane}")
    recompute_ready(state, repo, None)
    save_json(state_path(repo), state)
    for path in (
        lane_file(repo, lane),
        lane_mirror(repo, lane),
        lane_file(worktree_for_lane(repo, lane), lane),
    ):
        if path.is_file():
            path.unlink()
    worktree = worktree_for_lane(repo, lane)
    if worktree.is_dir():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=repo,
            capture_output=True,
        )
    if args.delete_branch:
        _git(repo, "branch", "-d", branch)
    release_lane_lock(repo, lane)
    update_claim(
        repo,
        "",
        lambda claims: [
            claims.pop(t) for t in [k for k, v in claims.items() if v.get("lane") == lane]
        ],
    )
    render_progress(repo)
    print(f"lane {lane} merged into main; state and PROGRESS.md updated")
    print("commit the merge (the lane file deletion is part of it)")


def cmd_machine_release(repo: Path, args: argparse.Namespace) -> None:
    path = machine_lock_path(repo)
    if not path.is_file():
        print(f"no machine lock at {path}")
        return
    info = _read_lock(path)
    if info and pid_alive(info.get("pid", 0)) and not args.force:
        die(
            f"machine lock holder pid {info.get('pid')} (repo {info.get('repo')}) is "
            f"alive; refusing. Use --force only after human confirmation that no "
            f"heavy work is running"
        )
    path.unlink()
    state = load_state(repo)
    append_event(state, "machine-lock-released", None, str(path))
    save_json(state_path(repo), state)
    print(f"machine lock {path} removed")


# --------------------------------------------------------------------- render


def progress_markdown(repo: Path, state: dict) -> str:
    eff = effective_tasks(repo, state)
    events = all_events(repo, state)
    cfg = load_config(repo)
    lines = [
        "# PROGRESS — GENERATED, DO NOT EDIT BY HAND",
        "",
        "Rendered by `wf-progress.sh render` from `.workflow/state.json` and the lane",
        "files; change them through the scripts only.",
        "",
        f"**Plan:** {state.get('title', '')}  ",
        f"**Phase:** {current_phase(state, eff) or '-'}",
        "",
        "## Tasks",
        "",
        "| id | title | status | lane | review |",
        "|---|---|---|---|---|",
    ]
    for tid in sorted(eff):
        task = eff[tid]
        flags = ""
        if task.get("plan_changed"):
            flags = " ⚠ re-acknowledge"
        record = latest_accept_record(repo, tid)
        if record and any(e["verdict"] == "judgement" for e in record.get("items", [])):
            flags += " (judgement)"
        lines.append(
            f"| {tid} | {task['title']} | {task['status']}{flags} | {task['lane']} | "
            f"{task.get('review', '')} |"
        )
    lines += ["", "## READY (grouped by lane)", ""]
    ready_by_lane: dict[int, list[str]] = {}
    for tid, task in eff.items():
        if task["status"] == "ready":
            ready_by_lane.setdefault(task["lane"], []).append(tid)
    if ready_by_lane:
        for lane in sorted(ready_by_lane):
            for tid in sorted(ready_by_lane[lane]):
                lines.append(f"- lane {lane}: **{tid}** {eff[tid]['title']}")
    else:
        lines.append("_(none)_")
    lines += ["", "## Escalation queue", ""]
    open_escalations = sorted(
        (eid, e) for eid, e in state.get("escalations", {}).items() if e["status"] == "open"
    )
    if open_escalations:
        for eid, info in open_escalations:
            lines.append(f"- **{eid}** ({info['type']}, task {info.get('task') or '-'}) — open")
    else:
        lines.append("_(none)_")
    lines += ["", "## Review queue", ""]
    review_queue = sorted(
        (tid, t) for tid, t in eff.items() if t["status"] in ("in-review", "changes-requested")
    )
    if review_queue:
        for tid, task in review_queue:
            cycles = state.get("review_cycles", {}).get(tid, 0)
            lines.append(
                f"- **{tid}** {task['title']} — {task['status']} (cycle {cycles}, max "
                f"{cfg['workflow']['max_review_cycles']})"
            )
    else:
        lines.append("_(none)_")
    lines += ["", "## Lanes", "", "| lane | lock | worktree | tasks |", "|---|---|---|---|"]
    for lane in sorted(set([1, *lane_numbers(repo)])):
        lock = shared_dir(repo) / "locks" / f"lane-{lane}.lock"
        info = _read_lock(lock) if lock.is_file() else None
        mirror = load_lane(repo, lane, from_mirror=True)
        tasks = sorted(mirror.get("tasks", {})) if mirror else []
        worktree = worktree_for_lane(repo, lane)
        lines.append(
            f"| {lane} | {'pid ' + str(info['pid']) if info else '-'} | "
            f"{'yes' if worktree.is_dir() else '-'} | {', '.join(tasks) or '-'} |"
        )
    lines += ["", "## Last events", ""]
    for e in events[-5:]:
        task = f" {e['task']}" if e.get("task") else ""
        detail = f" — {e['detail']}" if e.get("detail") else ""
        lines.append(f"- {e.get('ts', '')} {e['event']}{task}{detail}")
    lines.append("")
    return "\n".join(lines)


def render_progress(repo: Path) -> None:
    if not in_main(repo) or not state_path(repo).is_file():
        return
    try:
        state = load_state(repo)
    except WfError:
        return
    text = progress_markdown(repo, state)
    out = repo / "PROGRESS.md"
    tmp = out.with_suffix(".md.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, out)


def cmd_render(repo: Path, args: argparse.Namespace) -> None:
    render_progress(repo)
    print(f"PROGRESS.md rendered ({(repo / 'PROGRESS.md').stat().st_size} bytes)")


def cmd_event(repo: Path, args: argparse.Namespace) -> None:
    state = load_state(repo)
    append_event(state, "note", args.task, " ".join(args.text))
    recompute_ready(state, repo, None)
    save_json(state_path(repo), state)
    render_progress(repo)
    print("event recorded")


def cmd_config(repo: Path, args: argparse.Namespace) -> None:
    print(json.dumps(load_config(repo), indent=2, sort_keys=True))


def cmd_calibration_record(repo: Path, args: argparse.Namespace) -> None:
    out = repo / ".workflow" / "calibration.json"
    runs = []
    if out.is_file():
        try:
            runs = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            runs = []
    runs.append(
        {
            "date_utc": now_utc(),
            "model_name": args.model_name or "",
            "caught": args.caught,
            "missed": args.missed,
        }
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(runs, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, out)
    print(f"calibration recorded ({len(args.caught)} caught, {len(args.missed)} missed); {out}")


# ----------------------------------------------------------------------- CLI


def cmd_plan_check(repo: Path, args: argparse.Namespace) -> None:
    path = Path(args.plan)
    if not path.is_absolute():
        path = repo / path
    plan = parse_plan(path)
    warnings = validate_plan(plan, path)
    print(f"OK: {len(plan['cards'])} cards, {len(plan['assumptions'])} assumptions")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wf.sh", description="workflow-kit task state machine")
    p.add_argument("--version", action="version", version=f"workflow-kit {KIT_VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<subcommand>")

    def sp(name: str, help_: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=help_)

    s = sp("init-from-plan", "import PLAN.md and initialise state (fresh repo)")
    s.add_argument("plan")
    s.add_argument("--amend", action="store_true")
    s.set_defaults(fn=cmd_plan_import)

    s = sp("plan-import", "import (or --amend re-issue) PLAN.md")
    s.add_argument("plan")
    s.add_argument("--amend", action="store_true")
    s.set_defaults(fn=cmd_plan_import)

    s = sp("plan-check", "validate a plan file without touching state")
    s.add_argument("plan")
    s.set_defaults(fn=cmd_plan_check)

    s = sp("card", "print the shared rules and ONE task card, nothing else")
    s.add_argument("task")
    s.set_defaults(fn=cmd_card)

    s = sp("status", "one line per task")
    s.set_defaults(fn=cmd_status)

    s = sp("ready", "the READY list grouped by lane, with lane reasons")
    s.set_defaults(fn=cmd_ready)

    s = sp("claim", "claim a ready task into a lane (conflict checks, locks, worktree)")
    s.add_argument("task")
    s.add_argument("--lane", type=int, default=None)
    s.set_defaults(fn=cmd_claim)

    s = sp("start", "claimed -> in-progress (machine lock for heavy tasks)")
    s.add_argument("task")
    s.set_defaults(fn=cmd_start)

    s = sp("resume", "resume an orphaned in-progress task from its first incomplete step")
    s.add_argument("task")
    s.add_argument("--confirm", action="store_true")
    s.set_defaults(fn=cmd_resume)

    s = sp("step-done", "record a completed card step (checkpoint for resume)")
    s.add_argument("task")
    s.add_argument("step")
    s.add_argument("--note", default="")
    s.set_defaults(fn=cmd_step_done)

    s = sp("precheck", "run the card's preconditions (mismatch: STOP and report)")
    s.add_argument("task")
    s.set_defaults(fn=cmd_precheck)

    s = sp("gate-wait", "in-progress -> awaiting-gate (print what Zack must do)")
    s.add_argument("task")
    s.add_argument("--message", required=True)
    s.set_defaults(fn=cmd_gate_wait)

    s = sp("gate-release", "awaiting-gate -> in-progress (Zack said go)")
    s.add_argument("task")
    s.set_defaults(fn=cmd_gate_release)

    s = sp("accept", "run the card's acceptance commands and record evidence")
    s.add_argument("task")
    s.set_defaults(fn=cmd_accept)

    s = sp("done", "in-progress -> done (requires a passing acceptance record)")
    s.add_argument("task")
    s.set_defaults(fn=cmd_done)

    s = sp("review-open", "done -> in-review (cycle counted against the config max)")
    s.add_argument("task")
    s.set_defaults(fn=cmd_review_open)

    s = sp("review-verdict", "record the reviewer's verdict and archive the report")
    s.add_argument("task")
    s.add_argument("verdict", choices=REVIEW_VERDICTS)
    s.add_argument("--report-file", required=True)
    s.set_defaults(fn=cmd_review_verdict)

    s = sp(
        "review-disposition",
        "ACCEPT/REJECT/ESCALATE for one finding (BLOCKERs cannot be rejected)",
    )
    s.add_argument("task")
    s.add_argument("finding")
    s.add_argument("action", choices=["accept", "reject", "escalate"])
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_review_disposition)

    s = sp("block", "any active task -> blocked-decision")
    s.add_argument("task")
    s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_block)

    s = sp("unblock", "blocked-decision -> the status it was blocked from (or --to STATUS)")
    s.add_argument("task")
    s.add_argument("--to", metavar="STATUS", default=None)
    s.set_defaults(fn=cmd_unblock)

    s = sp(
        "restore-status",
        "repair a bug-regressed done -> accepted, guarded by a review-verdict event (T-022)",
    )
    s.add_argument("task")
    s.add_argument("--to", metavar="STATUS", required=True)
    s.add_argument("--verdict-seq", type=int, required=True)
    s.set_defaults(fn=cmd_restore_status)

    s = sp("escalate", "create escalations/E-NNN.md and block the task")
    s.add_argument("--task", default="")
    s.add_argument("--type", dest="type", choices=ESCALATION_TYPES, required=True)
    s.add_argument("--brief-file", required=True)
    s.set_defaults(fn=cmd_escalate)

    s = sp("decision", "record the planning chat's reply and unblock")
    s.add_argument("escalation")
    s.add_argument("--reply-file", required=True)
    s.set_defaults(fn=cmd_decision)

    s = sp("add-task", "import one card appended to PLAN-ADDED.md")
    s.add_argument("task")
    s.add_argument("--file", default=PLAN_ADDED_NAME)
    s.add_argument("--reason", default="")
    s.set_defaults(fn=cmd_add_task)

    s = sp("supersede", "mark a task superseded (--by names the replacement)")
    s.add_argument("task")
    s.add_argument("--by", default="")
    s.add_argument("--reason", default="")
    s.set_defaults(fn=cmd_supersede)

    s = sp("lane-status", "locks, worktrees and tasks per lane")
    s.add_argument("lane", nargs="?", type=int, default=None)
    s.set_defaults(fn=cmd_lane_status)

    s = sp("lane-release", "free a lane's lock and revert its active tasks to ready")
    s.add_argument("lane", type=int)
    s.set_defaults(fn=cmd_lane_release)

    s = sp("merge-lanes", "merge a finished lane branch into main and fold its file")
    s.add_argument("lane", type=int)
    s.add_argument("--delete-branch", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_merge_lanes)

    s = sp("machine-release", "remove the machine-wide lock (after human confirmation)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_machine_release)

    s = sp("render", "(re)generate PROGRESS.md from state + lane files")
    s.set_defaults(fn=cmd_render)

    s = sp("event", "append a custom event to the log")
    s.add_argument("text", nargs="+")
    s.add_argument("--task", default="")
    s.set_defaults(fn=cmd_event)

    s = sp("config", "print the effective configuration")
    s.set_defaults(fn=cmd_config)

    s = sp("guard", "consistency checks (plan hash, checksums, PROGRESS.md, locks)")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(fn=cmd_guard)

    s = sp(
        "calibration-record",
        "store a /calibrate-reviewer result in .workflow/calibration.json",
    )
    s.add_argument("--caught", nargs="*", default=[])
    s.add_argument("--missed", nargs="*", default=[])
    s.add_argument("--model-name", default="")
    s.set_defaults(fn=cmd_calibration_record)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo = repo_root()
    try:
        args.fn(repo, args)
    except WfError as exc:
        print(f"wf: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
