"""The interface WP9's sweep runner calls.

    from smallpc.workloads import get_workload, variant_for, depths_for_context, fits

    w = get_workload("pair", 32768, repetition=r)      # variant = r % 5
    w.a_tokens      # Request A: exactly 32,768 tokens, send with n_predict 0
    w.b_tokens      # Request B: a_tokens + exactly 3,000 appended tokens, n_predict 400
    w.nonce, w.seed # nonce already inside a_tokens; seed for sampling (B uses w.seed)
    w.expected      # token accounting the runner asserts, see below

Kinds: ``pair`` (A and B), ``short`` (2K, with generation prompt), ``warmup`` (8K; repetition 0
and 1 are the two discarded warm-up requests), ``sanity`` (variant 5, repetition 0..2) and
``equiv`` (2K, 8K, 32K). Token arrays are sent to ``/completion`` as ``prompt``; the server adds no
BOS to an array (``add_bos_token`` is false for this model; if it were true the BOS is already the
first token of the array).

``expected`` (all from the server's ``timings``): ``prompt_n`` counts tokens processed and
``cache_n`` tokens reused, so ``processed_plus_cached`` is ``{"A": d, "B": d + 3000}`` for a pair
and ``{"request": d}`` otherwise; a fresh request must show ``cache_n <= max_cache_n_fresh`` (32);
Request B ``cache_n >= min_cache_n_B`` (0.95 d) and ``predicted_n == n_predict_b`` (400).

Arrays come from the gitignored cache (validated against the manifest hashes). A missing entry is
rebuilt from the manifest when ``base_url`` of any running llama-server of this model is given (the
tokenizer and template do not depend on the server configuration); without it ``CacheMiss`` is
raised. Repetitions >= 5 are not in the manifest: they are built on demand with their own nonce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ..config import repo_root
from .build import make_clients, pools_from_manifest, read_gguf_info
from .builder import Builder, BuiltAppend, BuiltPrompt, sha256_text
from .cache import Cache
from .manifest import Manifest, PromptRecord, append_id, load_manifest, manifest_path, prompt_id
from .recipe import Recipe, load_recipe, variant_for
from .sources import Corpus
from .tokens import tokens_sha256

KINDS = ("pair", "short", "warmup", "sanity", "equiv")
MAX_CACHE_N_FRESH = 32
MIN_CACHE_FRACTION_B = 0.95


class CacheMiss(RuntimeError):
    """The prompt is not cached and no ``base_url`` was given to rebuild it."""


@dataclass(frozen=True)
class Workload:
    id: str
    kind: str
    length: int  # d: tokens of a_tokens
    variant: int
    repetition: int
    nonce: str
    seed: int
    a_tokens: list[int]
    b_tokens: list[int] | None
    expected: dict
    text_sha256: str
    tokens_sha256: str


_CACHED: dict[str, tuple[Recipe, Manifest]] = {}


def _load(root: Path) -> tuple[Recipe, Manifest]:
    key = str(root)
    if key not in _CACHED:
        _CACHED[key] = (
            load_recipe(root / "configs/workloads/recipe.toml"),
            load_manifest(manifest_path(root)),
        )
    return _CACHED[key]


def _expected(recipe: Recipe, d: int, pair: bool) -> dict:
    exp: dict = {
        "d": d,
        "append_n": recipe.append_tokens if pair else None,
        "max_cache_n_fresh": MAX_CACHE_N_FRESH,
        "processed_plus_cached": {"A": d, "B": d + recipe.append_tokens}
        if pair
        else {"request": d},
    }
    if pair:
        exp["min_cache_n_B"] = math.ceil(MIN_CACHE_FRACTION_B * d)
        exp["predicted_n_B"] = recipe.n_predict_b
    return exp


def get_workload(
    kind: str,
    length: int,
    variant: int | None = None,
    repetition: int = 0,
    *,
    base_url: str | None = None,
    root: Path | None = None,
) -> Workload:
    """Token arrays, nonce, seed and expected counts for one request (or A/B pair). See the
    module docstring."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, not {kind!r}")
    root = root or repo_root()
    recipe, manifest = _load(root)
    if variant is None:
        variant = (
            5 if kind in ("warmup", "sanity", "equiv") else variant_for(repetition, recipe.variants)
        )
    a_kind = "A" if kind == "pair" else kind
    pid = prompt_id(a_kind, variant, length, repetition)
    rec = next((p for p in manifest.prompts if p.id == pid), None)
    pair = kind == "pair"
    cache = Cache(root)

    a = _cached(cache, rec)
    app = None
    if pair:
        app_rec = manifest.append(append_id(variant))
        app = cache.get(app_rec.id, app_rec.text_sha256, app_rec.tokens_sha256)
    if a is None or (pair and app is None):
        if base_url is None:
            raise CacheMiss(
                f"{pid} is not cached; run `python -m smallpc.workloads run build` or pass base_url"
            )
        a_built, app_built = _rebuild(
            root, recipe, manifest, base_url, kind, variant, length, repetition, rec, cache
        )
        a = (a_built.text, a_built.tokens)
        app = (app_built.text, app_built.tokens) if app_built else None
        rec = a_built.record
    _, a_tokens = a
    b_tokens = a_tokens + app[1] if pair and app else None
    return Workload(
        id=rec.id,
        kind=kind,
        length=length,
        variant=variant,
        repetition=repetition,
        nonce=rec.nonce or "",
        seed=rec.seed if not pair else _b_seed(recipe, variant, length, repetition),
        a_tokens=a_tokens,
        b_tokens=b_tokens,
        expected=_expected(recipe, length, pair),
        text_sha256=rec.text_sha256,
        tokens_sha256=rec.tokens_sha256,
    )


