"""Analysis of sweep sessions: units, attempts, exclusion rules and the derived metrics of §5.3.

    from smallpc import analysis
    res = analysis.analyse([Path("data/raw/mini-20261109")])

Decisions (docs/decisions.md, "WP10 decisions"):

1. The unit of measurement is one repetition of one cell: (session, cell, repetition). When
   attempt-2 records exist for a unit they replace the attempt-1 records in every headline number;
   attempt 1 stays in the diagnostics. Warm-up and canary records never enter cell statistics;
   canaries are summarised separately.
2. A unit is *clean* if no request in it carries a flag and its session is not flagged for drift
   (attempt-1 units against ``drift.main``, attempt-2 units against ``drift.rerun``; a session
   without that drift record is "not assessed" and does not exclude). Headline statistics use clean
   units only and show ``n_clean`` and ``n_total``.
6. The cell record's ``server_instance`` is never used: the mini-sweep data has it one too high on
   final records. Only request records, cell summaries and telemetry references are read.

Records are read with ``Store.load()`` (complete batches only), never line by line. Per-repetition
values are keyed ``"<session>:<repetition>"`` so that sessions can be pooled and paired.
"""

from __future__ import annotations

import json
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import flags, parsers, stats, telemetry
from .sweep.records import Store

# Repetition indices of the canaries (step plan 5.1 / WP9: smallpc.sweep.session.CANARY_BASE).
CANARY_BASE = {"main": 100, "rerun": 110}
CANARY_DEPTH = 16384
DEPTH_METRICS = ("pp_fresh", "pp_inc", "tg", "t_turn_400", "t_b", "t_reread", "ttft", "predicted_n")
REP_METRICS = ("t_turn_400_mean", "t_reread_mean", "acceptance", "acceptance_short")
REQUEST_KINDS = ("short", "A", "B")
SHORT_TOKENS = 2048
SWAP_HEAVY_MIB = 64.0  # swap sensitivity (plan v1.4, 5.5): units with more swap growth than this


@dataclass
class LoadedSession:
    dir: Path
    id: str
    meta: dict
    requests: list[dict]
    cells: list[dict]  # cell records (never used for server_instance)
    summaries: dict[tuple[str, str], dict]  # (cell, config_hash) -> cell summary
    events: list[dict]
    torn_lines: int = 0
    incomplete_batches: int = 0
    warnings: list[str] = field(default_factory=list)


def load_session(path: str | Path) -> LoadedSession:
    d = Path(path)
    meta = json.loads((d / "session.json").read_text())
    loaded = Store(d / "records.jsonl").load()
    summaries: dict[tuple[str, str], dict] = {}
    for f in sorted((d / "cells").glob("*.json")):
        s = json.loads(f.read_text())
        summaries[(s["cell"], s["config_hash"])] = s
    events = []
    ev = d / "events.jsonl"
    if ev.exists():
        for line in ev.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    sess = LoadedSession(
        d,
        meta["session_id"],
        meta,
        loaded.requests,
        loaded.cells,
        summaries,
        events,
        loaded.torn_lines,
        loaded.incomplete_batches,
    )
    if loaded.torn_lines or loaded.incomplete_batches:
        sess.warnings.append(
            f"{sess.id}: {loaded.torn_lines} unparsable line(s) and "
            f"{loaded.incomplete_batches} incomplete batch(es) ignored"
        )
    return sess


# ------------------------------------------------------------------------------ per-request math


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def per_token_ms(rec: dict) -> float | None:
    """Time per generated token of a request: the server's ``predicted_per_token_ms``, else
    ``predicted_ms / predicted_n``."""
    t = (rec.get("timings") or {}).get("predicted_per_token_ms")
    if t:
        return float(t)
    if rec.get("predicted_n") and rec.get("predicted_ms") is not None:
        return rec["predicted_ms"] / rec["predicted_n"]
    return None


