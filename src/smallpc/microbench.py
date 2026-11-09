"""WP6 microbenchmarks: PCIe, RAM bandwidth (STREAM) and NVMe sequential read.

    python -m smallpc.microbench [--only pcie,stream,nvme] [--reps 5] [--out data/microbench]

Run it through ``scripts/run-microbench.sh`` (detached, under the GPU lock). For each
microbenchmark: preconditions first, one discarded warm-up repetition, then ``reps`` (5) measured
repetitions, ``smallpc.stats.summarize`` for the CI, the raw per-repetition values, a reference to
the environment snapshot, and the telemetry CSV of the run.
Results: ``<out>/{pcie,stream,nvme}.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import envsnap, telemetry
from .config import repo_root
from .scrub import Identity, scrub_json
from .stats import summarize

ROOT = repo_root()
BUILD = ROOT / "build/tools"
NVCC = "/opt/cuda/bin/nvcc"
MIB = 1024 * 1024
GIB = 1024**3
PCIE_REF_GBPS = 14.3  # project plan: identical card, measured
DDR5_6000_DUAL_PEAK_GBPS = 6000e6 * 8 * 2 / 1e9  # 96 GB/s
STREAM_ARRAY = 100_000_000  # elements per array: 800 MB each, 2.4 GB total
STREAM_NTIMES = 20
NVME_BS = "16M"
NVME_COUNT = 512  # 512 x 16 MiB = 8 GiB
NVME_BYTES = 512 * 16 * MIB


class Aborted(RuntimeError):
    pass


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def env_ref(out: Path, snap: dict | None = None) -> dict:
    """Snapshot reference for a result: id of a fresh snapshot, and the suite's snapshot file."""
    sid = (snap or envsnap.snapshot())["snapshot_id"]
    return {"snapshot_id": sid, "file": str((out / "env-snapshot.json").relative_to(ROOT))}


def require_preconditions(name: str) -> dict:
    """Run the section 5.3 preconditions (plan v1.3). The idle check waits for the CPU by itself
    (every 10 s, up to 10 minutes) and records the wait under ``values["idle"]``."""
    pre = envsnap.preconditions()
    idle = pre["values"].get("idle", {})
    pre["waited_for_idle_s"] = idle.get("waited_s")
    print(
        f"[{name}] preconditions: ok={pre['ok']} warnings={pre['warnings']} "
        f"idle_busy_pct={idle.get('busy_pct')} waited_for_idle_s={pre['waited_for_idle_s']}",
        flush=True,
    )
    if not pre["ok"]:
        raise Aborted(f"{name}: preconditions failed: {pre['aborts']}")
    return pre


def finish(
    name: str, out: Path, result: dict, sampler: telemetry.Sampler, t0: float, t1: float, pre: dict
) -> None:
    rows = telemetry.window(sampler.rows, t0, t1)
    result["telemetry"] = {
        "csv": str((out / f"telemetry-{name}.csv").relative_to(ROOT)),
        "rows": len(sampler.rows),
        "detectors": telemetry.evaluate(rows),
        "sampler_overhead": sampler.overhead(),
    }
    result["preconditions"] = pre
    result["finished_utc"] = utc_now()
    scrubbed = scrub_json(result, Identity.current())
    (out / f"{name}.json").write_text(json.dumps(scrubbed, indent=2) + "\n")
    print(f"[{name}] wrote {out / f'{name}.json'}", flush=True)


# ------------------------------------------------------------------------------------ PCIe


def build_pcie() -> tuple[Path, list[str]]:
    src, exe = ROOT / "tools/pcie_bw.cu", BUILD / "pcie_bw"
    cmd = [
        NVCC, "-ccbin", "/usr/bin/g++", "-gencode", "arch=compute_120,code=sm_120", "-O2",
        "-o", str(exe), str(src),
    ]  # fmt: skip
    BUILD.mkdir(parents=True, exist_ok=True)
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        p = sh(cmd)
        if p.returncode:
            raise Aborted(f"nvcc failed: {p.stderr[-800:]}")
    return exe, cmd


def expert_bytes(out: Path) -> int:
    d = json.loads((out / "model-sizes.json").read_text())
    return int(round(d["expert"]["bytes_per_expert_stats_trunk_layers"]["mean"]))


def run_pcie_once(exe: Path, direction: str, mem: str, nbytes: int, series: int = 0) -> dict:
    cmd = [str(exe), "--dir", direction, "--mem", mem, "--bytes", str(nbytes)]
    if series:
        cmd += ["--series", str(series)]
    p = sh(cmd, timeout=300)
    if p.returncode:
        raise Aborted(f"pcie_bw failed ({p.returncode}): {p.stderr[-500:]}")
    return json.loads(p.stdout)


