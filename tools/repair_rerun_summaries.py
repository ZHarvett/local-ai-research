"""Repair the ``coords`` and ``resolution`` keys of cell summaries that a re-run blanked
(WP12 part 2d, step B3; the writer bug is fixed in ``Session._job_from_resolved``).

For each damaged summary the two keys are taken from the same file in the last commit before the
re-run (``git show <commit>:<path>``), checked against the session's ``resolved/<cell>.toml`` and
``resolutions.jsonl`` (any inconsistency: report and skip that cell), and written into the current
file, which is otherwise unchanged (same content, same key order; atomic write). One audit line per
repaired cell is appended to ``data/raw/<session>/repairs.jsonl``.

Dry run by default; ``--apply`` writes."""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

KEYS = ("coords", "resolution")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def history(path: Path) -> list[tuple[str, dict]]:
    """Committed versions of ``path``, oldest first."""
    out = []
    for c in reversed(git("log", "--format=%H", "--", str(path)).split()):
        try:
            out.append((c, json.loads(git("show", f"{c}:{path}"))))
        except (subprocess.CalledProcessError, ValueError):
            continue
    return out


def last_resolution(session_dir: Path, cell: str) -> dict | None:
    f = session_dir / "resolutions.jsonl"
    if not f.exists():
        return None
    found = None
    for line in f.read_text().splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("cell") == cell:
            found = o
    return found


def consistent(session_dir: Path, cell: str, key: str, value: dict) -> str | None:
    """None if ``value`` agrees with the session's own records, else the reason it does not."""
    toml_path = session_dir / "resolved" / f"{cell}.toml"
    if not toml_path.exists():
        return f"no {toml_path}"
    resolved = tomllib.loads(toml_path.read_text())
    if key == "resolution":
        rec = last_resolution(session_dir, cell)
        if rec is None:
            return "no resolutions.jsonl entry for the cell"
        if rec.get("resolution") != value:
            return "resolution differs from resolutions.jsonl"
        for k, info in value.items():
            if "value" in info and resolved.get(k) != info["value"]:
                return f"resolution {k} value {info['value']} != resolved config {resolved.get(k)}"
        return None
    tokens = cell.split("-")
    for axis, v in value.items():
        if v not in tokens:
            return f"coords {axis}={v} not in the cell name {cell}"
    ctx = value.get("context")
    if ctx:
        m = re.fullmatch(r"(\d+)K", ctx)
        if not m or int(m[1]) * 1024 != resolved.get("context"):
            return f"coords context {ctx} != resolved context {resolved.get('context')}"
    b = value.get("batch")
    if b:
        m = re.fullmatch(r"b(\d+)", b)
        if not m or int(m[1]) != resolved.get("batch"):
            return f"coords batch {b} != resolved batch {resolved.get('batch')}"
    return None


def plan(session_dir: Path) -> tuple[list[dict], list[dict]]:
    todo, skipped = [], []
    for p in sorted((session_dir / "cells").glob("*.json")):
        text = p.read_text()
        cur = json.loads(text)
        cell = cur.get("cell")
        hist = history(p)
        fix: dict = {}
        src_commit = None
        n_skipped = len(skipped)
        for k in KEYS:
            if cur.get(k):
                continue
            good = [(c, v) for c, v in hist if v.get(k)]
            if not good:
                continue  # never set: nothing to repair
            c, v = good[-1]
            later = [vv for cc, vv in hist[[x for x, _ in hist].index(c) + 1 :]]
            if any(vv.get(k) for vv in later):
                skipped.append({"cell": cell, "why": f"{k}: set again after {c[:10]}"})
                continue
            why = consistent(session_dir, cell, k, v[k])
            if why:
                skipped.append({"cell": cell, "why": f"{k}: {why}"})
                continue
            fix[k] = v[k]
            src_commit = c if src_commit in (None, c) else src_commit + "," + c
        if len(skipped) > n_skipped:
            continue  # one inconsistent key: the whole cell is left alone
        if fix:
            if json.dumps(cur, indent=2, sort_keys=False) + "\n" != text:
                skipped.append({"cell": cell, "why": "file is not in the writer's format"})
                continue
            todo.append({"path": p, "cell": cell, "fix": fix, "source_commit": src_commit})
    return todo, skipped


def apply(session_dir: Path, item: dict) -> dict:
    p: Path = item["path"]
    before = p.read_bytes()
    cur = json.loads(before)
    for k, v in item["fix"].items():
        cur[k] = v  # the key exists (empty), so its position is kept
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(cur, indent=2, sort_keys=False) + "\n")
    os.replace(tmp, p)
    after = p.read_bytes()
    line = {
        "utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cell": item["cell"],
        "file": str(p.relative_to(session_dir)),
        "keys": sorted(item["fix"]),
        "source_commit": item["source_commit"],
        "sha256_before": sha256(before),
        "sha256_after": sha256(after),
        "tool": "tools/repair_rerun_summaries.py",
    }
    with open(session_dir / "repairs.jsonl", "a") as f:
        f.write(json.dumps(line) + "\n")
    return line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sessions", nargs="+", help="session directories under data/raw/")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    rc = 0
    for s in a.sessions:
        d = Path(s)
        todo, skipped = plan(d)
        print(f"{d.name}: {len(todo)} to repair, {len(skipped)} skipped")
        for it in todo:
            print(
                f"  {it['cell']:28} {','.join(sorted(it['fix'])):20} from {it['source_commit'][:10]}"
            )
        for sk in skipped:
            print(f"  SKIPPED {sk['cell']}: {sk['why']}")
            rc = 1
        if a.apply:
            for it in todo:
                apply(d, it)
    return rc


if __name__ == "__main__":
    sys.exit(main())
