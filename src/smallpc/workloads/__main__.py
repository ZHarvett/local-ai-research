"""CLI: ``python -m smallpc.workloads run <step>...`` with steps ``build``, ``verify``, ``check``.

All steps share one llama-server session, started through ``scripts/launch-server.sh`` with
``configs/server/workload-check-128k.toml`` (run the command under the GPU lock, for example via
``scripts/run-detached.sh --gpu``) and stopped through ``scripts/stop-server.sh``. ``--server-url``
reuses a server that is already running (it is left running).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from .. import envsnap
from ..config import repo_root
from .build import build_all, make_clients, model_path, read_gguf_info
from .check import run_checks
from .manifest import (
    MAX_MANIFEST_BYTES,
    assert_text_free,
    load_manifest,
    manifest_path,
    save_manifest,
)
from .recipe import load_recipe
from .session import DEFAULT_CONFIG, Session
from .verify import verify_all, write_report

ROOT = repo_root()


def log(msg: str) -> None:
    print(msg, flush=True)


def _props_essentials(props: dict) -> dict:
    gen = props.get("default_generation_settings", {}) or {}
    return {
        "total_slots": props.get("total_slots"),
        "n_ctx_per_slot": gen.get("n_ctx"),
        "build_info": props.get("build_info"),
    }


def cmd_run(args: argparse.Namespace) -> int:
    steps = args.steps
    unknown = [s for s in steps if s not in ("build", "verify", "check")]
    if unknown:
        raise SystemExit(f"unknown step(s): {unknown}")
    recipe = load_recipe(ROOT / "configs/workloads/recipe.toml")
    gguf = read_gguf_info(model_path(ROOT))
    date = time.strftime("%Y-%m-%d", time.gmtime())
    out_dir = ROOT / ("data/cache/workloads/checks" if args.scratch else "data/workloads")
    out_dir.mkdir(parents=True, exist_ok=True)

    snap_ref = None
    if "check" in steps:  # machine state before any server of this job exists
        snap = envsnap.snapshot()
        snap_path = out_dir / f"env-snapshot-{date}.json"
        snap_path.write_text(json.dumps(snap, indent=2) + "\n")
        snap_ref = {"snapshot_id": snap["snapshot_id"], "file": str(snap_path.relative_to(ROOT))}

    session = Session.attach(args.server_url) if args.server_url else Session(Path(args.config))
    rc = 0
    check_result: dict | None = None
    try:
        with session:
            tok, renderer, client = make_clients(session.base_url, gguf)
            props = session.props()
            if "build" in steps:
                manifest = build_all(
                    ROOT, tok=tok, renderer=renderer, gguf=gguf, recipe=recipe, log=log
                )
                digest = save_manifest(manifest)
                log(
                    f"manifest written: {manifest_path().relative_to(ROOT)} sha256 {digest[:16]}; "
                    f"summary {manifest.summary}"
                )
                assert_text_free(manifest_path(), MAX_MANIFEST_BYTES)
            if "verify" in steps:
                rep = verify_all(ROOT, tok, renderer, log=log, recipe=recipe, gguf=gguf)
                path = write_report(rep, ROOT)
                log(
                    f"verify: {'PASS' if rep.ok else 'FAIL'} ({len(rep.checks)} checks) -> "
                    f"{path.relative_to(ROOT)}"
                )
                rc = rc or (0 if rep.ok else 1)
            if "check" in steps:
                manifest = load_manifest()
                variants = [int(v) for v in args.variants.split(",")] if args.variants else None
                check_result = run_checks(
                    session.base_url, recipe, manifest, log=log, variants=variants
                )
                check_result["props"] = _props_essentials(props)
                check_result["server_argv"] = session.argv()
            client.close()
    finally:
        stop = session.stop()
    if check_result is not None:
        mtext = manifest_path().read_bytes()
        check_result |= {
            "schema": 1,
            "date_utc": date,
            "server_config": str(Path(args.config).relative_to(ROOT))
            if not args.server_url
            else None,
            "environment_snapshot": snap_ref,
            "manifest_sha256": hashlib.sha256(mtext).hexdigest(),
            "sampling": {
                "source": "configs/model.toml [sampling.general]",
                "seed": "per request, see pairs",
            },
            "stop_status": stop,
            "scratch": bool(args.scratch),
        }
        path = out_dir / f"live-check-{date}.json"
        path.write_text(json.dumps(check_result, indent=1) + "\n")
        assert_text_free(path)
        log(f"live check written: {path.relative_to(ROOT)}; summary {check_result['summary']}")
        if check_result["summary"]["findings"]:
            log("FINDINGS:\n  " + "\n  ".join(check_result["findings"]))
            rc = rc or 1
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.workloads", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run build / verify / check in one server session")
    run.add_argument("steps", nargs="+", help="build, verify, check")
    run.add_argument("--server-url", help="reuse a running llama-server (left running)")
    run.add_argument("--config", default=str(DEFAULT_CONFIG), help="server config to launch")
    run.add_argument("--variants", help="check only these variants (iteration; comma-separated)")
    run.add_argument(
        "--scratch", action="store_true", help="write results under data/cache (iteration)"
    )
    args = ap.parse_args(argv)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
