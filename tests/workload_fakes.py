"""Fakes for the workload tests: a tokenizer whose counts are NOT additive across joins, a ChatML
renderer, an HTTP fake of llama-server, and small git repositories of synthetic code."""

from __future__ import annotations

import re
import subprocess
import tomllib
import zlib
from pathlib import Path

import httpx

SPECIALS = [
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    "<think>",
    "</think>",
    "<tool_response>",
    "</tool_response>",
]
GEN_PROMPT = "<|im_start|>assistant\n<think>\n"


class FakeTokenizer:
    """Words, single digits (so a hex nonce costs a varying number of tokens), blank lines
    merged into one token (so joins are not additive), special strings as single tokens."""

    def __init__(
        self, add_bos_token: bool = False, bos_id: int = 1, bos_token: str = "<|endoftext|>"
    ):
        self.add_bos_token = add_bos_token
        self.bos_id, self.bos_token = bos_id, bos_token
        alt = "|".join(re.escape(s) for s in sorted(SPECIALS, key=len, reverse=True))
        self._re = re.compile(rf"(?P<sp>{alt})|\n\n|\n|[A-Za-z_]+|\d|[ \t]+|[^\sA-Za-z_\d]")
        self.calls = 0

    def _ids(self, text: str, parse_special: bool) -> list[int]:
        self.calls += 1
        out = []
        for m in self._re.finditer(text):
            piece = m.group(0)
            if m.group("sp") and not parse_special:
                out.extend(zlib.crc32(c.encode()) + 10 for c in piece)  # split into characters
            else:
                out.append(zlib.crc32(piece.encode()) + 10)
        return out

    def tokenize(self, text: str, *, parse_special: bool = True, bos: bool = True) -> list[int]:
        ids = self._ids(text, parse_special)
        if self.add_bos_token and bos and not text.startswith(self.bos_token):
            ids = [self.bos_id, *ids]
        return ids

    def count(self, text: str, *, parse_special: bool = True, bos: bool = True) -> int:
        return len(self.tokenize(text, parse_special=parse_special, bos=bos))


class FakeRenderer:
    """ChatML like the embedded template. ``break_prefix`` makes the user turn render
    differently once more messages follow it (A is then not a prefix of B)."""

    def __init__(self, break_prefix: bool = False):
        self.break_prefix = break_prefix

    def render(self, messages: list[dict], add_generation_prompt: bool) -> str:
        out = ""
        for i, m in enumerate(messages):
            role, content = m["role"], m["content"]
            if role == "tool":
                out += f"<|im_start|>user\n<tool_response>\n{content}\n</tool_response><|im_end|>\n"
            else:
                if self.break_prefix and role == "user" and i == 1 and len(messages) > 2:
                    content += " (continued)"
                out += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        return out + (GEN_PROMPT if add_generation_prompt else "")


# ------------------------------------------------------------------------------------ repos

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(path: Path, *args: str) -> str:
    import os

    p = subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    return p.stdout.strip()


def code_file(ext: str, i: int, n_lines: int = 40) -> str:
    if ext == ".py":
        head = ["import os\n", "from typing import Any\n", "import sys\n", "\n"]
        body = [f"def func_{i}_{j}(x): return x + {j * i + 7}\n" for j in range(n_lines)]
    else:
        head = ["use std::fmt;\n", "use std::io;\n", "pub use crate::x;\n", "\n"]
        body = [f"fn func_{i}_{j}(x: i32) -> i32 {{ x + {j * i + 7} }}\n" for j in range(n_lines)]
    return "".join(head + body)


