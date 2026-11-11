"""Union of per-run sanity files into one file for ``smallpc.select --sanity`` (WP12 part 2g).

    uv run python tools/merge_sanity.py data/sanity/stage2-32K.json data/sanity/stage2-64K.json \\
        data/sanity/stage2-128K.json data/sanity/diagnostic-32K.json \\
        data/sanity/diagnostic-32K-repeat.json data/sanity/diagnostic-64K.json \\
        --out data/sanity/stage2-all.json

Cells only. Where a cell appears in more than one file (a repeated run, or the reference that
every run contains), the FIRST occurrence in argument order is kept under ``cells`` and the later
ones are listed under ``repeats`` with their source file, result and run id, so a repeat that
disagrees with the first run stays visible. Nothing but verdicts, hashes and ids is copied (the
inputs contain no text). This replaces the one-off merge written in part 2f.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

KEEP = ("result", "failed_prompts", "reference", "resolved_from", "config_sha256", "run_id")


def _entry(cell: dict, source: str) -> dict:
    out = {k: cell[k] for k in KEEP if k in cell}
    out["source"] = source
    if cell.get("prompts"):
        out["tokens_sha256"] = {
            p: v.get("tokens_sha256") for p, v in sorted(cell["prompts"].items())
        }
    return out


def merge(paths: list[Path]) -> dict:
    cells: dict[str, dict] = {}
    repeats: dict[str, list[dict]] = {}
    for path in paths:
        data = json.loads(Path(path).read_text())
        if "cells" not in data:
            raise ValueError(f"{path}: not a sanity file (no 'cells')")
        for name, cell in data["cells"].items():
            entry = _entry(cell, Path(path).name)
            if name in cells:
                repeats.setdefault(name, []).append(entry)
            else:
                cells[name] = entry
    return {
        "note": "union of per-run sanity files (cells only); the first run of a cell is kept, "
        "later runs of the same cell are under 'repeats' (tools/merge_sanity.py)",
        "sources": [Path(p).name for p in paths],
        "cells": cells,
        "repeats": repeats,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        res = merge(a.files)
    except (OSError, ValueError) as e:
        print(f"merge_sanity: {e}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    n_rep = sum(len(v) for v in res["repeats"].values())
    print(f"wrote {a.out}: {len(res['cells'])} cells, {n_rep} repeated entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
