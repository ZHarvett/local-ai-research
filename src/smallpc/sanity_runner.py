"""Output sanity runner (step plan 5.6, WP12): greedy 512-token outputs of the three sanity prompts
of the workload manifest, from the reference and from each candidate cell, judged by the pure
functions of ``smallpc.sanity``.

    python -m smallpc.sanity run --cells <names or resolved toml files> --reference <cell> \
        --out data/sanity/<name>.json

Run it detached under the GPU lock (``scripts/run-detached.sh --gpu sanity-<name> -- uv run
python -m smallpc.sanity run ...``). For the reference (the plain ``--fit`` cell of the same
context, P1, batch b2048) and for each cell it starts a server through
``scripts/launch-server.sh`` with the cell's resolved config (the same effective config as the
measured cell: a cell name is looked up in ``data/raw/*/resolved/<name>.toml``), sends the three
prompts greedily for 512 tokens asking for the token ids (``return_tokens``), stops the server
cleanly and applies the section 5.6 thresholds against the reference. Servers run one after
another, never two at once.

The output JSON has, per cell and prompt, the metrics, the pass/fail reasons and the first
divergence index, and the overall ``result`` per cell in the shape ``smallpc.select --sanity`` reads
(``{"cells": {name: {"result": "pass"|"fail"|"not run", ...}}}``). It contains no prompt text and no
output text or token arrays: only prompt ids, counts, hashes and metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from . import labels, sanity
from .config import repo_root
from .scrub import Identity, scrub_json
from .stage2.specgen import FT_PREFIX
from .sweep.client import Client, RequestTimeout, ServerGone
from .sweep.core import WorkloadProvider
from .sweep.server import ServerProc, safe_id

SCHEMA = 1
PROMPT_LENGTH = 2048
N_PROMPTS = 3
N_PREDICT = 512
SEED = 20261110
# Greedy: temperature 0 (argmax), no truncation sampling, token ids returned with the text.
GREEDY = {"temperature": 0.0, "top_k": 1, "top_p": 1.0, "min_p": 0.0, "return_tokens": True}
ENV_NO_LOCK = "SMALLPC_SANITY_NO_LOCK"


class SanityError(RuntimeError):
    """The run cannot start (bad arguments, no lock, unknown cell); the message says what to do."""


def _require_lock(require: bool) -> None:
    if not require:
        return
    if os.environ.get(ENV_NO_LOCK) == "1" and "PYTEST_CURRENT_TEST" in os.environ:
        return
    if not os.environ.get("SMALLPC_GPU_LOCK_HELD"):
        raise SanityError(
            "the GPU lock is not held: start this through scripts/run-detached.sh --gpu "
            "(or scripts/with-gpu-lock.sh)"
        )


def resolve_cell(spec: str, root: Path, sessions: Sequence[Path] | None = None) -> dict:
    """``{"name", "toml", "resolved_from"}`` for a path to a resolved TOML or a cell name. A name is
    looked up in the ``resolved/`` directory of the sessions under ``data/raw`` (newest first,
    functional-test sessions skipped); the session it came from is recorded."""
    p = Path(spec)
    if p.suffix == ".toml" and p.exists():
        return {"name": p.stem, "toml": p.resolve(), "resolved_from": str(p)}
    dirs = [Path(s) for s in sessions] if sessions else sorted(
        (root / "data/raw").glob("*"), key=lambda d: d.stat().st_mtime, reverse=True
    )  # fmt: skip
    for d in dirs:
        if d.name.startswith(FT_PREFIX) and not sessions:
            continue
        f = d / "resolved" / f"{spec}.toml"
        if f.exists():
            return {"name": spec, "toml": f.resolve(), "resolved_from": d.name}
    raise SanityError(f"no resolved config for cell {spec!r} under data/raw/*/resolved/")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ids_sha256(ids: Sequence[int]) -> str:
    return hashlib.sha256(json.dumps(list(ids)).encode()).hexdigest()


_COUNTER = itertools.count()


def _stamp() -> str:
    """A run-id suffix that is unique within and across processes (second, pid, counter)."""
    return f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}-{os.getpid()}-{next(_COUNTER)}"


def run_cell(
    cell: dict,
    *,
    provider,
    scripts_dir: Path,
    log_root: Path,
    machine: Path | None,
    model_config: Path | None,
    server_env: dict | None = None,
    health_timeout: int = 600,
    n_predict: int = N_PREDICT,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """One server: start, three greedy requests, stop. Returns ``{"tokens": {prompt id: ids},
    "stop_types", "timings", "run_id", "error"}``; ``error`` is set (and ``tokens`` may be partial)
    if the server did not start or a request failed."""
    from .config import load_machine

    run_id = safe_id("sanity", cell["name"], _stamp())
    proc = ServerProc(
        scripts_dir, log_root, machine, model_config, health_timeout=health_timeout, env=server_env
    )
    out: dict = {"run_id": run_id, "tokens": {}, "stop_types": {}, "timings": {}, "error": None}
    t0 = clock()
    start = proc.start(Path(cell["toml"]), run_id)
    out["load_time_s"] = round(clock() - t0, 2)
    if not start.healthy:
        out["error"] = {"stage": "start", "reason": start.reason, "log_matches": start.log_matches}
        proc.stop()
        return out
    mach = load_machine(machine)
    client = Client(f"http://{mach.server.host}:{mach.server.port}")
    try:
        for i in range(N_PROMPTS):
            w = provider.get("sanity", PROMPT_LENGTH, i, base_url=client.base_url)
            c = client.completion(
                list(w.a_tokens), n_predict, GREEDY, seed=SEED, stream=False, cache_prompt=False
            )
            body = c.body
            ids = body.get("tokens")
            if not isinstance(ids, list):
                out["error"] = {"stage": "request", "reason": "the response has no token ids"}
                break
            out["tokens"][w.id] = [int(t) for t in ids]
            out["stop_types"][w.id] = body.get("stop_type")
            t = body.get("timings") or {}
            out["timings"][w.id] = {
                "predicted_n": t.get("predicted_n"),
                "predicted_per_second": t.get("predicted_per_second"),
            }
    except (RequestTimeout, ServerGone) as e:
        out["error"] = {"stage": "request", "reason": f"{type(e).__name__}: {e}"}
    finally:
        client.close()
        out["stop"] = proc.stop()
    return out


def degenerate_reference(tokens: dict[str, list[int]]) -> list[str]:
    """Warnings if the reference's own output is degenerate by the absolute limits: the relative
    thresholds would then pass any candidate that is as bad."""
    out = []
    for pid, ids in sorted(tokens.items()):
        m = sanity.metrics(ids)
        if m["longest_run"] >= sanity.RUN_LIMIT:
            out.append(f"{pid}: the reference repeats one token {m['longest_run']} times in a row")
        if m["max_8gram_repeat"] >= sanity.NGRAM_REPEAT_LIMIT:
            out.append(f"{pid}: the reference repeats an 8-gram {m['max_8gram_repeat']} times")
        if m["length"] < sanity.MIN_LENGTH:
            out.append(f"{pid}: the reference output has only {m['length']} tokens")
    return out


def _prompt_entry(ids: Sequence[int], stop_type: str | None) -> dict:
    return {
        "n_tokens": len(ids),
        "tokens_sha256": ids_sha256(ids),
        "stop_type": stop_type,
        "metrics": sanity.metrics(ids),
    }


def run_sanity(
    cells: Sequence[str],
    reference: str,
    *,
    root: Path | None = None,
    provider=None,
    scripts_dir: Path | None = None,
    log_root: Path | None = None,
    machine: Path | None = None,
    model_config: Path | None = None,
    server_env: Callable[[str], dict] | None = None,
    sessions: Sequence[Path] | None = None,
    label: str = "results",
    health_timeout: int = 600,
    require_lock: bool = True,
) -> dict:
    """Run the reference, then each cell (one server at a time) and judge them. ``server_env(name)``
    is the environment of the server of that cell (tests make one cell misbehave)."""
    _require_lock(require_lock)
    root = Path(root) if root else repo_root()
    provider = provider or WorkloadProvider()
    scripts_dir = Path(scripts_dir) if scripts_dir else root / "scripts"
    log_root = Path(log_root) if log_root else Path(
        os.environ.get("SMALLPC_LOG_ROOT", root / "data/logs")
    )  # fmt: skip
    ref = resolve_cell(reference, root, sessions)
    cands = []
    for c in cells:
        r = resolve_cell(c, root, sessions)
        if r["name"] != ref["name"] and all(r["name"] != x["name"] for x in cands):
            cands.append(r)
    kw = dict(provider=provider, scripts_dir=scripts_dir, log_root=log_root, machine=machine,
              model_config=model_config, health_timeout=health_timeout)  # fmt: skip

    def env_of(name: str) -> dict | None:
        return server_env(name) if server_env else None

    t0 = time.time()
    ref_run = run_cell(ref, server_env=env_of(ref["name"]), **kw)
    ref_ok = ref_run["error"] is None and len(ref_run["tokens"]) == N_PROMPTS
    result: dict = {
        "schema": SCHEMA,
        "label": label,
        "banner": labels.banner(label),
        "prompts": {
            "kind": "sanity",
            "ids": sorted(ref_run["tokens"]) or None,
            "n_predict": N_PREDICT,
            "sampling": "greedy (temperature 0, top_k 1), return_tokens, fixed seed",
        },
        "thresholds": {
            "min_length": sanity.MIN_LENGTH,
            "length_fraction": sanity.LENGTH_FRACTION,
            "distinct_4gram_fraction": sanity.DISTINCT_4GRAM_FRACTION,
            "run_limit": sanity.RUN_LIMIT,
            "ngram_repeat_limit": sanity.NGRAM_REPEAT_LIMIT,
            "rule": "plan v1.6 section 5.6, smallpc.sanity",
        },
        "reference": {
            "cell": ref["name"],
            "resolved_from": ref["resolved_from"],
            "config_sha256": _sha(ref["toml"]),
            "run_id": ref_run["run_id"],
            "ok": ref_ok,
            "error": ref_run["error"],
            "warnings": degenerate_reference(ref_run["tokens"]) if ref_ok else [],
            "prompts": {
                pid: _prompt_entry(ids, ref_run["stop_types"].get(pid))
                for pid, ids in sorted(ref_run["tokens"].items())
            },
        },
        "cells": {},
    }
    result["cells"][ref["name"]] = {
        "result": "pass" if ref_ok else "not run",
        "reference": True,
        "note": "the reference itself: its outputs are the baseline, not compared with anything",
        "config_sha256": _sha(ref["toml"]),
        "run_id": ref_run["run_id"],
    }
    for c in cands:
        run = run_cell(c, server_env=env_of(c["name"]), **kw)
        entry: dict = {
            "reference": False,
            "resolved_from": c["resolved_from"],
            "config_sha256": _sha(c["toml"]),
            "run_id": run["run_id"],
            "load_time_s": run.get("load_time_s"),
        }
        if not ref_ok:
            entry |= {"result": "not run", "error": "the reference run failed", "prompts": {}}
        elif run["error"] is not None or len(run["tokens"]) < N_PROMPTS:
            entry |= {"result": "not run", "error": run["error"], "prompts": {}}
        else:
            verdict = sanity.check_candidate(run["tokens"], ref_run["tokens"])
            prompts = {}
            for pid, p in verdict["prompts"].items():
                prompts[pid] = {
                    **p,
                    **_prompt_entry(run["tokens"][pid], run["stop_types"].get(pid)),
                }
            entry |= {
                "result": verdict["result"],
                "failed_prompts": verdict["failed_prompts"],
                "prompts": prompts,
            }
        result["cells"][c["name"]] = entry
    result["duration_s"] = round(time.time() - t0, 1)
    result["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return json.loads(json.dumps(result))


def format_table(res: dict) -> str:
    """A text table of the metrics (candidate against reference) and the verdicts."""
    lines = [f"reference: {res['reference']['cell']}"]
    for name, c in res["cells"].items():
        if c.get("reference"):
            continue
        lines.append(f"{name}: {c['result'].upper()}")
        for pid, p in c.get("prompts", {}).items():
            m, r = p["candidate"], p["reference"]
            lines.append(
                f"  {pid}: len {m['length']} (ref {r['length']}), distinct-4gram "
                f"{m['distinct_4gram_ratio']:.3f} (ref {r['distinct_4gram_ratio']:.3f}), run "
                f"{m['longest_run']} (ref {r['longest_run']}), 8-gram repeat "
                f"{m['max_8gram_repeat']} (ref {r['max_8gram_repeat']}), first divergence "
                f"{p['first_divergence']}, "
                + ("ok" if p["ok"] else "FAIL: " + "; ".join(p["reasons"]))
            )
        if c.get("error"):
            lines.append(f"  not run: {c['error']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.sanity run")
    ap.add_argument("--cells", nargs="+", required=True, help="cell names or resolved toml files")
    ap.add_argument("--reference", required=True, help="the plain --fit cell of the same context")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--label", default="results", choices=list(labels.LABELS))
    ap.add_argument("--session", action="append", type=Path, help="look cells up here only")
    ap.add_argument("--machine", type=Path)
    ap.add_argument("--model-config", type=Path)
    ap.add_argument("--health-timeout", type=int, default=600)
    a = ap.parse_args(argv)
    try:
        res = run_sanity(
            a.cells, a.reference, sessions=a.session, machine=a.machine,
            model_config=a.model_config, label=a.label, health_timeout=a.health_timeout,
        )  # fmt: skip
    except SanityError as e:
        print(f"smallpc.sanity: {e}", file=sys.stderr)
        return 2
    res = scrub_json(res, Identity.current())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(format_table(res))
    print(f"wrote {a.out}")
    bad = [n for n, c in res["cells"].items() if c["result"] in ("fail", "not run")]
    return 1 if bad else 0
