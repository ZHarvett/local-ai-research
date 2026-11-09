"""What a session is made of: hashes of the spec, manifest and sampling settings, the code commit
and whether the code is dirty, the config hash, and the model's SHA-256."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

DIRTY_DIRS = ("src", "configs", "scripts")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def sampling_sha256(model_toml: Path) -> str:
    """Hash of the ``[sampling]`` section of configs/model.toml (canonical JSON)."""
    with open(model_toml, "rb") as f:
        sampling = tomllib.load(f).get("sampling", {})
    return hashlib.sha256(json.dumps(sampling, sort_keys=True).encode()).hexdigest()


def _git(root: Path, *args: str) -> str:
    """stdout of a git command with trailing newlines removed (leading spaces are significant in
    ``status --porcelain``)."""
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return p.stdout.rstrip("\n") if p.returncode == 0 else ""


def git_state(root: Path) -> dict:
    commit = _git(root, "rev-parse", "HEAD").strip()
    dirty = [
        line[3:] for line in _git(root, "status", "--porcelain", "--", *DIRTY_DIRS).splitlines()
    ]
    return {"commit": commit or "unknown", "short": (commit or "unknown")[:10],
            "dirty": bool(dirty), "dirty_paths": dirty}  # fmt: skip


def model_sha256(model_file: Path, declared: str | None, cache_file: Path) -> dict:
    """SHA-256 of the model file, cached by (path, size, mtime). If the file is missing (CI with
    the mock server) the declared value from configs/model.toml is used and marked unverified."""
    if not model_file.exists():
        return {"sha256": declared or "unknown", "verified": False, "note": "model file missing"}
    st = model_file.stat()
    key = f"{model_file}|{st.st_size}|{st.st_mtime_ns}"
    cache: dict = {}
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text())
        except ValueError:
            cache = {}
    sha = cache.get(key)
    if sha is None:
        sha = sha256_file(model_file)
        cache = {key: sha}
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache) + "\n")
    return {"sha256": sha, "verified": declared is None or sha == declared,
            "declared": declared, "size_bytes": st.st_size}  # fmt: skip


def config_hash(argv: list[str], model_sha: str, llama_commit: str) -> str:
    """Hash of the rendered argv, the model SHA-256 and the llama.cpp commit (16 hex digits)."""
    blob = json.dumps({"argv": argv, "model_sha256": model_sha, "llama_cpp_commit": llama_commit},
                      sort_keys=True, separators=(",", ":"))  # fmt: skip
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def resume_check(stored: dict, current: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings) when resuming. The spec, manifest and sampling hashes (and the filter)
    must match; a different code commit only warns."""
    errors = []
    for key in ("spec_sha256", "manifest_sha256", "sampling_sha256"):
        if stored.get(key) != current.get(key):
            errors.append(
                f"{key} differs from the session's ({stored.get(key)} != {current.get(key)})"
            )
    if (stored.get("filters") or {}) != (current.get("filters") or {}):
        errors.append(
            f"--only filter differs: session {stored.get('filters')} vs {current.get('filters')}"
        )
    for key in ("model_sha256", "llama_cpp_commit"):
        if stored.get(key) != current.get(key):
            errors.append(f"{key} differs from the session's")
    warnings = []
    if stored.get("git", {}).get("commit") != current.get("git", {}).get("commit"):
        warnings.append(
            f"code commit changed: session {stored.get('git', {}).get('short')} -> "
            f"{current.get('git', {}).get('short')}; new records carry the new commit"
        )
    return errors, warnings
