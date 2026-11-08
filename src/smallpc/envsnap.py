"""Environment snapshot and per-cell preconditions (step plan section 5.3, steps 1 and 3).

    python -m smallpc.envsnap [--out FILE]         write a scrubbed snapshot (default: stdout)
    python -m smallpc.envsnap --preconditions      run the preconditions, exit 1 on an abort

``snapshot()`` returns a dict with two parts:

* ``identity``: what identifies the machine state (versions, tuning, build, model, harnesses, BIOS
  fields, display wiring, the set of processes on the GPU by name). ``snapshot_id`` is the first
  16 hex digits of the SHA-256 of its canonical JSON, so a sweep record can reference one snapshot.
* ``state``: values that change from call to call (temperatures, clocks, memory.used, MemAvailable,
  swap use, load, timestamps). They are recorded but excluded from the id.

Everything is read-only; the output is passed through ``smallpc.scrub``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from .config import repo_root
from .scrub import Identity, scrub_json

U = "unavailable"
GIB_KIB = 1024 * 1024
MEM_WARN_GIB, MEM_ABORT_GIB, LOAD_MAX = 24, 20, 1.5
VENDORS = {"0x1002": "AMD (amdgpu)", "0x10de": "NVIDIA", "0x8086": "Intel"}


# ------------------------------------------------------------------------------ helpers


def _read(path: str | Path) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return U


def _run(cmd: list[str], timeout: float = 20) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return U
    return p.stdout.strip() if p.returncode == 0 else U


def _bracket(text: str) -> str:
    """The active choice of a sysfs list such as ``always [madvise] never``."""
    m = re.search(r"\[([^\]]+)\]", text)
    return m.group(1) if m else text


def _num(s: str) -> float | None:
    try:
        return float(s.split()[0])
    except (ValueError, IndexError):
        return None


# ------------------------------------------------------------------------------ pure parsers


def parse_processes_xml(xml_text: str) -> list[dict]:
    """GPU processes (compute "C", graphics "G", "C+G") from ``nvidia-smi -q -x``."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for p in root.iter("process_info"):
        out.append(
            {
                "pid": int((p.findtext("pid") or "0").strip() or 0),
                "type": (p.findtext("type") or "").strip(),
                "name": (p.findtext("process_name") or "").strip(),
                "vram_mib": _num(p.findtext("used_memory") or ""),
            }
        )
    return out


def classify_processes(procs: list[dict]) -> dict:
    """compute = type "C" only; graphics = any type containing "G" (C+G is a desktop client)."""
    return {
        "compute": [p for p in procs if p["type"] == "C"],
        "graphics": [p for p in procs if "G" in p["type"]],
    }


def parse_drm(rows: list[dict]) -> dict:
    """Display connectors by GPU. ``rows``: connector, card, status, vendor, driver, pci."""
    conns = [
        {**r, "gpu": VENDORS.get(r["vendor"], r["vendor"])}
        for r in sorted(rows, key=lambda r: r["connector"])
    ]
    connected = [c for c in conns if c["status"] == "connected"]
    return {
        "connectors": conns,
        "connected_on_nvidia": [c["connector"] for c in connected if c["vendor"] == "0x10de"],
        "connected_on_amdgpu": [c["connector"] for c in connected if c["vendor"] == "0x1002"],
    }


def read_drm(root: str = "/sys/class/drm") -> list[dict]:
    rows = []
    for c in sorted(Path(root).glob("card*-*")):
        if not (c / "status").exists():
            continue
        card = c.name.split("-")[0]
        dev = Path(root) / card / "device"
        rows.append(
            {
                "connector": c.name,
                "card": card,
                "status": _read(c / "status"),
                "vendor": _read(dev / "vendor"),
                "driver": os.path.basename(os.path.realpath(dev / "driver")),
                "pci": os.path.basename(os.path.realpath(dev)),
            }
        )
    return rows


