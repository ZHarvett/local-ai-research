"""Server lifecycle for the sweep: start through ``scripts/launch-server.sh``, stop through
``scripts/stop-server.sh`` (SIGINT, then SIGKILL after a timeout). Nothing else starts llama-server.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import flags


@dataclass
class StartResult:
    started: bool  # the server process was launched (a run directory with a pid exists)
    healthy: bool
    run_id: str
    run_dir: Path
    rc: int
    output: str
    pid: int | None = None
    exit_code: int | None = None  # the server's own exit code if it ended before becoming healthy
    reason: str | None = None  # oom_at_load | startup_failure | startup_timeout
    infrastructure: bool = False  # launch refused (port, lock, binary): not a fit problem
    load_time_s: float = 0.0
    log_matches: list[str] = field(default_factory=list)


def pid_alive(pid: int, start: str | None = None) -> bool:
    """True if the process exists and (when ``start`` is given) has that start time."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    fields = stat.rsplit(") ", 1)[1].split()
    if fields[0] == "Z":
        return False
    return start is None or fields[19] == start


class ServerProc:
    def __init__(
        self,
        scripts_dir: Path,
        log_root: Path,
        machine: Path | None = None,
        model_config: Path | None = None,
        health_timeout: int = 600,
        env: dict | None = None,
    ):
        self.scripts = Path(scripts_dir)
        self.log_root = Path(log_root)
        self.machine, self.model_config = machine, model_config
        self.health_timeout = health_timeout
        self.env = {**os.environ, **(env or {}), "SMALLPC_LOG_ROOT": str(self.log_root)}
        self.run_dir: Path | None = None
        self.start_result: StartResult | None = None

    # -- start
    def start(self, config_toml: Path, run_id: str) -> StartResult:
        cmd = [str(self.scripts / "launch-server.sh"), "--run-id", run_id]
        cmd += ["--health-timeout", str(self.health_timeout)]
        if self.machine:
            cmd += ["--machine", str(self.machine)]
        if self.model_config:
            cmd += ["--model-config", str(self.model_config)]
        cmd.append(str(config_toml))
        kw = {"pass_fds": (9,)} if os.environ.get("SMALLPC_GPU_LOCK_HELD") and _fd_open(9) else {}
        t0 = time.monotonic()
        p = subprocess.run(cmd, capture_output=True, text=True, check=False, env=self.env, **kw)
        load = time.monotonic() - t0
        run_dir = self.log_root / run_id
        self.run_dir = run_dir
        out = (p.stdout + p.stderr).strip()
        pidfile = run_dir / "server.pid"
        pid = int(pidfile.read_text()) if pidfile.exists() and pidfile.read_text().strip() else None
        res = StartResult(
            started=pid is not None,
            healthy=p.returncode == 0,
            run_id=run_id,
            run_dir=run_dir,
            rc=p.returncode,
            output=out,
            pid=pid,
            load_time_s=round(load, 2),
        )
        if p.returncode != 0:
            self._classify_failure(res)
        self.start_result = res
        return res

    def _classify_failure(self, res: StartResult) -> None:
        if not res.started:
            res.infrastructure = True
            res.reason = "launch_refused"
            return
        ec = self.run_dir / "exit-code"  # type: ignore[operator]
        log = self.log_text()
        if "no healthy /health" in res.output:
            res.reason = "startup_timeout"
        if ec.exists() and ec.read_text().strip().lstrip("-").isdigit():
            res.exit_code = int(ec.read_text())
        verdict = flags.did_not_fit(res.exit_code, log)
        res.log_matches = verdict["log_matches"]
        if res.reason is None:
            res.reason = "oom_at_load" if verdict["log_matches"] else "startup_failure"
        elif verdict["log_matches"]:
            res.reason = "oom_at_load"

    # -- state
    @property
    def pid(self) -> int | None:
        if self.run_dir and (self.run_dir / "server.pid").exists():
            return int((self.run_dir / "server.pid").read_text())
        return None

    def alive(self) -> bool:
        if not self.run_dir:
            return False
        pidf, startf = self.run_dir / "server.pid", self.run_dir / "server.start"
        if not pidf.exists():
            return False
        start = startf.read_text().strip() if startf.exists() else None
        return pid_alive(int(pidf.read_text()), start)

    def exit_code(self) -> int | None:
        f = self.run_dir / "exit-code" if self.run_dir else None
        if f and f.exists() and f.read_text().strip().lstrip("-").isdigit():
            return int(f.read_text())
        return None

    def log_text(self) -> str:
        f = self.run_dir / "server.log" if self.run_dir else None
        return f.read_text(errors="replace") if f and f.exists() else ""

    # -- stop
    def stop(self, timeout_s: int = 60) -> dict:
        """SIGINT, wait, SIGKILL after ``timeout_s`` (all inside stop-server.sh)."""
        if not self.run_dir or not (self.run_dir / "server.pid").exists():
            return {"method": "not_started"}
        p = subprocess.run(
            [str(self.scripts / "stop-server.sh"), "--timeout", str(timeout_s), str(self.run_dir)],
            capture_output=True,
            text=True,
            check=False,
            env=self.env,
        )
        sf = self.run_dir / "stop-status.json"
        status = json.loads(sf.read_text()) if sf.exists() else {"error": p.stderr.strip()}
        status["stop_rc"] = p.returncode
        return status


def _fd_open(fd: int) -> bool:
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False


def stop_orphan(scripts_dir: Path, log_root: Path, run_id: str, timeout_s: int = 30) -> dict | None:
    """Stop a server of an earlier run of this session (after a hard kill of the runner), if its
    recorded process is still the one that was started. Returns the stop status or None."""
    run_dir = Path(log_root) / run_id
    pidf, startf = run_dir / "server.pid", run_dir / "server.start"
    if not (pidf.exists() and startf.exists()):
        return None
    if not pid_alive(int(pidf.read_text()), startf.read_text().strip()):
        return None
    proc = ServerProc(scripts_dir, log_root)
    proc.run_dir = run_dir
    return proc.stop(timeout_s)


_PLACEMENT_RE = re.compile(r"[A-Za-z0-9._-]+")


def safe_id(*parts: str) -> str:
    return "-".join(
        _PLACEMENT_RE.fullmatch(p) and p or re.sub(r"[^A-Za-z0-9._-]", "_", p) for p in parts
    )
