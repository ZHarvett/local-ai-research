"""A sweep session: provenance, the cell loop with restarts, resume, probing, canaries and the
re-run mode. Files (all under ``data/raw/<session-id>/``):

    session.json        identity: hashes, code state, filters, cell order, inhibit status, runs
    records.jsonl       request and cell records (append-only, see ``records``)
    events.jsonl        every lifecycle event, precondition attempt, warning and discarded partial
    resolutions.jsonl   run-time values of placement tokens, with their provenance
    probes.jsonl        every probing step
    cells/              one summary JSON per cell (all server instances of that cell)
    resolved/           the concrete server TOML of every cell
    snapshots/          environment snapshots by id
    telemetry/          2 Hz telemetry, gzip CSV
    progress.json       current cell and phase (for scripts/sweep-status.sh)
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tomllib
from pathlib import Path

from .. import flags, stats
from ..config import ServerConfig, SweepSpec
from ..render import render_argv
from ..scrub import Identity, scrub_json
from . import probe as pr
from . import provenance
from . import records as rec
from . import spec as sp
from .core import (
    EXIT_INTERRUPTED,
    EXIT_OK,
    Env,
    HardAbort,
    InhibitError,
    Job,
    Outcome,
    ProvenanceError,
    SessionAbort,
    TransientAbort,
    utc_now,
    write_json_atomic,
)
from .instance import Instance
from .server import stop_orphan

CANARY_BASE = {"main": 100, "rerun": 110}  # repetition indices of the canaries (section 5.1)
DRIFT_METRICS = ("pp_fresh_16k", "tg_16k")  # the drift flag looks at prefill and decode speed


class Session:
    def __init__(
        self,
        env: Env,
        spec: SweepSpec,
        spec_path: Path,
        sid: str,
        *,
        filters: dict | None = None,
        allow_dirty: bool = False,
        inhibit_tag: str | None = None,
        mode: str = "run",
    ):
        self.env, self.spec, self.spec_path, self.sid = env, spec, Path(spec_path), sid
        self.filters = filters or {}
        self.allow_dirty, self.inhibit_tag, self.mode = allow_dirty, inhibit_tag, mode
        self.dir = env.out_root / sid
        self.store = rec.Store(self.dir / "records.jsonl")
        self.session: dict = {}
        self.cells: list[sp.CellDef] = []
        self.order: list[str] = []
        self.started_monotonic = 0.0
        self.last_error: str | None = None
        self._progress: dict = {}
        # True once every provenance check has passed and the session's own files may be written.
        # Until then a refused start must leave an existing session byte-for-byte untouched.
        self._loaded = False

    # ------------------------------------------------------------------ small file helpers

    def event(self, name: str, **kw) -> None:
        line = json.dumps({"utc": utc_now(), "event": name, **kw}, default=str)
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.dir / "events.jsonl", "a") as f:
            f.write(line + "\n")

    @staticmethod
    def _read_json_file(path: Path) -> dict | None:
        """The JSON object in ``path``; None if the file does not exist. A file that exists but
        cannot be read as a JSON object raises ``ProvenanceError``: it is never overwritten."""
        if not path.exists():
            return None
        try:
            obj = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            raise ProvenanceError(
                f"{path.name} of the session is unreadable ({e}); not touching it"
            ) from e
        if not isinstance(obj, dict):
            raise ProvenanceError(
                f"{path.name} of the session is not a JSON object; not touching it"
            )
        return obj

    def _merge_write(self, path: Path, updates: dict) -> None:
        """Read-modify-write: merge ``updates`` into the JSON object already in ``path`` (keys not
        mentioned are kept) and write it atomically. Refuses if the existing file is unreadable.
        Only a loaded session may write (see ``_loaded``)."""
        if not self._loaded:
            raise ProvenanceError(f"refusing to write {path.name}: the session was not opened")
        merged = {**(self._read_json_file(path) or {}), **updates}
        write_json_atomic(path, scrub_json(merged, Identity.current()))

    def progress(self, **kw) -> None:
        self._progress.update(kw)
        self._progress["updated_utc"] = utc_now()
        if not self._loaded:
            return
        self._merge_write(self.dir / "progress.json", {"session_id": self.sid, **self._progress})

    def save_snapshot(self, snap: dict) -> None:
        sid = snap.get("snapshot_id")
        if sid and not (self.dir / "snapshots" / f"{sid}.json").exists():
            write_json_atomic(self.dir / "snapshots" / f"{sid}.json", snap)

    def write_cell_summary(self, job: Job, instance_summary: dict) -> str:
        """Merge one server instance into the cell's summary file (runner-maintained)."""
        rel = f"cells/{job.name}-{job.hash8}.json"
        path = self.dir / rel
        cur = json.loads(path.read_text()) if path.exists() else {}
        # an instance of a job that carries no coordinates or resolution never blanks what an
        # earlier instance of the cell recorded (a re-run job did, before WP12 part 2d)
        keep = {k: cur[k] for k in ("coords", "resolution") if cur.get(k) and not getattr(job, k)}
        cur.update(
            {
                "cell": job.name,
                "role": job.role,
                "profile": job.profile,
                "config_hash": job.config_hash,
                "argv": job.argv,
                "resolved_config": f"resolved/{job.name}.toml",
                "coords": job.coords,
                "resolution": job.resolution,
                "model_sha256": self.env.model_sha["sha256"],
                "llama_cpp_commit": self.env.llama_commit,
            }
        )
        cur.update(keep)
        cur.setdefault("instances", []).append(instance_summary)
        cur["flags"] = sorted(
            {f for i in cur["instances"] for w in i.get("windows", []) for f in w["flags"]}
        )
        write_json_atomic(path, scrub_json(cur, Identity.current()))
        return rel

    def cell_summary(self, name: str) -> dict | None:
        found = sorted((self.dir / "cells").glob(f"{name}-????????.json"))
        return json.loads(found[-1].read_text()) if found else None

    # ------------------------------------------------------------------ provenance

    def current_provenance(self) -> dict:
        m = self.env.manifest_path
        return {
            "spec_sha256": provenance.sha256_file(self.spec_path),
            "manifest_sha256": provenance.sha256_file(m) if m.exists() else "missing",
            "sampling_sha256": provenance.sampling_sha256(self.env.model_path),
            "git": self.env.git,
            "filters": self.filters,
            "model_sha256": self.env.model_sha["sha256"],
            "llama_cpp_commit": self.env.llama_commit,
        }

    def verify_inhibit(self) -> dict:
        """The sweep must run under ``systemd-inhibit --what=sleep:idle``; stop if it does not."""
        if not self.env.check_inhibit:
            return {"checked": False}
        tag = self.inhibit_tag or ""
        p = subprocess.run(
            ["systemd-inhibit", "--list", "--no-pager"], capture_output=True, text=True, check=False
        )
        line = next((ln for ln in p.stdout.splitlines() if tag and tag in ln), None)
        if not line:
            raise InhibitError(
                "no systemd-inhibit lock found for this sweep (expected a lock whose reason "
                f"contains {tag!r}); refusing to run unprotected"
            )
        return {"checked": True, "active": True, "tag": tag, "line": " ".join(line.split())}

    def open(self, *, resume: bool) -> None:
        cur = self.current_provenance()
        defs = sp.expand(self.spec, self.env.root)
        sp.validate_cells(defs)
        defs = sp.apply_filter(defs, self.filters)
        self.cells = defs
        sj = self.dir / "session.json"
        inhibit = self.verify_inhibit()
        run_entry = {
            "start_utc": utc_now(),
            "pid": os.getpid(),
            "mode": self.mode,
            "code_commit": self.env.git["short"],
            "inhibit": inhibit,
        }
        if sj.exists():
            if not resume:
                raise ProvenanceError(f"session {self.sid} already exists; use --resume")
            stored = self._read_json_file(sj) or {}
            errors, warnings = provenance.resume_check(stored, cur)
            if errors:
                raise ProvenanceError("cannot resume: " + "; ".join(errors))
            self.order = stored["cell_order"]
            if sorted(self.order) != sorted(c.name for c in defs):
                raise ProvenanceError("the cells of the spec no longer match the session's order")
            self._loaded = True  # every check passed: from here on the session's files may change
            for w in warnings:
                self.event("warning", kind="code_commit_changed", message=w)
            run_entry["warnings"] = warnings
            run_entry["resumed"] = True
            stored["runs"].append(run_entry)
            stored["state"] = "running"
            self.session = stored
        else:
            if resume:
                raise ProvenanceError(f"no session {self.sid} to resume")
            if self.env.git["dirty"] and not self.allow_dirty:
                raise ProvenanceError(
                    "uncommitted changes in "
                    + ", ".join(self.env.git["dirty_paths"][:8])
                    + "; commit them or pass --allow-dirty"
                )
            self._loaded = True
            self.order = [c.name for c in sp.order_cells(defs, self.spec.shuffle_seed)]
            self.session = {
                "schema": 1,
                "session_id": self.sid,
                "created_utc": utc_now(),
                "spec": {"name": self.spec.name, "path": str(self.spec_path)},
                **cur,
                "allow_dirty": self.allow_dirty,
                "model": self.env.model_sha,
                "shuffle_seed": self.spec.shuffle_seed,
                "cell_order": self.order,
                "cell_order_rule": "seeded shuffle respecting @n_fit dependencies "
                "(smallpc.sweep.spec.order_cells), not spec order",
                "repetitions": self.spec.repetitions,
                "state": "running",
                "runs": [run_entry],
            }
        self.session["inhibit"] = inhibit
        if resume:  # merge into the stored file; a new session writes all of its keys
            self._merge_write(sj, {k: self.session[k] for k in ("runs", "state", "inhibit")})
        else:
            self._merge_write(sj, self.session)
        self.event(
            "session_open",
            mode=self.mode,
            resumed=bool(run_entry.get("resumed")),
            cells=len(self.order),
            filters=self.filters,
        )

    def update_session(self, **kw) -> None:
        """Merge ``kw`` into the session file (read-modify-write); other keys are kept."""
        self._merge_write(self.dir / "session.json", kw)
        self.session.update(kw)

    def _refused(self, e: BaseException) -> None:
        """A start that was refused before the session was loaded: nothing of the session is
        written (not session.json, progress.json, events.jsonl or records.jsonl). The message goes
        to stderr, which the detached job log captures."""
        self.last_error = str(e)
        print(f"smallpc.sweep: refused, no session file touched: {e}", file=sys.stderr)

    # ------------------------------------------------------------------ preconditions

    def precondition_step(self, label: str, *, idle: bool) -> tuple[dict, list[dict]]:
        """Section 5.3 step 1 with retries: a transient failure (idle CPU, MemAvailable) is retried
        ``precond_retries`` more times after ``precond_pause_s`` each; a hard one aborts at once."""
        attempts: list[dict] = []
        for i in range(1 + self.env.precond_retries):
            pre = self.env.preconditions_fn(idle)
            att = {
                "attempt": i + 1,
                "utc": utc_now(),
                "ok": pre["ok"],
                "aborts": pre["aborts"],
                "hard": pre.get("hard_aborts", []),
                "warnings": pre["warnings"],
                "idle": pre["values"].get("idle"),
                "mem_available_gib": pre["values"].get("mem_available_gib"),
            }
            attempts.append(att)
            self.event("precondition", cell=label, **att)
            if pre["ok"]:
                return pre, attempts
            if pre.get("hard_aborts"):
                raise HardAbort(f"{label}: {'; '.join(pre['hard_aborts'])}")
            if i == self.env.precond_retries:
                raise TransientAbort(
                    f"{label}: {'; '.join(pre['aborts'])} (after {i + 1} attempts)"
                )
            self.event("precondition_wait", cell=label, wait_s=self.env.precond_pause_s, next=i + 2)
            self.progress(phase="precondition_wait", cell=label)
            self.env.sleep(self.env.precond_pause_s)
        raise AssertionError("unreachable")

    # ------------------------------------------------------------------ configs

    def prepare_job(self, job: Job) -> Job:
        cfg = ServerConfig.model_validate({"profile": job.profile, **job.fields})
        job.argv = render_argv(cfg, self.env.machine, self.env.model)
        job.config_hash = provenance.config_hash(
            job.argv, self.env.model_sha["sha256"], self.env.llama_commit
        )
        path = self.dir / "resolved" / f"{job.name}.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        eff = cfg.effective().model_dump(exclude_none=True)
        eff.pop("profile", None)
        path.write_text(sp.render_toml(job.profile, eff))
        job.toml_path = path
        return job

    # ------------------------------------------------------------------ resolution of tokens

    def _load_resolutions(self) -> dict:
        out: dict = {}
        f = self.dir / "resolutions.jsonl"
        if f.exists():
            for line in f.read_text().splitlines():
                try:
                    o = json.loads(line)
                    out[o["cell"]] = o
                except (ValueError, KeyError):
                    continue
        return out

    def resolve(self, cdef: sp.CellDef) -> tuple[dict | None, dict, str | None]:
        """(fields, resolution, not_applicable_reason). Reuses an earlier resolution of this
        session, so a resumed session keeps its config hashes."""
        prior = self._load_resolutions().get(cdef.name)
        if prior:
            return prior["fields"], prior["resolution"], prior.get("not_applicable")
        fields = dict(cdef.overrides)
        resolution: dict = {}
        na: str | None = None
        for key, tok in cdef.tokens.items():
            if tok.kind == "n_fit":
                dep = cdef.template.format(**{**cdef.coords, sp.PLACEMENT_AXIS: tok.ref})  # type: ignore[union-attr]
                base, info = self.n_fit(cdef, dep, {k: v for k, v in fields.items() if k != key})
            else:
                base, info = self.max_fit(cdef, {k: v for k, v in fields.items() if k != key})
            value = None if base is None else base - tok.offset
            info.update(
                {
                    "token": f"{tok.kind}-{tok.offset}" if tok.offset else tok.kind,
                    "base": base,
                    "value": value,
                }
            )
            resolution[key] = info
            if (
                value is None
                or (key == "n_cpu_moe" and value < 0)
                or (key == "moe_cache_mib" and value < pr.STEP_MIB)
            ):
                na = f"{key}: {tok.kind} resolves to {value} (base {base}); not applicable"
            else:
                fields[key] = value
        f = self.dir / "resolutions.jsonl"
        with open(f, "a") as fh:
            fh.write(
                json.dumps(
                    {
                        "cell": cdef.name,
                        "fields": None if na else fields,
                        "resolution": resolution,
                        "not_applicable": na,
                        "utc": utc_now(),
                    }
                )
                + "\n"
            )
        return (None if na else fields), resolution, na

    def n_fit(self, cdef: sp.CellDef, dep: str, fields: dict) -> tuple[int | None, dict]:
        """N_fit: the expert layers P1's ``--fit`` placed on the CPU, read from its summary (parsed
        from its log). A partly offloaded layer counts as one layer. Falls back to a search."""
        summ = self.cell_summary(dep)
        if summ:
            for inst in reversed(summ.get("instances", [])):
                pl = ((inst.get("parsed") or {}).get("placement")) or {}
                if pl.get("expert_layers_on_cpu") is not None and inst.get("status") == "complete":
                    return int(pl["expert_layers_on_cpu"]), {
                        "source": "p1_log",
                        "source_cell": dep,
                        "p1_expert_layers_on_cpu": pl["expert_layers_on_cpu"],
                        "p1_first_partial_layer_overflow": pl.get("first_partial_layer_overflow"),
                        "p1_fit_device_used_mib": pl.get("fit_device_used_mib"),
                        "p1_realized_peak_used_mib": (inst.get("vram") or {}).get("peak_used_mib"),
                        "p1_realized_min_free_mib": (inst.get("vram") or {}).get("min_free_mib"),
                    }
        return self._probe("n_fit", cdef, fields)

    def max_fit(self, cdef: sp.CellDef, fields: dict) -> tuple[int | None, dict]:
        return self._probe("max_fit", cdef, fields)

    # ------------------------------------------------------------------ probing

    def _probe(self, kind: str, cdef: sp.CellDef, fields: dict) -> tuple[int | None, dict]:
        ctx = int(fields["context"])
        depths = self.env.provider.depths(ctx)
        total = self.env.gpu_total_mib()
        key = pr.probe_key(
            kind,
            fields,
            d_max=max(depths),
            llama_commit=self.env.llama_commit,
            model_sha256=self.env.model_sha["sha256"],
            gpu_total_mib=total,
        )
        cache = pr.ProbeCache(self.env.probe_cache)
        hit = cache.get(key)
        if hit is not None:
            self.event("probe_cache_hit", kind=kind, key=key, value=hit.get("value"))
            return hit["value"], {
                "source": "probe_cache",
                "probe_key": key,
                "n_steps": 0,
                "cached_from": hit.get("session_id"),
            }

        def evaluate(value: int) -> pr.StepResult:
            f = {**fields, "moe_cache_mib" if kind == "max_fit" else "n_cpu_moe": value}
            return self.probe_step(kind, cdef.name, f, value, max(depths))

        if kind == "max_fit":
            res = pr.search_max_fit(evaluate, cap_mib=int(total or 0))
        else:
            res = pr.search_n_fit(evaluate, n_layer=self.env.n_layer())
        cache.put(
            key,
            pr.result_entry(
                kind,
                res,
                session_id=self.sid,
                utc=utc_now(),
                context=ctx,
                ubatch=fields.get("ubatch"),
            ),
        )
        return res.value, {
            "source": "binary_search",
            "probe_key": key,
            "n_steps": len(res.steps),
            "steps": res.steps,
            "verified": res.verified,
        }

    def probe_step(
        self, kind: str, cell: str, fields: dict, value: int, d_max: int
    ) -> pr.StepResult:
        """Start a server with ``fields``, send the longest request, and judge the VRAM."""
        label = f"probe-{cell}-{kind}-{value}"
        job = Job(label, "probe", "candidate", fields, [0], short=False, depths=[d_max])
        self.prepare_job(job)
        t0 = self.env.now()
        self.progress(phase="probe", cell=cell, probe=f"{kind}={value}")
        pre, _ = self.precondition_step(label, idle=False)
        inst = Instance(self, job, [0], 0)
        inst.run_id = f"{self.sid}-{label}"
        step = self._run_probe(inst, d_max)
        self.event(
            "probe_step",
            kind=kind,
            cell=cell,
            value=value,
            ok=step.ok,
            free_mib=step.free_mib,
            reason=step.reason,
            seconds=round(self.env.now() - t0, 1),
        )
        with open(self.dir / "probes.jsonl", "a") as f:
            f.write(
                json.dumps(
                    {
                        "utc": utc_now(),
                        "kind": kind,
                        "cell": cell,
                        "value": value,
                        "ok": step.ok,
                        "free_mib": step.free_mib,
                        "reason": step.reason,
                        "detail": step.detail,
                        "seconds": round(self.env.now() - t0, 1),
                    }
                )
                + "\n"
            )
        return step

    def _run_probe(self, inst: Instance, d_max: int) -> pr.StepResult:
        from .client import Client, RequestTimeout, ServerGone
        from .core import min_free_mib, rows_between

        srv, env = inst.srv, self.env
        total = env.gpu_total_mib()
        try:
            res = srv.start(inst.job.toml_path, inst.run_id)
            if res.infrastructure:
                raise SessionAbort(f"probe launch refused: {res.output[-300:]}")
            if not res.healthy:
                return pr.StepResult(False, None, res.reason, {"exit_code": res.exit_code})
            client = Client(env.base_url)
            inst.client = client
            sampler = env.sampler_factory(
                self.dir / "telemetry" / f"{inst.run_id}.csv", srv.run_dir / "server.pid"
            )
            inst.sampler = sampler
            sampler.start()
            try:
                t0 = env.now()
                w = env.provider.get("pair", d_max, repetition=0, base_url=env.base_url)
                client.completion(w.a_tokens, 0, inst.sampling, seed=w.seed, stream=False)
                client.completion(w.b_tokens, 16, inst.sampling, seed=w.seed, stream=False)
                env.sleep(env.settle_s)
                rows = rows_between(list(sampler.rows), t0, env.now())
            except (ServerGone, RequestTimeout) as e:
                reason = (
                    "oom_runtime"
                    if flags.did_not_fit(srv.exit_code(), srv.log_text())["log_matches"]
                    else "crash_mid_cell"
                )
                inst.stop_timeout = 20
                return pr.StepResult(False, None, reason, {"error": repr(e)[:200]})
            from .. import parsers

            pl = parsers.parse_fit_placement(srv.log_text())
            free = min_free_mib(rows, total)
            if pl.get("required_reduction_mib") is not None:
                return pr.StepResult(
                    False,
                    free,
                    "fit_intervened",
                    {"required_reduction_mib": pl["required_reduction_mib"]},
                )
            ok = free is not None and free >= pr.MARGIN_MIB
            return pr.StepResult(ok, free, None if ok else "margin", {"total_mib": total})
        finally:
            old = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                if inst.sampler is not None:
                    inst.sampler.stop()
                    from .core import gzip_file

                    gzip_file(self.dir / "telemetry" / f"{inst.run_id}.csv")
                if inst.client is not None:
                    inst.client.close()
                inst.srv.stop(inst.stop_timeout)
            finally:
                signal.signal(signal.SIGINT, old)

    # ------------------------------------------------------------------ the main loop

    def install_signals(self) -> None:
        def handler(signum, frame):  # noqa: ARG001
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def stop_orphans(self) -> None:
        """After a hard kill the runner's own server may still be running: stop it."""
        f = self.dir / "events.jsonl"
        if not f.exists():
            return
        for line in f.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event") == "server_start" and e.get("run_id"):
                st = stop_orphan(self.env.scripts_dir, self.env.log_root, e["run_id"])
                if st is not None:
                    self.event("orphan_server_stopped", run_id=e["run_id"], status=st)

    def run(self, *, resume: bool = False) -> int:
        self.started_monotonic = self.env.now()
        code = EXIT_OK
        try:
            self.open(resume=resume)
            self.stop_orphans()
            self.progress(
                state="running",
                phase="start",
                cells_total=len(self.order),
                cells_done=0,
                started_utc=self.session.get("created_utc"),
            )
            if self.spec.canary:
                self.run_canary("start", "main")
            by_name = {c.name: c for c in self.cells}
            for name in self.order:
                self.run_cell(by_name[name])
            if self.spec.canary:
                self.run_canary("end", "main")
                self.finish_drift("main")
            self.update_session(state="complete", finished_utc=utc_now())
            self.progress(state="complete", phase="done")
        except KeyboardInterrupt:
            code = EXIT_INTERRUPTED
            if self._loaded:
                self.update_session(state="interrupted")
                self.progress(state="interrupted", phase="interrupted")
                self.event("session_interrupted")
        except SessionAbort as e:
            code = e.exit_code
            if not self._loaded:
                self._refused(e)
            else:
                self.last_error = str(e)
                self.update_session(state="aborted", last_error=str(e), exit_code=code)
                self.progress(state="aborted", phase="aborted", last_error=str(e))
                self.event("session_abort", error=str(e), exit_code=code)
        return code

    def _done_count(self) -> int:
        idx = rec.Index(self.store.load())
        return sum(1 for c in self.cells if idx.final_cell(None, c.name) is not None)

    # ------------------------------------------------------------------ cells

    def run_cell(self, cdef: sp.CellDef) -> None:
        idx = rec.Index(self.store.load())
        if idx.final_cell(None, cdef.name) is not None:
            self.event("cell_skipped", cell=cdef.name, reason="final record exists")
            return
        self.progress(cell=cdef.name, phase="resolve", cells_done=self._done_count())
        fields, resolution, na = self.resolve(cdef)
        if fields is None:
            self.write_cell_record(cdef.name, None, "not_applicable", True, reason=na)
            return
        job = Job(
            cdef.name,
            "measured",
            cdef.profile,
            fields,
            list(range(self.spec.repetitions)),
            resolution=resolution,
            coords=dict(cdef.coords),
        )
        self.prepare_job(job)
        self.run_job(job)

    def write_cell_record(
        self,
        name: str,
        job: Job | None,
        status: str,
        final: bool,
        *,
        reason: str | None = None,
        outcome: Outcome | None = None,
        instance: int | None = None,
        role: str = "measured",
        attempt: int = 1,
    ) -> None:
        fl = ["did_not_fit"] if status == "did_not_fit" else []
        r = rec.CellRecord.model_validate(
            {
                "schema": 1,
                "record_type": "cell",
                "session_id": self.sid,
                "cell": name,
                "config_hash": job.config_hash if job else None,
                "role": role,
                "status": status,
                "final": final,
                "reason": reason,
                "flags": fl,
                "server_instance": instance,
                "exit_code": outcome.exit_code if outcome else None,
                "attempt": attempt,
                "repetitions_done": outcome.reps_done if outcome else [],
                "n_requests": outcome.n_requests if outcome else 0,
                "load_time_s": outcome.load_time_s if outcome else None,
                "summary_file": outcome.summary_rel if outcome else None,
                "code_commit": self.env.git["short"],
                "utc": utc_now(),
                "batch_id": "x",
            }
        )
        batch = rec.stamp_batch([r.model_dump(by_alias=True)])
        self.store.append_batch(batch)
        self.event("cell_record", cell=name, status=status, final=final, reason=reason)

    def _next_instance(self, job: Job) -> int:
        """Number of the next server instance of this job (run ids must be unique)."""
        prefix = f"{self.sid}-{job.name}-{job.hash8}-i"
        f = self.dir / "events.jsonl"
        n = 0
        if f.exists():
            for line in f.read_text().splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("event") == "server_start" and str(e.get("run_id", "")).startswith(prefix):
                    n += 1
        return n

    def run_job(self, job: Job) -> Outcome | None:
        """Run a job to a final state: complete, or did_not_fit. A server that dies is restarted
        (new server, warm-up again, only the missing repetitions) up to ``max_restarts`` times."""
        restarts = 0
        instance = self._next_instance(job)
        last: Outcome | None = None
        while True:
            idx = rec.Index(self.store.load())
            done = idx.done_repetitions(job.config_hash, job.role, job.attempt)
            todo = [r for r in job.reps if r not in done]
            if not todo:
                out = last or Outcome("complete", reps_done=sorted(done))
                last_instance = instance - 1 if last is not None else None  # the one that ran
                self.write_cell_record(
                    job.name,
                    job,
                    "complete",
                    True,
                    outcome=out,
                    instance=last_instance,
                    role=job.role,
                    attempt=job.attempt,
                )
                return out
            self.event(
                "cell_start",
                cell=job.name,
                hash=job.config_hash,
                todo=todo,
                instance=instance,
                restarts=restarts,
                role=job.role,
            )
            inst = Instance(self, job, todo, instance)
            try:
                out = inst.run()
            except KeyboardInterrupt:
                if inst.outcome is not None:
                    self.write_cell_record(
                        job.name,
                        job,
                        "interrupted",
                        False,
                        outcome=inst.outcome,
                        instance=instance,
                        role=job.role,
                        attempt=job.attempt,
                    )
                raise
            last = out
            instance += 1
            if out.status == "complete":
                continue  # the loop re-reads the records and writes the final cell record
            if out.status == "did_not_fit":
                self.write_cell_record(
                    job.name,
                    job,
                    "did_not_fit",
                    True,
                    reason=out.reason,
                    outcome=out,
                    instance=instance - 1,
                    role=job.role,
                    attempt=job.attempt,
                )
                return out
            # server_died: restart, or give up
            self.write_cell_record(
                job.name,
                job,
                "server_died",
                False,
                reason=out.reason,
                outcome=out,
                instance=instance - 1,
                role=job.role,
                attempt=job.attempt,
            )
            restarts += 1
            if restarts > self.spec.max_restarts:
                self.write_cell_record(
                    job.name,
                    job,
                    "did_not_fit",
                    True,
                    reason=out.reason,
                    outcome=out,
                    instance=instance - 1,
                    role=job.role,
                    attempt=job.attempt,
                )
                return out
            self.event("cell_restart", cell=job.name, reason=out.reason, restarts=restarts)

    # ------------------------------------------------------------------ canary

    def canary_job(self, phase: str, which: str) -> Job:
        c = self.spec.canary
        assert c is not None
        if c.config:
            with open(self.env.root / c.config, "rb") as f:
                data = tomllib.load(f)
            profile = data.pop("profile")
            fields = data
        else:
            fields = dict(c.cell)
            profile = fields.pop("profile", "candidate")
        base = CANARY_BASE[which] + (c.repetitions if phase == "end" else 0)
        depths = [self._point_tokens(p) for p in c.points if p != "short"]
        name = f"canary-{phase}" if which == "main" else f"canary-{which}-{phase}"
        job = Job(
            name,
            f"canary_{phase}",
            profile,
            fields,
            [base + i for i in range(c.repetitions)],
            short="short" in c.points,
            depths=depths,
        )
        return self.prepare_job(job)

    @staticmethod
    def _point_tokens(p: str) -> int:
        m = re.fullmatch(r"(\d+)[Kk]", p)
        return int(m[1]) * 1024 if m else int(p)

    def run_canary(self, phase: str, which: str) -> None:
        job = self.canary_job(phase, which)
        idx = rec.Index(self.store.load())
        if idx.final_cell(job.config_hash, job.name, job.role) is not None:
            return
        self.progress(cell=job.name, phase=f"canary_{phase}")
        self.run_job(job)

    def drift_metrics(self, which: str) -> dict:
        """Start and end canary values per metric, from the records."""
        c = self.spec.canary
        assert c is not None
        n = c.repetitions
        base = CANARY_BASE[which]
        reqs = self.store.load().requests
        depth = (
            max(self._point_tokens(p) for p in c.points if p != "short")
            if any(p != "short" for p in c.points)
            else None
        )

        def collect(lo: int, role: str) -> dict:
            rs = [
                r
                for r in reqs
                if r["role"] == role and lo <= r["repetition"] < lo + n and r["attempt"] == 1
            ]
            return {
                "pp_fresh_16k": [
                    r["prompt_per_second"]
                    for r in rs
                    if r["kind"] == "A" and r["depth"] == depth and r["prompt_per_second"]
                ],
                "tg_16k": [
                    r["predicted_per_second"]
                    for r in rs
                    if r["kind"] == "B" and r["depth"] == depth and r["predicted_per_second"]
                ],
                "tg_short": [
                    r["predicted_per_second"]
                    for r in rs
                    if r["kind"] == "short" and r["predicted_per_second"]
                ],
            }

        return {"start": collect(base, "canary_start"), "end": collect(base + n, "canary_end")}

    def finish_drift(self, which: str) -> dict:
        m = self.drift_metrics(which)
        out: dict = {"metrics": {}, "flag": None, "decided_on": list(DRIFT_METRICS)}
        for name in ("pp_fresh_16k", "tg_16k", "tg_short"):
            a, b = m["start"][name], m["end"][name]
            if not a or not b:
                out["metrics"][name] = {"note": "missing canary data"}
                continue
            res = flags.drift(stats.summarize(a), stats.summarize(b))
            out["metrics"][name] = res | {"start_values": a, "end_values": b}
            if res["flag"] and name in DRIFT_METRICS:
                out["flag"] = "drift"
        out["complete"] = all("flag" in out["metrics"].get(k, {}) for k in DRIFT_METRICS)
        self.event("drift", which=which, **{k: v for k, v in out.items()})
        self.update_session(drift={**self.session.get("drift", {}), which: out})
        return out

    # ------------------------------------------------------------------ re-run mode

    def rerun_flagged(self) -> int:
        """Re-run, once, every repetition flagged in attempt 1 (section 5.6). Appends attempt-2
        records; never edits or deletes. ``short_gen``, ``drift`` and ``did_not_fit`` are not
        re-run."""
        code = EXIT_OK
        try:
            self._adopt_stored_filters()
            self.open(resume=True)
            self.stop_orphans()
            idx = rec.Index(self.store.load())
            flagged = idx.flagged_repetitions()
            todo: dict[str, list[int]] = {}
            names: dict[str, str] = {}
            for (h, r), _fl in sorted(flagged.items()):
                if r in idx.done_repetitions(h, "measured", attempt=2):
                    continue  # already re-run: never an attempt 3
                todo.setdefault(h, []).append(r)
            for q in idx.loaded.requests:
                # a canary may share its config (and hash) with a cell: name hashes by measured
                # requests only
                if q["role"] == "measured":
                    names[q["config_hash"]] = q["cell"]
            self.event(
                "rerun_plan",
                cells={names[h]: reps for h, reps in todo.items()},
                flags={f"{names[h]}:{r}": v for (h, r), v in flagged.items()},
            )
            self.progress(
                state="running", phase="rerun", cells_total=len(todo), cells_done=0, mode="rerun"
            )
            if todo and self.spec.canary:
                self.run_canary("start", "rerun")
            for name in self.order:
                for h, reps in todo.items():
                    if names[h] != name:
                        continue
                    job = self._job_from_resolved(name, reps)
                    if job.config_hash != h:
                        raise ProvenanceError(
                            f"{name}: resolved config no longer hashes to {h} ({job.config_hash})"
                        )
                    self.run_job(job)
            if todo and self.spec.canary:
                self.run_canary("end", "rerun")
                self.finish_drift("rerun")
            # the main run's finished_utc stays as it was; the re-run records its own end
            self.update_session(state="complete", rerun_finished_utc=utc_now())
            self.progress(state="complete", phase="done")
        except KeyboardInterrupt:
            code = EXIT_INTERRUPTED
            if self._loaded:
                self.update_session(state="interrupted")
        except SessionAbort as e:
            code = e.exit_code
            if not self._loaded:
                self._refused(e)
            else:
                self.update_session(state="aborted", last_error=str(e), exit_code=code)
                self.progress(state="aborted", phase="aborted", last_error=str(e))
        return code

    def _adopt_stored_filters(self) -> None:
        """A re-run is of the session as it was started, so it takes that session's ``--only``
        filter from ``session.json``. A filter given on the command line must equal it. Read-only:
        nothing is written here."""
        stored = self._read_json_file(self.dir / "session.json")
        if stored is None:
            raise ProvenanceError(f"no session {self.sid} to re-run")
        stored_filters = stored.get("filters") or {}
        if self.filters and self.filters != stored_filters:
            raise ProvenanceError(
                f"--rerun-flagged re-runs session {self.sid} with the --only filter it was started "
                f"with, {stored_filters or 'none'}; the command line gave {self.filters}. "
                "Leave --only out (the stored filter is used)"
            )
        self.filters = dict(stored_filters)

    def _job_from_resolved(self, name: str, reps: list[int]) -> Job:
        with open(self.dir / "resolved" / f"{name}.toml", "rb") as f:
            data = tomllib.load(f)
        profile = data.pop("profile")
        # a re-run job carries what the first-run job (run_cell) carries: the cell's coordinates
        # (from the spec) and its token resolution (from this session's resolutions.jsonl), so the
        # cell summary written after the re-run keeps both
        cdef = next((c for c in self.cells if c.name == name), None)
        prior = self._load_resolutions().get(name) or {}
        job = Job(
            name,
            "measured",
            profile,
            data,
            reps,
            attempt=2,
            resolution=dict(prior.get("resolution") or {}),
            coords=dict(cdef.coords) if cdef else {},
        )
        return self.prepare_job(job)