def _b_seed(recipe: Recipe, variant: int, length: int, repetition: int) -> int:
    from .recipe import sampling_seed

    return sampling_seed(recipe.seed, "B", variant, length, repetition)


def _cached(cache: Cache, rec: PromptRecord | None):
    return None if rec is None else cache.get(rec.id, rec.text_sha256, rec.tokens_sha256)


def _rebuild(root, recipe, manifest, base_url, kind, variant, length, repetition, rec, cache):
    """Rebuild a missing entry from the manifest (or, for repetitions outside it, from the
    recipe) using a running server for ``/tokenize`` and ``/apply-template``."""
    gguf = read_gguf_info(_model_path(root))
    tok, renderer, client = make_clients(base_url, gguf)
    try:
        builder = Builder(
            recipe,
            Corpus(recipe, root),
            tok,
            renderer,
            pools_from_manifest(manifest),
            manifest.special_token_strings["strings"],
        )
        a_kind = "A" if kind == "pair" else kind
        if rec is not None:
            text, system, user = builder.regenerate_prompt(rec)
            built = BuiltPrompt(rec, text, tok.tokenize(text), system, user)
            if (sha256_text(text), tokens_sha256(built.tokens)) != (
                rec.text_sha256,
                rec.tokens_sha256,
            ):
                raise ValueError(f"{rec.id}: regenerated prompt does not match the manifest")
        else:
            if length not in {recipe.tokens(k) for k in recipe.lengths_k}:
                raise ValueError(f"unsupported length {length}")
            built, _ = builder.build_prompt(a_kind, variant, length, repetition)
        cache.put(built.record.id, built.text, built.tokens)
        app_built = None
        if kind == "pair":
            ar = manifest.append(append_id(variant))
            at, tool = builder.regenerate_append(ar)
            app_built = BuiltAppend(ar, at, tok.tokenize(at, bos=False), tool)
            if (sha256_text(at), tokens_sha256(app_built.tokens)) != (
                ar.text_sha256,
                ar.tokens_sha256,
            ):
                raise ValueError(f"{ar.id}: regenerated append does not match the manifest")
            cache.put(ar.id, at, app_built.tokens)
            builder.make_pair(built, app_built)  # prefix property on the real renderer
        return built, app_built
    finally:
        client.close()


def _model_path(root: Path) -> str:
    from .build import model_path

    return model_path(root)
