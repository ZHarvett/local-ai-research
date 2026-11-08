"""A llama-server for the workload steps, started and stopped through the repository scripts.

The server is started with ``scripts/launch-server.sh <config>`` (which refuses to run unless the
GPU lock is held by this job or free to take) and stopped with ``scripts/stop-server.sh``. A
running server can be reused with ``Session.attach(url)``; it is then left running."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import httpx

from ..config import load_machine, repo_root

ROOT = repo_root()
DEFAULT_CONFIG = ROOT / "configs/server/workload-check-128k.toml"


class Session:
    def __init__(self, config: Path = DEFAULT_CONFIG, run_id: str | None = None):
        machine = load_machine()
        self.config = config
        self.base_url = f"http://{machine.server.host}:{machine.server.port}"
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.run_id = run_id or f"workloads-{stamp}-{config.stem}"
        self.run_dir = ROOT / "data/logs" / self.run_id
        self.client: httpx.Client | None = None
        self.owned = False
        self.launch_output = ""
        self.stop_status: dict | None = None

    @classmethod
    def attach(cls, base_url: str) -> Session:
        s = cls()
        s.base_url = base_url
        s.client = httpx.Client(base_url=base_url, timeout=httpx.Timeout(1800.0))
        return s

    def __enter__(self) -> Session:
        if self.client is None:
            self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self, health_timeout: int = 420) -> None:
        kw: dict = {}
        try:
            os.fstat(9)
            kw["pass_fds"] = (9,)  # the GPU lock fd, so the server keeps the lock
        except OSError:
            pass
        p = subprocess.run(
            [
                str(ROOT / "scripts/launch-server.sh"),
                "--run-id",
                self.run_id,
                "--health-timeout",
                str(health_timeout),
                str(self.config),
            ],
            capture_output=True,
            text=True,
            check=False,
            **kw,
        )
        self.launch_output = (p.stdout + p.stderr).strip()
        if p.returncode != 0:
            raise RuntimeError(
                f"launch-server.sh failed ({p.returncode}): {self.launch_output[-500:]}"
            )
        self.owned = True
        self.client = httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(1800.0))

    def stop(self) -> dict | None:
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.owned and self.stop_status is None and (self.run_dir / "server.pid").exists():
            subprocess.run(
                [str(ROOT / "scripts/stop-server.sh"), "--timeout", "90", str(self.run_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            sf = self.run_dir / "stop-status.json"
            self.stop_status = json.loads(sf.read_text()) if sf.exists() else {"error": "no status"}
        return self.stop_status

    def argv(self) -> list[str]:
        f = self.run_dir / "argv.txt"
        return f.read_text().split("\n")[:-1] if f.exists() else []

    def props(self) -> dict:
        r = self.client.get("/props")
        r.raise_for_status()
        return r.json()