def pair_metrics(depth: int, a: dict, b: dict) -> dict:
    """The §5.3 metrics of one depth from Request A and Request B (real ``timings`` fields).

    * PP_fresh = A ``prompt_per_second`` (None if A reports ``cache_n`` > 32: ``warm_prefill``);
    * PP_inc = B ``prompt_n`` / B prompt time (s);
    * TG = B ``predicted_per_second``;
    * T_turn_400 = (B ``prompt_ms`` + 400 x B per-token ms) / 1000, in seconds;
    * T_B = (B ``prompt_ms`` + ``predicted_ms``) / 1000, reported with ``predicted_n``;
    * T_reread = d / PP_fresh;
    * TTFT = B client-side ``ttft_s``.
    TG and T_turn_400 are None when B generated fewer than 100 tokens (``short_gen``).
    """
    clean_a = not flags.warm_prefill(a)
    short = flags.short_gen(b)
    pp_fresh = a.get("prompt_per_second") if clean_a else None
    ptm = per_token_ms(b)
    prompt_ms = b.get("prompt_ms")
    return {
        "pp_fresh": pp_fresh,
        "pp_inc": (b["prompt_n"] / (prompt_ms / 1000.0))
        if b.get("prompt_n") and prompt_ms
        else None,
        "tg": None if short else b.get("predicted_per_second"),
        "t_turn_400": None
        if short or ptm is None or prompt_ms is None
        else (prompt_ms + 400 * ptm) / 1000.0,
        "t_b": (prompt_ms + b["predicted_ms"]) / 1000.0
        if prompt_ms is not None and b.get("predicted_ms") is not None
        else None,
        "t_reread": depth / pp_fresh if pp_fresh else None,
        "ttft": (b.get("client") or {}).get("ttft_s"),
        "predicted_n": b.get("predicted_n"),
    }


def _accept(recs: list[dict]) -> tuple[int, int]:
    drafts = [(r["draft_n_accepted"] or 0, r["draft_n"]) for r in recs if r.get("draft_n")]
    return sum(a for a, _ in drafts), sum(n for _, n in drafts)


# ----------------------------------------------------------------------------------- units


def drift_state(sess: LoadedSession, attempt: int) -> dict:
    """The drift verdict for units of this attempt: attempt 1 uses ``drift.main``, attempt 2 uses
    ``drift.rerun`` (the re-run's own canaries). As the runner records it: ``session.json`` ->
    ``drift[which] = {flag, complete, metrics, ...}``."""
    which = "main" if attempt == 1 else "rerun"
    d = (sess.meta.get("drift") or {}).get(which)
    if not d or not d.get("complete"):
        return {"which": which, "state": "not assessed", "flagged": False}
    return {"which": which, "state": "drift" if d.get("flag") == "drift" else "ok",
            "flagged": d.get("flag") == "drift"}  # fmt: skip


