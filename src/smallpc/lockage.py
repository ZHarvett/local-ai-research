"""Age check of an npm lockfile against the registry's publish times (WP7 pinning rule).

    python -m smallpc.lockage LOCKFILE --before TIMESTAMP [--out FILE]

Reads every package of ``package-lock.json`` (lockfile version 2/3), looks up its publish time in
the registry packument (metadata only, no tarball, no credentials) and lists the packages published
*after* ``--before``: those are less than 7 days old at install time and need an ``overrides``
entry.
Exit code 1 if any are found, 2 if a version could not be looked up.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

REGISTRY = "https://registry.npmjs.org"


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def lock_packages(lock: dict) -> list[tuple[str, str]]:
    """Unique (name, version) pairs of every installed package, in sorted order."""
    out = set()
    for path, meta in lock.get("packages", {}).items():
        if not path or meta.get("link") or "version" not in meta:
            continue
        name = meta.get("name") or path.rsplit("node_modules/", 1)[-1]
        out.add((name, meta["version"]))
    return sorted(out)


def fetch_time_map(name: str, client: httpx.Client) -> dict[str, str]:
    url = f"{REGISTRY}/{urllib.parse.quote(name, safe='@')}"
    r = client.get(url, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json().get("time", {})


def check(
    packages: list[tuple[str, str]],
    cutoff: datetime,
    get_times: Callable[[str], dict[str, str]],
    workers: int = 8,
) -> dict:
    names = sorted({n for n, _ in packages})
    with ThreadPoolExecutor(workers) as pool:
        maps = dict(zip(names, pool.map(get_times, names), strict=True))
    rows, too_new, missing = [], [], []
    for name, version in packages:
        ts = maps[name].get(version)
        if ts is None:
            missing.append(f"{name}@{version}")
            continue
        rows.append({"name": name, "version": version, "published": ts})
        if parse_ts(ts) > cutoff:
            too_new.append({"name": name, "version": version, "published": ts})
    return {
        "cutoff_utc": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "packages_checked": len(rows),
        "too_new": too_new,
        "missing_publish_time": missing,
        "packages": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.lockage")
    ap.add_argument("lockfile")
    ap.add_argument("--before", required=True, help="UTC timestamp; newer packages are listed")
    ap.add_argument("--out", help="write the full result as JSON")
    a = ap.parse_args(argv)
    lock = json.loads(Path(a.lockfile).read_text())
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        res = check(lock_packages(lock), parse_ts(a.before), lambda n: fetch_time_map(n, client))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"checked {res['packages_checked']} packages against cutoff {res['cutoff_utc']}")
    for p in res["too_new"]:
        print(f"TOO NEW  {p['name']}@{p['version']}  published {p['published']}")
    for m in res["missing_publish_time"]:
        print(f"NO TIME  {m}", file=sys.stderr)
    if res["missing_publish_time"]:
        return 2
    return 1 if res["too_new"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
