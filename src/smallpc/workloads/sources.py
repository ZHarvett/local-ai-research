"""Source repositories: eligible hand-written files, special-token exclusion, disjoint pools, and
the deterministic git command outputs used as tool-output-like text.

Nothing here writes repository text anywhere; callers keep it in memory (or in the gitignored
cache)."""

from __future__ import annotations

import hashlib
import os
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .packing import Unit
from .recipe import Exclusions, Recipe, Source
from .tokens import Tokenizer

N_POOLS = 6  # variants 0-4 and the reserve pool


def split_lines(text: str) -> list[str]:
    """Lines with their newline kept; split on "\\n" only (str.splitlines also splits on form
    feeds and Unicode separators, which would change the text)."""
    parts = text.split("\n")
    lines = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FileInfo:
    path: str
    tokens: int
    sha16: str  # first 16 hex of the SHA-256 of the file bytes (integrity of the clone)


# ----------------------------------------------------------------------- special-token strings


def vocab_special_candidates(gguf_path: str) -> list[str]:
    """Control and user-defined token strings of the model vocabulary (GGUF ``token_type`` 3 and
    4), read from the GGUF metadata, not from a hard-coded list."""
    from gguf import GGUFReader

    reader = GGUFReader(gguf_path)
    toks = reader.get_field("tokenizer.ggml.tokens")
    types = reader.get_field("tokenizer.ggml.token_type")
    if toks is None or types is None:
        raise RuntimeError("GGUF has no tokenizer.ggml.tokens / token_type")
    strings = toks.contents()
    kinds = types.contents()
    return [s for s, t in zip(strings, kinds, strict=True) if int(t) in (3, 4) and s]


def parsed_special_strings(candidates: list[str], tok: Tokenizer) -> list[str]:
    """The candidates that would really turn into control tokens: they tokenize to exactly one
    token with special parsing and to something else without it. Sorted, so the list (and its
    hash) is stable."""
    out = []
    for s in candidates:
        if tok.count(s, parse_special=True) == 1 and tok.count(s, parse_special=False) != 1:
            out.append(s)
    return sorted(set(out))


def has_special(text: str, specials: list[str]) -> bool:
    return any(s in text for s in specials)


# ------------------------------------------------------------------------------ file selection