def parse_meminfo(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            out[m[1]] = int(m[2])
    return out


def snapshot_id(identity: dict) -> str:
    blob = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ------------------------------------------------------------------------------ collectors

GPU_QUERY = [
    ("name", "name"),
    ("driver_version", "driver_version"),
    ("persistence_mode", "persistence_mode"),
    ("pcie.link.gen.max", "pcie_gen_max"),
    ("pcie.link.gen.gpumax", "pcie_gen_gpu_max"),
    ("pcie.link.gen.hostmax", "pcie_gen_host_max"),
    ("pcie.link.width.max", "pcie_width_max"),
    ("power.limit", "power_limit_w"),
    ("power.default_limit", "power_default_limit_w"),
    ("power.max_limit", "power_max_limit_w"),
    ("memory.total", "memory_total_mib"),
    ("pcie.link.gen.current", "pcie_gen_current"),
    ("pcie.link.width.current", "pcie_width_current"),
    ("clocks.current.graphics", "clock_graphics_mhz"),
    ("clocks.current.memory", "clock_memory_mhz"),
    ("clocks.max.graphics", "clock_graphics_max_mhz"),
    ("clocks.max.memory", "clock_memory_max_mhz"),
    ("temperature.gpu", "temperature_c"),
    ("pstate", "pstate"),
    ("memory.used", "memory_used_mib"),
]
GPU_STABLE = {
    "name", "driver_version", "persistence_mode", "pcie_gen_max", "pcie_gen_gpu_max",
    "pcie_gen_host_max", "pcie_width_max", "power_limit_w", "power_default_limit_w",
    "power_max_limit_w", "memory_total_mib", "clock_graphics_max_mhz", "clock_memory_max_mhz",
}  # fmt: skip


def gpu_query(gpu_index: int = 0) -> dict:
    q = ",".join(f for f, _ in GPU_QUERY)
    out = _run(
        ["nvidia-smi", f"--id={gpu_index}", f"--query-gpu={q}", "--format=csv,noheader,nounits"]
    )
    parts = [p.strip() for p in out.split(",")] if out != U else []
    if len(parts) != len(GPU_QUERY):
        return {name: U for _, name in GPU_QUERY}
    return {name: v for (_, name), v in zip(GPU_QUERY, parts, strict=True)}


def gpu_processes() -> list[dict]:
    xml = _run(["nvidia-smi", "-q", "-x"])
    return [] if xml == U else parse_processes_xml(xml)


def llama_server_pids() -> list[int]:
    out = _run(["pgrep", "-x", "llama-server"])
    return [int(x) for x in out.split()] if out != U else []


def cuda_versions() -> dict:
    nvcc = next((p for p in ("/opt/cuda/bin/nvcc", "nvcc") if _run([p, "--version"]) != U), None)
    rel = None
    if nvcc:
        m = re.search(r"release ([\d.]+), (V[\d.]+)", _run([nvcc, "--version"]))
        rel = f"{m[1]} ({m[2]})" if m else None
    smi = _run(["nvidia-smi", "-q", "-x"])
    m = re.search(r"<cuda_version>([\d.]+)</cuda_version>", smi) if smi != U else None
    return {"driver_supports_cuda": m[1] if m else U, "nvcc_release": rel or U}


def cpu_state() -> dict:
    base = "/sys/devices/system/cpu"
    cpus = sorted(Path(base).glob("cpu[0-9]*"))

    def uniq(name: str) -> dict:
        vals: dict[str, int] = {}
        for c in cpus:
            v = _read(c / "cpufreq" / name)
            vals[v] = vals.get(v, 0) + 1
        return vals

    return {
        "scaling_driver": _read(f"{base}/cpu0/cpufreq/scaling_driver"),
        "governor": uniq("scaling_governor"),
        "epp": uniq("energy_performance_preference"),
        "amd_pstate_status": _read(f"{base}/amd_pstate/status"),
        "boost": _read(f"{base}/cpufreq/boost"),
        "model": next(
            (
                ln.split(":", 1)[1].strip()
                for ln in _read("/proc/cpuinfo").splitlines()
                if ln.startswith("model name")
            ),
            U,
        ),
        "logical_cpus": len(cpus),
    }


def memory_state() -> dict:
    mi = parse_meminfo(_read("/proc/meminfo") if _read("/proc/meminfo") != U else "")
    vm = {}
    for line in _read("/proc/vmstat").splitlines():
        k, _, v = line.partition(" ")
        if k in ("pswpin", "pswpout", "pgmajfault"):
            vm[k] = int(v)
    zram = _run(
        ["zramctl", "--bytes", "--noheadings", "--output", "NAME,DISKSIZE,DATA,COMPR,TOTAL"]
    )
    return {
        "mem_total_kib": mi.get("MemTotal"),
        "mem_available_kib": mi.get("MemAvailable"),
        "mem_available_gib": round(mi["MemAvailable"] / GIB_KIB, 2) if "MemAvailable" in mi else U,
        "cached_kib": mi.get("Cached"),
        "swap_total_kib": mi.get("SwapTotal"),
        "swap_used_kib": (mi["SwapTotal"] - mi["SwapFree"]) if "SwapTotal" in mi else U,
        "zram_bytes_name_disksize_data_compr_total": zram,
        "vmstat": vm,
        "swappiness": _read("/proc/sys/vm/swappiness"),
        "thp_enabled": _bracket(_read("/sys/kernel/mm/transparent_hugepage/enabled")),
        "thp_defrag": _bracket(_read("/sys/kernel/mm/transparent_hugepage/defrag")),
    }


def load_toml(path: Path) -> dict | None:
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None


def build_info(root: Path) -> dict:
    p = root / "data/env/build-info.json"
    if not p.exists():
        return {"status": U}
    b = json.loads(p.read_text())
    return {
        "tag": b.get("tag"),
        "commit": b.get("commit"),
        "build_date": b.get("build_date"),
        "binaries_sha256": b.get("binaries_sha256"),
        "cmake_flags": b.get("cmake_flags"),
        "nvcc": b.get("tools", {}).get("nvcc"),
    }


def model_info(root: Path) -> dict:
    m = load_toml(root / "configs/model.toml")
    if not m:
        return {"status": U}
    return {k: m.get(k) for k in ("repo", "revision", "file", "size_bytes", "sha256")} | {
        "base_repo": m.get("base", {}).get("repo"),
        "base_revision": m.get("base", {}).get("revision"),
    }


def _installed_version(root: Path, prefix: str, name: str) -> str:
    """Version in the installed package's own package.json, or "unavailable" if not installed."""
    try:
        data = json.loads((root / prefix / "node_modules" / name / "package.json").read_text())
    except (OSError, ValueError):
        return U
    return str(data.get("version", U))


def harness_info(root: Path) -> dict:
    """Harness versions from configs/harness.toml (pinned) and from the installed packages."""
    h = load_toml(root / "configs/harness.toml")
    if not h:
        return {"status": U, "note": "configs/harness.toml is missing or does not parse"}
    try:
        prefix = h["install"]["prefix"]
        pins = {p["name"]: p for p in h["packages"]}
        out: dict = {
            "node": h["runtime"]["node"],
            "npm": h["runtime"]["npm"],
            "lockfile_sha256": h["install"]["lockfile_sha256"],
            "plugins_version": h["plugins"]["version"],
            "plugins_count": h["plugins"]["count"],
            "age_check": {
                "cutoff_utc": h["age_check"]["cutoff_utc"],
                "packages_checked": h["age_check"]["packages_checked"],
                "too_new": h["age_check"]["too_new"],
            },
        }
        for key, name in (("opencode", "opencode-ai"), ("dsh", "@deepseek-ai/dsh")):
            out[key] = {
                "package": name,
                "pinned_version": pins[name]["version"],
                "published_utc": pins[name]["published_utc"],
                "integrity": pins[name]["integrity"],
                "installed_version": _installed_version(root, prefix, name),
            }
        return out
    except (KeyError, TypeError) as e:
        return {"status": U, "note": f"configs/harness.toml is incomplete: {e!r}"}


def bios_info(root: Path) -> dict:
    m = load_toml(root / "configs/machine.toml")
    return dict(m.get("bios", {})) if m and "bios" in m else {"status": U}


def gpu_lock_state(root: Path) -> dict:
    """Whether the GPU lock is held, probed with a non-blocking flock on a fresh descriptor."""
    lock = Path(os.environ.get("SMALLPC_GPU_LOCK_FILE", root / ".locks/gpu.lock"))
    lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"held": True, "file": str(lock)}
        fcntl.flock(fd, fcntl.LOCK_UN)
        return {"held": False, "file": str(lock)}
    finally:
        os.close(fd)


