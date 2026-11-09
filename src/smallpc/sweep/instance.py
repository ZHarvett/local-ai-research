"""One server instance of a job: the section 5.3 protocol from preconditions to log parsing.

``Instance.run`` starts one llama-server through scripts/launch-server.sh, runs the warm-up and
the repetitions still missing, and always stops the server through scripts/stop-server.sh. It
returns an ``Outcome``; a session-level problem (hard precondition, refused launch) raises
``SessionAbort`` instead. A repetition is committed to ``records.jsonl`` only when it is complete
(see ``records``); the requests of an interrupted repetition go to ``events.jsonl`` as
``discarded_partial`` and the repetition is run again after a restart or resume.
"""

from __future__ import annotations

import signal
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from .. import flags, parsers
from ..scrub import Identity
from . import records as rec
from .client import Client, RequestTimeout, ServerGone
from .core import (
    Job,
    Outcome,
    SessionAbort,
    gzip_file,
    log_excerpt,
    min_free_mib,
    peak_used_mib,
    rows_between,
    utc_now,
)
from .spec import depth_order

if TYPE_CHECKING:
    from .session import Session

SHORT_LENGTH = 2048
WARMUP_LENGTH = 8192
WARMUP_PREDICT = 128
N_PREDICT = 400
LOG_FLAG = {"A": "A", "B": "B", "short": "fresh", "warmup": "fresh"}


