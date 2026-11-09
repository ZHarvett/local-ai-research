"""Shared pieces of the sweep runner: the environment with its test seams, jobs, exceptions and
small helpers (atomic JSON writes, gzip, log excerpts, VRAM arithmetic)."""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import envsnap, telemetry
from ..config import MachineConfig, ModelConfig, load_machine, load_model, repo_root
from . import provenance
from .server import ServerProc

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PROVENANCE = 2
EXIT_PRECONDITION = 3  # resumable
EXIT_INHIBIT = 4
EXIT_INTERRUPTED = 130


class SessionAbort(RuntimeError):
    """Stop the session; ``exit_code`` says how. Never recorded as a cell failure."""

    exit_code = EXIT_ERROR


class HardAbort(SessionAbort):
    """A condition a wait cannot fix: GPU lock, foreign compute process, busy port, no binary."""

    exit_code = EXIT_PRECONDITION


class TransientAbort(SessionAbort):
    """Transient preconditions (idle CPU, MemAvailable) still failing after every retry."""

    exit_code = EXIT_PRECONDITION


class ProvenanceError(SessionAbort):
    exit_code = EXIT_PROVENANCE


class InhibitError(SessionAbort):
    exit_code = EXIT_INHIBIT


# ------------------------------------------------------------------------------ workloads


class WorkloadProvider:
    """The WP8 interface the runner uses. Tests replace it with a synthetic provider."""

    def get(self, kind: str, length: int, repetition: int, base_url: str | None = None):
        from ..workloads import get_workload

        return get_workload(kind, length, repetition=repetition, base_url=base_url)

    def depths(self, context: int) -> list[int]:
        from ..workloads import depths_for_context

        return depths_for_context(context)

    def fits(self, d: int, per_slot_ctx: int) -> bool:
        from ..workloads import fits

        return fits(d, per_slot_ctx)


# ------------------------------------------------------------------------------ environment


@dataclass
class Env:
    root: Path
    scripts_dir: Path
    out_root: Path  # data/raw
    log_root: Path  # data/logs
    probe_cache: Path
    machine_path: Path
    model_path: Path
    machine: MachineConfig
    model: ModelConfig
    llama_commit: str
    model_sha: dict  # provenance.model_sha256 result
    git: dict  # provenance.git_state
    manifest_path: Path
    server_factory: Callable[[], ServerProc]
    sampler_factory: Callable[[Path, Path | None], Any]
    snapshot_fn: Callable[[], dict]
    preconditions_fn: Callable[[bool], dict]
    provider: Any = field(default_factory=WorkloadProvider)
    gpu_total_mib: Callable[[], float | None] = lambda: None
    gpu_used_mib: Callable[[], float | None] = lambda: None
    settle_s: float = 0.6  # lets the 2 Hz sampler catch the last state after a phase
    n_layer: Callable[[], int] = lambda: 40
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.time
    precond_pause_s: float = 600.0
    precond_retries: int = 3
    health_timeout: int = 600
    check_inhibit: bool = True

    @property
    def base_url(self) -> str:
        return f"http://{self.machine.server.host}:{self.machine.server.port}"


def default_env(
    root: Path | None = None,
    machine_path: Path | None = None,
    model_path: Path | None = None,
    *,
    health_timeout: int = 600,
) -> Env:
    root = root or repo_root()
    machine_path = machine_path or root / "configs/machine.toml"
    model_path = model_path or root / "configs/model.toml"
    machine, model = load_machine(machine_path), load_model(model_path)
    build = json.loads((root / "data/env/build-info.json").read_text())
    msha = provenance.model_sha256(
        Path(machine.paths.models_dir) / (model.file or ""),
        model.sha256,
        root / "data/cache/model-sha.json",
    )
    scripts = root / "scripts"
    log_root = Path(os.environ.get("SMALLPC_LOG_ROOT", root / "data/logs"))

    def sampler_factory(out: Path, pidfile: Path | None):
        return telemetry.Sampler(out, pidfile=pidfile, gpu_index=machine.gpu.index)

    def preconditions_fn(idle: bool) -> dict:
        if idle:
            return envsnap.preconditions(root)
        return envsnap.preconditions(
            root, idle_check=lambda: {"ok": True, "skipped": "probe step", "loadavg_1m": None}
        )

    def gpu_total() -> float | None:
        v = envsnap.gpu_query(machine.gpu.index).get("memory_total_mib")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def gpu_used() -> float | None:
        v = envsnap.gpu_query(machine.gpu.index).get("memory_used_mib")
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return Env(
        root=root,
        scripts_dir=scripts,
        out_root=root / "data/raw",
        log_root=log_root,
        probe_cache=root / "data/probes/cache.jsonl",
        machine_path=machine_path,
        model_path=model_path,
        machine=machine,
        model=model,
        llama_commit=build["commit"],
        model_sha=msha,
        git=provenance.git_state(root),
        manifest_path=root / "configs/workloads/manifest.json",
        server_factory=lambda: ServerProc(
            scripts, log_root, machine_path, model_path, health_timeout=health_timeout
        ),
        sampler_factory=sampler_factory,
        snapshot_fn=lambda: envsnap.snapshot(root, machine.gpu.index),
        preconditions_fn=preconditions_fn,
        gpu_total_mib=gpu_total,
        gpu_used_mib=gpu_used,
        n_layer=lambda: _gguf_block_count(Path(machine.paths.models_dir) / (model.file or "")),
        health_timeout=health_timeout,
    )


