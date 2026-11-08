"""Build the whole workload set and its manifest from the recipe, the pinned clones and a running
llama-server (``/tokenize``, ``/apply-template``)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from ..config import load_machine, load_model, load_server, repo_root
from ..gguf_check import normalize_template
from ..render import resolve_model_path
from .builder import Builder, BuiltAppend, Pair, sha256_text
from .cache import Cache
from .manifest import Identity, Manifest, SourceRecord, TokenizeSettings
from .packing import PackingError
from .recipe import (
    RESERVE_VARIANT,
    Recipe,
    load_recipe,
    variant_for,
)
from .sources import (
    N_POOLS,
    Corpus,
    FileInfo,
    make_pools,
    parsed_special_strings,
    vocab_special_candidates,
)
from .tokens import HttpRenderer, HttpTokenizer, Renderer, Tokenizer

MIN_SOURCE_TOKENS = 300_000  # hand-written tokens required per repository
GENERATED_BY = "smallpc.workloads build (WP8)"


def read_gguf_info(path: str) -> dict:
    """Tokenizer settings and the embedded chat template of the GGUF."""
    from gguf import GGUFReader

    reader = GGUFReader(path)

    def field(key: str):
        f = reader.get_field(key)
        return None if f is None else f.contents()

    bos_id = int(field("tokenizer.ggml.bos_token_id"))
    tokens = field("tokenizer.ggml.tokens")
    template = field("tokenizer.chat_template")
    return {
        "add_bos_token": bool(field("tokenizer.ggml.add_bos_token")),
        "bos_token_id": bos_id,
        "bos_token": tokens[bos_id],
        "template_sha256": hashlib.sha256(normalize_template(str(template)).encode()).hexdigest(),
    }


def model_path(root: Path) -> str:
    machine = load_machine()
    model = load_model()
    server = load_server(repo_root() / "configs/server/workload-check-128k.toml")
    return resolve_model_path(server, machine, model)


def make_clients(base_url: str, gguf: dict):
    """HTTP tokenizer and renderer for a running llama-server."""
    import httpx

    client = httpx.Client(base_url=base_url, timeout=httpx.Timeout(1800.0))
    tok = HttpTokenizer(client, gguf["add_bos_token"], gguf["bos_token_id"], gguf["bos_token"])
    return tok, HttpRenderer(client), client


def source_state(
    recipe: Recipe, corpus: Corpus, tok: Tokenizer, specials: list[str], log: Callable[[str], None]
) -> tuple[dict[str, list[list[FileInfo]]], list[SourceRecord]]:
    """Eligible files, disjoint pools and the source records of the manifest."""
    pools: dict[str, list[list[FileInfo]]] = {}
    records = []
    half_longest = recipe.tokens(max(recipe.depths_k)) // 2
    for src in recipe.sources:
        head = corpus.head(src.name)
        if head != src.commit:
            raise RuntimeError(f"{src.name}: clone is at {head}, recipe pins {src.commit}")
        files, skipped = corpus.eligible(src.name, tok, specials)
        total = sum(f.tokens for f in files)
        log(f"{src.name}: {len(files)} eligible files, {total} tokens; excluded {skipped}")
        if total < MIN_SOURCE_TOKENS:
            raise RuntimeError(
                f"{src.name}: only {total} hand-written tokens, need {MIN_SOURCE_TOKENS}"
            )
        pools[src.name] = make_pools(files, recipe.seed, src.name)
        small = [
            i
            for i, p in enumerate(pools[src.name][: recipe.variants])
            if sum(f.tokens for f in p) < half_longest
        ]
        if small:
            raise RuntimeError(f"{src.name}: pools {small} are too small for the longest prompt")
        records.append(
            SourceRecord(
                name=src.name,
                url=src.url,
                commit=src.commit,
                spdx=src.spdx,
                license_files=corpus.license_hashes(src.name),
                eligible_files=len(files),
                eligible_tokens=total,
                excluded=skipped,
                pools=[[[f.path, f.tokens, f.sha16] for f in pool] for pool in pools[src.name]],
            )
        )
    return pools, records


def pools_from_manifest(manifest: Manifest) -> dict[str, list[list[FileInfo]]]:
    return {
        s.name: [[FileInfo(p, int(t), h) for p, t, h in pool] for pool in s.pools]
        for s in manifest.sources
    }


def identity_for(gguf: dict, generation_prompt: str, root: Path) -> Identity:
    model = load_model()
    build = json.loads((root / "data/env/build-info.json").read_text())
    return Identity(
        model_sha256=model.sha256,
        embedded_template_sha256=gguf["template_sha256"],
        llama_cpp_commit=build["commit"],
        generation_prompt=generation_prompt,
        thinking_default="on: enable_thinking is left unset, the generation prompt opens <think>",
        chat_template_source="the template embedded in the GGUF (no --chat-template-file)",
    )


def generation_prompt_of(builder: Builder) -> str:
    plain, gen = builder.skeleton.plain[2], builder.skeleton.gen[2]
    if not gen.startswith(plain):
        raise ValueError("the generation prompt is not an extension of the plain rendering")
    return gen[len(plain) :]


def build_all(
    root: Path | None = None,
    base_url: str | None = None,
    log: Callable[[str], None] = print,
    tok: Tokenizer | None = None,
    renderer: Renderer | None = None,
    gguf: dict | None = None,
    recipe: Recipe | None = None,
    special_candidates: list[str] | None = None,
) -> Manifest:
    """Build every prompt, pair and append; write the manifest and the cache."""
    root = root or repo_root()
    recipe = recipe or load_recipe(root / "configs/workloads/recipe.toml")
    gguf = gguf or read_gguf_info(model_path(root))
    if tok is None or renderer is None:
        tok, renderer, _ = make_clients(base_url, gguf)
    corpus = Corpus(recipe, root)
    candidates = (
        vocab_special_candidates(model_path(root))
        if special_candidates is None
        else special_candidates
    )
    specials = parsed_special_strings(candidates, tok)
    log(
        f"special tokens: {len(candidates)} control/user-defined candidates, {len(specials)} parsed"
    )
    pools, source_records = source_state(recipe, corpus, tok, specials, log)
    builder = Builder(recipe, corpus, tok, renderer, pools, specials)
    cache = Cache(root)

    prompts, appends = [], []
    built_appends: dict[int, BuiltAppend] = {}

    def keep(built) -> None:
        cache.put(built.record.id, built.text, built.tokens)

    for v in range(recipe.variants):
        ap = builder.build_append(v)
        built_appends[v] = ap
        appends.append(ap.record)
        keep(ap)
        log(f"append v{v}: {ap.record.token_count} tokens, {ap.record.dropped_lines} lines dropped")

    short_len = recipe.tokens(recipe.short_k)
    for r in range(recipe.variants):
        built, _ = builder.build_prompt("short", variant_for(r, recipe.variants), short_len, r)
        prompts.append(built.record)
        keep(built)
    log(f"short points: {recipe.variants} x {short_len}")

    pairs: list[Pair] = []
    for d in recipe.depths:
        for v in range(recipe.variants):
            a, _ = builder.build_prompt("A", v, d, v)
            pair = builder.make_pair(a, built_appends[v])
            pairs.append(pair)
            prompts.extend([pair.a.record, pair.b_record])
            keep(pair.a)
        log(f"depth {d}: {recipe.variants} pairs built")

    # reserve prompts: warm-up (two requests, two nonces), sanity, equivalence
    cursor: dict[str, int] = {n: 0 for n in builder.names}
    warm_len = recipe.tokens(recipe.warmup_k)
    nxt = cursor
    for r in range(2):
        built, nxt = builder.build_prompt(
            "warmup", RESERVE_VARIANT, warm_len, r, starts=dict(cursor)
        )
        prompts.append(built.record)
        keep(built)
    cursor = nxt
    for i in range(3):
        built, cursor = builder.build_prompt(
            "sanity",
            RESERVE_VARIANT,
            recipe.tokens(recipe.sanity_k),
            i,
            reserve_index=i,
            starts=dict(cursor),
        )
        prompts.append(built.record)
        keep(built)
    for k in recipe.equiv_k:
        built, cursor = builder.build_prompt(
            "equiv", RESERVE_VARIANT, recipe.tokens(k), 0, starts=dict(cursor)
        )
        prompts.append(built.record)
        keep(built)
    log("reserve prompts built")

    summary = {
        "A": sum(p.kind == "A" for p in prompts),
        "B": sum(p.kind == "B" for p in prompts),
        "short": sum(p.kind == "short" for p in prompts),
        "warmup": sum(p.kind == "warmup" for p in prompts),
        "sanity": sum(p.kind == "sanity" for p in prompts),
        "equiv": sum(p.kind == "equiv" for p in prompts),
        "appends": len(appends),
        "prompts_total": len(prompts),
    }
    manifest = Manifest(
        schema=recipe.schema_version,
        generated_by=GENERATED_BY,
        seed=recipe.seed,
        K=recipe.K,
        append_tokens=recipe.append_tokens,
        n_predict_b=recipe.n_predict_b,
        tokenize=TokenizeSettings(
            add_special=gguf["add_bos_token"],
            parse_special=recipe.tokenize["parse_special"],
            add_bos_token=gguf["add_bos_token"],
            bos_token_id=gguf["bos_token_id"],
            bos_token=gguf["bos_token"],
        ),
        identity=identity_for(gguf, generation_prompt_of(builder), root),
        special_token_strings={
            "count": len(specials),
            "sha256": sha256_text("\n".join(specials)),
            "strings": specials,
        },
        sources=source_records,
        prompts=prompts,
        appends=appends,
        summary=summary,
    )
    return manifest


__all__ = ["N_POOLS", "PackingError", "build_all", "pools_from_manifest", "read_gguf_info"]