def link_hist(rows: list[dict]) -> dict:
    h: dict[str, int] = {}
    for r in rows:
        if r.get("pcie_gen") is not None:
            k = f"gen{int(r['pcie_gen'])}x{int(r['pcie_width'] or 0)}"
            h[k] = h.get(k, 0) + 1
    return h


def run_pcie(out: Path, reps: int, snap_ref: dict) -> dict:
    pre = require_preconditions("pcie")
    exe, nvcc_cmd = build_pcie()
    eb = expert_bytes(out)
    sizes = [("expert", eb), ("16MiB", 16 * MIB), ("256MiB", 256 * MIB)]
    plan = [
        (lbl, n, d, m, 0)
        for lbl, n in sizes
        for d in ("h2d", "d2h")
        for m in ("pinned", "pageable")
    ]
    plan += [
        ("expert_series200", eb, d, m, 200) for d in ("h2d", "d2h") for m in ("pinned", "pageable")
    ]
    result: dict = {
        "microbench": "pcie",
        "started_utc": utc_now(),
        "environment": snap_ref,
        "tool": "tools/pcie_bw.cu",
        "build_command": " ".join(nvcc_cmd),
        "repetitions": reps,
        "warm_up": "one discarded invocation per configuration, plus >= 0.7 s of untimed copies "
        "inside every invocation",
        "bandwidth_unit": "decimal GB/s (1e9 bytes/s), CUDA events",
        "sizes_bytes": {k: v for k, v in sizes},
        "expert_size_note": "mean bytes per expert over the 40 trunk layers (model-sizes.json); "
        "layers range from 1769472 to 2039808 bytes",
        "reference_gbps": PCIE_REF_GBPS,
        "configs": [],
    }
    link_rows: list[dict] = []
    t_start = time.time()
    with telemetry.Sampler(out / "telemetry-pcie.csv") as sam:
        time.sleep(1.2)  # idle link readings before any transfer
        for lbl, nbytes, d, m, series in plan:
            run_pcie_once(exe, d, m, nbytes, series)  # warm-up, discarded
            runs = [run_pcie_once(exe, d, m, nbytes, series) for _ in range(reps)]
            w0 = min(r["t_active_start"] for r in runs)
            w1 = max(r["t_end"] for r in runs)
            rows = telemetry.window(sam.rows, w0, w1)
            link_rows += rows
            cfg: dict = {
                "size": lbl, "dir": d, "mem": m, "bytes": nbytes,
                "mode": "series200" if series else "bulk",
                "raw": runs,
                "gb_per_s": summarize([r["gb_per_s"] for r in runs]),
                "link_during_transfers": link_hist(rows),
                "gpu_clock_gr_mhz_during": sorted({r["gpu_clock_gr_mhz"] for r in rows}),
                "pstate_during": sorted({r["gpu_pstate"] for r in rows if r["gpu_pstate"]}),
            }  # fmt: skip
            if series:
                cfg["latency_mean_us"] = summarize([r["latency_us"]["mean"] for r in runs])
                cfg["latency_p50_us"] = summarize([r["latency_us"]["p50"] for r in runs])
                cfg["latency_p95_us"] = summarize([r["latency_us"]["p95"] for r in runs])
                cfg["copies_per_s"] = summarize([series / (r["elapsed_ms"] / 1e3) for r in runs])
            cfg["vs_reference_pct"] = (
                (cfg["gb_per_s"]["mean"] - PCIE_REF_GBPS) / PCIE_REF_GBPS * 100
            )
            result["configs"].append(cfg)
            print(
                f"[pcie] {lbl:16s} {d} {m:8s} {cfg['gb_per_s']['mean']:6.2f} GB/s "
                f"link={cfg['link_during_transfers']}",
                flush=True,
            )
        time.sleep(1.2)
        t_end = time.time()
    idle = [r for r in sam.rows if r["t_epoch"] < t_start + 1.0]
    result["link"] = {
        "during_all_transfers": link_hist(link_rows),
        "idle_before_transfers": link_hist(idle),
        "note": "pcie.link.gen/width.current from nvidia-smi at 2 Hz. The link downshifts at idle "
        "(Gen1 in P8), so only the 'during' histogram says what transfers ran at.",
    }
    finish("pcie", out, result, sam, t_start, t_end, pre)
    return result


# ----------------------------------------------------------------------------------- STREAM


