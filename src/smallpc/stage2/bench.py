"""llama-bench cross-check wrapper (plan v1.6, Stage 2e).

``python -m smallpc.stage2 bench-crosscheck --cell <name> --out data/microbench/<name>.json``

Maps what it can of a cell's resolved config to the flags of the built ``llama-bench`` (names taken
from its ``--help``), runs it under the GPU lock, parses the JSON output and summarises the
per-repetition samples with ``smallpc.stats.summarize``. llama-bench measures random-token
prompts, so the result is labelled ``CROSSCHECK_LABEL`` and is never used for a decision;
every field of the cell that llama-bench cannot express is listed.

Two invocations per cell: the fresh prefill of the depths (``-p d1,d2,d3 -n 0 -d 0``, the analogue
of PP_fresh) and the turn (``-p 3000 -n 400 -d d1,d2,d3``: prefill of 3,000 tokens and decode of 400
at each depth, the analogue of PP_inc and TG).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .. import stats
from ..config import ModelConfig, ServerConfig, load_machine, load_model, repo_root
from ..render import resolve_model_path
from ..scrub import Identity, scrub_json

CROSSCHECK_LABEL = "cross-check, random-token prompts, never used for a decision"
APPEND_TOKENS = 3000
N_GEN = 400
# what llama-server's --cpu-moe does (common.h LLM_FFN_EXPS_REGEX); llama-bench has no -cmoe
CPU_MOE_PATTERN = r"\.ffn_(up|down|gate|gate_up)_(ch|)exps=CPU"
DEFAULT_FIT_MARGIN_MIB = 1024  # --fit's default margin (the server's --fit-target default)
NOT_INFERENCE = {
    "profile": "not an inference setting",
    "host": "serving only",
    "port": "serving only",
    "model": "mapped to -m",
    "metrics": "serving only (Prometheus endpoint)",
    "log_verbosity": "logging only",
    "slot_save_path": "serving only",
}
NO_EQUIVALENT = {
    "moe_cache_mib": "llama-bench has no expert cache (--moe-cache-mib)",
    "cache_ram": "llama-bench has no server host prompt cache (--cache-ram)",
    "spec_type": "llama-bench has no speculative decoding",
    "spec_draft_n_max": "llama-bench has no speculative decoding",
}


def _entry(field: str, value, flag: str | None = None, note: str | None = None) -> dict:
    return {"field": field, "value": value, "flag": flag, "note": note}


def map_config(fields: dict, model_path: str) -> dict:
    """The llama-bench arguments for a resolved cell config (a dict of ``ServerConfig`` fields with
    the sweep defaults applied, as in ``data/raw/<session>/resolved/<cell>.toml``).

    Returns ``argv`` (model and settings, no test selection), ``expressed`` (exact),
    ``approximated``
    (expressed with a caveat), ``unexpressed`` (inference settings llama-bench cannot express, with
    the reason) and ``not_inference`` (serving and logging fields that do not matter here)."""
    f = {k: v for k, v in fields.items() if v is not None}
    argv = ["-m", model_path]
    out: dict = {"expressed": [_entry("model", model_path, "-m")], "approximated": [],
                 "unexpressed": [], "not_inference": []}  # fmt: skip
    ctx = f.get("context")
    fit_on = f.get("fit") == "on"
    for key, flag in (
        ("batch", "-b"), ("ubatch", "-ub"), ("cache_type_k", "-ctk"), ("cache_type_v", "-ctv"),
        ("flash_attn", "-fa"), ("threads", "-t"), ("load_mode", "-lm"),
    ):  # fmt: skip
        if key in f:
            argv += [flag, str(f[key])]
            out["expressed"].append(_entry(key, f[key], flag))
    if fit_on:
        margin = f.get("fit_target", DEFAULT_FIT_MARGIN_MIB)
        argv += ["-fitt", str(margin), "-fitc", str(ctx)]
        out["expressed"].append(_entry("fit", "on", "-fitt", f"margin {margin} MiB"))
        if "fit_target" in f:
            out["expressed"].append(_entry("fit_target", f["fit_target"], "-fitt"))
        out["approximated"].append(
            _entry(
                "context",
                ctx,
                "-fitc",
                "only the minimum context of the fit; the KV cache "
                "that llama-bench allocates follows the test depth, not -c",
            )  # fmt: skip
        )
    else:
        argv += ["-ngl", "99"]
        if f.get("fit") == "off":
            out["expressed"].append(_entry("fit", "off", "-ngl", "all layers, placement explicit"))
        out["unexpressed"].append(
            _entry(
                "context",
                ctx,
                None,
                "llama-bench has no context size option and, without fit, nothing else carries it",
            )  # fmt: skip
        )
    if f.get("cpu_moe"):
        argv += ["-ot", CPU_MOE_PATTERN]
        out["approximated"].append(
            _entry(
                "cpu_moe",
                True,
                "-ot",
                "llama-bench has no -cmoe; the same tensor override "
                "(experts to the CPU buffer type) is passed with -ot",
            )  # fmt: skip
        )
    if "n_cpu_moe" in f:
        argv += ["-ncmoe", str(f["n_cpu_moe"])]
        out["expressed"].append(_entry("n_cpu_moe", f["n_cpu_moe"], "-ncmoe"))
    if "parallel" in f:
        out["expressed" if f["parallel"] == 1 else "unexpressed"].append(
            _entry("parallel", f["parallel"], None, "llama-bench runs a single sequence")
        )
    for key, why in NO_EQUIVALENT.items():
        if key in f:
            out["unexpressed"].append(_entry(key, f[key], None, why))
    for key, why in NOT_INFERENCE.items():
        if key in f and key not in ("model",):
            out["not_inference"].append(_entry(key, f[key], None, why))
    known = {"context", "fit", "fit_target", "cpu_moe", "n_cpu_moe", "batch", "ubatch",
             "cache_type_k", "cache_type_v", "flash_attn", "parallel", "threads", "load_mode",
             *NO_EQUIVALENT, *NOT_INFERENCE}  # fmt: skip
    for key in sorted(set(f) - known):
        out["unexpressed"].append(_entry(key, f[key], None, "unknown field: not mapped"))
    out["argv"] = argv
    return out


def commands(mapping: dict, depths: list[int], reps: int) -> list[dict]:
    """The two llama-bench invocations (arguments after the binary)."""
    d = ",".join(str(x) for x in depths)
    tail = ["-r", str(reps), "-o", "json"]
    return [
        {"name": "fresh_prefill", "argv": [*mapping["argv"], "-p", d, "-n", "0", "-d", "0", *tail]},
        {"name": "turn", "argv": [*mapping["argv"], "-p", str(APPEND_TOKENS), "-n", str(N_GEN),
                                  "-d", d, *tail]},
    ]  # fmt: skip


def parse_rows(stdout: str) -> list[dict]:
    """The JSON array llama-bench prints with ``-o json`` (log lines before it are skipped)."""
    start = stdout.find("[")
    if start < 0:
        raise ValueError("no JSON array in the llama-bench output")
    rows = json.loads(stdout[start:])
    if not isinstance(rows, list):
        raise ValueError("the llama-bench output is not a JSON array")
    return rows


def summarize_rows(rows: list[dict]) -> list[dict]:
    """One entry per test: kind (prefill, decode), tokens, depth, the samples and their summary."""
    out = []
    for r in rows:
        n_p, n_g, n_d = int(r.get("n_prompt", 0)), int(r.get("n_gen", 0)), int(r.get("n_depth", 0))
        samples = [float(x) for x in r.get("samples_ts") or []]
        kind = "prefill" if n_p and not n_g else ("decode" if n_g and not n_p else "mixed")
        out.append(
            {
                "kind": kind,
                "n_prompt": n_p,
                "n_gen": n_g,
                "n_depth": n_d,
                "tokens_per_second": stats.summarize(samples) if samples else None,
                "samples_ts": samples,
                "llama_bench_avg_ts": r.get("avg_ts"),
                "build_commit": r.get("build_commit"),
            }
        )
    return out


def default_cell(scores: list[dict]) -> dict:
    """The cross-check cell that llama-bench can express most completely: fewest inexpressible
    inference fields, then fewest approximated fields, then a member of the Stage 1 shortlist, then
    the name. ``scores``: dicts with ``cell``, ``unexpressed`` (int), ``approximated`` (int) and
    ``shortlisted`` (bool)."""
    return min(
        scores, key=lambda s: (s["unexpressed"], s["approximated"], not s["shortlisted"], s["cell"])
    )


def load_resolved(path: Path) -> dict:
    import tomllib

    with open(path, "rb") as fh:
        return tomllib.load(fh)


def expressibility(
    root: Path | None = None, context: str = "64K", sessions: list[Path] | None = None
) -> list[dict]:
    """For every Stage 1 candidate cell of a context: how many fields llama-bench cannot express."""
    from ..sanity_runner import SanityError, resolve_cell
    from ..sweep import spec as sp
    from .shortlist import load_shortlist

    root = Path(root) if root else repo_root()
    sl = load_shortlist(root)
    short = {e.cell for e in sl.contexts[context]}
    machine, model = load_machine(root / "configs/machine.toml"), load_model()
    out = []
    for c in sp.expand(sl.spec, root):  # type: ignore[arg-type]
        if c.profile == "stock" or c.coords.get("context") != context:
            continue
        try:
            r = resolve_cell(c.name, root, sessions)
        except SanityError:
            continue
        fields = load_resolved(r["toml"])
        cfg = ServerConfig.model_validate(fields)
        m = map_config(fields, resolve_model_path(cfg, machine, model))
        out.append(
            {
                "cell": c.name,
                "unexpressed": len(m["unexpressed"]),
                "approximated": len(m["approximated"]),
                "shortlisted": c.name in short,
                "unexpressed_fields": [e["field"] for e in m["unexpressed"]],
                "approximated_fields": [e["field"] for e in m["approximated"]],
            }
        )
    return sorted(out, key=lambda s: s["cell"])


def bench_binary(machine_path: Path | None = None) -> Path:
    machine = load_machine(machine_path or repo_root() / "configs/machine.toml")
    return Path(machine.paths.llama_server).with_name("llama-bench")


def run_bench(
    cell: str,
    out: Path,
    *,
    reps: int = 5,
    root: Path | None = None,
    sessions: list[Path] | None = None,
    binary: Path | None = None,
    machine_path: Path | None = None,
    model: ModelConfig | None = None,
    data_label: str | None = None,
    provider=None,
    require_lock: bool = True,
    preconditions: Callable[[], dict] | None = None,
    snapshot: Callable[[], dict] | None = None,
    sampler_factory: Callable[[Path], object] | None = None,
    timeout_s: int = 3600,
) -> dict:
    """Run llama-bench for a cell under the GPU lock (``SMALLPC_GPU_LOCK_HELD``), write ``out`` (and
    the telemetry CSV next to it) and return the result."""
    from .. import envsnap, microbench, telemetry
    from ..sanity_runner import SanityError, resolve_cell
    from ..sweep.core import WorkloadProvider

    root = Path(root) if root else repo_root()
    test_bypass = (
        os.environ.get("SMALLPC_BENCH_NO_LOCK") == "1" and "PYTEST_CURRENT_TEST" in os.environ
    )
    if require_lock and not os.environ.get("SMALLPC_GPU_LOCK_HELD") and not test_bypass:
        raise SanityError(
            "the GPU lock is not held: start this through scripts/run-detached.sh --gpu"
        )
    machine_path = machine_path or root / "configs/machine.toml"
    machine, model = load_machine(machine_path), model or load_model()
    r = resolve_cell(cell, root, sessions)
    fields = load_resolved(r["toml"])
    cfg = ServerConfig.model_validate(fields)
    mapping = map_config(fields, resolve_model_path(cfg, machine, model))
    depths = (provider or WorkloadProvider()).depths(int(fields["context"]))
    cmds = commands(mapping, depths, reps)
    binary = Path(binary) if binary else bench_binary(machine_path)
    pre = (preconditions or (lambda: microbench.require_preconditions("bench")))()
    snap = (snapshot or envsnap.snapshot)()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    csv = out.with_name(out.stem + "-telemetry.csv")
    sam = sampler_factory(csv) if sampler_factory else telemetry.Sampler(csv)
    runs, tests = [], []
    t0 = time.time()
    with sam:
        for c in cmds:
            t_start = time.time()
            p = subprocess.run(
                [str(binary), *c["argv"]], capture_output=True, text=True, check=False,
                timeout=timeout_s, env={**os.environ, "LD_LIBRARY_PATH": str(binary.parent)},
            )  # fmt: skip
            runs.append(
                {"name": c["name"], "argv": [binary.name, *c["argv"]], "exit_code": p.returncode,
                 "seconds": round(time.time() - t_start, 1), "stderr_tail": p.stderr[-400:]}
            )  # fmt: skip
            if p.returncode != 0:
                raise RuntimeError(
                    f"llama-bench {c['name']} failed ({p.returncode}): {p.stderr[-400:]}"
                )
            tests += [{"invocation": c["name"], **t} for t in summarize_rows(parse_rows(p.stdout))]
    t1 = time.time()
    rows = telemetry.window(sam.rows, t0, t1)
    result = {
        "label": CROSSCHECK_LABEL,
        "data_label": data_label,
        "cell": r["name"],
        "resolved_from": r["resolved_from"],
        "config_sha256": hashlib.sha256(Path(r["toml"]).read_bytes()).hexdigest(),
        "repetitions": reps,
        "depths": depths,
        "llama_bench": {
            "binary": binary.name,
            "commit": next((t["build_commit"] for t in tests if t.get("build_commit")), None),
        },
        "runs": runs,
        "tests": tests,
        "expressed": mapping["expressed"],
        "approximated": mapping["approximated"],
        "unexpressed": mapping["unexpressed"],
        "not_inference": mapping["not_inference"],
        "note": "llama-bench uses random-token prompts of the requested lengths: these figures "
        "show how far such numbers differ from the real-prompt figures of the sweep and are "
        "never used to choose a configuration.",
        "environment": {"snapshot_id": snap.get("snapshot_id")},
        "telemetry": {
            "csv": csv.name,
            "rows": len(sam.rows),
            "detectors": telemetry.evaluate(rows),
        },  # fmt: skip
        "preconditions": pre,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0)),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t1)),
    }
    result = scrub_json(result, Identity.current())
    out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def format_expressibility(scores: list[dict]) -> str:
    best = default_cell(scores)
    lines = ["cell | inexpressible | approximated | shortlisted"]
    for s in scores:
        mark = "  <- default" if s["cell"] == best["cell"] else ""
        lines.append(
            f"{s['cell']} | {s['unexpressed']} ({', '.join(s['unexpressed_fields']) or '-'}) | "
            f"{s['approximated']} ({', '.join(s['approximated_fields']) or '-'}) | "
            f"{'yes' if s['shortlisted'] else 'no'}{mark}"
        )
    return "\n".join(lines)


__all__ = ["CROSSCHECK_LABEL", "default_cell", "map_config", "run_bench"]