def _gguf_block_count(path: Path) -> int:
    from gguf import GGUFReader

    r = GGUFReader(str(path))
    for key in r.fields:
        if key.endswith(".block_count"):
            return int(r.fields[key].contents())
    raise RuntimeError("block_count not found in the GGUF")


# ------------------------------------------------------------------------------ jobs


@dataclass
class Job:
    """One server configuration to measure: a cell, or one of the canary configurations."""

    name: str
    role: str  # measured | canary_start | canary_end
    profile: str
    fields: dict  # resolved server-config fields
    reps: list[int]
    attempt: int = 1
    short: bool = True
    depths: list[int] | None = None  # None: the depths of the context (section 5.3)
    resolution: dict = field(default_factory=dict)
    coords: dict = field(default_factory=dict)
    # filled by Session.prepare_job
    toml_path: Path | None = None
    argv: list[str] = field(default_factory=list)
    config_hash: str = ""

    @property
    def context(self) -> int:
        return int(self.fields["context"])

    @property
    def hash8(self) -> str:
        return self.config_hash[:8]


@dataclass
class Outcome:
    status: str  # complete | did_not_fit | server_died | interrupted | failed
    reason: str | None = None
    exit_code: int | None = None
    load_time_s: float | None = None
    reps_done: list[int] = field(default_factory=list)
    n_requests: int = 0
    summary_rel: str | None = None
    detail: dict = field(default_factory=dict)


# ------------------------------------------------------------------------------ helpers


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json_atomic(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n")
    os.replace(tmp, path)


def gzip_file(path: Path) -> Path | None:
    """Compress ``path`` to ``path + .gz`` and remove the original; None if it does not exist."""
    if not path.exists():
        return None
    gz = path.with_suffix(path.suffix + ".gz")
    with open(path, "rb") as src, gzip.open(gz, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()
    return gz


_EXCERPT = re.compile(
    r"fit|memory breakdown|buffer size|n_ctx|n_slots|kv_unified|offloaded|override|MoE cache|"
    r"checkpoint|prompt cache|load_tensors|listening|llama_context|moe_cache|slot|common_params",
    re.IGNORECASE,
)


def log_excerpt(log: str, limit: int = 160) -> list[str]:
    """The informative lines of a startup log (placement, buffers, cache), at most ``limit``."""
    out = [ln for ln in log.splitlines() if _EXCERPT.search(ln)]
    return out[:limit]


def min_free_mib(rows: list[dict], total_mib: float | None) -> float | None:
    """Minimum free VRAM in the rows: card total minus the highest ``memory.used`` sample."""
    used = [r["gpu_mem_used_mib"] for r in rows if r.get("gpu_mem_used_mib") is not None]
    if total_mib is None or not used:
        return None
    return round(total_mib - max(used), 1)


def peak_used_mib(rows: list[dict]) -> float | None:
    used = [r["gpu_mem_used_mib"] for r in rows if r.get("gpu_mem_used_mib") is not None]
    return max(used) if used else None


def rows_between(rows: list[dict], t0: float, t1: float) -> list[dict]:
    return [r for r in rows if t0 <= r["t_epoch"] <= t1]


def hash8_of(h: str) -> str:
    return h[:8]
