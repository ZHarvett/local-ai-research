"""A one-request smoke start of a server with changed settings (WP12 check of a new code path).

``python -m smallpc.stage2 smoke --base-cell P6-32K-b4096 --set load_mode=none --out <json>``

Takes the resolved config of a measured cell, applies ``--set key=value`` overrides, writes the
result to a scratch TOML, starts a server through ``scripts/launch-server.sh``, sends one short
request, records the timings, the server's RssAnon, RssFile and VmSwap (after load, peak, after the
request) and the log lines that mention the loader, stops the server cleanly, and writes a JSON
labelled functional-test. It proves that a setting loads and answers; it is not a measurement.
Runs under the GPU lock.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import tomllib
from pathlib import Path

from .. import telemetry
from ..config import ServerConfig, repo_root
from ..sanity_runner import SanityError, _stamp, resolve_cell
from ..scrub import Identity, scrub_json
from ..sweep.client import Client, RequestTimeout, ServerGone
from ..sweep.core import WorkloadProvider
from ..sweep.server import ServerProc, safe_id

LOADER_LINES = re.compile(
    r"load_mode|mmap|mlock|direct.?io|dio|use_mmap|use_direct|CPU_Mapped|model buffer size|"
    r"load_tensors|cache state",
    re.IGNORECASE,
)


def parse_sets(items: list[str]) -> dict:
    out: dict = {}
    for item in items:
        k, sep, v = item.partition("=")
        if not sep or not k:
            raise SanityError(f"--set needs key=value, got {item!r}")
        if v.lower() in ("true", "false"):
            out[k] = v.lower() == "true"
        else:
            try:
                out[k] = int(v)
            except ValueError:
                out[k] = v
    return out


def _toml_text(fields: dict) -> str:
    lines = []
    for k, v in fields.items():
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, int | float):
            lines.append(f"{k} = {v}")
        else:
            lines.append(f"{k} = {json.dumps(v)}")
    return "\n".join(lines) + "\n"


def _mem(pid: int | None) -> dict:
    if pid is None:
        return {}
    try:
        text = Path(f"/proc/{pid}/status").read_text()
    except OSError:
        return {}
    return {
        "rss_anon_kib": telemetry.parse_status_field_kib(text, "RssAnon"),
        "rss_file_kib": telemetry.parse_status_field_kib(text, "RssFile"),
        "vmswap_kib": telemetry.parse_status_vmswap_kib(text),
    }


def run_smoke(
    base_cell: str,
    overrides: dict,
    out: Path,
    *,
    root: Path | None = None,
    sessions: list[Path] | None = None,
    scratch: Path,
    scripts_dir: Path | None = None,
    log_root: Path | None = None,
    machine: Path | None = None,
    model_config: Path | None = None,
    server_env: dict | None = None,
    provider=None,
    n_predict: int = 64,
    health_timeout: int = 600,
    data_label: str = "functional-test",
    require_lock: bool = True,
) -> dict:
    from ..config import load_machine

    root = Path(root) if root else repo_root()
    test_bypass = (
        os.environ.get("SMALLPC_SMOKE_NO_LOCK") == "1" and "PYTEST_CURRENT_TEST" in os.environ
    )
    if require_lock and not os.environ.get("SMALLPC_GPU_LOCK_HELD") and not test_bypass:
        raise SanityError(
            "the GPU lock is not held: start this through scripts/run-detached.sh --gpu"
        )
    base = resolve_cell(base_cell, root, sessions)
    with open(base["toml"], "rb") as fh:
        fields = tomllib.load(fh)
    fields.update(overrides)
    ServerConfig.model_validate(fields)  # the changed config must still be a valid server config
    scratch.mkdir(parents=True, exist_ok=True)
    toml = scratch / f"smoke-{base['name']}.toml"
    toml.write_text(_toml_text(fields))
    scripts_dir = Path(scripts_dir) if scripts_dir else root / "scripts"
    log_root = (
        Path(log_root) if log_root else Path(os.environ.get("SMALLPC_LOG_ROOT", root / "data/logs"))
    )
    machine = machine or root / "configs/machine.toml"
    run_id = safe_id("ft-smoke", base["name"], _stamp())
    proc = ServerProc(scripts_dir, log_root, machine, model_config, health_timeout, server_env)
    result: dict = {
        "label": data_label,
        "base_cell": base["name"],
        "resolved_from": base["resolved_from"],
        "overrides": overrides,
        "effective_fields": fields,
        "run_id": run_id,
        "ok": False,
        "error": None,
    }
    t0 = time.monotonic()
    start = proc.start(toml, run_id)
    result["load_time_s"] = round(time.monotonic() - t0, 2)
    if not start.healthy:
        result["error"] = {
            "stage": "start",
            "reason": start.reason,
            "log_matches": start.log_matches,
        }
        result["log_tail"] = proc.log_text().splitlines()[-30:]
        proc.stop()
        return _write(out, result)
    peaks: dict = {"rss_anon_kib": 0, "rss_file_kib": 0, "vmswap_kib": 0}
    result["memory_after_load"] = _mem(proc.pid)
    stop_evt = threading.Event()

    def poll() -> None:
        while not stop_evt.wait(0.5):
            for k, v in _mem(proc.pid).items():
                if v is not None:
                    peaks[k] = max(peaks[k], v)

    th = threading.Thread(target=poll, daemon=True)
    th.start()
    mach = load_machine(machine)
    client = Client(f"http://{mach.server.host}:{mach.server.port}")
    try:
        w = (provider or WorkloadProvider()).get("short", 2048, 0, base_url=client.base_url)
        c = client.completion(
            list(w.a_tokens), n_predict, {"temperature": 0.0, "top_k": 1}, seed=1, stream=False,
            cache_prompt=False,
        )  # fmt: skip
        t = c.body.get("timings") or {}
        result["request"] = {
            "workload": w.id,
            "prompt_n": t.get("prompt_n"),
            "predicted_n": t.get("predicted_n"),
            "prompt_per_second": t.get("prompt_per_second"),
            "predicted_per_second": t.get("predicted_per_second"),
            "stop_type": c.body.get("stop_type"),
            "http_status": c.http_status,
        }
        result["ok"] = (t.get("predicted_n") or 0) > 0
    except (RequestTimeout, ServerGone) as e:
        result["error"] = {"stage": "request", "reason": f"{type(e).__name__}: {e}"}
    finally:
        stop_evt.set()
        th.join(timeout=2)
        client.close()
    result["memory_after_request"] = _mem(proc.pid)
    for snap in (result["memory_after_load"], result["memory_after_request"]):
        for k, v in snap.items():
            if v is not None:
                peaks[k] = max(peaks[k], v)
    result["memory_peak"] = peaks
    result["stop"] = proc.stop()
    log = proc.log_text().splitlines()
    result["log_loader_lines"] = [ln for ln in log if LOADER_LINES.search(ln)][:40]
    return _write(out, result)


def _write(out: Path, result: dict) -> dict:
    result = scrub_json(result, Identity.current())
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1) + "\n")
    return result
