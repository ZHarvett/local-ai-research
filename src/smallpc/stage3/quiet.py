"""Quiet-machine check (G3 for Stages 3 and 4): process NAMES against a blocklist.

Reads ``ps -eo comm=,rss=`` output (a name and a resident size in KiB per line, nothing else: no
window titles, no command lines) from a file or stdin, prints the blocklisted apps that run, warns
about processes over the memory limit, and prints the CPU busy figure as information. Exit 0 if no
blocklisted app runs, 1 if one does, 2 for a usage or configuration error.

    ps -eo comm=,rss= | python -m smallpc.stage3.quiet [--config configs/quiet-check.toml]

``scripts/check-quiet.sh`` is the command to run.
"""

from __future__ import annotations

import argparse
import sys
import time
import tomllib
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from ..config import repo_root
from ..envsnap import measure_cpu_busy_pct

COMM_WIDTH = 15  # ps truncates comm to 15 characters


class QuietConfigError(ValueError):
    pass


def load_config(path: Path) -> dict:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    names = (raw.get("blocklist") or {}).get("names")
    if not names or not all(isinstance(n, str) and n for n in names):
        raise QuietConfigError(f"{path}: [blocklist] names must be a non-empty list of names")
    mem = raw.get("memory") or {}
    cpu = raw.get("cpu") or {}
    return {
        "blocklist": sorted({n[:COMM_WIDTH] for n in names}),
        "warn_mib": float(mem.get("warn_mib", 1536)),
        "exempt": {n[:COMM_WIDTH] for n in mem.get("exempt", ["llama-server", "claude"])},
        "cpu_window_s": float(cpu.get("window_s", 10)),
        "cpu_busy_max_pct": float(cpu.get("busy_max_pct", 10.0)),
    }


def parse_ps(text: str) -> list[tuple[str, int]]:
    """``(name, rss KiB)`` per line. The name may contain spaces; the size is the last field."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, rss = line.rpartition(" ")
        if not name or not rss.isdigit():
            continue  # not a "name size" line: ignored, never echoed
        out.append((name.strip()[:COMM_WIDTH], int(rss)))
    return out


def check(procs: list[tuple[str, int]], cfg: dict) -> dict:
    block = set(cfg["blocklist"])
    offenders = Counter(n for n, _ in procs if n in block)
    heavy = sorted(
        (
            (n, kib / 1024)
            for n, kib in procs
            if n not in cfg["exempt"] and kib / 1024 > cfg["warn_mib"]
        ),
        key=lambda x: -x[1],
    )
    return {
        "processes": len(procs),
        "offenders": dict(sorted(offenders.items())),
        "heavy": [{"name": n, "resident_mib": round(m)} for n, m in heavy],
        "quiet": not offenders,
    }


def cpu_line(cfg: dict, busy: float | None) -> str:
    if busy is None:
        return "CPU idle check (informational): /proc/stat could not be read"
    return (
        f"CPU idle check (informational): busy {busy:.1f}% over {cfg['cpu_window_s']:.0f} s "
        f"(the runner's precondition needs below {cfg['cpu_busy_max_pct']:.0f}%)"
    )


def report(result: dict, cfg: dict, busy: float | None, measure_cpu: bool) -> str:
    L = [f"quiet-machine check: {result['processes']} processes (names only)"]
    if result["offenders"]:
        L.append("NOT QUIET: close these apps (blocklisted, process name and count):")
        L += [f"  {n}  x{c}" for n, c in result["offenders"].items()]
    else:
        L.append("no blocklisted app is running")
    if result["heavy"]:
        L.append(
            f"warning: processes above {cfg['warn_mib'] / 1024:.1f} GiB resident "
            "(name and size only):"
        )
        L += [f"  {h['name']}  {h['resident_mib']} MiB" for h in result["heavy"]]
    if measure_cpu:
        L.append(cpu_line(cfg, busy))
    L.append("RESULT: " + ("QUIET" if result["quiet"] else "NOT QUIET (exit 1)"))
    return "\n".join(L)


def main(
    argv: list[str] | None = None,
    *,
    stdin: Callable[[], str] | None = None,
    read_stat: Callable[[], str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m smallpc.stage3.quiet", description=__doc__.split("\n")[0]
    )
    ap.add_argument("--config", type=Path, default=repo_root() / "configs/quiet-check.toml")
    ap.add_argument(
        "--ps-file", type=Path, help="read `ps -eo comm=,rss=` output from this file, not stdin"
    )
    ap.add_argument("--no-cpu", action="store_true", help="skip the CPU idle line")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        cfg = load_config(a.config)
    except (OSError, ValueError) as e:
        print(f"check-quiet: {e}", file=sys.stderr)
        return 2
    text = a.ps_file.read_text() if a.ps_file else (stdin or sys.stdin.read)()
    procs = parse_ps(text)
    if not procs:
        print("check-quiet: no process list was given", file=sys.stderr)
        return 2
    result = check(procs, cfg)
    busy = None
    if not a.no_cpu:
        reader = read_stat or (lambda: Path("/proc/stat").read_text())
        try:
            busy = measure_cpu_busy_pct(reader, sleep, cfg["cpu_window_s"])
        except OSError:
            busy = None
    if a.json:
        import json

        print(json.dumps(result | {"cpu_busy_pct": busy}, indent=1))
    else:
        print(report(result, cfg, busy, not a.no_cpu))
    return 0 if result["quiet"] else 1


if __name__ == "__main__":
    sys.exit(main())