def build_units(sessions: list[LoadedSession]) -> list[dict]:
    """Every (session, cell, repetition) with its final attempt, superseded attempt-1 records,
    flags, clean/not clean and the per-depth metrics."""
    groups: dict[tuple, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    sess_of = {s.id: s for s in sessions}
    for s in sessions:
        for r in s.requests:
            if r["role"] != "measured" or r["kind"] not in REQUEST_KINDS:
                continue  # warm-ups and canaries never enter cell statistics
            groups[(s.id, r["cell"], r["repetition"])][r["attempt"]].append(r)
    cell_depths: dict[str, set[int]] = defaultdict(set)
    for (_, cell, _), by_att in groups.items():
        for reqs in by_att.values():
            cell_depths[cell] |= {r["depth"] for r in reqs if r["kind"] in ("A", "B")}
    units = []
    for (sid, cell, rep), by_att in sorted(groups.items()):
        final = max(by_att)
        for att in sorted(by_att):
            reqs = sorted(by_att[att], key=lambda r: r["position"])
            u = _unit(sess_of[sid], cell, rep, att, reqs, cell_depths[cell])
            u["superseded"] = att != final
            u["superseded_by_attempt"] = final if att != final else None
            units.append(u)
    return units


_CSV_CACHE: dict[str, list[dict]] = {}


def _csv_rows(path: Path) -> list[dict] | None:
    key = str(path)
    if key not in _CSV_CACHE:
        try:
            _CSV_CACHE[key] = telemetry.read_csv(path)
        except (OSError, ValueError, EOFError):
            return None
    return _CSV_CACHE[key]


def unit_swap_activity(
    sess: LoadedSession, cell: str, config_hash: str, rep: int, attempt: int
) -> tuple[float | None, str]:
    """``(swap_activity_mib, source)`` of one unit's window: from the cell summary (sessions since
    plan v1.4), else derived from the instance's telemetry CSV between the window's start and end
    (older sessions such as the mini-sweep), else ``(None, "not available")``."""
    summ = sess.summaries.get((cell, config_hash)) or {}
    for ins in summ.get("instances", []):
        for w in ins.get("windows", []):
            if w.get("repetition") != rep or w.get("attempt") != attempt:
                continue
            if w.get("swap_activity_mib") is not None:
                return float(w["swap_activity_mib"]), "summary"
            f = (ins.get("telemetry") or {}).get("file")
            if f and w.get("t0_epoch") is not None and w.get("t1_epoch") is not None:
                rows = _csv_rows(sess.dir / f)
                if rows is not None:
                    seg = telemetry.window(rows, w["t0_epoch"], w["t1_epoch"])
                    v = flags.swap_activity(seg)["swap_activity_mib"]
                    if v is not None:
                        return float(v), "telemetry"
    return None, "not available"


def _unit(
    sess: LoadedSession, cell: str, rep: int, attempt: int, reqs: list[dict], depths: set[int]
) -> dict:
    flag_set = sorted({f for r in reqs for f in r.get("flags", [])})
    by_depth: dict[int, dict[str, dict]] = defaultdict(dict)
    short = None
    for r in reqs:
        if r["kind"] == "short":
            short = r
        else:
            by_depth[r["depth"]][r["kind"]] = r
    problems = []
    if set(by_depth) != depths or any({"A", "B"} - set(v) for v in by_depth.values()):
        problems.append("incomplete")
    drift = drift_state(sess, attempt)
    reasons = list(flag_set) + problems + (["drift"] if drift["flagged"] else [])
    metrics = {
        d: pair_metrics(d, v["A"], v["B"]) for d, v in sorted(by_depth.items()) if len(v) == 2
    }
    tt = [m["t_turn_400"] for m in metrics.values()]
    rr = [m["t_reread"] for m in metrics.values()]
    complete = bool(metrics) and not problems
    b_recs = [v["B"] for v in by_depth.values() if "B" in v]
    acc_b, acc_s = _accept(b_recs), _accept([short] if short else [])
    swap, swap_source = unit_swap_activity(sess, cell, reqs[0]["config_hash"], rep, attempt)
    return {
        "swap_activity_mib": swap,
        "swap_source": swap_source,
        "session": sess.id,
        "cell": cell,
        "repetition": rep,
        "attempt": attempt,
        "key": f"{sess.id}:{rep}",
        "config_hash": reqs[0]["config_hash"],
        "windows": sorted({r["window_id"] for r in reqs if r.get("window_id")}),
        "flags": flag_set,
        "problems": problems,
        "drift": drift,
        "reasons": reasons,
        "clean": not reasons,
        "metrics": {str(d): m for d, m in metrics.items()},
        "rep": {
            "t_turn_400_mean": _mean(tt) if complete and None not in tt else None,
            "t_reread_mean": _mean(rr) if complete and None not in rr else None,
            "acceptance": acc_b[0] / acc_b[1] if acc_b[1] else None,
            "acceptance_short": acc_s[0] / acc_s[1] if acc_s[1] else None,
        },
        "draft_counts": {"B": list(acc_b), "short": list(acc_s)},
        "short": None
        if short is None
        else {
            "pp": short.get("prompt_per_second"),
            "tg": short.get("predicted_per_second"),
            "predicted_n": short.get("predicted_n"),
        },
    }


# ------------------------------------------------------------------------------------ cells


def context_label(tokens: int | None) -> str | None:
    if not tokens:
        return None
    return f"{tokens // 1024}K" if tokens % 1024 == 0 else str(tokens)


def _resolved(sess: LoadedSession, summary: dict | None) -> dict:
    if not summary or not summary.get("resolved_config"):
        return {}
    p = sess.dir / summary["resolved_config"]
    return tomllib.loads(p.read_text()) if p.exists() else {}


def final_status(sess: LoadedSession, cell: str, role: str = "measured") -> dict | None:
    """The last final cell record of a cell in a session (status, reason); never the instance."""
    last = None
    for c in sess.cells:
        if c["cell"] == cell and c["role"] == role and c.get("final"):
            last = c
    return last


def _vram_parts(instance: dict) -> dict:
    pl = (instance.get("parsed") or {}).get("placement") or {}
    cuda = lambda items: sum(  # noqa: E731
        i["mib"] for i in items or [] if str(i.get("device", "")).startswith("CUDA")
        and "Host" not in str(i.get("device", ""))
    )  # fmt: skip
    model = sum(
        v["mib"]
        for k, v in (pl.get("model_buffers") or {}).items()
        if k.startswith("CUDA") and "Host" not in k
    )
    vram = instance.get("vram") or {}
    parts = {
        "model_mib": model,
        "kv_mib": cuda(pl.get("kv_buffers")),
        "recurrent_mib": cuda(pl.get("recurrent_state_buffers")),
        "compute_mib": cuda(parsers.resident_compute_buffers(pl)),  # last reservation per context
        "total_mib": vram.get("total_mib"),
        "loaded_mib": vram.get("loaded_mib"),
        "peak_used_mib": vram.get("peak_used_mib"),
        "min_free_mib": vram.get("min_free_mib"),
    }
    # the expert cache (--moe-cache-mib) lives in VRAM but is not a llama.cpp buffer in the load log
    mc = (instance.get("parsed") or {}).get("moe_cache") or {}
    cache = ((mc.get("config") or {}).get("cache_mib")) if mc.get("present") else None
    parts["expert_cache_mib"] = float(cache) if cache else 0.0
    known = (
        parts["model_mib"]
        + parts["kv_mib"]
        + parts["recurrent_mib"]
        + parts["compute_mib"]
        + parts["expert_cache_mib"]
    )
    parts["other_mib"] = (
        None if parts["peak_used_mib"] is None else round(parts["peak_used_mib"] - known, 1)
    )
    parts["kv_type"] = (pl.get("kv") or {}).get("k_type")
    parts["expert_layers_on_cpu"] = pl.get("expert_layers_on_cpu")
    return parts


def merge_cache_stats(instances: list[dict]) -> dict:
    """Expert-cache statistics pooled over all server instances of a cell (everything the server
    served: warm-up, every repetition and attempt). Hit rates are for decode-sized batches only;
    prefill-sized batches report only how many experts were copied from the cache."""
    classes: dict[str, dict] = {}
    large = {"experts": 0, "mib": 0.0}
    cfg = None
    present = False
    for ins in instances:
        mc = (ins.get("parsed") or {}).get("moe_cache") or {}
        if not mc.get("present"):
            continue
        present = True
        cfg = cfg or mc.get("config")
        for c in mc["classes"]:
            k = classes.setdefault(
                c["name"],
                {"name": c["name"], "hits": 0, "misses": 0, "cpu": 0, "uploaded_mib": 0.0},
            )
            k["hits"] += c["hits"]
            k["misses"] += c["misses"]
            k["cpu"] += c.get("cpu", 0)
            k["uploaded_mib"] += c.get("uploaded_mib", 0.0)
        lb = mc.get("large_batch_copies") or {}
        large["experts"] += lb.get("experts", 0)
        large["mib"] += lb.get("mib", 0.0)
    for k in classes.values():
        n = k["hits"] + k["misses"]
        k["hit_rate_pct"] = round(100.0 * k["hits"] / n, 2) if n else None
    decode = next((c for c in classes.values() if "<" in c["name"]), None)
    return {
        "present": present,
        "classes": list(classes.values()),
        "decode_hit_rate_pct": decode["hit_rate_pct"] if decode else None,
        "large_batch_copies": large if present else None,
        "config": cfg,
        "instances": len(instances),
    }


def _stats_block(values: dict[str, float]) -> dict:
    vals = list(values.values())
    return {"values": values, "stats": stats.summarize(vals) if vals else None}


def _cell_entry(name: str, units: list[dict], sessions: list[LoadedSession]) -> dict:
    mine = [u for u in units if u["cell"] == name]
    finals = [u for u in mine if not u["superseded"]]
    clean = [u for u in finals if u["clean"]]
    sess_of = {s.id: s for s in sessions}
    summary_by_sess = {}
    for s_ in sessions:
        hashes = [u["config_hash"] for u in mine if u["session"] == s_.id]
        hashes += [
            c["config_hash"]
            for c in s_.cells
            if c["cell"] == name and c["role"] == "measured" and c.get("config_hash")
        ]
        found = next((s_.summaries[(name, h)] for h in hashes if (name, h) in s_.summaries), None)
        summary_by_sess[s_.id] = found
    summaries = [v for v in summary_by_sess.values() if v]
    first = summaries[0] if summaries else {}
    first_sess = next((sid for sid, v in summary_by_sess.items() if v), None)
    resolved = _resolved(sess_of[first_sess], first) if first_sess else {}
    context = resolved.get("context")
    coords = first.get("coords") or {}

    # final status: the worst over the sessions that have the cell
    statuses = []
    for s in sessions:
        rec = final_status(s, name)
        if rec is not None:
            statuses.append((s.id, rec["status"], rec.get("reason")))
    order = ["did_not_fit", "not_applicable", "interrupted", "server_died", "failed", "complete"]
    status, reason = (None, None)
    if statuses:
        worst = min(statuses, key=lambda x: order.index(x[1]) if x[1] in order else 99)
        status, reason = worst[1], worst[2]
    elif mine:
        status = "partial"  # requests but no final cell record

    # windows of the units' final attempts: the VRAM headroom of the cell
    free, peak_totals = [], []
    for u in finals:
        s = sess_of[u["session"]]
        summ = s.summaries.get((name, u["config_hash"])) or {}
        for ins in summ.get("instances", []):
            for w in ins.get("windows", []):
                if w["repetition"] == u["repetition"] and w["attempt"] == u["attempt"]:
                    if w.get("min_free_vram_mib") is not None:
                        free.append(w["min_free_vram_mib"])
                    if ins.get("vram", {}).get("total_mib") is not None:
                        peak_totals.append(ins["vram"]["total_mib"])
    min_free = min(free) if free else None
    total = max(peak_totals) if peak_totals else None

    instances = [i for sm in summaries for i in sm.get("instances", [])]
    last_inst = next(
        (i for i in reversed(instances) if (i.get("parsed") or {}).get("placement")), None
    )
    depths = sorted({int(d) for u in finals for d in u["metrics"]})
    depth_metrics: dict = {}
    for d in depths:
        depth_metrics[str(d)] = {
            m: _stats_block(
                {u["key"]: u["metrics"][str(d)][m] for u in clean
                 if str(d) in u["metrics"] and u["metrics"][str(d)][m] is not None}
            )
            for m in DEPTH_METRICS
        }  # fmt: skip
    rep_metrics = {
        m: _stats_block({u["key"]: u["rep"][m] for u in clean if u["rep"][m] is not None})
        for m in REP_METRICS
    }
    short = {
        m: _stats_block({u["key"]: u["short"][m] for u in clean if u["short"] and u["short"][m]})
        for m in ("pp", "tg")
    }
    b_acc = [sum(u["draft_counts"]["B"][i] for u in clean) for i in (0, 1)]
    s_acc = [sum(u["draft_counts"]["short"][i] for u in clean) for i in (0, 1)]
    mtp = (resolved.get("spec_type") not in (None, "none")) or any(
        u["draft_counts"]["B"][1] for u in mine
    )
    unit_flags = sorted({f for u in finals for f in u["reasons"]})
    return {
        "name": name,
        "profile": first.get("profile") or resolved.get("profile"),
        "coords": coords,
        "context": context,
        "context_label": context_label(context) or coords.get("context"),
        "config_hashes": sorted({u["config_hash"] for u in mine}),
        "has_context": context is not None or bool(coords.get("context")),
        "sessions": sorted({u["session"] for u in mine}),
        "status": status,
        "reason": reason,
        "resolved": {k: v for k, v in resolved.items() if k != "profile"},
        "mtp": bool(mtp),
        "cache_mib": resolved.get("moe_cache_mib") or 0,
        "n_total": len(finals),
        "n_clean": len(clean),
        "unit_flags": unit_flags,
        "flagged_units": [u["key"] for u in finals if not u["clean"]],
        "depths": depths,
        "depth_metrics": depth_metrics,
        "rep_metrics": rep_metrics,
        "short": short,
        "acceptance_pooled": {
            "B": b_acc[0] / b_acc[1] if b_acc[1] else None,
            "short": s_acc[0] / s_acc[1] if s_acc[1] else None,
            "all": (b_acc[0] + s_acc[0]) / (b_acc[1] + s_acc[1]) if b_acc[1] + s_acc[1] else None,
            "counts": {"B": b_acc, "short": s_acc},
            "note": "draft counts exist only for Request B and the short point: "
            "Request A (n_predict 0) has no drafts",
        },
        "min_free_vram_mib": min_free,
        "total_vram_mib": total,
        "peak_vram_mib": None if min_free is None or total is None else total - min_free,
        "vram": _vram_parts(last_inst) if last_inst else None,
        "cache": merge_cache_stats(instances),
        "placement_check": (last_inst or {}).get("placement_check"),
    }


# --------------------------------------------------------------------------- session health


def canary_summary(sess: LoadedSession) -> dict:
    """The canary records of one session (never part of cell statistics): per phase and
    start/end, PP_fresh at 16K (Request A), TG of the 16K Request B and TG of the short point."""
    out: dict = {}
    for which in CANARY_BASE:
        part = {}
        for role in ("canary_start", "canary_end"):
            rs = [
                r
                for r in sess.requests
                if r["role"] == role
                and r["attempt"] == 1
                and (r["repetition"] >= CANARY_BASE["rerun"]) == (which == "rerun")
            ]
            if not rs:
                continue

            def vals(kind: str, key: str, depth: int | None = None, rs=rs) -> list[float]:
                return [
                    r[key]
                    for r in rs
                    if r["kind"] == kind and (depth is None or r["depth"] == depth) and r.get(key)
                ]

            part[role] = {
                "repetitions": sorted({r["repetition"] for r in rs}),
                "flagged_requests": sum(1 for r in rs if r.get("flags")),
                "flags": sorted({f for r in rs for f in r.get("flags", [])}),
                "pp_fresh_16k": vals("A", "prompt_per_second", CANARY_DEPTH),
                "tg_16k": vals("B", "predicted_per_second", CANARY_DEPTH),
                "tg_short": vals("short", "predicted_per_second"),
            }
            for k in ("pp_fresh_16k", "tg_16k", "tg_short"):
                v = part[role][k]
                part[role][k] = {"values": v, "stats": stats.summarize(v) if v else None}
        if part:
            out[which] = part
    return out


def idle_waits(sess: LoadedSession) -> dict:
    """Idle-precondition waits from ``events.jsonl`` (``precondition`` events)."""
    pre = [e for e in sess.events if e.get("event") == "precondition"]
    waited = [(e.get("idle") or {}).get("waited_s") or 0.0 for e in pre]
    busy = [
        (e.get("idle") or {}).get("busy_pct")
        for e in pre
        if (e.get("idle") or {}).get("busy_pct") is not None
    ]
    return {
        "checks": len(pre),
        "failed_checks": sum(1 for e in pre if not e.get("ok")),
        "total_waited_s": round(sum(waited), 1),
        "max_waited_s": round(max(waited, default=0.0), 1),
        "busy_pct_max": max(busy, default=None),
    }


def session_info(sess: LoadedSession) -> dict:
    m = sess.meta
    git = m.get("git") or {}
    return {
        "session_id": sess.id,
        "spec": (m.get("spec") or {}).get("name"),
        "spec_path": (m.get("spec") or {}).get("path"),
        "spec_sha256": m.get("spec_sha256"),
        "manifest_sha256": m.get("manifest_sha256"),
        "sampling_sha256": m.get("sampling_sha256"),
        "git_commit": git.get("commit"),
        "git_dirty": git.get("dirty"),
        "dirty_paths": git.get("dirty_paths", []),
        "allow_dirty": bool(m.get("allow_dirty")),
        "request_commits": sorted({r["code_commit"] for r in sess.requests}),
        "run_commits": sorted(
            {r.get("code_commit") for r in m.get("runs", []) if r.get("code_commit")}
        ),
        "llama_cpp_commit": m.get("llama_cpp_commit"),
        "model_sha256": m.get("model_sha256"),
        "snapshot_ids": sorted({r["snapshot_id"] for r in sess.requests if r.get("snapshot_id")}),
        "state": m.get("state"),
        "created_utc": m.get("created_utc"),
        "runs": [
            {
                "mode": r.get("mode"),
                "inhibit_checked": (r.get("inhibit") or {}).get("checked"),
                "inhibit_active": (r.get("inhibit") or {}).get("active"),
            }
            for r in m.get("runs", [])
        ],
        "inhibit": {
            "checked": (m.get("inhibit") or {}).get("checked"),
            "active": (m.get("inhibit") or {}).get("active"),
        },
        "drift": {
            which: {
                "flag": d.get("flag"),
                "complete": d.get("complete"),
                "decided_on": d.get("decided_on"),
                "metrics": {
                    k: {kk: vv for kk, vv in v.items() if kk not in ("start_values", "end_values")}
                    for k, v in (d.get("metrics") or {}).items()
                },
            }
            for which, d in (m.get("drift") or {}).items()
        },
        "canaries": canary_summary(sess),
        "idle": idle_waits(sess),
        "warnings": sess.warnings,
    }


# --------------------------------------------------------------------------------- entry point


def analyse(paths: list[str | Path]) -> dict:
    """Load sessions and analyse them. Returns ``sessions``, ``cells`` (by name, in a stable
    order), ``units`` (every attempt of every unit) and ``diagnostics``."""
    sessions = [load_session(p) for p in paths]
    units = build_units(sessions)
    names = sorted({u["cell"] for u in units} | {
        c["cell"] for s in sessions for c in s.cells if c["role"] == "measured"
    })  # fmt: skip
    cells = {n: _cell_entry(n, units, sessions) for n in names}
    for n, c in cells.items():
        if len(c["config_hashes"]) > 1:
            c.setdefault("warnings", []).append(
                f"cell {n} has more than one config hash across sessions: {c['config_hashes']}"
            )
    diagnostics = []
    for u in units:
        if u["superseded"]:
            diagnostics.append(_diag(u, f"attempt {u['attempt']} of a unit re-run as attempt 2"))
        elif not u["clean"]:
            diagnostics.append(_diag(u, "flagged unit"))
    return {
        "sessions": [session_info(s) for s in sessions],
        "cells": cells,
        "units": units,
        "diagnostics": diagnostics,
        "swap_alt": swap_alternative(units, sessions, names, cells),
    }


def swap_alternative(
    units: list[dict], sessions: list[LoadedSession], names: list[str], cells: dict
) -> dict:
    """The swap sensitivity (plan v1.4, 5.5): every cell recomputed without the clean final units
    whose window shows more than 64 MiB of llama-server swap growth. ``removed`` lists them,
    ``unavailable`` the final units whose swap activity could not be determined (they stay in both
    versions). With nothing removed, ``cells`` is the main result itself."""
    final = [u for u in units if not u["superseded"]]
    removed = [
        u
        for u in final
        if u["clean"]
        and u["swap_activity_mib"] is not None
        and u["swap_activity_mib"] > SWAP_HEAVY_MIB
    ]
    info = [
        {
            "cell": u["cell"],
            "session": u["session"],
            "repetition": u["repetition"],
            "attempt": u["attempt"],
            "swap_activity_mib": u["swap_activity_mib"],
            "source": u["swap_source"],
        }
        for u in removed
    ]
    gone = {id(u) for u in removed}
    alt_cells = (
        {n: _cell_entry(n, [u for u in units if id(u) not in gone], sessions) for n in names}
        if removed
        else cells
    )
    return {
        "threshold_mib": SWAP_HEAVY_MIB,
        "removed": info,
        "already_excluded": [
            {
                "cell": u["cell"],
                "session": u["session"],
                "repetition": u["repetition"],
                "swap_activity_mib": u["swap_activity_mib"],
                "flags": u["reasons"],
            }
            for u in final
            if not u["clean"]
            and u["swap_activity_mib"] is not None
            and u["swap_activity_mib"] > SWAP_HEAVY_MIB
        ],
        "unavailable": [
            {"cell": u["cell"], "session": u["session"], "repetition": u["repetition"]}
            for u in final
            if u["swap_activity_mib"] is None
        ],
        "cells": alt_cells,
    }


def _diag(u: dict, why: str) -> dict:
    tt = u["rep"]["t_turn_400_mean"]
    if tt is None:  # a flagged unit may still have its figures; show what is computable
        vals = [m["t_turn_400"] for m in u["metrics"].values() if m["t_turn_400"] is not None]
        tt = _mean(vals) if vals else None
    return {
        "cell": u["cell"],
        "session": u["session"],
        "repetition": u["repetition"],
        "attempt": u["attempt"],
        "why": why,
        "flags": u["reasons"] or ["(none: unflagged attempt 1)"],
        "t_turn_400_mean": tt,
        "windows": u["windows"],
    }