def verify_stream_source() -> tuple[Path, dict]:
    man = json.loads((ROOT / "tools/stream/MANIFEST.json").read_text())
    src = ROOT / "tools/stream" / man["file"]
    got = hashlib.sha256(src.read_bytes()).hexdigest()
    if got != man["sha256"]:
        raise Aborted(f"stream.c hash mismatch: {got} != {man['sha256']}")
    return src, man


def build_stream() -> tuple[Path, list[str], dict]:
    src, man = verify_stream_source()
    exe = BUILD / "stream"
    cmd = [
        "gcc", "-O3", "-march=native", "-fopenmp", "-mcmodel=medium",
        f"-DSTREAM_ARRAY_SIZE={STREAM_ARRAY}", f"-DNTIMES={STREAM_NTIMES}",
        str(src), "-o", str(exe),
    ]  # fmt: skip
    BUILD.mkdir(parents=True, exist_ok=True)
    p = sh(cmd)
    if p.returncode:
        raise Aborted(f"gcc failed: {p.stderr[-800:]}")
    return exe, cmd, man


STREAM_LINE = re.compile(r"^(Copy|Scale|Add|Triad):\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)")


def parse_stream(text: str) -> dict:
    """Best rate (MB/s) per kernel, plus whether the run validated."""
    rates = {m[1]: float(m[2]) for line in text.splitlines() if (m := STREAM_LINE.match(line))}
    return {"best_mb_s": rates, "validated": "Solution Validates" in text}


STREAM_THREADS = {
    8: {"OMP_NUM_THREADS": "8", "OMP_PROC_BIND": "spread", "OMP_PLACES": "cores"},
    16: {"OMP_NUM_THREADS": "16", "OMP_PROC_BIND": "spread", "OMP_PLACES": "threads"},
}


def run_stream(out: Path, reps: int, snap_ref: dict) -> dict:
    pre = require_preconditions("stream")
    exe, cmd, man = build_stream()
    result: dict = {
        "microbench": "stream",
        "started_utc": utc_now(),
        "environment": snap_ref,
        "label": "STREAM-based measurement: unmodified stream.c 5.10 (pinned), array size and "
        "NTIMES set on the compile line; not submitted to the STREAM site and not claimed to "
        "follow the Run Rules beyond the array-size rule (licence: tools/stream/MANIFEST.json)",
        "source": {k: man[k] for k in ("source", "commit", "sha256")},
        "build_command": " ".join(cmd),
        "array_elements": STREAM_ARRAY,
        "array_bytes_each": STREAM_ARRAY * 8,
        "ntimes": STREAM_NTIMES,
        "rate_unit": "MB/s (1e6 bytes/s) as printed by STREAM: best of NTIMES-1 iterations",
        "theoretical_peak_gb_s": DDR5_6000_DUAL_PEAK_GBPS,
        "theoretical_peak_note": "dual-channel DDR5-6000: 6000 MT/s x 8 B x 2 channels = 96 GB/s",
        "repetitions": reps,
        "warm_up": "one discarded run per thread count",
        "thread_settings": {str(k): v for k, v in STREAM_THREADS.items()},
        "configs": [],
    }
    t_start = time.time()
    with telemetry.Sampler(out / "telemetry-stream.csv") as sam:
        for nthreads, envv in STREAM_THREADS.items():
            env = os.environ | envv
            runs = []
            for i in range(reps + 1):
                p = sh([str(exe)], env=env, timeout=600)
                r = parse_stream(p.stdout)
                if p.returncode or not r["validated"] or len(r["best_mb_s"]) != 4:
                    raise Aborted(f"stream failed or did not validate: {p.stdout[-400:]}")
                if i:  # run 0 is the discarded warm-up
                    runs.append(r)
            cfg: dict = {"threads": nthreads, "env": envv, "raw": runs, "kernels": {}}
            for k in ("Copy", "Scale", "Add", "Triad"):
                s = summarize([r["best_mb_s"][k] for r in runs])
                s["pct_of_theoretical_peak"] = s["mean"] / 1e3 / DDR5_6000_DUAL_PEAK_GBPS * 100
                cfg["kernels"][k] = s
            result["configs"].append(cfg)
            print(
                f"[stream] {nthreads:2d} threads "
                + " ".join(f"{k}={v['mean'] / 1e3:.1f}" for k, v in cfg["kernels"].items())
                + " GB/s",
                flush=True,
            )
        t_end = time.time()
    finish("stream", out, result, sam, t_start, t_end, pre)
    return result


# ------------------------------------------------------------------------------------ NVMe


def cached_kib() -> int:
    return envsnap.parse_meminfo(Path("/proc/meminfo").read_text())["Cached"]


