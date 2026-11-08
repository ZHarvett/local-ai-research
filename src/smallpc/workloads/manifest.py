"""The committed manifest (``configs/workloads/manifest.json``): recipes only, never source text.

Every string in it is short (paths, hashes, ids); ``assert_text_free`` enforces a length cap on the
manifest and on any other committed data file. Source text lives only in the gitignored clones and
cache."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..config import repo_root
from .recipe import MANIFEST_PATH

MAX_STRING_CHARS = 200  # no string value in committed workload data may be longer
MAX_MANIFEST_BYTES = 600_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TokenizeSettings(_Strict):
    add_special: bool  # = add_bos_token of the GGUF
    parse_special: bool
    add_bos_token: bool
    bos_token_id: int
    bos_token: str


class Identity(_Strict):
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    embedded_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    llama_cpp_commit: str
    generation_prompt: str
    thinking_default: str
    chat_template_source: str


class SourceRecord(_Strict):
    name: str
    url: str
    commit: str
    spdx: str
    license_files: dict[str, str]  # path -> SHA-256 of the file's bytes
    eligible_files: int
    eligible_tokens: int
    excluded: dict[str, int]
    # six disjoint pools (variants 0-4, reserve): [path, tokens, sha16] in pool order
    pools: list[list[list[Any]]]


class FileUse(_Strict):
    path: str
    lines: int
    partial_chars: int = 0


class PromptRecord(_Strict):
    id: str
    kind: str  # A, B, short, warmup, sanity, equiv
    variant: int
    length: int  # tokens of the whole array (B: A's length + the append)
    repetition: int
    nonce: str | None = None
    seed: int
    wording: str | None = None  # instruction wording id (text in recipe.toml)
    instruction_sha256: str | None = None
    generation_prompt: bool | None = None
    files: dict[str, list[FileUse]] | None = None  # repository -> files used, in order
    pool: int | None = None
    start_file: dict[str, int] | None = None  # reserve prompts: first pool file per repository
    a_id: str | None = None  # B only
    append_id: str | None = None  # B only
    token_count: int
    text_sha256: str
    tokens_sha256: str


class AppendRecord(_Strict):
    id: str
    variant: int
    commands: list[list[str]]
    files: dict[str, list[FileUse]]  # repository -> output blocks (path = command header index)
    wording: str
    instruction_sha256: str
    dropped_lines: int
    token_count: int
    text_sha256: str
    tokens_sha256: str


class Manifest(_Strict):
    schema_version: int = Field(alias="schema")
    generated_by: str
    seed: str
    K: int
    append_tokens: int
    n_predict_b: int
    tokenize: TokenizeSettings
    identity: Identity
    special_token_strings: dict[str, Any]  # count and SHA-256 of the sorted list
    sources: list[SourceRecord]
    prompts: list[PromptRecord]
    appends: list[AppendRecord]
    summary: dict[str, int]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def prompt(self, pid: str) -> PromptRecord:
        for p in self.prompts:
            if p.id == pid:
                return p
        raise KeyError(pid)

    def append(self, aid: str) -> AppendRecord:
        for a in self.appends:
            if a.id == aid:
                return a
        raise KeyError(aid)


def prompt_id(kind: str, variant: int, length: int, repetition: int) -> str:
    return f"{kind}-v{variant}-{length}-r{repetition}"


def append_id(variant: int) -> str:
    return f"append-v{variant}"


def dump(manifest: Manifest) -> str:
    data = manifest.model_dump(by_alias=True, exclude_none=True)
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


def manifest_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / MANIFEST_PATH


def load_manifest(path: Path | None = None) -> Manifest:
    return Manifest.model_validate(json.loads((path or manifest_path()).read_text()))


def save_manifest(manifest: Manifest, path: Path | None = None) -> str:
    text = dump(manifest)
    (path or manifest_path()).write_text(text)
    return hashlib.sha256(text.encode()).hexdigest()


def long_strings(obj: Any, limit: int = MAX_STRING_CHARS, path: str = "$") -> list[str]:
    """JSON paths of string values (and keys) longer than ``limit`` characters."""
    out: list[str] = []
    if isinstance(obj, str):
        if len(obj) > limit:
            out.append(f"{path} ({len(obj)} chars)")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if len(str(k)) > limit:
                out.append(f"{path}.<key> ({len(str(k))} chars)")
            out.extend(long_strings(v, limit, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(long_strings(v, limit, f"{path}[{i}]"))
    return out


def assert_text_free(path: Path, max_bytes: int | None = None) -> None:
    """Raise if a committed JSON data file has a string longer than 200 characters (a sign that
    prompt or generated text got in) or exceeds the size cap."""
    raw = path.read_text()
    if max_bytes is not None and len(raw.encode()) > max_bytes:
        raise ValueError(f"{path} is {len(raw.encode())} bytes, over the {max_bytes} cap")
    bad = long_strings(json.loads(raw))
    if bad:
        raise ValueError(f"{path}: strings over {MAX_STRING_CHARS} characters: {bad[:5]}")
