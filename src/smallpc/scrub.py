"""Replace the account name, hostname and home paths in text and JSON before publication.

The username and hostname are read at run time (``getpass``, ``socket``) and never stored in the
repository. Home paths become ``~``; the username becomes ``<user>`` and the hostname ``<host>``.
Both plain and JSON-escaped spellings are handled (``\\/`` slashes, escaped characters).

    python -m smallpc.scrub --check PATH...     exit 1 and list file:line:kind on any finding
    python -m smallpc.scrub FILE                print the scrubbed file on stdout

``--check`` prints only the position and the kind of a finding, never the matched text.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import socket
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MIN_LEN = 2  # shorter names would match inside ordinary words
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}


@dataclass(frozen=True)
class Identity:
    username: str
    hostname: str
    home: str

    @classmethod
    def current(cls) -> Identity:
        host = socket.gethostname()
        try:
            user = getpass.getuser()
        except Exception:
            user = ""
        return cls(user, host, os.path.expanduser("~"))


def _spellings(s: str) -> list[str]:
    """Plain, JSON-escaped, and slash-escaped (``\\/``) spellings of ``s``, longest first."""
    plain = s
    escaped = json.dumps(s, ensure_ascii=False)[1:-1]
    out = {plain, escaped, plain.replace("/", "\\/"), escaped.replace("/", "\\/")}
    return sorted(out, key=len, reverse=True)


def _word(name: str) -> re.Pattern[str]:
    alts = "|".join(re.escape(s) for s in _spellings(name))
    return re.compile(r"(?<![A-Za-z0-9])(?:" + alts + r")(?![A-Za-z0-9])")


def _home_patterns(ident: Identity) -> list[re.Pattern[str]]:
    homes = set()
    if ident.home and ident.home.rstrip("/") not in ("", "/"):
        homes.add(ident.home.rstrip("/"))
    if len(ident.username) >= MIN_LEN:
        homes.add("/home/" + ident.username)
    pats = []
    for h in sorted(homes, key=len, reverse=True):
        alts = "|".join(re.escape(s) for s in _spellings(h))
        pats.append(re.compile(r"(?:" + alts + r")(?![A-Za-z0-9_-])"))
    return pats


def _patterns(ident: Identity) -> list[tuple[str, re.Pattern[str], str]]:
    """(kind, pattern, replacement) in the order they are applied: home paths first."""
    pats = [("home-path", p, "~") for p in _home_patterns(ident)]
    if len(ident.username) >= MIN_LEN:
        pats.append(("username", _word(ident.username), "<user>"))
    names = {ident.hostname, ident.hostname.split(".")[0]}
    for h in sorted((h for h in names if len(h) >= MIN_LEN), key=len, reverse=True):
        pats.append(("hostname", _word(h), "<host>"))
    return pats


def scrub_text(text: str, ident: Identity | None = None) -> str:
    for _kind, pat, repl in _patterns(ident or Identity.current()):
        text = pat.sub(repl, text)
    return text


def scrub_json(obj, ident: Identity | None = None):
    """Scrub every string (keys and values) in a JSON-compatible structure."""
    ident = ident or Identity.current()
    if isinstance(obj, str):
        return scrub_text(obj, ident)
    if isinstance(obj, list):
        return [scrub_json(v, ident) for v in obj]
    if isinstance(obj, dict):
        return {
            scrub_json(k, ident) if isinstance(k, str) else k: scrub_json(v, ident)
            for k, v in obj.items()
        }
    return obj


def find_in_text(text: str, ident: Identity | None = None) -> list[tuple[int, str]]:
    """(1-based line, kind) of every finding. Never returns the matched text."""
    pats = _patterns(ident or Identity.current())
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for kind, pat, _ in pats:
            if pat.search(line):
                found.append((lineno, kind))
    return found


def iter_files(paths: Iterable[str | Path]) -> Iterable[Path]:
    for p in map(Path, paths):
        if p.is_dir():
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for f in sorted(files):
                    yield Path(root) / f
        elif p.exists():
            yield p


def check_paths(paths: Iterable[str | Path], ident: Identity | None = None) -> list[tuple]:
    """(file, line, kind) for every finding; binary files are skipped."""
    ident = ident or Identity.current()
    out = []
    for f in iter_files(paths):
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        for lineno, kind in find_in_text(data.decode("utf-8", errors="replace"), ident):
            out.append((str(f), lineno, kind))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.scrub", description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="report findings instead of scrubbing")
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)
    if a.check:
        findings = check_paths(a.paths)
        for f, line, kind in findings:
            print(f"{f}:{line}: {kind}")
        n_files = sum(1 for _ in iter_files(a.paths))
        print(f"scrub --check: {len(findings)} finding(s) in {n_files} file(s)", file=sys.stderr)
        return 1 if findings else 0
    for p in a.paths:
        sys.stdout.write(scrub_text(Path(p).read_text(encoding="utf-8", errors="replace")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
