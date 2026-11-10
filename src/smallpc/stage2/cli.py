"""``python -m smallpc.stage2``: the subcommands of the Stage 2 tooling."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bench as bn
from . import decide as dc
from . import eligibility, smoke, specgen
from . import gate as gt

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_NOT_NEEDED = 0, 1, 2, 3


def _spec_parser(sub) -> None:
    p = sub.add_parser("spec", help="write a Stage 2 sweep spec")
    p.add_argument("--stage", required=True, choices=["2f", "2a", "2a2", "2b", "2c", "2d"])
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--preset", choices=["functional-test"], help="tiny spec for the GPU checks")
    p.add_argument("--cache-ram", help="the chosen --cache-ram: a size in MiB, or 'default'")
    p.add_argument("--from-2f", type=Path, help="2f decision json (chosen_cache_ram)")
    p.add_argument("--from-2a", type=Path, help="2a decision json (the 2a2 input)")
    p.add_argument("--winner-from", type=Path, help="2a2 decision json (2b, 2c, 2d)")
    p.add_argument("--no-anchor", action="store_true", help="2a2: leave out the anchor cells")
    p.add_argument("--default-threads", type=int, help="2d: n_threads the server uses by default")


def _run_spec(a: argparse.Namespace) -> int:
    argv = " ".join(sys.argv[1:]) if sys.argv[1:2] == ["spec"] else f"spec --stage {a.stage}"
    try:
        text = specgen.generate(
            a.stage,
            preset=a.preset,
            cache_ram=a.cache_ram,
            from_2f=a.from_2f,
            from_2a=a.from_2a,
            winner_from=a.winner_from,
            anchor=not a.no_anchor,
            default_threads=a.default_threads,
            command=f"python -m smallpc.stage2 {argv}",
        )
    except specgen.NotNeeded as e:
        print(f"smallpc.stage2: {e}", file=sys.stderr)
        return EXIT_NOT_NEEDED
    except (specgen.SpecGenError, ValueError, OSError) as e:
        print(f"smallpc.stage2: {e}", file=sys.stderr)
        return EXIT_USAGE
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text)
    print(f"wrote {a.out}")
    return EXIT_OK


def _decide_parser(sub) -> None:
    p = sub.add_parser("decide", help="apply the declared Stage 2 rules to session data")
    p.add_argument("--stage", required=True, choices=list(dc.STAGES))
    p.add_argument("--sessions", nargs="*", default=[], type=Path, help="session directories")
    p.add_argument("--out", required=True, type=Path, help="writes <out>.json and <out>.md")
    p.add_argument(
        "--label", default="results", choices=["functional-test", "screening", "results"]
    )
    p.add_argument("--default-threads", type=int, help="2d without sessions: the default n_threads")


def _run_decide(a: argparse.Namespace) -> int:
    try:
        if a.stage == "2d" and not a.sessions:
            if a.default_threads is None:
                print(
                    "smallpc.stage2: 2d needs --sessions, or --default-threads 8", file=sys.stderr
                )
                return EXIT_USAGE
            res = dc.decide_2d_skipped(a.default_threads, label=a.label)
        else:
            if not a.sessions:
                print("smallpc.stage2: --sessions is needed", file=sys.stderr)
                return EXIT_USAGE
            res = dc.decide(a.stage, a.sessions, label=a.label)
    except eligibility.Refused as e:
        print(f"smallpc.stage2: refused: {e}", file=sys.stderr)
        return EXIT_USAGE
    except (ValueError, OSError, KeyError) as e:
        print(f"smallpc.stage2: {e}", file=sys.stderr)
        return EXIT_ERROR
    jpath, mpath = dc.write_outputs(res, a.out)
    print(f"wrote {jpath} and {mpath}")
    print(f"status: {res.get('status', 'see the contexts')}")
    for h in res.get("human_decision_needed", []):
        print(f"HUMAN DECISION NEEDED: {h}")
    return EXIT_OK


def _gate_parser(sub) -> None:
    p = sub.add_parser("gate", help="may the next Stage 2 session start?")
    p.add_argument("--stage", required=True, choices=list(gt.NEXT))
    p.add_argument("--session", required=True, type=Path, help="session directory (data/raw/<id>)")
    p.add_argument("--json", action="store_true")


def _run_gate(a: argparse.Namespace) -> int:
    try:
        g = gt.gate(a.stage, a.session)
    except (ValueError, OSError, KeyError) as e:
        print(f"smallpc.stage2: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(json.dumps(g, indent=1) if a.json else gt.format_gate(g))
    return EXIT_OK if g["pass"] else EXIT_ERROR


def _bench_parser(sub) -> None:
    p = sub.add_parser("bench-crosscheck", help="llama-bench cross-check of a cell (Stage 2e)")
    p.add_argument("--cell", help="cell name or resolved toml (default: the best expressible)")
    p.add_argument("--out", type=Path, help="data/microbench/<name>.json")
    p.add_argument("--reps", type=int, default=5)
    p.add_argument("--session", action="append", type=Path, help="look the cell up here only")
    p.add_argument("--data-label", help="e.g. functional-test")
    p.add_argument(
        "--list-expressibility", action="store_true", help="64K candidates and the default"
    )


def _run_bench(a: argparse.Namespace) -> int:
    from ..sanity_runner import SanityError

    try:
        if a.list_expressibility:
            scores = bn.expressibility(sessions=a.session)
            print(bn.format_expressibility(scores))
            return EXIT_OK
        if not a.out:
            print("smallpc.stage2: --out is needed", file=sys.stderr)
            return EXIT_USAGE
        cell = a.cell or bn.default_cell(bn.expressibility(sessions=a.session))["cell"]
        res = bn.run_bench(cell, a.out, reps=a.reps, sessions=a.session, data_label=a.data_label)
    except SanityError as e:
        print(f"smallpc.stage2: {e}", file=sys.stderr)
        return EXIT_USAGE
    except (RuntimeError, ValueError, OSError) as e:
        print(f"smallpc.stage2: {e}", file=sys.stderr)
        return EXIT_ERROR
    print(f"wrote {a.out}: {len(res['tests'])} tests, label: {res['label']}")
    print("not expressible: " + ", ".join(e["field"] for e in res["unexpressed"]))
    return EXIT_OK


def _smoke_parser(sub) -> None:
    p = sub.add_parser("smoke", help="one-request smoke start of a cell with changed settings")
    p.add_argument("--base-cell", required=True)
    p.add_argument("--set", dest="sets", action="append", default=[], help="key=value override")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--scratch", type=Path, help="where the scratch TOML goes (default: --out dir)")
    p.add_argument("--session", action="append", type=Path)
    p.add_argument("--n-predict", type=int, default=64)


def _run_smoke(a: argparse.Namespace) -> int:
    from ..sanity_runner import SanityError

    try:
        res = smoke.run_smoke(
            a.base_cell, smoke.parse_sets(a.sets), a.out, sessions=a.session,
            scratch=a.scratch or a.out.parent / "scratch", n_predict=a.n_predict,
        )  # fmt: skip
    except (SanityError, ValueError) as e:
        print(f"smallpc.stage2: {e}", file=sys.stderr)
        return EXIT_USAGE
    print(
        json.dumps(
            {k: res.get(k) for k in ("ok", "load_time_s", "request", "memory_peak", "error")},
            indent=1,
        )
    )
    return EXIT_OK if res["ok"] else EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.stage2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    _spec_parser(sub)
    _decide_parser(sub)
    _gate_parser(sub)
    _bench_parser(sub)
    _smoke_parser(sub)
    a = ap.parse_args(argv)
    if a.cmd == "spec":
        return _run_spec(a)
    if a.cmd == "decide":
        return _run_decide(a)
    if a.cmd == "gate":
        return _run_gate(a)
    if a.cmd == "bench-crosscheck":
        return _run_bench(a)
    if a.cmd == "smoke":
        return _run_smoke(a)
    return EXIT_USAGE