# ------------------------------------------------------------------------------ snapshot


def snapshot(root: Path | None = None, gpu_index: int = 0, scrub: bool = True) -> dict:
    root = root or repo_root()
    now = dt.datetime.now(dt.UTC)
    gpu = gpu_query(gpu_index)
    procs = gpu_processes()
    cls = classify_processes(procs)
    drm = parse_drm(read_drm())
    servers = llama_server_pids()
    mem = memory_state()

    identity = {
        "kernel": platform.release(),
        "driver_version": gpu["driver_version"],
        "cuda": cuda_versions(),
        "cpu": {k: v for k, v in cpu_state().items()},
        "gpu": {k: v for k, v in gpu.items() if k in GPU_STABLE},
        "pcie_note": (
            "pcie_gen_max is what the card/driver report as the current maximum; gpumax is the "
            "card's own maximum and hostmax what the host side allows. The link downshifts at "
            "idle (Gen1 in P8), so the current link is only meaningful under load "
            "(microbench pcie.json)."
        ),
        "memory_tuning": {
            k: mem[k] for k in ("swappiness", "thp_enabled", "thp_defrag", "mem_total_kib")
        },
        "llama_cpp": build_info(root),
        "model": model_info(root),
        "harnesses": harness_info(root),
        "bios_manual_fields": bios_info(root),
        "display": {
            "connected_on_nvidia": drm["connected_on_nvidia"],
            "connected_on_amdgpu": drm["connected_on_amdgpu"],
            "connectors": [
                {k: c[k] for k in ("connector", "status", "gpu")} for c in drm["connectors"]
            ],
        },
        "desktop_gpu_steering": {
            # llama-server is the workload under test, not part of the machine state
            "gpu_process_names": sorted(
                {
                    f"{p['type']}:{os.path.basename(p['name'])}"
                    for p in procs
                    if os.path.basename(p["name"]) != "llama-server"
                }
            ),
            "mechanism": "BIOS: Integrated Graphics = Forced, Initial Display Output = IGD Video "
            "(docs/environment.md)",
        },
    }
    state = {
        "timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gpu": {k: v for k, v in gpu.items() if k not in GPU_STABLE},
        "gpu_processes": procs,
        "gpu_processes_compute": cls["compute"],
        "gpu_processes_graphics": cls["graphics"],
        "llama_server_pids": servers,
        "desktop_gpu_steering": {
            "memory_used_mib_before_any_server": gpu["memory_used_mib"] if not servers else None,
            "note": "taken with no llama-server running"
            if not servers
            else "a llama-server was running: memory.used includes it",
            "processes_on_card": procs,
        },
        "memory": mem,
        "loadavg": _read("/proc/loadavg"),
        "gpu_lock": gpu_lock_state(root),
    }
    snap = {
        "schema": 1,
        "snapshot_id": snapshot_id(identity),
        "identity": identity,
        "state": state,
    }
    return scrub_json(snap, Identity.current()) if scrub else snap


