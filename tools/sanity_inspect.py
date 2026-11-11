"""Characterise the 8-gram repeats of failing sanity outputs (WP12 part 2g, step B.2).

Runs the reference and each named cell once (one server at a time, through the sanity runner's
own functions, so the outputs are produced exactly as in ``python -m smallpc.sanity run``) and
records, per prompt and cell, ONLY counts and token indices; no generated text, no token ids and
no token arrays are written anywhere:

* how many distinct 8-grams repeat 4 or more times (non-overlapping occurrences, counted the way
  ``smallpc.sanity.max_ngram_repeat`` counts);
* for the most repeated 8-gram: its count and the token index (start) of each occurrence, the gaps
  between successive occurrences and the pattern: ``loop`` (3 or more occurrences, all gaps equal),
  ``clustered`` (all gaps at most 64 tokens, not equal) or ``scattered`` (any larger gap);
* the position of the first divergence from the reference (``smallpc.sanity.first_divergence``) and
  whether the first occurrence of the most repeated 8-gram lies after it.

Run it detached under the GPU lock:

    scripts/run-detached.sh --gpu sanity-inspect -- \\
        uv run --frozen python tools/sanity_inspect.py --reference P1-32K-b2048 \\
        --cells s2b-P6-32K-b4096-mtp2-kvf16 s2a2-P2-32K-b4096-mtp2 \\
        --out data/sanity/diagnostic-32K-inspect.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from smallpc import sanity, sanity_runner
from smallpc.config import repo_root
from smallpc.scrub import Identity, scrub_json
from smallpc.sweep.core import WorkloadProvider

NGRAM = sanity.NGRAM_N
MIN_REPEATS = 4
CLUSTER_GAP = 64


def occurrences(tokens: Sequence[int], n: int = NGRAM) -> dict[tuple, list[int]]:
    """Start indices of the non-overlapping occurrences of each n-gram (greedy from the left)."""
    found: dict[tuple, list[int]] = {}
    next_free: dict[tuple, int] = {}
    for i in range(len(tokens) - n + 1):
        g = tuple(tokens[i : i + n])
        if i >= next_free.get(g, 0):
            found.setdefault(g, []).append(i)
            next_free[g] = i + n
    return found


def pattern_of(starts: Sequence[int]) -> tuple[list[int], str]:
    gaps = [b - a for a, b in zip(starts, starts[1:], strict=False)]
    if len(starts) >= 3 and len(set(gaps)) == 1:
        return gaps, "loop"
    if gaps and max(gaps) <= CLUSTER_GAP:
        return gaps, "clustered"
    return gaps, "scattered"


def characterise(tokens: Sequence[int], reference: Sequence[int]) -> dict:
    """Counts and indices only (see the module docstring)."""
    occ = occurrences(tokens)
    repeated = {g: s for g, s in occ.items() if len(s) >= MIN_REPEATS}
    div = sanity.first_divergence(tokens, reference)
    out: dict = {
        "length": len(tokens),
        "distinct_8grams_repeating_4_or_more": len(repeated),
        "max_8gram_repeat": sanity.max_ngram_repeat(tokens),
        "first_divergence": div,
        "top_8gram": None,
    }
    if occ:
        # ties are broken by the earliest first occurrence, so the choice is deterministic
        top = max(occ.values(), key=lambda s: (len(s), -s[0]))
        gaps, kind = pattern_of(top)
        out["top_8gram"] = {
            "count": len(top),
            "start_indices": list(top),
            "gaps": gaps,
            "pattern": kind,
            "first_occurrence_after_divergence": None if div is None else top[0] >= div,
        }
    return out


def inspect(
    cells: Sequence[str],
    reference: str,
    *,
    root: Path | None = None,
    sessions: Sequence[Path] | None = None,
    machine: Path | None = None,
    model_config: Path | None = None,
    health_timeout: int = 600,
    provider=None,
    run_cell=sanity_runner.run_cell,
    require_lock: bool = True,
) -> dict:
    sanity_runner._require_lock(require_lock)
    root = Path(root) if root else repo_root()
    provider = provider or WorkloadProvider()
    kw = dict(
        provider=provider,
        scripts_dir=root / "scripts",
        log_root=Path(os.environ.get("SMALLPC_LOG_ROOT", root / "data/logs")),
        machine=machine,
        model_config=model_config,
        health_timeout=health_timeout,
    )
    ref = sanity_runner.resolve_cell(reference, root, sessions)
    ref_run = run_cell(ref, **kw)
    if ref_run["error"] is not None or len(ref_run["tokens"]) != sanity_runner.N_PROMPTS:
        raise sanity_runner.SanityError(f"the reference run failed: {ref_run['error']}")
    res: dict = {
        "note": "counts and token indices only: no generated text and no token ids",
        "ngram": NGRAM,
        "min_repeats": MIN_REPEATS,
        "cluster_gap": CLUSTER_GAP,
        "reference": ref["name"],
        "cells": {},
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for spec in cells:
        cell = sanity_runner.resolve_cell(spec, root, sessions)
        run = run_cell(cell, **kw)
        if run["error"] is not None or len(run["tokens"]) != sanity_runner.N_PROMPTS:
            res["cells"][cell["name"]] = {"error": str(run["error"]), "prompts": {}}
            continue
        res["cells"][cell["name"]] = {
            "resolved_from": cell["resolved_from"],
            "run_id": run["run_id"],
            "prompts": {
                pid: characterise(ids, ref_run["tokens"][pid])
                for pid, ids in sorted(run["tokens"].items())
            },
        }
    return json.loads(json.dumps(res))


def format_table(res: dict) -> str:
    lines = [f"reference: {res['reference']}"]
    for name, c in res["cells"].items():
        lines.append(f"{name}:")
        for pid, p in c["prompts"].items():
            t = p["top_8gram"]
            top = (
                "none"
                if t is None
                else f"{t['count']} occurrences at {t['start_indices']} ({t['pattern']})"
            )
            lines.append(
                f"  {pid}: {p['distinct_8grams_repeating_4_or_more']} 8-gram(s) repeat "
                f"{MIN_REPEATS}+ times, max {p['max_8gram_repeat']}; most repeated: {top}; "
                f"first divergence {p['first_divergence']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cells", nargs="+", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--session", action="append", type=Path, help="look cells up here only")
    ap.add_argument("--machine", type=Path)
    ap.add_argument("--model-config", type=Path)
    ap.add_argument("--health-timeout", type=int, default=600)
    a = ap.parse_args(argv)
    try:
        res = inspect(
            a.cells,
            a.reference,
            sessions=a.session,
            machine=a.machine,
            model_config=a.model_config,
            health_timeout=a.health_timeout,
        )
    except sanity_runner.SanityError as e:
        print(f"sanity_inspect: {e}", file=sys.stderr)
        return 2
    res = scrub_json(res, Identity.current())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(format_table(res))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
