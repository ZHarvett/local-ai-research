"""Probing of placement values: max-fit cache size and N_fit (step plan 5.4, P6 to P9).

A *step* starts a server with one candidate value, sends the cell's longest request (Request A at
the deepest depth, then Request B) and measures the VRAM that stays free. A candidate **passes** if
the server starts, ``fit`` did not change the explicit placement, and at least ``MARGIN_MIB`` MiB of
VRAM stayed free through the longest request (section 3.3). The searches below are pure functions
over an ``evaluate(value) -> StepResult`` callback, so they are tested against a fake VRAM model.

``search_max_fit``: the largest cache size (a multiple of 256 MiB) that passes. A bracketing
bisection seeded by a linear prediction (VRAM use grows about 1 MiB per MiB of cache): start at
4096 MiB, jump to the cache size the measured free VRAM predicts, and finish with a verified pair
(passes at m, fails at m + 256). Typically three steps; at most about log2(range / 256) + 2.

``search_n_fit``: the smallest ``--n-cpu-moe`` that passes, by plain bisection (more layers on the
CPU means more free VRAM). Used only when N_fit cannot be read from P1's log.

Results are cached in ``data/probes/cache.jsonl`` (append-only, latest entry wins) under a key made
of everything that changes the VRAM picture: the kind, context, ubatch, MTP on or off (and draft
length), KV types, flash attention, slots, the placement family, the deepest depth, margin, step,
the llama.cpp commit, the model SHA-256 and the card's total VRAM.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

STEP_MIB = 256
MARGIN_MIB = 512
START_MIB = 4096

# Fields that change how much VRAM a placement search sees. ``moe_cache_mib`` and ``n_cpu_moe`` are
# deliberately absent: they are the quantities being searched.
KEY_FIELDS = (
    "context",
    "ubatch",
    "batch",
    "cache_type_k",
    "cache_type_v",
    "flash_attn",
    "parallel",
    "fit",
    "fit_target",
    "cpu_moe",
    "spec_type",
    "spec_draft_n_max",
    "threads",
    "load_mode",
)


@dataclass
class StepResult:
    ok: bool
    free_mib: float | None = None  # min free VRAM across load and the longest request
    reason: str | None = None  # startup_failure, oom_at_load, fit_intervened, margin, crash ...
    detail: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    value: int | None
    steps: list[dict]  # [{"value": v, "ok": bool, "free_mib": f, "reason": r}, ...] in order
    verified: bool = False  # a pass at value and a fail one step above (or the cap)


def _snap(v: int, step: int) -> int:
    return (v // step) * step


def search_max_fit(
    evaluate: Callable[[int], StepResult],
    *,
    cap_mib: int,
    start_mib: int = START_MIB,
    step: int = STEP_MIB,
    margin: int = MARGIN_MIB,
) -> SearchResult:
    cap = _snap(cap_mib, step)
    steps: list[dict] = []
    known: dict[int, StepResult] = {}

    def ev(c: int) -> StepResult:
        r = evaluate(c)
        known[c] = r
        steps.append({"value": c, "ok": r.ok, "free_mib": r.free_mib, "reason": r.reason})
        return r

    if cap < step:
        return SearchResult(None, steps)
    c = min(_snap(start_mib, step), cap)
    last = ev(c)
    while True:
        oks = [v for v, r in known.items() if r.ok]
        fails = [v for v, r in known.items() if not r.ok]
        lo = max(oks, default=0)  # 0: nothing known to pass
        hi = min((v for v in fails if v > lo), default=cap + step)  # cap + step: beyond the cap
        if hi - lo <= step:
            return SearchResult(lo if lo >= step else None, steps, verified=lo >= step)
        pred = None
        if last.free_mib is not None:
            pred = c + math.floor((last.free_mib - margin) / step) * step
        if pred is not None and lo < pred < hi:
            nxt = pred
        elif pred is not None and pred <= lo:
            nxt = lo + step  # the prediction says "here": verify the next step up
        elif pred is not None and pred >= hi:
            nxt = hi - step  # the prediction says "higher" than known to fail: verify just below
        else:
            nxt = lo + max(1, ((hi - lo) // step) // 2) * step  # no number to go on: bisect
        nxt = max(lo + step, min(nxt, hi - step))
        c = nxt
        last = ev(c)


def search_n_fit(evaluate: Callable[[int], StepResult], *, n_layer: int) -> SearchResult:
    """Smallest N in [0, n_layer] that passes, by bisection; None if even n_layer fails."""
    steps: list[dict] = []
    lo, hi = -1, n_layer + 1  # lo: assumed fail, hi: assumed pass (verified below)
    best: int | None = None
    while hi - lo > 1:
        mid = (lo + hi) // 2
        r = evaluate(mid)
        steps.append({"value": mid, "ok": r.ok, "free_mib": r.free_mib, "reason": r.reason})
        if r.ok:
            hi, best = mid, mid
        else:
            lo = mid
    return SearchResult(best, steps, verified=best is not None)


# ------------------------------------------------------------------------------ cache


def probe_key(
    kind: str,
    fields: dict,
    *,
    d_max: int,
    llama_commit: str,
    model_sha256: str,
    gpu_total_mib: float | None,
    margin: int = MARGIN_MIB,
    step: int = STEP_MIB,
) -> str:
    picked = {k: fields.get(k) for k in KEY_FIELDS}
    mtp = picked["spec_type"] not in (None, "none")
    if not mtp:  # "none" and unset are the same configuration
        picked["spec_type"] = picked["spec_draft_n_max"] = None
    material = {
        "kind": kind,
        "fields": picked,
        "mtp": mtp,
        "d_max": d_max,
        "margin": margin,
        "step": step,
        "llama_commit": llama_commit,
        "model_sha256": model_sha256,
        "gpu_total_mib": gpu_total_mib,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:20]


class ProbeCache:
    """Append-only JSONL; the latest entry for a key wins."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def get(self, key: str) -> dict | None:
        if not self.path.exists():
            return None
        found = None
        for line in self.path.read_text().splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("key") == key:
                found = obj
        return found

    def put(self, key: str, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps({"key": key, **entry}, sort_keys=True) + "\n")


def result_entry(kind: str, res: SearchResult, **extra) -> dict:
    return {
        "kind": kind,
        "value": res.value,
        "verified": res.verified,
        "steps": res.steps,
        "n_steps": len(res.steps),
        **extra,
    }


__all__ = [
    "KEY_FIELDS",
    "MARGIN_MIB",
    "STEP_MIB",
    "ProbeCache",
    "SearchResult",
    "StepResult",
    "probe_key",
    "result_entry",
    "search_max_fit",
    "search_n_fit",
]