def parse_dd(text: str) -> tuple[int, float]:
    m = re.search(r"(\d+) bytes .*copied, ([\d.]+) s", text)
    if not m:
        raise Aborted(f"cannot parse dd output: {text[-300:]}")
    return int(m[1]), float(m[2])


def drop_file_cache(path: Path) -> None:
    """Discard this file's clean page-cache pages (posix_fadvise DONTNEED via dd; no privileges)."""
    sh(["dd", f"if={path}", "of=/dev/null", "iflag=nocache", "count=0"])


def run_nvme(out: Path, reps: int, snap_ref: dict) -> dict:
    pre = require_preconditions("nvme")
    model = ROOT / "models" / envsnap.model_info(ROOT)["file"]
    mnt = sh(["findmnt", "-T", str(model), "-n", "-o", "FSTYPE,OPTIONS"]).stdout.strip()
    result: dict = {
        "microbench": "nvme",
        "started_utc": utc_now(),
        "environment": snap_ref,
        "file": model.name,
        "command": f"dd if=<model> of=/dev/null iflag=direct bs={NVME_BS} count={NVME_COUNT}",
        "bytes_per_repetition": NVME_BYTES,
        "rate_unit": "MB/s (1e6 bytes/s) = bytes / elapsed reported by dd",
        "repetitions": reps,
        "filesystem_at_model": mnt,
        "kind": "sequential read upper bound (one stream, 16 MiB blocks, queue depth 1 at the "
        "block layer); not a random-read or mixed-load number",
    }

    def one(drop_cache: bool = False) -> dict:
        if drop_cache:
            drop_file_cache(model)
        c0 = cached_kib()
        p = sh(["dd", f"if={model}", "of=/dev/null", "iflag=direct", f"bs={NVME_BS}",
                f"count={NVME_COUNT}"])  # fmt: skip
        c1 = cached_kib()
        nbytes, secs = parse_dd(p.stderr)
        return {
            "bytes": nbytes, "seconds": secs, "mb_s": nbytes / secs / 1e6,
            "cached_before_kib": c0, "cached_after_kib": c1,
            "cached_growth_bytes": (c1 - c0) * 1024,
        }  # fmt: skip

    t_start = time.time()
    with telemetry.Sampler(out / "telemetry-nvme.csv") as sam:
        probe = one()  # warm-up, also the page-cache probe
        buffered = probe["cached_growth_bytes"] > 0.5 * probe["bytes"]
        result["warm_up"] = probe
        runs = [one(drop_cache=buffered) for _ in range(reps)]
        t_end = time.time()
    grew = [r["cached_growth_bytes"] > 0.5 * r["bytes"] for r in runs]
    result["raw"] = runs
    result["mb_s"] = summarize([r["mb_s"] for r in runs])
    result["page_cache_check"] = {
        "method": "'Cached' in /proc/meminfo before and after each dd; growth of about the "
        "amount read means the data went through the page cache",
        "warm_up_growth_bytes": probe["cached_growth_bytes"],
        "growth_bytes_per_rep": [r["cached_growth_bytes"] for r in runs],
        "buffered_reps": sum(grew),
        "verdict": "BUFFERED: iflag=direct fell back to buffered reads; this is NOT a raw-device "
        "number (file cache was dropped with posix_fadvise before each repetition)"
        if buffered or any(grew)
        else "DIRECT: the page cache did not grow, so the reads bypassed it",
    }
    print(
        f"[nvme] {result['mb_s']['mean']:.0f} MB/s; {result['page_cache_check']['verdict']}",
        flush=True,
    )
    finish("nvme", out, result, sam, t_start, t_end, pre)
    return result


# ------------------------------------------------------------------------------------ main

BENCHES = {"pcie": run_pcie, "stream": run_stream, "nvme": run_nvme}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.microbench")
    ap.add_argument("--only", default="pcie,stream,nvme")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default=str(ROOT / "data/microbench"))
    a = ap.parse_args(argv)
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (out / "model-sizes.json").exists():
        model = ROOT / "models" / envsnap.model_info(ROOT)["file"]
        from . import sizes

        sizes.main([str(model), "--out", str(out / "model-sizes.json")])

    snap = envsnap.snapshot()
    (out / "env-snapshot.json").write_text(json.dumps(snap, indent=2) + "\n")
    ref = env_ref(out, snap)
    print(f"environment snapshot {ref['snapshot_id']}", flush=True)
    rc = 0
    for name in a.only.split(","):
        try:
            BENCHES[name](out, a.reps, ref)
        except Aborted as e:
            print(f"[{name}] ABORTED: {e}", file=sys.stderr, flush=True)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
