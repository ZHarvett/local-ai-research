"""Tokenizer and renderer interfaces, and the HTTP implementations that talk to llama-server."""

from __future__ import annotations

import array
import hashlib
import sys
from typing import Protocol

import httpx

SENT_SYS = "@@SENT_SYSTEM@@"
SENT_USER = "@@SENT_USER@@"
SENT_TOOL = "@@SENT_TOOL@@"


class Tokenizer(Protocol):
    """Token counting and tokenizing exactly as the requests will be sent (special tokens parsed,
    BOS handled per ``add_bos_token``)."""

    add_bos_token: bool

    def tokenize(self, text: str, *, parse_special: bool = True, bos: bool = True) -> list[int]: ...

    def count(self, text: str, *, parse_special: bool = True, bos: bool = True) -> int: ...


class Renderer(Protocol):
    """Renders chat messages with the model's chat template."""

    def render(self, messages: list[dict], add_generation_prompt: bool) -> str: ...


def tokens_sha256(tokens: list[int]) -> str:
    """SHA-256 of the token array as little-endian uint32."""
    a = array.array("I", tokens)
    if a.itemsize != 4:  # pragma: no cover - platform guard
        raise RuntimeError("unexpected array('I') item size")

    if sys.byteorder != "little":  # pragma: no cover
        a.byteswap()
    return hashlib.sha256(a.tobytes()).hexdigest()


class HttpTokenizer:
    """``/tokenize`` of a running llama-server.

    The array sent to ``/completion`` is never given a BOS by the server, so when the GGUF says
    ``add_bos_token`` the BOS id is prepended here (unless the text already starts with the BOS
    string); the equivalent string request gets its BOS from the server.
    """

    def __init__(
        self,
        client: httpx.Client,
        add_bos_token: bool = False,
        bos_token_id: int | None = None,
        bos_token: str | None = None,
    ):
        self.client = client
        self.add_bos_token = add_bos_token
        self.bos_token_id = bos_token_id
        self.bos_token = bos_token
        self.calls = 0
        self._memo: dict[tuple[str, bool, bool], int] = {}

    def _raw(self, text: str, parse_special: bool) -> list[int]:
        self.calls += 1
        r = self.client.post(
            "/tokenize",
            json={"content": text, "add_special": False, "parse_special": parse_special},
        )
        r.raise_for_status()
        return r.json()["tokens"]

    def tokenize(self, text: str, *, parse_special: bool = True, bos: bool = True) -> list[int]:
        """Tokens of ``text``. ``bos=False`` for a text that is appended to an earlier prefix."""
        toks = self._raw(text, parse_special)
        if self.add_bos_token and bos:
            if self.bos_token_id is None:
                raise ValueError("add_bos_token is set but the BOS id is unknown")
            if not (self.bos_token and text.startswith(self.bos_token)):
                toks = [self.bos_token_id, *toks]
        return toks

    def count(self, text: str, *, parse_special: bool = True, bos: bool = True) -> int:
        key = (hashlib.sha256(text.encode()).hexdigest(), parse_special, bos)
        if key not in self._memo:
            self._memo[key] = len(self.tokenize(text, parse_special=parse_special, bos=bos))
        return self._memo[key]


class HttpRenderer:
    """``/apply-template`` of a running llama-server (the embedded template)."""

    def __init__(self, client: httpx.Client):
        self.client = client

    def render(self, messages: list[dict], add_generation_prompt: bool) -> str:
        r = self.client.post(
            "/apply-template",
            json={"messages": messages, "add_generation_prompt": add_generation_prompt},
        )
        r.raise_for_status()
        return r.json()["prompt"]