# ------------------------------------------------------------------------------ preconditions


def preconditions(
    root: Path | None = None,
    *,
    expect_lock_held_by_wrapper: bool | None = None,
    ignore_pids: tuple[int, ...] = (),
) -> dict:
    """The checks of section 5.3 step 1. ``ok`` is False if anything aborts.

    * GPU lock free. When the caller runs under ``scripts/with-gpu-lock.sh``
      (``SMALLPC_GPU_LOCK_HELD`` set), the lock must be held, by that wrapper; otherwise it must
      be free. ``expect_lock_held_by_wrapper`` overrides the autodetection.
    * No other GPU compute processes (type "C" in ``nvidia-smi``) and no running llama-server.
    * Display clients on the dGPU (graphics-type processes, or a connected display on the NVIDIA
      card): warning only. "C+G" desktop clients count as graphics clients (warning).
    * MemAvailable >= 24 GiB (warn below) and >= 20 GiB (abort below).
    * 1-minute load average below 1.5.
    """
    root = root or repo_root()
    aborts: list[str] = []
    warns: list[str] = []

    wrapper = os.environ.get("SMALLPC_GPU_LOCK_HELD")
    want_held = (
        bool(wrapper) if expect_lock_held_by_wrapper is None else expect_lock_held_by_wrapper
    )
    lock = gpu_lock_state(root)
    if want_held and not lock["held"]:
        aborts.append("SMALLPC_GPU_LOCK_HELD is set but the GPU lock is not held (stale variable)")
    elif not want_held and lock["held"]:
        aborts.append("the GPU lock is held by another job")

    procs = [p for p in gpu_processes() if p["pid"] not in ignore_pids]
    cls = classify_processes(procs)
    if cls["compute"]:
        aborts.append(
            "other GPU compute processes: "
            + ", ".join(f"{os.path.basename(p['name'])}({p['pid']})" for p in cls["compute"])
        )
    servers = [p for p in llama_server_pids() if p not in ignore_pids]
    if servers:
        aborts.append(f"llama-server already running: pids {servers}")
    drm = parse_drm(read_drm())
    if cls["graphics"] or drm["connected_on_nvidia"]:
        warns.append(
            "display/graphics clients on the dGPU: "
            f"{len(cls['graphics'])} graphics process(es), "
            f"connected on NVIDIA: {drm['connected_on_nvidia'] or 'none'}"
        )

    mi = parse_meminfo(_read("/proc/meminfo"))
    avail_gib = mi.get("MemAvailable", 0) / GIB_KIB
    if avail_gib < MEM_ABORT_GIB:
        aborts.append(f"MemAvailable {avail_gib:.1f} GiB < {MEM_ABORT_GIB} GiB")
    elif avail_gib < MEM_WARN_GIB:
        warns.append(f"MemAvailable {avail_gib:.1f} GiB < {MEM_WARN_GIB} GiB")

    try:
        load1 = float(_read("/proc/loadavg").split()[0])
    except (ValueError, IndexError):
        load1 = float("nan")
    if not load1 < LOAD_MAX:
        aborts.append(f"1-minute load average {load1} is not below {LOAD_MAX}")

    return {
        "ok": not aborts,
        "aborts": aborts,
        "warnings": warns,
        "values": {
            "gpu_lock_held": lock["held"],
            "lock_expected_held_by_wrapper": want_held,
            "gpu_compute_processes": len(cls["compute"]),
            "gpu_graphics_processes": len(cls["graphics"]),
            "connected_on_nvidia": drm["connected_on_nvidia"],
            "mem_available_gib": round(avail_gib, 2),
            "loadavg_1m": load1,
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.envsnap")
    ap.add_argument("--out", help="write the snapshot here (default: stdout)")
    ap.add_argument("--preconditions", action="store_true", help="run the preconditions instead")
    ap.add_argument("--gpu", type=int, default=0)
    a = ap.parse_args(argv)
    if a.preconditions:
        res = preconditions()
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    text = json.dumps(snapshot(gpu_index=a.gpu), indent=2) + "\n"
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text)
        print(f"wrote {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