def make_repo(path: Path, ext: str, n_files: int = 160) -> str:
    """A git repository of synthetic code, plus files that must be excluded. Returns HEAD."""
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    for i in range(n_files):
        f = path / f"pkg{i // 10}" / f"mod{i}{ext}"
        f.parent.mkdir(exist_ok=True)
        f.write_text(code_file(ext, i))
    (path / "vendor").mkdir()
    (path / "vendor" / f"skip{ext}").write_text(code_file(ext, 999))
    (path / f"tiny{ext}").write_text("x\n")
    (path / f"special{ext}").write_text(code_file(ext, 998) + "// literal <|im_start|> in source\n")
    (path / f"crlf{ext}").write_bytes(code_file(ext, 997).replace("\n", "\r\n").encode())
    (path / "LICENSE").write_text("MIT License\n\nPermission is hereby granted.\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "initial import")
    for c in range(3):
        for i in range(8):
            f = path / f"pkg{i // 10}" / f"mod{i}{ext}"
            f.write_text(f.read_text() + f"// change {c} {i}\n" * 4)
        _git(path, "commit", "-q", "-am", f"change {c}")
    return _git(path, "rev-parse", "HEAD")


def make_recipe(tmp_path: Path, repo_recipe: Path):
    """The real recipe with small K, a small append, and the two fake repositories."""
    from smallpc.workloads.recipe import Recipe

    data = tomllib.loads(repo_recipe.read_text())
    data["K"] = 256
    data["append_tokens"] = 300
    heads = {}
    for src, ext in zip(data["sources"], (".py", ".rs"), strict=True):
        clone = tmp_path / "clones" / src["name"]
        heads[src["name"]] = make_repo(clone, ext)
        src["commit"] = heads[src["name"]]
        src["clone_dir"] = f"clones/{src['name']}"
        src["license_files"] = ["LICENSE"]
    for a in data["appends"]:
        a["commands"] = [
            [x.replace("HEAD~60", "HEAD~1").replace("HEAD~12", "HEAD~1") for x in c]
            for c in a["commands"]
        ]
    return Recipe.model_validate(data)


# ------------------------------------------------------------------------------- HTTP fake


class FakeLlama:
    """llama-server's /tokenize, /apply-template and /completion over httpx.MockTransport, with a
    single-slot prefix cache so ``cache_n`` / ``prompt_n`` behave like the real server.

    ``cache_bug`` forces a wrong accounting (A reports a warm cache); ``stop_early`` stops
    generation before ``n_predict``."""

    def __init__(
        self,
        tok: FakeTokenizer,
        renderer: FakeRenderer,
        *,
        cache_bug: bool = False,
        stop_early: int | None = None,
    ):
        self.tok, self.renderer = tok, renderer
        self.cache_bug, self.stop_early = cache_bug, stop_early
        self.cache: list[int] = []
        self.requests: list[dict] = []

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle), base_url="http://fake")

    def handle(self, req: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(req.content) if req.content else {}
        if req.url.path == "/tokenize":
            ids = self.tok._ids(body["content"], body.get("parse_special", True))
            return httpx.Response(200, json={"tokens": ids})
        if req.url.path == "/apply-template":
            text = self.renderer.render(body["messages"], body.get("add_generation_prompt", True))
            return httpx.Response(200, json={"prompt": text})
        if req.url.path == "/completion":
            return self.completion(body)
        return httpx.Response(404)

    def completion(self, body: dict) -> httpx.Response:
        p = body["prompt"]
        tokens = p if isinstance(p, list) else self.tok.tokenize(p, parse_special=True)
        if isinstance(p, str) and self.tok.add_bos_token:
            pass  # tokenize() already prepended the BOS, like the server does for strings
        common = 0
        if body.get("cache_prompt", True):
            for a, b in zip(self.cache, tokens, strict=False):
                if a != b:
                    break
                common += 1
        common = min(common, len(tokens) - 1) if tokens else 0
        n_predict = body["n_predict"]
        n_gen = n_predict if self.stop_early is None else min(n_predict, self.stop_early)
        stop = (
            "limit"
            if n_gen == n_predict and n_predict > 0
            else ("eos" if n_predict > 0 else "limit")
        )
        self.cache = list(tokens) if body.get("cache_prompt", True) else []
        cache_n = common + (40 if self.cache_bug and n_predict == 0 else 0)
        self.requests.append({"n_prompt": len(tokens), "n_predict": n_predict, "cache_n": cache_n})
        gen_tokens = [101 + i for i in range(min(n_gen, 16))]
        return httpx.Response(
            200,
            json={
                "timings": {
                    "cache_n": cache_n,
                    "prompt_n": len(tokens) - common,
                    "predicted_n": n_gen,
                    "prompt_ms": 1.0,
                    "predicted_ms": 1.0,
                },
                "stop_type": stop,
                "tokens_evaluated": len(tokens),
                "tokens_cached": common,
                "tokens": gen_tokens,
                "content": "SHOULD NEVER BE STORED",
            },
        )
