"""Deterministic synthetic sweep sessions for the WP10 tests (no GPU, no server).

``build_session(dir, session_id, cells, ...)`` writes a session directory with the same layout as a
real one: ``records.jsonl`` (batches, one per repetition, written through ``Store``), cell summaries,
resolved configs, ``session.json`` (with drift), ``events.jsonl`` and ``resolutions.jsonl``. All
numbers come from ``random.Random`` seeded by (seed, cell, repetition, attempt), so the output is
byte-identical from run to run.

``standard_cells()`` is the set the golden report is rendered from: a clean stock cell, candidates,
an MTP cell with draft counts, a cache cell with cache statistics, a did_not_fit cell for each
reason, a not_applicable cell, a flagged repetition with a clean attempt-2 replacement, one still
flagged after attempt 2, a short_gen request, and 5 repetitions in the 32K context.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field, replace
from pathlib import Path

from smallpc.sweep.records import Store, stamp_batch

TOTAL_MIB = 16311.0
DEPTHS = {
    32768: (8192, 16384, 24576),
    65536: (16384, 32768, 49152),
    131072: (32768, 65536, 98304),
}
DNF_REASONS = (
    "oom_at_load", "startup_failure", "startup_timeout", "context",
    "crash_mid_cell", "oom_runtime", "hung_server", "request_timeout",
)  # fmt: skip


@dataclass
class RepSpec:
    rep: int
    attempt: int = 1
    flags: tuple[str, ...] = ()  # put on every request of the unit (a window flag such as paging)
    short_gen: bool = False  # the first Request B generates 40 tokens and carries short_gen
    cache_miss: bool = False  # the first Request B reports a cache miss and carries cache_miss
    swap_mib: float | None = None  # swap_activity_mib of the window (a note, never a flag)
    faults: int | None = (
        None  # major faults of the window (also writes the window's paging figures)
    )
    anon_mib: tuple[float, float] | None = None  # RssAnon at the window's start and end
    slow: float = 1.0  # multiplies the cell's PP and TG for this repetition


@dataclass
class CellSpec:
    name: str
    profile: str = "candidate"
    context: int = 32768
    pp: float = 1000.0  # tokens/s of a fresh prompt
    tg: float = 80.0  # tokens/s of decoding
    reps: list[RepSpec] | None = None  # None: 5 clean repetitions
    status: str = "complete"  # complete | did_not_fit | not_applicable | interrupted
    reason: str | None = None
    min_free: float = 1200.0
    spec_type: str | None = None  # "draft-mtp" for an MTP cell
    accept: float = 0.7
    cache_mib: int = 0
    cache_hit_rate: float = 0.0  # decode-batch hit rate of the cache statistics
    kv_type: str = "q8_0"
    model_mib: float = 13500.0
    placement: str | None = None
    batch: str | None = None
    session_rerun_attempt: int = 2
    extra: dict = field(default_factory=dict)  # more fields of the resolved config (WP12)

    def rep_specs(self) -> list[RepSpec]:
        return self.reps if self.reps is not None else [RepSpec(i) for i in range(5)]


def chash(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def _timings_a(rng: random.Random, c: CellSpec, d: int) -> dict:
    pp = round(c.pp - d / 1024 * 1.5 + rng.uniform(-2, 2), 3)
    return {
        "cache_n": 0, "prompt_n": d, "prompt_ms": round(d / pp * 1000, 3),
        "prompt_per_second": pp, "predicted_n": 1, "predicted_ms": 12.0,
        "predicted_per_token_ms": 12.0, "predicted_per_second": 83.3,
    }  # fmt: skip


def _timings_b(rng: random.Random, c: CellSpec, d: int, n_pred: int, cache_n: int) -> dict:
    pp = round(c.pp * 0.92 + rng.uniform(-2, 2), 3)
    tg = round(c.tg - d / 1024 * 0.3 + rng.uniform(-0.4, 0.4), 3)
    per_tok = round(1000 / tg, 6)
    return {
        "cache_n": cache_n, "prompt_n": 3000, "prompt_ms": round(3000 / pp * 1000, 3),
        "prompt_per_second": pp, "predicted_n": n_pred, "predicted_ms": round(n_pred * per_tok, 3),
        "predicted_per_token_ms": per_tok, "predicted_per_second": tg,
    }  # fmt: skip


def _request(
    session_id: str,
    c: CellSpec,
    r: RepSpec,
    role: str,
    kind: str,
    depth: int,
    position: int,
    timings: dict,
    flags: list[str],
    *,
    cell_name: str | None = None,
    t0: float = 0.0,
    draft: tuple[int, int] | None = None,
    window_id: str | None = None,
) -> dict:
    name = cell_name or c.name
    return {
        "schema": 1, "record_type": "request", "session_id": session_id, "cell": name,
        "config_hash": chash(c.name), "attempt": r.attempt, "server_run_id": f"{session_id}-{name}-i0",
        "server_instance": 0, "code_commit": "abc1234567", "utc": "2026-01-01T00:00:00Z",
        "role": role, "warmup": role == "warmup", "kind": kind, "workload_id": f"w-{kind}-{depth}-r{r.rep}",
        "workload_kind": kind, "depth": depth, "variant": r.rep, "repetition": r.rep, "nonce": "n",
        "seed": 1, "position": position, "depth_order": [], "window_id": window_id,
        "n_predict": 400, "stream": kind == "B", "cache_prompt": True, "sampling": {}, "expected": {},
        "timings": timings, "cache_n": timings["cache_n"], "prompt_n": timings["prompt_n"],
        "prompt_ms": timings["prompt_ms"], "prompt_per_second": timings["prompt_per_second"],
        "predicted_n": timings["predicted_n"], "predicted_ms": timings["predicted_ms"],
        "predicted_per_second": timings["predicted_per_second"],
        "draft_n": None if draft is None else draft[0],
        "draft_n_accepted": None if draft is None else draft[1],
        "stop_type": "limit", "truncated": False, "id_slot": 0,
        "client": {
            "t_start_epoch": t0, "t_end_epoch": t0 + 1.0, "wall_s": 1.0,
            "ttft_s": round(timings["prompt_ms"] / 1000 + 0.05, 3) if kind == "B" else None,
            "http_status": 200,
        },
        "snapshot_id": "5ca1ab1e5ca1ab1e", "telemetry": {}, "free_vram_min_mib": c.min_free,
        "flags": flags, "flag_detail": {},
    }  # fmt: skip


def unit_requests(session_id: str, c: CellSpec, r: RepSpec, seed: int) -> list[dict]:
    rng = random.Random(f"{seed}-{c.name}-{r.rep}-{r.attempt}")
    if r.slow != 1.0:
        c = replace(c, pp=c.pp * r.slow, tg=c.tg * r.slow)
    window = f"{c.name}-{chash(c.name)[:8]}-r{r.rep}-a{r.attempt}"
    flags = sorted(r.flags)
    mtp = c.spec_type == "draft-mtp"

    def drafts(n: int) -> tuple[int, int] | None:
        if not mtp:
            return None
        return n, int(round(n * c.accept))

    out = []
    short = _timings_b(rng, c, 2048, 400, 0) | {"prompt_n": 2048, "cache_n": 0}
    short["prompt_ms"] = round(2048 / (c.pp + rng.uniform(-2, 2)) * 1000, 3)
    short["prompt_per_second"] = round(2048 / short["prompt_ms"] * 1000, 3)
    out.append(_request(session_id, c, r, "measured", "short", 2048, 0, short, list(flags),
                        draft=drafts(300), window_id=window))  # fmt: skip
    pos = 1
    first_b = True
    for d in DEPTHS[c.context]:
        out.append(_request(session_id, c, r, "measured", "A", d, pos, _timings_a(rng, c, d),
                            list(flags), window_id=window))  # fmt: skip
        pos += 1
        n_pred, cache_n, fl = 400, d, list(flags)
        if first_b and r.short_gen:
            n_pred, fl = 40, sorted({*flags, "short_gen"})
        if first_b and r.cache_miss:
            cache_n, fl = 0, sorted({*flags, "cache_miss"})
        first_b = False
        out.append(_request(session_id, c, r, "measured", "B", d, pos,
                            _timings_b(rng, c, d, n_pred, cache_n), fl, draft=drafts(280),
                            window_id=window))  # fmt: skip
        pos += 1
    for i, q in enumerate(out):
        q["client"]["t_start_epoch"] = float(r.rep * 100 + i)
        q["client"]["t_end_epoch"] = float(r.rep * 100 + i) + 1.0
    return out


def _summary(c: CellSpec, session_id: str) -> dict:
    h = chash(c.name)
    insts = []
    attempts = sorted({r.attempt for r in c.rep_specs()}) if c.status == "complete" else []
    for a in attempts:
        reps = [r for r in c.rep_specs() if r.attempt == a]
        classes = []
        if c.cache_mib:
            n = 100000
            hits = int(n * c.cache_hit_rate)
            classes = [
                {"name": "ubatch <= 8", "hits": hits, "misses": n - hits, "cpu": 0,
                 "hit_rate_pct": 100 * c.cache_hit_rate, "uploaded_mib": 1500.5},
                {"name": "ubatch > 8", "hits": 0, "misses": 0, "cpu": 0, "hit_rate_pct": 0.0,
                 "uploaded_mib": 0.0},
            ]  # fmt: skip
        insts.append(
            {
                "instance": len(insts), "run_id": f"{session_id}-{c.name}-i{len(insts)}",
                "attempt": a, "telemetry": {"file": None},
                "vram": {"total_mib": TOTAL_MIB, "loaded_mib": 14000.0, "peak_used_mib": TOTAL_MIB - c.min_free,
                         "min_free_mib": c.min_free},
                "windows": [
                    {"window_id": f"{c.name}-{h[:8]}-r{r.rep}-a{a}", "repetition": r.rep,
                     "attempt": a, "min_free_vram_mib": c.min_free, "flags": sorted(r.flags),
                     **({} if r.swap_mib is None else {"swap_activity_mib": r.swap_mib}),
                     **_paging_figures(r)}
                    for r in reps
                ],
                "parsed": {
                    "placement": {
                        "model_buffers": {"CUDA0": {"count": 1, "mib": c.model_mib},
                                          "CPU_Mapped": {"count": 3, "mib": 6000.0}},
                        "kv_buffers": [{"device": "CUDA0", "mib": 340.0}],
                        "kv": {"mib": 340.0, "k_type": c.kv_type},
                        "recurrent_state_buffers": [{"device": "CUDA0", "mib": 62.81}],
                        "compute_buffers": [{"device": "CUDA0", "mib": 318.02},
                                            {"device": "CUDA_Host", "mib": 48.02}],
                        "expert_layers_on_cpu": 14,
                    },
                    "moe_cache": {
                        "present": bool(classes), "classes": classes,
                        "large_batch_copies": {"experts": 4321, "mib": 8000.0} if classes else None,
                        "config": {"cache_mib": float(c.cache_mib), "host_expert_mib": 9000.0,
                                   "cpu_share_pct": 0} if classes else None,
                    },
                },
                "placement_check": {"fit_setting": "on"},
            }
        )  # fmt: skip
    coords = {"context": f"{c.context // 1024}K"}
    if c.placement:
        coords["placement"] = c.placement
    if c.batch:
        coords["batch"] = c.batch
    return {
        "cell": c.name, "role": "measured", "profile": c.profile, "config_hash": h, "argv": [],
        "resolved_config": f"resolved/{c.name}.toml", "coords": coords, "resolution": {},
        "model_sha256": "m" * 64, "llama_cpp_commit": "c" * 40, "instances": insts, "flags": [],
    }  # fmt: skip


def _paging_figures(r: RepSpec) -> dict:
    """Window keys of a real summary that the WP12 decision tool reads (only if the repetition
    sets them, so the older golden reports are unchanged)."""
    if r.faults is None and r.anon_mib is None:
        return {}
    out: dict = {
        "paging": {"flag": "paging" if "paging" in r.flags else None,
                   "major_faults": r.faults or 0},
        "t0_epoch": float(r.rep * 100), "t1_epoch": float(r.rep * 100 + 9),
    }  # fmt: skip
    if r.anon_mib is not None:
        out["rss_anon_start_mib"], out["rss_anon_end_mib"] = r.anon_mib
    return out


def _resolved_toml(c: CellSpec) -> str:
    lines = [f'profile = "{c.profile}"', f"context = {c.context}"]
    if c.spec_type:
        lines.append(f'spec_type = "{c.spec_type}"')
    if c.cache_mib:
        lines.append(f"moe_cache_mib = {c.cache_mib}")
    for k, v in c.extra.items():
        lines.append(f'{k} = "{v}"' if isinstance(v, str) else f"{k} = {v}")
    return "\n".join(lines) + "\n"


def _cell_record(
    session_id: str,
    name: str,
    h: str | None,
    status: str,
    final: bool,
    reason,
    role="measured",
    attempt=1,
) -> dict:  # noqa: E501
    return {
        "schema": 1, "record_type": "cell", "session_id": session_id, "cell": name,
        "config_hash": h, "role": role, "status": status, "final": final, "reason": reason,
        "flags": ["did_not_fit"] if status == "did_not_fit" else [],
        "server_instance": 98765,  # deliberately wrong, as in the mini data: must never be used
        "exit_code": None, "attempt": attempt, "repetitions_done": [], "n_requests": 0,
        "load_time_s": None, "summary_file": None, "code_commit": "abc1234567",
        "utc": "2026-01-01T00:00:00Z",
    }  # fmt: skip


def build_session(
    root: Path,
    session_id: str,
    cells: list[CellSpec],
    *,
    seed: int = 7,
    spec_path: str = "configs/sweeps/fixture.toml",
    state: str = "complete",
    drift_main: str | None = None,
    drift_rerun: str | None | bool = False,
    canary: bool = True,
    allow_dirty: bool = False,
    inhibit_active: bool = True,
) -> Path:
    """Write the session ``root/session_id`` and return its directory. ``drift_main`` is None or
    ``"drift"``; ``drift_rerun`` False (no re-run drift record), None (not flagged) or ``"drift"``."""
    d = Path(root) / session_id
    (d / "cells").mkdir(parents=True)
    (d / "resolved").mkdir()
    store = Store(d / "records.jsonl")
    events: list[dict] = []
    resolutions = []
    for c in cells:
        h = chash(c.name)
        (d / "resolved" / f"{c.name}.toml").write_text(_resolved_toml(c))
        if c.status == "not_applicable":
            store.append_batch(
                stamp_batch(
                    [_cell_record(session_id, c.name, None, "not_applicable", True, c.reason)]
                )
            )
            resolutions.append(
                {"cell": c.name, "fields": None, "resolution": {}, "not_applicable": c.reason}
            )
            continue
        resolutions.append(
            {
                "cell": c.name,
                "fields": {"context": c.context},
                "resolution": {},
                "not_applicable": None,
            }
        )
        if c.status == "did_not_fit":
            store.append_batch(
                stamp_batch([_cell_record(session_id, c.name, h, "did_not_fit", True, c.reason)])
            )
            (d / "cells" / f"{c.name}-{h[:8]}.json").write_text(json.dumps(_summary(c, session_id)))
            continue
        # a warm-up batch with absurd speeds: if it ever leaked into cell statistics, tests would see it
        slow = {"cache_n": 0, "prompt_n": 8192, "prompt_ms": 5461333.333, "prompt_per_second": 1.5,
                "predicted_n": 128, "predicted_ms": 128000.0, "predicted_per_token_ms": 1000.0,
                "predicted_per_second": 1.0}  # fmt: skip
        warm = [_request(session_id, c, RepSpec(i), "warmup", "warmup", 8192, i, dict(slow), [])
                for i in range(2)]  # fmt: skip
        store.append_batch(stamp_batch(warm))
        for att in sorted({r.attempt for r in c.rep_specs()}):
            for r in [x for x in c.rep_specs() if x.attempt == att]:
                store.append_batch(stamp_batch(unit_requests(session_id, c, r, seed)))
            store.append_batch(
                stamp_batch(
                    [
                        _cell_record(
                            session_id,
                            c.name,
                            h,
                            c.status,
                            c.status != "interrupted",
                            None,
                            attempt=att,
                        )
                    ]
                )
            )
        (d / "cells" / f"{c.name}-{h[:8]}.json").write_text(json.dumps(_summary(c, session_id)))
        events.append({"event": "precondition", "cell": c.name, "ok": True,
                       "idle": {"waited_s": 0.0, "busy_pct": 2.5}})  # fmt: skip
    if canary:
        cc = CellSpec("canary", pp=1000.0, tg=80.0)
        for role, base, name in (
            ("canary_start", 100, "canary-start"),
            ("canary_end", 103, "canary-end"),
        ):
            for i in range(3):
                r = RepSpec(base + i)
                rng = random.Random(f"{seed}-{name}-{i}")
                recs = [
                    _request(session_id, cc, r, role, "short", 2048, 0, _timings_b(rng, cc, 2048, 400, 0) | {"prompt_n": 2048, "cache_n": 0}, [], cell_name=name),
                    _request(session_id, cc, r, role, "A", 16384, 1, _timings_a(rng, cc, 16384), [], cell_name=name),
                    _request(session_id, cc, r, role, "B", 16384, 2, _timings_b(rng, cc, 16384, 400, 16384), [], cell_name=name),
                ]  # fmt: skip
                store.append_batch(stamp_batch(recs))
            store.append_batch(
                stamp_batch(
                    [
                        _cell_record(
                            session_id, name, chash("canary"), "complete", True, None, role=role
                        )
                    ]
                )
            )

    def drift_entry(flag):
        return {"flag": flag, "complete": True, "decided_on": ["pp_fresh_16k", "tg_16k"],
                "metrics": {"pp_fresh_16k": {"flag": flag, "relative_difference": 0.08 if flag else 0.002,
                                             "threshold": 0.05, "start_values": [1], "end_values": [1]}}}  # fmt: skip

    drift = {"main": drift_entry(drift_main)}
    if drift_rerun is not False:
        drift["rerun"] = drift_entry(drift_rerun)
    session = {
        "schema": 1, "session_id": session_id, "created_utc": "2026-01-01T00:00:00Z",
        "spec": {"name": "fixture", "path": spec_path},
        "spec_sha256": "a" * 64, "manifest_sha256": "b" * 64, "sampling_sha256": "d" * 64,
        "git": {"commit": "f" * 40, "short": "f" * 10, "dirty": allow_dirty,
                "dirty_paths": ["src/smallpc/sweep/"] if allow_dirty else []},
        "allow_dirty": allow_dirty, "llama_cpp_commit": "c" * 40, "model_sha256": "m" * 64,
        "runs": [{"mode": "run", "code_commit": "abc1234567",
                  "inhibit": {"checked": True, "active": inhibit_active}}],
        "inhibit": {"checked": True, "active": inhibit_active},
        "drift": drift, "state": state,
        "cell_order": [c.name for c in cells if c.status != "not_applicable"],
    }  # fmt: skip
    (d / "session.json").write_text(json.dumps(session))
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (d / "resolutions.jsonl").write_text("".join(json.dumps(e) + "\n" for e in resolutions))
    return d


def standard_cells() -> list[CellSpec]:
    """The cells of the golden report (32K and 64K)."""
    cells = [
        CellSpec("stock-32K", "stock", pp=950, tg=78, kv_type="f16", model_mib=13400),
        CellSpec("P1-32K-b2048", pp=1000, tg=84, placement="P1", batch="b2048"),
        CellSpec("P2-32K-b2048", pp=1002, tg=83.5, placement="P2", batch="b2048", min_free=700),
        CellSpec("MTP-32K", pp=990, tg=95, spec_type="draft-mtp", accept=0.7, placement="P1"),
        CellSpec("P4-32K-b2048", pp=1010, tg=80, cache_mib=2048, cache_hit_rate=0.62, placement="P4",
                 batch="b2048", model_mib=13000),
        CellSpec("rerun-ok-32K", pp=1005, tg=82,
                 reps=[RepSpec(0), RepSpec(1), RepSpec(2, flags=("paging",)), RepSpec(2, attempt=2),
                       RepSpec(3), RepSpec(4)]),
        CellSpec("rerun-bad-32K", pp=1001, tg=82,
                 reps=[RepSpec(0), RepSpec(1, cache_miss=True), RepSpec(1, attempt=2, cache_miss=True),
                       RepSpec(2), RepSpec(3), RepSpec(4)]),
        CellSpec("shortgen-32K", pp=1000, tg=81, reps=[RepSpec(0), RepSpec(1, short_gen=True),
                                                        RepSpec(2), RepSpec(3), RepSpec(4)]),
        # swap sensitivity: faster than stock overall, but its three swap-heavy repetitions (300 MiB
        # of VmSwap growth, no faults, so no flag) are slow; without them the ratio is below 1
        CellSpec("swap-32K-b2048", pp=1000, tg=84, placement="P3", batch="b2048",
                 reps=[RepSpec(0), RepSpec(1, swap_mib=300.0, slow=0.7), RepSpec(2, swap_mib=250.0, slow=0.7),
                       RepSpec(3, swap_mib=40.0), RepSpec(4, swap_mib=310.0, slow=0.7)]),
        CellSpec("NA-32K", status="not_applicable", reason="n_cpu_moe: n_fit resolves to -1; not applicable"),
        CellSpec("stock-64K", "stock", context=65536, pp=900, tg=70, kv_type="f16"),
        CellSpec("P1-64K-b2048", context=65536, pp=950, tg=76, placement="P1", batch="b2048"),
    ]  # fmt: skip
    cells += [
        CellSpec(f"dnf-{r}-32K", status="did_not_fit", reason=r, placement="P6")
        for r in DNF_REASONS
    ]
    return cells
