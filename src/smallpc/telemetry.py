"""2 Hz telemetry sampler: GPU (one long-running nvidia-smi), CPU Tctl, llama-server /proc, memory.

    python -m smallpc.telemetry run --out samples.csv [--pid N | --pidfile F] [--duration S]
    python -m smallpc.telemetry flags samples.csv        # thermal / paging detectors over a CSV

A single ``nvidia-smi --query-gpu=... --format=csv,nounits -lms 500`` process produces the GPU
rows; each row it prints becomes one CSV row, stamped on arrival, with the other sources read at
that moment (hwmon k10temp ``Tctl`` found by name and label, llama-server RSS and major faults from
/proc/<pid>, system ``pswpin`` and ``MemAvailable``). As a context manager::

    with Sampler("out.csv", pidfile=run_dir / "server.pid") as s: ...
    s.overhead()   # CPU seconds used by the sampler and its nvidia-smi child

Parsers are pure functions over text (fixtures in tests/fixtures/telemetry/).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from pathlib import Path

from . import flags

# (nvidia-smi query field, CSV column, kind). Names checked with `nvidia-smi --help-query-gpu`.
GPU_FIELDS: list[tuple[str, str, str]] = [
    ("utilization.gpu", "gpu_util_pct", "float"),
    ("utilization.memory", "gpu_mem_util_pct", "float"),
    ("memory.used", "gpu_mem_used_mib", "float"),
    ("power.draw", "gpu_power_w", "float"),
    ("clocks.current.graphics", "gpu_clock_gr_mhz", "float"),
    ("clocks.current.sm", "gpu_clock_sm_mhz", "float"),
    ("clocks.current.memory", "gpu_clock_mem_mhz", "float"),
    ("temperature.gpu", "gpu_temp_c", "float"),
    ("pstate", "gpu_pstate", "str"),
    ("pcie.link.gen.current", "pcie_gen", "float"),
    ("pcie.link.width.current", "pcie_width", "float"),
    ("clocks_event_reasons.gpu_idle", "reason_gpu_idle", "reason"),
    ("clocks_event_reasons.applications_clocks_setting", "reason_applications_clocks", "reason"),
    ("clocks_event_reasons.sw_power_cap", "reason_sw_power_cap", "reason"),
    ("clocks_event_reasons.hw_slowdown", "reason_hw_slowdown", "reason"),
    ("clocks_event_reasons.hw_thermal_slowdown", "reason_hw_thermal_slowdown", "reason"),
    ("clocks_event_reasons.hw_power_brake_slowdown", "reason_hw_power_brake_slowdown", "reason"),
    ("clocks_event_reasons.sw_thermal_slowdown", "reason_sw_thermal_slowdown", "reason"),
    ("clocks_event_reasons.sync_boost", "reason_sync_boost", "reason"),
    ("clocks_event_reasons.board_limit", "reason_board_limit", "reason"),
    ("clocks_event_reasons.reliability", "reason_reliability", "reason"),
]
OTHER_COLUMNS = ["tctl_c", "server_rss_kib", "majflt", "pswpin", "memavailable_kib"]
COLUMNS = ["t_epoch", "t_utc", "t_rel_s", *[c for _, c, _ in GPU_FIELDS], *OTHER_COLUMNS]
INTERVAL_MS = 500


def nvidia_smi_cmd(gpu_index: int = 0, interval_ms: int = INTERVAL_MS) -> list[str]:
    q = ",".join(f for f, _, _ in GPU_FIELDS)
    return [
        "nvidia-smi",
        f"--id={gpu_index}",
        f"--query-gpu={q}",
        "--format=csv,nounits",
        "-lms",
        str(interval_ms),
    ]


# ------------------------------------------------------------------------------- pure parsers


def _num(s: str) -> float | None:
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None  # "[N/A]", "[Not Supported]", ""


def parse_nvsmi_row(line: str) -> dict | None:
    """One data line of the nvidia-smi CSV -> {column: value}; None for the header or junk."""
    parts = [p.strip() for p in line.rstrip("\n").split(",")]
    if len(parts) != len(GPU_FIELDS) or parts[0].startswith("utilization.gpu"):
        return None
    out: dict = {}
    for (_, col, kind), raw in zip(GPU_FIELDS, parts, strict=True):
        if kind == "float":
            out[col] = _num(raw)
        elif kind == "reason":
            out[col] = True if raw == "Active" else False if raw == "Not Active" else None
        else:
            out[col] = raw or None
    return out


def parse_hwmon_temp(name: str, labels_and_inputs: dict[str, str]) -> float | None:
    """Tctl in degrees C from the contents of a k10temp hwmon directory.

    ``labels_and_inputs`` maps a file name (``name``, ``temp1_label``, ``temp1_input`` ...) to its
    text. The reading is in millidegrees.
    """
    if name.strip() != "k10temp":
        return None
    for fname, text in labels_and_inputs.items():
        if fname.endswith("_label") and text.strip() == "Tctl":
            raw = labels_and_inputs.get(fname.replace("_label", "_input"))
            if raw is not None:
                return int(raw.strip()) / 1000.0
    return None


def parse_proc_stat_majflt(text: str) -> int | None:
    """Major faults (field 12) from /proc/<pid>/stat; the comm field may contain spaces."""
    try:
        return int(text.rsplit(") ", 1)[1].split()[9])
    except (IndexError, ValueError):
        return None


def parse_proc_stat_cpu_ticks(text: str) -> int | None:
    """utime + stime in clock ticks (fields 14 and 15)."""
    try:
        f = text.rsplit(") ", 1)[1].split()
        return int(f[11]) + int(f[12])
    except (IndexError, ValueError):
        return None


def parse_status_rss_kib(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return None


def parse_vmstat(text: str, key: str = "pswpin") -> int | None:
    for line in text.splitlines():
        k, _, v = line.partition(" ")
        if k == key:
            return int(v)
    return None


def parse_meminfo_kib(text: str, key: str = "MemAvailable") -> int | None:
    for line in text.splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1])
    return None


# --------------------------------------------------------------------------------- readers


def _read(path: str | Path) -> str | None:
    try:
        return Path(path).read_text()
    except OSError:
        return None


def find_k10temp(hwmon_root: str = "/sys/class/hwmon") -> Path | None:
    """The k10temp hwmon directory, found by its name (hwmon numbers change between boots)."""
    for d in sorted(Path(hwmon_root).glob("hwmon*")):
        if (_read(d / "name") or "").strip() == "k10temp":
            return d
    return None


def tctl_input_path(hwmon_dir: Path | None) -> Path | None:
    if hwmon_dir is None:
        return None
    for lab in sorted(hwmon_dir.glob("temp*_label")):
        if (_read(lab) or "").strip() == "Tctl":
            return Path(str(lab).replace("_label", "_input"))
    return None


def read_pid(pid: int | None, pidfile: Path | None) -> int | None:
    if pid:
        return pid
    if pidfile:
        txt = _read(pidfile)
        if txt and txt.strip().isdigit():
            return int(txt.strip())
    return None


# --------------------------------------------------------------------------------- sampler


class Sampler:
    """Writes one CSV row per nvidia-smi sample (2 Hz). Context manager; ``rows`` kept in memory."""

    def __init__(
        self,
        out: str | Path,
        pid: int | None = None,
        pidfile: str | Path | None = None,
        gpu_index: int = 0,
        interval_ms: int = INTERVAL_MS,
    ):
        self.out = Path(out)
        self.pid, self.pidfile = pid, Path(pidfile) if pidfile else None
        self.cmd = nvidia_smi_cmd(gpu_index, interval_ms)
        self.rows: list[dict] = []
        self.error: str | None = None
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._tctl = tctl_input_path(find_k10temp())
        self._t0 = 0.0
        self._cpu0: dict = {}
        self._cpu1: dict = {}

    # -- lifecycle
    def start(self) -> Sampler:
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self._t0 = time.time()
        self._cpu0 = {"wall": time.monotonic(), "self": self._self_cpu_s()}
        self._proc = subprocess.Popen(
            self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1
        )
        self._cpu0["smi_pid"] = self._proc.pid
        self._thread = threading.Thread(target=self._loop, name="telemetry", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._proc is None:
            return
        smi_ticks = parse_proc_stat_cpu_ticks(_read(f"/proc/{self._proc.pid}/stat") or "")
        self._cpu1 = {
            "wall": time.monotonic(),
            "self": self._self_cpu_s(),
            "smi_ticks": smi_ticks,
        }
        self._proc.send_signal(signal.SIGTERM)
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        if self._thread:
            self._thread.join(timeout=5)
        self._proc = None

    def __enter__(self) -> Sampler:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- sampling
    @staticmethod
    def _self_cpu_s() -> float:
        return time.process_time()  # all threads of this process

    def _other_sources(self) -> dict:
        pid = read_pid(self.pid, self.pidfile)
        stat = _read(f"/proc/{pid}/stat") if pid else None
        status = _read(f"/proc/{pid}/status") if pid else None
        tctl = _read(self._tctl) if self._tctl else None
        return {
            "tctl_c": int(tctl) / 1000.0 if tctl and tctl.strip().lstrip("-").isdigit() else None,
            "server_rss_kib": parse_status_rss_kib(status) if status else None,
            "majflt": parse_proc_stat_majflt(stat) if stat else None,
            "pswpin": parse_vmstat(_read("/proc/vmstat") or ""),
            "memavailable_kib": parse_meminfo_kib(_read("/proc/meminfo") or ""),
        }

    def _loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        with open(self.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            for line in self._proc.stdout:
                row = parse_nvsmi_row(line)
                if row is None:
                    continue
                now = time.time()
                row |= {
                    "t_epoch": round(now, 3),
                    "t_utc": dt.datetime.fromtimestamp(now, dt.UTC).strftime("%H:%M:%S.%f")[:-3],
                    "t_rel_s": round(now - self._t0, 3),
                } | self._other_sources()
                self.rows.append(row)
                w.writerow({k: ("" if v is None else v) for k, v in row.items()})
                fh.flush()
        if self._proc.poll() not in (None, 0, -signal.SIGTERM):
            self.error = f"nvidia-smi exited with {self._proc.poll()}"

    # -- overhead
    def overhead(self) -> dict:
        """CPU use of the sampler (python process) and its nvidia-smi child over the run."""
        wall = self._cpu1["wall"] - self._cpu0["wall"]
        py = self._cpu1["self"] - self._cpu0["self"]
        smi = (self._cpu1.get("smi_ticks") or 0) / os.sysconf("SC_CLK_TCK")
        return {
            "wall_s": wall,
            "python_cpu_s": py,
            "nvidia_smi_cpu_s": smi,
            "python_core_fraction": py / wall if wall else None,
            "nvidia_smi_core_fraction": smi / wall if wall else None,
            "total_core_fraction": (py + smi) / wall if wall else None,
            "n_rows": len(self.rows),
        }


# ------------------------------------------------------------------------- reading a CSV back

_FLOAT_COLS = {c for _, c, k in GPU_FIELDS if k == "float"} | {
    "t_epoch",
    "t_rel_s",
    "tctl_c",
    "server_rss_kib",
    "majflt",
    "pswpin",
    "memavailable_kib",
}
_BOOL_COLS = {c for _, c, k in GPU_FIELDS if k == "reason"}


def read_csv(path: str | Path) -> list[dict]:
    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            row: dict = {}
            for k, v in r.items():
                if v == "":
                    row[k] = None
                elif k in _FLOAT_COLS:
                    row[k] = float(v)
                elif k in _BOOL_COLS:
                    row[k] = v == "True"
                else:
                    row[k] = v
            out.append(row)
    return out


def window(rows: Iterable[dict], t0: float, t1: float) -> list[dict]:
    """Rows with t0 <= t_epoch <= t1."""
    return [r for r in rows if t0 <= r["t_epoch"] <= t1]


def evaluate(rows: list[dict]) -> dict:
    """The sample-based detectors (thermal, paging) over a window of rows."""
    return {"thermal": flags.thermal(rows), "paging": flags.paging(rows)}


def link_under_load(rows: list[dict], min_util_pct: float = 10.0) -> dict:
    """PCIe generation/width seen in the window, overall and for samples with GPU util >= min."""

    def hist(rs):
        h: dict[str, int] = {}
        for r in rs:
            if r.get("pcie_gen") is not None:
                k = f"gen{int(r['pcie_gen'])}x{int(r['pcie_width'] or 0)}"
                h[k] = h.get(k, 0) + 1
        return h

    busy = [r for r in rows if (r.get("gpu_util_pct") or 0) >= min_util_pct]
    return {"all_samples": hist(rows), f"util_ge_{int(min_util_pct)}pct": hist(busy)}


# ------------------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.telemetry")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="sample until --duration or SIGINT/SIGTERM")
    r.add_argument("--out", required=True)
    r.add_argument("--pid", type=int)
    r.add_argument("--pidfile")
    r.add_argument("--duration", type=float, help="seconds (default: until signalled)")
    r.add_argument("--gpu", type=int, default=0)
    f = sub.add_parser("flags", help="run the thermal and paging detectors over a CSV")
    f.add_argument("csv")
    a = ap.parse_args(argv)

    if a.cmd == "flags":
        print(json.dumps(evaluate(read_csv(a.csv)), indent=2))
        return 0

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    with Sampler(a.out, pid=a.pid, pidfile=a.pidfile, gpu_index=a.gpu) as s:
        stop.wait(a.duration)
    print(json.dumps(s.overhead()), file=sys.stderr)
    return 1 if s.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