def git(clone: Path, *args: str) -> str:
    """Run git offline and deterministically (no user or system config, UTC, no pager)."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": "/nonexistent",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_PAGER": "cat",
        "TZ": "UTC",
        "LC_ALL": "C",
    }
    p = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(clone), *args],
        capture_output=True,
        env=env,
        check=True,
    )
    return p.stdout.decode("utf-8", errors="replace")


def rejects(path: str, data: bytes, ex: Exclusions) -> str | None:
    """Reason a file is not hand-written source worth packing, or None if it is eligible by its
    path and bytes (the special-token and tokenizer checks come later)."""
    parts = path.split("/")
    if any(p in ex.dir_names for p in parts[:-1]):
        return "excluded directory"
    name = parts[-1]
    if any(s in name for s in ex.name_substrings):
        return "excluded name"
    if not (ex.min_file_bytes <= len(data) <= ex.max_file_bytes):
        return "size"
    if b"\x00" in data or b"\r" in data:
        return "binary or CRLF"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "not UTF-8"
    head = text[:1024]
    if any(m in head for m in ex.generated_markers):
        return "generated"
    if max((len(line) for line in text.split("\n")), default=0) > ex.max_line_chars:
        return "long lines (minified or data)"
    return None


class Corpus:
    """File access for one workload build: eligibility, text and lines, with in-memory caching."""

    def __init__(self, recipe: Recipe, root: Path):
        self.recipe = recipe
        self.root = root
        self.sources = {s.name: s for s in recipe.sources}
        self._text: dict[tuple[str, str], str] = {}

    def clone(self, name: str) -> Path:
        return self.root / self.sources[name].clone_dir

    def head(self, name: str) -> str:
        return git(self.clone(name), "rev-parse", "HEAD").strip()

    def text(self, name: str, path: str) -> str:
        key = (name, path)
        if key not in self._text:
            self._text[key] = (self.clone(name) / path).read_bytes().decode("utf-8")
        return self._text[key]

    def lines(self, name: str, path: str) -> list[str]:
        return split_lines(self.text(name, path))

    def license_hashes(self, name: str) -> dict[str, str]:
        src = self.sources[name]
        return {lf: sha256_bytes((self.clone(name) / lf).read_bytes()) for lf in src.license_files}

    def eligible(
        self, name: str, tok: Tokenizer, specials: list[str]
    ) -> tuple[list[FileInfo], dict[str, int]]:
        """Eligible hand-written files (sorted by path) and counts of what was excluded and why."""
        src: Source = self.sources[name]
        ex = self.recipe.exclusions
        listing = git(self.clone(name), "ls-files", "-z").split("\0")
        files, skipped = [], {}
        for path in sorted(p for p in listing if p.endswith(src.extension)):
            data = (self.clone(name) / path).read_bytes()
            why = rejects(path, data, ex)
            if why is None:
                text = data.decode("utf-8")
                if has_special(text, specials):
                    why = "contains a special-token string"
                else:
                    n = tok.count(text, parse_special=True)
                    if n != tok.count(text, parse_special=False):
                        why = "tokenizes differently with special tokens parsed"
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            files.append(FileInfo(path, n, sha256_bytes(data)[:16]))
        return files, skipped


def make_pools(
    files: list[FileInfo], seed: str, name: str, n_pools: int = N_POOLS
) -> list[list[FileInfo]]:
    """Disjoint pools balanced by token count (largest file first into the lightest pool), then
    each pool is put in a seeded random order. Deterministic for a fixed seed and file list."""
    pools: list[list[FileInfo]] = [[] for _ in range(n_pools)]
    load = [0] * n_pools
    for f in sorted(files, key=lambda f: (-f.tokens, f.path)):
        i = min(range(n_pools), key=lambda j: (load[j], j))
        pools[i].append(f)
        load[i] += f.tokens
    for i, pool in enumerate(pools):
        pool.sort(key=lambda f: f.path)
        random.Random(f"{seed}|{name}|pool{i}").shuffle(pool)
    return pools


# --------------------------------------------------------------------------- file block units


def file_units(path: str, lines: list[str], header: str = "") -> list[Unit]:
    """Units of one file: the first carries the repository header and the ``=== path ===`` line,
    the last a blank separator line."""
    units = []
    for i, line in enumerate(lines):
        prefix = (header if i == 0 else "") + (f"=== {path} ===\n" if i == 0 else "")
        last = i == len(lines) - 1
        body = line if line.endswith("\n") or not last else line + "\n"
        units.append(Unit(body=body, prefix=prefix, suffix="\n" if last else ""))
    return units


def repo_header(src: Source) -> str:
    return f"Repository: {src.name} ({src.spdx}) @ {src.commit[:12]}\n\n"


# ---------------------------------------------------------------------- tool-output-like text


def expand(arg: str, src: Source) -> str:
    return (
        arg.replace("{glob}", f"*{src.extension}")
        .replace("{defs}", src.defs_pattern)
        .replace("{imports}", src.imports_pattern)
    )


def command_lines(
    corpus: Corpus, src: Source, commands: list[list[str]], specials: list[str], max_line_chars: int
) -> tuple[list[str], int]:
    """Output of the git commands for one repository as lines (``$ ...`` header then output), and
    the number of lines dropped (special-token strings, overlong lines)."""
    lines, dropped = [], 0
    for cmd in commands:
        args = [expand(a, src) for a in cmd]
        lines.append(f"$ cd {src.name} && " + " ".join(args) + "\n")
        for line in split_lines(git(corpus.clone(src.name), *args[1:])):
            if (
                has_special(line, specials)
                or len(line) > max_line_chars
                or "\r" in line
                or "\x00" in line
            ):
                dropped += 1
                continue
            lines.append(line)
    return lines, dropped