class Instance:
    def __init__(self, sess: Session, job: Job, todo: list[int], number: int):
        self.s, self.job, self.todo, self.n = sess, job, todo, number
        self.env = sess.env
        self.run_id = f"{sess.sid}-{job.name}-{job.hash8}-i{number}"
        self.summary: dict[str, Any] = {
            "instance": number,
            "run_id": self.run_id,
            "attempt": job.attempt,
            "started_utc": utc_now(),
            "repetitions_planned": list(todo),
            "phases_s": {},
        }
        self.srv = self.env.server_factory()
        self.client: Client | None = None
        self.sampler: Any = None
        self.total_mib: float | None = None
        self.snapshot_id: str | None = None
        self.csv_rel = f"telemetry/{job.name}-{job.hash8}-i{number}.csv"
        self.gz_rel = self.csv_rel + ".gz"
        self.sampling = self._sampling()
        self.windows: list[dict] = []
        self.reps_done: list[int] = []
        self.n_requests = 0
        self.partial: list[dict] = []
        self.current: dict = {}
        self.stop_timeout = 60
        self.vram: dict[str, Any] = {}
        self.outcome: Outcome | None = None

    # ------------------------------------------------------------------ helpers

    def _sampling(self) -> dict:
        g = self.env.model.sampling.general
        keys = (
            "temperature",
            "top_p",
            "top_k",
            "min_p",
            "presence_penalty",
            "frequency_penalty",
            "repeat_penalty",
        )
        return {k: getattr(g, k) for k in keys if g is not None and getattr(g, k) is not None}

    @contextmanager
    def phase(self, name: str):
        self.s.progress(phase=name, cell=self.job.name)
        t0 = time.monotonic()
        try:
            yield
        finally:
            self.summary["phases_s"][name] = round(
                self.summary["phases_s"].get(name, 0.0) + time.monotonic() - t0, 2
            )

    def _rows(self) -> list[dict]:
        return list(self.sampler.rows) if self.sampler is not None else []

    # ------------------------------------------------------------------ run

    def run(self) -> Outcome:
        outcome: Outcome | None = None
        interrupted = False
        try:
            outcome = self._body()
        except KeyboardInterrupt:
            interrupted = True
            outcome = Outcome("interrupted", detail={"where": dict(self.current)})
            self._discard_partial("interrupted")
        except (ServerGone, RequestTimeout) as e:
            outcome = self._died(e)
        finally:
            self._cleanup(outcome)
        assert outcome is not None
        self.outcome = self._finish(outcome)
        if interrupted:
            raise KeyboardInterrupt
        return self.outcome

    def _body(self) -> Outcome:
        job, s = self.job, self.s
        with self.phase("preconditions"):
            pre, attempts = s.precondition_step(job.name, idle=True)
        self.summary["preconditions"] = {
            "final": pre["values"],
            "attempts": attempts,
            "warnings": pre["warnings"],
        }
        self.vram["before_launch_mib"] = self.env.gpu_used_mib()
        self.total_mib = self.env.gpu_total_mib()
        self.vram["total_mib"] = self.total_mib

        with self.phase("launch"):
            res = self.srv.start(job.toml_path, self.run_id)
        s.event(
            "server_start",
            cell=job.name,
            run_id=self.run_id,
            rc=res.rc,
            started=res.started,
            healthy=res.healthy,
            load_time_s=res.load_time_s,
        )
        self.summary["launch"] = {
            "rc": res.rc,
            "load_time_s": res.load_time_s,
            "started": res.started,
            "healthy": res.healthy,
            "reason": res.reason,
            "exit_code": res.exit_code,
            "output": res.output[-600:],
        }
        if res.infrastructure:
            raise SessionAbort(f"launch refused for {job.name}: {res.output[-300:]}")
        if not res.healthy:
            return Outcome(
                "did_not_fit",
                res.reason,
                res.exit_code,
                res.load_time_s,
                detail={"log_matches": res.log_matches},
            )
        self.stop_timeout = 60
        base = self.env.base_url
        self.client = Client(base)
        with self.phase("props"):
            props = self.client.get_json("/props")
        placement = parsers.parse_fit_placement(self.srv.log_text())
        per_slot = (props.get("default_generation_settings") or {}).get("n_ctx") or props.get(
            "n_ctx"
        )
        unified = props.get("kv_unified")
        if unified is None and placement.get("server_kv_unified") is not None:
            unified = placement["server_kv_unified"] == "true"
        self.summary["props"] = {
            "n_ctx": props.get("n_ctx"),
            "total_slots": props.get("total_slots"),
            "n_ctx_per_slot": per_slot,
            "kv_unified": unified,
            "build_info": props.get("build_info"),
            "log_n_ctx": placement.get("n_ctx"),
            "log_n_slots": placement.get("n_slots"),
            "log_n_ctx_slot": placement.get("n_ctx_slot"),
        }
        depths = self._depths()
        table = {d: bool(per_slot and self.env.provider.fits(d, per_slot)) for d in depths}
        self.summary["context_check"] = {"per_slot_n_ctx": per_slot, "depths_fit": table}
        if not all(table.values()):
            return Outcome(
                "did_not_fit",
                "context",
                None,
                res.load_time_s,
                detail={"per_slot_n_ctx": per_slot, "depths_fit": table},
            )

        with self.phase("snapshot"):
            snap = self.env.snapshot_fn()
        self.snapshot_id = snap.get("snapshot_id")
        self.s.save_snapshot(snap)
        self.summary["snapshot_id"] = self.snapshot_id
        self.summary["snapshot_state"] = snap.get("state")

        with self.phase("prefetch"):
            self._prefetch(base)

        csv = self.s.dir / self.csv_rel
        self.sampler = self.env.sampler_factory(csv, self.srv.run_dir / "server.pid")
        self.sampler.start()
        self.vram["loaded_mib"] = self.env.gpu_used_mib()

        with self.phase("warmup"):
            self._warmup()
        for r in self.todo:
            with self.phase("measure"):
                self._repetition(r, depths)
        return Outcome("complete", None, None, res.load_time_s)

    # ------------------------------------------------------------------ workloads

    def _depths(self) -> list[int]:
        return list(self.job.depths or self.env.provider.depths(self.job.context))

    def _prefetch(self, base: str) -> None:
        """Materialise every prompt before anything is timed (builds on demand for repetitions
        outside the manifest, e.g. the canary's, through the running server's /tokenize)."""
        p = self.env.provider
        for i in range(2):
            p.get("warmup", WARMUP_LENGTH, repetition=i, base_url=base)
        for r in self.todo:
            if self.job.short:
                p.get("short", SHORT_LENGTH, repetition=r, base_url=base)
            for d in self._depths():
                p.get("pair", d, repetition=r, base_url=base)

    # ------------------------------------------------------------------ requests

    def _request(
        self,
        kind: str,
        w: Any,
        tokens: list[int],
        n_predict: int,
        stream: bool,
        *,
        role: str,
        rep: int,
        position: int,
        order: list[int],
        window_id: str | None,
        depth: int | None,
        label: str,
    ) -> dict:
        assert self.client is not None
        self.current = {"rep": rep, "kind": kind, "depth": depth, "position": position}
        self.s.progress(phase=label, cell=self.job.name, repetition=rep, depth=depth, kind=kind)
        c = self.client.completion(tokens, n_predict, self.sampling, seed=w.seed, stream=stream)
        body = c.body
        t = body.get("timings") or {}
        typed = {
            k: t.get(k)
            for k in (
                "cache_n",
                "prompt_n",
                "prompt_ms",
                "prompt_per_second",
                "predicted_n",
                "predicted_ms",
                "predicted_per_second",
                "draft_n",
                "draft_n_accepted",
            )
        }
        slot = body.get("id_slot")
        flag_in = {
            "cache_n": t.get("cache_n"),
            "prompt_n": t.get("prompt_n"),
            "predicted_n": t.get("predicted_n"),
        }
        fl = flags.request_flags(LOG_FLAG[kind], flag_in, depth, w.expected)
        rows = rows_between(self._rows(), c.t_start_epoch, c.t_end_epoch)
        record = {
            "schema": rec.SCHEMA,
            "record_type": "request",
            "session_id": self.s.sid,
            "cell": self.job.name,
            "config_hash": self.job.config_hash,
            "attempt": self.job.attempt,
            "server_run_id": self.run_id,
            "server_instance": self.n,
            "code_commit": self.env.git["short"],
            "utc": utc_now(),
            "role": role,
            "warmup": role == "warmup",
            "kind": kind,
            "workload_id": w.id if kind != "B" else w.id.replace("A-", "B-", 1),
            "workload_kind": w.kind,
            "depth": depth,
            "variant": w.variant,
            "repetition": rep,
            "nonce": w.nonce,
            "seed": w.seed,
            "position": position,
            "depth_order": order,
            "window_id": window_id,
            "n_predict": n_predict,
            "stream": stream,
            "cache_prompt": True,
            "sampling": {**self.sampling, "seed": w.seed},
            "expected": w.expected,
            "timings": t,
            **typed,
            "stop_type": body.get("stop_type"),
            "truncated": body.get("truncated"),
            "tokens_evaluated": body.get("tokens_evaluated"),
            "tokens_cached": body.get("tokens_cached"),
            "id_slot": slot if isinstance(slot, int) else None,
            "client": {
                "t_start_epoch": c.t_start_epoch,
                "t_end_epoch": c.t_end_epoch,
                "wall_s": round(c.wall_s, 4),
                "ttft_s": None if c.ttft_s is None else round(c.ttft_s, 4),
                "http_status": c.http_status,
            },
            "snapshot_id": self.snapshot_id,
            "telemetry": {
                "file": self.gz_rel,
                "t0_epoch": c.t_start_epoch,
                "t1_epoch": c.t_end_epoch,
            },
            "free_vram_min_mib": min_free_mib(rows, self.total_mib),
            "flags": fl,
            "flag_detail": {"request_flags": list(fl)},
        }
        return record

    def _commit(self, records: list[dict]) -> None:
        validated = [rec.RequestRecord.model_validate(r) for r in rec.stamp_batch(records)]
        batch = [v.model_dump(by_alias=True) for v in validated]
        self.s.store.append_batch(batch)
        self.n_requests += len(batch)

    def _warmup(self) -> None:
        t0 = self.env.now()
        out = []
        for i in range(2):
            w = self.env.provider.get(
                "warmup", WARMUP_LENGTH, repetition=i, base_url=self.env.base_url
            )
            out.append(
                self._request(
                    "warmup",
                    w,
                    w.a_tokens,
                    WARMUP_PREDICT,
                    False,
                    role="warmup",
                    rep=i,
                    position=i,
                    order=[],
                    window_id=None,
                    depth=w.length,
                    label="warmup",
                )
            )
        self._commit(out)
        self.env.sleep(self.env.settle_s)
        rows = rows_between(self._rows(), t0, self.env.now())
        self.vram["after_warmup_min_free_mib"] = min_free_mib(rows, self.total_mib)
        self.vram["after_warmup_used_mib"] = peak_used_mib(rows[-2:]) if rows else None

    def _repetition(self, rep: int, depths: list[int]) -> None:
        job = self.job
        role = job.role
        order = depth_order(self.s.spec.shuffle_seed, job.name, rep, depths)
        wid = f"{job.name}-{job.hash8}-r{rep}-a{job.attempt}"
        p = self.env.provider
        base = self.env.base_url
        self.partial = []
        t0 = self.env.now()
        recs: list[dict] = []
        pos = 0
        if job.short:
            w = p.get("short", SHORT_LENGTH, repetition=rep, base_url=base)
            recs.append(
                self._request(
                    "short",
                    w,
                    w.a_tokens,
                    N_PREDICT,
                    False,
                    role=role,
                    rep=rep,
                    position=pos,
                    order=order,
                    window_id=wid,
                    depth=w.length,
                    label="short",
                )
            )
            self.partial.append(recs[-1])
            pos += 1
        for d in order:
            w = p.get("pair", d, repetition=rep, base_url=base)
            a = self._request(
                "A",
                w,
                w.a_tokens,
                0,
                False,
                role=role,
                rep=rep,
                position=pos,
                order=order,
                window_id=wid,
                depth=d,
                label=f"A@{d}",
            )
            self.partial.append(a)
            b = self._request(
                "B",
                w,
                w.b_tokens,
                N_PREDICT,
                True,
                role=role,
                rep=rep,
                position=pos + 1,
                order=order,
                window_id=wid,
                depth=d,
                label=f"B@{d}",
            )
            self.partial.append(b)
            recs += [a, b]
            pos += 2
        t1 = self.env.now()
        rows = rows_between(self._rows(), t0, t1)
        th, pg = flags.thermal(rows), flags.paging(rows)
        wf = [f for f, r in (("thermal", th), ("paging", pg)) if r["flag"]]
        for r in recs:
            r["flags"] = sorted(set(r["flags"]) | set(wf))
            r["flag_detail"]["window_flags"] = wf
        self._commit(recs)
        self.reps_done.append(rep)
        self.partial = []
        self.windows.append(
            {
                "window_id": wid,
                "repetition": rep,
                "attempt": job.attempt,
                "t0_epoch": t0,
                "t1_epoch": t1,
                "n_samples": len(rows),
                "thermal": th,
                "paging": pg,
                "min_free_vram_mib": min_free_mib(rows, self.total_mib),
                "peak_used_mib": peak_used_mib(rows),
                "request_flags": sorted(
                    {f for r in recs for f in r["flag_detail"]["request_flags"]}
                ),
                "flags": sorted({f for r in recs for f in r["flags"]}),
            }
        )

    # ------------------------------------------------------------------ failures

    def _discard_partial(self, why: str) -> None:
        if self.partial or self.current:
            self.s.event(
                "discarded_partial",
                cell=self.job.name,
                reason=why,
                where=dict(self.current),
                requests=[
                    {k: r.get(k) for k in ("kind", "depth", "repetition", "timings", "client")}
                    for r in self.partial
                ],
            )
        self.partial = []

    def _died(self, e: Exception) -> Outcome:
        """Classify a failure in the middle of a cell."""
        srv = self.srv
        detail = {"error": repr(e)[:300], "where": dict(self.current)}
        if isinstance(e, RequestTimeout):
            healthy = self.client.healthy(5.0) if self.client else False
            reason = "request_timeout" if healthy else "hung_server"
            detail["elapsed_s"] = round(e.elapsed_s, 1)
            if not healthy:
                self.stop_timeout = 20
        else:
            time.sleep(0.5)
            if srv.alive():
                reason, self.stop_timeout = "hung_server", 20
            else:
                verdict = flags.did_not_fit(srv.exit_code(), srv.log_text())
                reason = "oom_runtime" if verdict["log_matches"] else "crash_mid_cell"
                detail["log_matches"] = verdict["log_matches"]
        self._discard_partial(reason)
        self.s.event("server_died", cell=self.job.name, reason=reason, **detail)
        return Outcome("server_died", reason, srv.exit_code(), detail=detail)

    # ------------------------------------------------------------------ cleanup and summary

    def _cleanup(self, outcome: Outcome | None) -> None:
        old = _ignore_sigint()
        try:
            overhead = None
            if self.sampler is not None:
                try:
                    self.sampler.stop()
                    overhead = (
                        self.sampler.overhead() if hasattr(self.sampler, "overhead") else None
                    )
                except Exception as e:  # noqa: BLE001 - cleanup must go on
                    self.summary["sampler_error"] = repr(e)
                rows = self._rows()
                self.summary["telemetry"] = {
                    "file": self.gz_rel,
                    "rows": len(rows),
                    "overhead": overhead,
                    "error": getattr(self.sampler, "error", None),
                }
                self.vram["peak_used_mib"] = peak_used_mib(rows)
                self.vram["min_free_mib"] = min_free_mib(rows, self.total_mib)
                gzip_file(self.s.dir / self.csv_rel)
            if self.client is not None:
                self.client.close()
            with self.phase("shutdown"):
                stop = self.srv.stop(self.stop_timeout)
            self.summary["stop"] = stop
            if self.srv.start_result is not None:
                with self.phase("parse"):
                    self._parse_log()
            if outcome is not None:
                self.summary["status"] = outcome.status
                self.summary["reason"] = outcome.reason
        finally:
            _restore_sigint(old)

    def _parse_log(self) -> None:
        log = self.srv.log_text()
        home = Identity.current().home
        placement = parsers.parse_fit_placement(log)
        self.summary["parsed"] = {
            "placement": placement,
            "moe_cache": parsers.parse_moe_cache_stats(log),
            "checkpoints": parsers.parse_checkpoints(log),
            "spec_stats": parsers.parse_spec_stats(log),
        }
        self.summary["startup_excerpt"] = [parsers.scrub_log(ln, home) for ln in log_excerpt(log)]
        self.summary["placement_check"] = placement_check(self.job.fields, placement, log)
        if self.summary["placement_check"].get("fit_intervened") and self.summary[
            "placement_check"
        ].get("explicit_placement"):
            self.s.event(
                "warning",
                cell=self.job.name,
                kind="fit_changed_explicit_placement",
                detail=self.summary["placement_check"],
            )

    def _finish(self, outcome: Outcome) -> Outcome:
        self.summary["vram"] = self.vram
        self.summary["windows"] = self.windows
        self.summary["finished_utc"] = utc_now()
        self.summary["repetitions_done"] = list(self.reps_done)
        self.summary["n_requests"] = self.n_requests
        rel = self.s.write_cell_summary(self.job, self.summary)
        outcome.summary_rel = rel
        outcome.reps_done = list(self.reps_done)
        outcome.n_requests = self.n_requests
        if outcome.load_time_s is None:
            outcome.load_time_s = (self.summary.get("launch") or {}).get("load_time_s")
        return outcome


