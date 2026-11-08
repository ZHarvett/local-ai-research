"""Gitignored cache of rendered prompts (``data/cache/workloads/``): the text and the token array
of each prompt. Entries are validated against the manifest hashes, so a stale or damaged entry is
never used."""

from __future__ import annotations

import array
import hashlib
import sys
from pathlib import Path

from .recipe import CACHE_DIR
from .tokens import tokens_sha256


class Cache:
    def __init__(self, root: Path):
        self.dir = root / CACHE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def put(self, pid: str, text: str, tokens: list[int]) -> None:
        a = array.array("I", tokens)
        if sys.byteorder != "little":  # pragma: no cover
            a.byteswap()
        (self.dir / f"{pid}.u32").write_bytes(a.tobytes())
        (self.dir / f"{pid}.txt").write_bytes(
            text.encode("utf-8")
        )  # exact bytes, no newline translation

    def get(self, pid: str, text_sha256: str, tokens_sha: str) -> tuple[str, list[int]] | None:
        """The cached (text, tokens), or None if missing or not matching the given hashes."""
        tp, kp = self.dir / f"{pid}.txt", self.dir / f"{pid}.u32"
        if not (tp.exists() and kp.exists()):
            return None
        a = array.array("I")
        a.frombytes(kp.read_bytes())
        if sys.byteorder != "little":  # pragma: no cover
            a.byteswap()
        tokens = a.tolist()
        text = tp.read_bytes().decode("utf-8")
        if hashlib.sha256(text.encode()).hexdigest() != text_sha256:
            return None
        if tokens_sha256(tokens) != tokens_sha:
            return None
        return text, tokens
