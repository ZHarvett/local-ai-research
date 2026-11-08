"""WP6 task 6: a 60-second telemetry CSV from a live server.

    scripts/run-detached.sh --gpu livecheck -- uv run --frozen python -m smallpc.livecheck

Starts ``configs/server/health-64k.toml`` through ``scripts/launch-server.sh`` (via
``smallpc.health.Server``), runs the sampler as a separate process for 60 s (so its CPU use can be
read from /proc/<pid>/stat, free of the request client's CPU), sends real generation requests
(code prompts from ``smallpc.health``, temperature 0, ``cache_prompt`` false), runs the detectors
over the CSV and stops the server with ``scripts/stop-server.sh``. Writes
``data/microbench/sampler-60s.csv`` and ``sampler-60s.json``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import envsnap, flags, health, microbench, telemetry
from .config import repo_root
from .scrub import Identity, scrub_json

ROOT = repo_root()
OUT = ROOT / "data/microbench"
DURATION_S = 60
LAST_REQUEST_START_S = 45  # so every request finishes inside the window
N_PREDICT = 256


def cpu_seconds(pid: int) -> float | None:
    try:
        ticks = telemetry.parse_proc_stat_cpu_ticks(Path(f"/proc/{pid}/stat").read_text())
    except OSError:
        return None
    return None if ticks is None else ticks / os.sysconf("SC_CLK_TCK")


def child_pids(pid: int) -> list[int]:
    p = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True, check=False)
    return [int(x) for x in p.stdout.split()]


def main() -> int:
    try:
        pre = microbench.require_preconditions("livecheck")
    except microbench.Aborted as e:
        print("ABORT:", e, file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "sampler-60s.csv"
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    commit = json.loads((ROOT / "data/env/build-info.json").read_text())["commit"]
    scratch = Path(f"/dev/shm/local-ai-research-livecheck-{stamp}")
    scratch.mkdir(parents=True, exist_ok=True)

    snap = envsnap.snapshot()  # before any server starts: the desktop-steering state
    (OUT / "sampler-60s-env-snapshot.json").write_text(json.dumps(snap, indent=2) + "\n")
    result: dict = {
        "started_utc": stamp,
        "server_config": "configs/server/health-64k.toml",
        "snapshot_id": snap["snapshot_id"],
        "preconditions": pre,
    }
    reqs: list[dict] = []
    with health.Server("livecheck", "sampler60", {}, scratch, stamp) as srv:
        result["server_started"] = srv.started
        result["launch_output"] = srv.launch_output[-400:]
        if not srv.started:
            result["did_not_fit"] = flags.did_not_fit(srv.launch_rc, srv.log())
            result["server_log_tail"] = srv.log()[-1500:]
        else:
            prompts = health.build_code_prompts(srv, commit)
            result["prompts"] = [p["recipe"] for p in prompts]
            sampler_cmd = [
                sys.executable, "-m", "smallpc.telemetry", "run", "--out", str(csv_path),
                "--pidfile", str(srv.run_dir / "server.pid"), "--duration", str(DURATION_S),
            ]  # fmt: skip
            sampler = subprocess.Popen(sampler_cmd, stderr=subprocess.PIPE, text=True)
            t0 = time.time()
            time.sleep(0.5)
            cpu_py0 = cpu_seconds(sampler.pid)
            kids0 = {c: cpu_seconds(c) for c in child_pids(sampler.pid)}
            wall0 = time.monotonic()

            def requests_loop() -> None:
                i = 0
                while time.time() - t0 < LAST_REQUEST_START_S:
                    p = prompts[i % len(prompts)]
                    r0 = time.time()
                    resp = srv.completion(
                        p["prompt"], N_PREDICT, cache_prompt=False, temperature=0.0, seed=1234
                    )
                    reqs.append(
                        {
                            "file": p["recipe"]["file"],
                            "t_start_epoch": r0,
                            "t_end_epoch": time.time(),
                            "timings": health.timings_of(resp),
                        }
                    )
                    i += 1

            th = threading.Thread(target=requests_loop)
            th.start()
            time.sleep(DURATION_S - 3)
            cpu_py1, wall1 = cpu_seconds(sampler.pid), time.monotonic()
            kids1 = {c: cpu_seconds(c) for c in child_pids(sampler.pid)}
            th.join()
            _, err = sampler.communicate(timeout=30)
            wall = wall1 - wall0
            smi = sum((kids1[c] or 0) - (kids0.get(c) or 0) for c in kids1)
            py = (cpu_py1 or 0) - (cpu_py0 or 0)
            result["sampler_overhead"] = {
                "method": "utime+stime from /proc/<pid>/stat of the separate sampler process and "
                "its nvidia-smi child, read about 0.5 s and 57 s after it started",
                "window_s": round(wall, 2),
                "python_cpu_s": round(py, 3),
                "nvidia_smi_cpu_s": round(smi, 3),
                "python_core_fraction": py / wall,
                "nvidia_smi_core_fraction": smi / wall,
                "total_core_fraction": (py + smi) / wall,
                "sampler_self_report": json.loads(err.strip().splitlines()[-1])
                if err.strip()
                else None,
                "sampler_exit_code": sampler.returncode,
            }
            result["requests"] = reqs
            rows = telemetry.read_csv(csv_path)
            result["rows"] = len(rows)
            result["duration_s"] = rows[-1]["t_epoch"] - rows[0]["t_epoch"] if rows else None
            result["detectors"] = telemetry.evaluate(rows)
            busy = [r for r in rows if (r["gpu_util_pct"] or 0) >= 10]
            result["gpu_busy_samples"] = len(busy)
            result["link_under_load"] = telemetry.link_under_load(rows)
            result["peaks"] = {
                "gpu_util_pct": max(r["gpu_util_pct"] or 0 for r in rows),
                "gpu_power_w": max(r["gpu_power_w"] or 0 for r in rows),
                "gpu_temp_c": max(r["gpu_temp_c"] or 0 for r in rows),
                "gpu_mem_used_mib": max(r["gpu_mem_used_mib"] or 0 for r in rows),
                "tctl_c": max(r["tctl_c"] or 0 for r in rows),
                "server_rss_kib": max(r["server_rss_kib"] or 0 for r in rows),
            }
            result["request_flags"] = [
                {"file": q["file"], "flags": flags.request_flags("A", q["timings"])} for q in reqs
            ]
            result["did_not_fit"] = flags.did_not_fit(None, srv.log())
    result["stop_status"] = srv.stop_status
    result["cleanup"] = health.cleanup()
    result["servers_left"] = health.llama_server_processes()
    result["vram_mib_after"] = health.vram_mib()
    (OUT / "sampler-60s.json").write_text(
        json.dumps(scrub_json(result, Identity.current()), indent=2) + "\n"
    )
    print(
        json.dumps({k: result.get(k) for k in ("rows", "detectors", "sampler_overhead")}, indent=1)
    )
    return 0 if result.get("server_started") else 1


if __name__ == "__main__":
    raise SystemExit(main())