def placement_check(fields: dict, placement: dict, log: str) -> dict:
    """What the log says about explicit placement versus ``--fit`` (plan v1.3 follow-up).

    With ``-cmoe`` or ``--n-cpu-moe`` the placement is given explicitly. ``--fit`` (on by default)
    must not change it: the log then says "no changes needed" and has no "need to reduce device
    memory" line. ``fit_intervened`` is True if fit asked to reduce device memory.
    """
    explicit = bool(fields.get("cpu_moe")) or fields.get("n_cpu_moe") is not None
    return {
        "explicit_placement": explicit,
        "fit_setting": fields.get("fit", "default (on)"),
        "fit_attempted": placement.get("fit_attempted"),
        "fit_succeeded": placement.get("fit_succeeded"),
        "fit_no_changes_needed": "no changes needed" in log,
        "fit_intervened": placement.get("required_reduction_mib") is not None,
        "required_reduction_mib": placement.get("required_reduction_mib"),
        "expert_layers_on_cpu": placement.get("expert_layers_on_cpu"),
        "offloaded_layers": placement.get("offloaded_layers"),
        "tensor_overrides_to_cpu": placement.get("tensor_overrides_to_cpu"),
    }


def _ignore_sigint():
    try:
        return signal.signal(signal.SIGINT, signal.SIG_IGN), signal.signal(
            signal.SIGTERM, signal.SIG_IGN
        )
    except ValueError:  # not the main thread
        return None


def _restore_sigint(old) -> None:
    if old is not None:
        signal.signal(signal.SIGINT, old[0])
        signal.signal(signal.SIGTERM, old[1])
