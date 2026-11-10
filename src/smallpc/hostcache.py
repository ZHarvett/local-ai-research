"""Host prompt cache size and per-window memory figures of a server (moved from
``tools/stage1_diagnostics.py`` in WP12 so ``smallpc.stage2`` can use them).

The host prompt cache size is the line ``srv update: - cache state: N prompts, X MiB (limits: ...)``
that llama-server logs (at ``-lv 4``) when a new task makes it save the idle slot's prompt. Log
times are "minutes.seconds.ms.us" since process start; they are aligned to the wall clock by
matching the k-th ``slot print_timing ... total time`` line to the end time of the k-th request of
the instance (median offset). No figure here changes a flag, an eligibility rule or a statistic.
"""

from __future__ import annotations

import csv
import gzip
import re
import statistics as st
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

MIB = 1024.0  # kiB per MiB

TS = r"(\d+)\.(\d\d)\.(\d{3})\.(\d{3})"
RE_STATE = re.compile(TS + r" .*cache state: (\d+) prompts?, ([\d.]+) MiB")
RE_TIMING = re.compile(TS + r" I slot print_timing: id\s+\d+ \| task \d+ \|\s+total time")

TELEMETRY_COLUMNS = (
    "t_epoch",
    "majflt",
    "memavailable_kib",
    "server_vmswap_kib",
    "server_rss_anon_kib",
    "server_rss_file_kib",
    "server_rss_shmem_kib",
)


def rel_s(m: Sequence[str]) -> float:
    return int(m[0]) * 60 + int(m[1]) + int(m[2]) / 1e3 + int(m[3]) / 1e6


def telemetry_rows(path: Path) -> list[dict]:
    """The columns this module needs from a telemetry CSV (gzip or plain); a missing or
    unparsable cell is None."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    out = []
    with opener(path, "rt") as fh:
        for r in csv.DictReader(fh):
            row = {}
            for k in TELEMETRY_COLUMNS:
                try:
                    row[k] = float(r[k])
                except (KeyError, ValueError, TypeError):
                    row[k] = None
            out.append(row)
    return out


def cache_series(
    reqs: Iterable[Mapping], run_id: str, log_path: Path
) -> list[tuple[float, int, float]]:
    """``[(epoch, n_prompts, MiB)]`` of the host prompt cache, from the server log of one instance.
    ``reqs`` are the request records of the session (``server_run_id``, ``client.t_end_epoch``).
    Empty if the log is missing, has no ``print_timing`` lines, or their count differs from the
    number of requests (the alignment would be a guess)."""
    log_path = Path(log_path)
    if not log_path.exists():
        return []
    ends = sorted(
        r["client"]["t_end_epoch"]
        for r in reqs
        if r["server_run_id"] == run_id and r["client"].get("t_end_epoch")
    )
    timings, states = [], []
    for line in log_path.read_text(errors="replace").splitlines():
        m = RE_TIMING.match(line)
        if m:
            timings.append(rel_s(m.groups()))
            continue
        m = RE_STATE.match(line)
        if m:
            g = m.groups()
            states.append((rel_s(g[:4]), int(g[4]), float(g[5])))
    if not timings or len(timings) != len(ends):
        return []
    off = st.median(e - t for e, t in zip(ends, timings, strict=True))
    return [(off + t, n, mib) for t, n, mib in states]


def cache_in_window(
    cache: Sequence[tuple[float, int, float]], t0: float, t1: float
) -> tuple[tuple[int, float] | None, tuple[int, float] | None]:
    """``(prompts, MiB)`` of the host prompt cache at the first and last save inside
    ``[t0 - 1, t1 + 1]`` (None, None if there is none). The last slot is saved only when the next
    fresh request arrives, so the value at the end of a window omits it."""
    c_in = [(n, m) for (t, n, m) in cache if t0 - 1 <= t <= t1 + 1]
    return (c_in[0] if c_in else None, c_in[-1] if c_in else None)


def window_figures(
    rows: Sequence[Mapping], t0: float, t1: float, cache: Sequence[tuple[float, int, float]]
) -> dict | None:
    """Memory figures of the window ``t0 <= t <= t1`` (None if there is no telemetry in it):
    ``(first, last)`` of RssAnon, RssFile and RssShmem in MiB, ``vmswap`` (first, last, max) in MiB,
    the change in major faults, the minimum MemAvailable in GiB and the host prompt cache
    ``(prompts, MiB)`` at the first and last save inside the window (the last slot is saved only
    when the next fresh request arrives, so the value at the end omits it)."""
    sel = [r for r in rows if t0 <= (r["t_epoch"] or 0) <= t1]
    if not sel:
        return None
    first, last = sel[0], sel[-1]

    def mib(row: Mapping, k: str) -> float | None:
        return None if row[k] is None else row[k] / MIB

    vm = [r["server_vmswap_kib"] for r in sel if r["server_vmswap_kib"] is not None]
    mem = [r["memavailable_kib"] for r in sel if r["memavailable_kib"] is not None]
    fl = [r["majflt"] for r in sel if r["majflt"] is not None]
    cache_first, cache_last = cache_in_window(cache, t0, t1)
    return {
        "anon": (mib(first, "server_rss_anon_kib"), mib(last, "server_rss_anon_kib")),
        "file": (mib(first, "server_rss_file_kib"), mib(last, "server_rss_file_kib")),
        "shmem": (mib(first, "server_rss_shmem_kib"), mib(last, "server_rss_shmem_kib")),
        "vmswap": (vm[0] / MIB, vm[-1] / MIB, max(vm) / MIB) if vm else (None, None, None),
        "faults": (fl[-1] - fl[0]) if fl else None,
        "memavail_min_gib": min(mem) / MIB / MIB if mem else None,
        "cache_first": cache_first,
        "cache_last": cache_last,
    }
