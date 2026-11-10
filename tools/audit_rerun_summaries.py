"""Read-only audit (WP12 part 2d, B2): which cell summaries under data/raw/ lost ``coords`` or
``resolution`` after they were first committed. For each summary file, the earliest committed
version is compared with the current one. Prints a table and writes JSON with ``--out``."""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

KEYS = ("coords", "resolution")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows: list[dict] = []
    for p in sorted(Path(a.raw).glob("*/cells/*.json")):
        cur = json.loads(p.read_text())
        commits = git("log", "--format=%H", "--", str(p)).split()
        if not commits:
            continue
        versions = []
        for c in reversed(commits):  # oldest first
            try:
                versions.append((c, json.loads(git("show", f"{c}:{p}"))))
            except subprocess.CalledProcessError:
                continue
        first_c, first = versions[0]
        # the last commit before the one where a key became empty/missing
        for k in KEYS:
            now = cur.get(k)
            if k in cur and now:
                continue
            src = next(((c, v) for c, v in reversed(versions) if v.get(k)), None)
            if src is None:
                continue  # never set (a canary, or a cell without tokens)
            rows.append(
                {
                    "session": p.parts[-3],
                    "cell": cur.get("cell"),
                    "file": str(p),
                    "key": k,
                    "now": "missing" if k not in cur else "empty",
                    "set_in_commit": src[0],
                    "last_good_commit": src[0][:10],
                    "commits_touching": [c[:10] for c in reversed(commits)],
                }
            )
    print(f"{len(rows)} damaged (file, key) pairs")
    for r in rows:
        print(
            f"{r['session']:12} {r['cell']:28} {r['key']:10} {r['now']:8} last good {r['last_good_commit']}"
        )
    if a.out:
        Path(a.out).write_text(json.dumps(rows, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
