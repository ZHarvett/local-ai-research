"""Detectors for the section 5.6 flags. Pure functions: no I/O, no GPU, no clock.

Telemetry samples are dicts with the column names of ``smallpc.telemetry`` (booleans for the clock
event reasons, ``tctl_c``, ``majflt``, ``pswpin``). Request records use the real llama-server
``timings`` names: ``cache_n``, ``prompt_n``, ``predicted_n``, ... Thresholds are strict ("more
than 1%", "more than 1,000", "fewer than 100"), tested with integer arithmetic so exactly 1% is
not a flag.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

THERMAL_SAMPLE_FRACTION_PCT = 1  # more than 1% of samples in the window
TCTL_LIMIT_C = 95.0  # "reaches 95 C": at or above
MAJFLT_LIMIT = 1000  # more than 1,000 major page faults in the window
DRIFT_MIN_REL = 0.05  # max(95% CI, 5%)
WARM_PREFILL_CACHE_N = 32  # cache_n > 32 on a fresh request
CACHE_MISS_FRACTION = 0.95  # cache_n < 0.95 * d
SHORT_GEN_TOKENS = 100  # predicted_n < 100

# nvidia-smi clocks_event_reasons that count as a thermal or hardware slowdown. The software
# power cap is recorded (see POWER_CAP_COLUMN), not flagged.
GPU_SLOWDOWN_COLUMNS = (
    "reason_hw_slowdown",
    "reason_hw_thermal_slowdown",
    "reason_sw_thermal_slowdown",
    "reason_hw_power_brake_slowdown",
)
POWER_CAP_COLUMN = "reason_sw_power_cap"


def _truthy(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() in ("1", "true", "active"))


def _exceeds_pct(count: int, n: int, pct: int) -> bool:
    return count * 100 > n * pct


def thermal(samples: Sequence[dict]) -> dict:
    """GPU slowdown reason active, or Tctl >= 95 C, in more than 1% of the window's samples."""
    n = len(samples)
    gpu_n = sum(1 for s in samples if any(_truthy(s.get(c)) for c in GPU_SLOWDOWN_COLUMNS))
    tctl_n = sum(1 for s in samples if (t := s.get("tctl_c")) is not None and t >= TCTL_LIMIT_C)
    cap_n = sum(1 for s in samples if _truthy(s.get(POWER_CAP_COLUMN)))
    per_reason = {c: sum(1 for s in samples if _truthy(s.get(c))) for c in GPU_SLOWDOWN_COLUMNS}
    return {
        "flag": "thermal"
        if n and (_exceeds_pct(gpu_n, n, 1) or _exceeds_pct(tctl_n, n, 1))
        else None,
        "n_samples": n,
        "gpu_slowdown_samples": gpu_n,
        "gpu_slowdown_by_reason": per_reason,
        "tctl_ge_95_samples": tctl_n,
        "sw_power_cap_samples": cap_n,  # recorded, not flagged
        "max_tctl_c": max(
            (s["tctl_c"] for s in samples if s.get("tctl_c") is not None), default=None
        ),
        "max_gpu_temp_c": max(
            (s["gpu_temp_c"] for s in samples if s.get("gpu_temp_c") is not None), default=None
        ),
    }


def paging(samples: Sequence[dict], swap_in_tolerance_pages: int = 0) -> dict:
    """More than 1,000 major faults of llama-server, or any swap-in (``pswpin``), in the window.

    ``majflt`` is the cumulative per-process counter and ``pswpin`` the cumulative system counter,
    so the window's value is last minus first. Samples without the process (None) are skipped.
    The plan says "any swap-in", so the tolerance defaults to 0. ``pswpin`` is system-wide, so
    background swap-in (WP6 saw ~20 pages in 5 s on an idle machine) counts too; WP9 can pass a
    tolerance if that proves noisy, and the raw counts are always returned.
    """
    maj = [s["majflt"] for s in samples if s.get("majflt") is not None]
    swp = [s["pswpin"] for s in samples if s.get("pswpin") is not None]
    d_maj = (maj[-1] - maj[0]) if len(maj) >= 2 else 0
    d_swp = (swp[-1] - swp[0]) if len(swp) >= 2 else 0
    return {
        "flag": "paging" if d_maj > MAJFLT_LIMIT or d_swp > swap_in_tolerance_pages else None,
        "major_faults": d_maj,
        "swap_in_pages": d_swp,
        "process_samples": len(maj),
    }


def drift(start: dict, end: dict) -> dict:
    """Start and end canaries (``smallpc.stats.summarize`` results) differ by more than the larger
    of their 95% CIs (relative to their means) and 5%."""

    def rel_half(s: dict) -> float:
        if s.get("ci") is None or not s["mean"]:
            return 0.0
        return (s["ci"][1] - s["ci"][0]) / 2 / abs(s["mean"])

    rel = abs(end["mean"] - start["mean"]) / abs(start["mean"])
    threshold = max(rel_half(start), rel_half(end), DRIFT_MIN_REL)
    return {
        "flag": "drift" if rel > threshold else None,
        "relative_difference": rel,
        "threshold": threshold,
        "start_mean": start["mean"],
        "end_mean": end["mean"],
    }


def warm_prefill(rec: dict) -> bool:
    """A fresh request (Request A) that nevertheless reports cache_n > 32."""
    return (rec.get("cache_n") or 0) > WARM_PREFILL_CACHE_N


def cache_miss(rec: dict, depth: int) -> bool:
    """Request B served with cache_n < 0.95 * d."""
    return (rec.get("cache_n") or 0) < CACHE_MISS_FRACTION * depth


def short_gen(rec: dict) -> bool:
    """Request B generating fewer than 100 tokens."""
    return (rec.get("predicted_n") or 0) < SHORT_GEN_TOKENS


def request_flags(kind: str, rec: dict, depth: int | None = None) -> list[str]:
    """Flags of one request record. ``kind`` is "A" (fresh, n_predict 0) or "B" (append)."""
    out = []
    if kind == "A" and warm_prefill(rec):
        out.append("warm_prefill")
    if kind == "B":
        if depth is not None and cache_miss(rec, depth):
            out.append("cache_miss")
        if short_gen(rec):
            out.append("short_gen")
    return out


OOM_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"out of memory",
        r"cudaMalloc failed",
        r"failed to allocate .*buffer",
        r"unable to allocate",
        r"CUDA error: .*(memory|alloc)",
        r"failed to load model",
        r"error loading model",
        r"llama_model_load: error",
        r"failed to fit params",
        r"std::bad_alloc",
    )
)


def did_not_fit(startup_exit_code: int | None, log: str) -> dict:
    """Startup failure or out-of-memory.

    ``startup_exit_code`` is the server's exit code if it exited before becoming healthy, or None
    if it came up (a clean SIGINT exit code at shutdown is not a startup failure).
    """
    hits = [p.pattern for p in OOM_PATTERNS if p.search(log or "")]
    failed = startup_exit_code is not None and startup_exit_code != 0
    return {
        "flag": "did_not_fit" if failed or hits else None,
        "startup_exit_code": startup_exit_code,
        "log_matches": hits,
    }
