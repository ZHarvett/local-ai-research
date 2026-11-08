"""``verify``: regenerate every prompt and append from the committed manifest (ignoring the cache),
check token counts against ``/tokenize`` and reproduce every hash; check the prefix property, the
context-fit table, nonce uniqueness and that the manifest holds no repository text."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from ..config import load_model, repo_root
from .build import model_path, pools_from_manifest, read_gguf_info
from .builder import Builder, sha256_text
from .manifest import (
    MAX_MANIFEST_BYTES,
    MAX_STRING_CHARS,
    Manifest,
    dump,
    load_manifest,
    long_strings,
    manifest_path,
)
from .packing import PackingError
from .recipe import Recipe, fits, load_recipe, nonce, plan_sweep, sampling_seed
from .sources import Corpus, make_pools, parsed_special_strings, vocab_special_candidates
from .tokens import Renderer, Tokenizer, tokens_sha256


class Report:
    def __init__(self, log: Callable[[str], None]):
        self.log = log
        self.checks: list[dict] = []

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        self.log(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
        return ok

    @property
    def ok(self) -> bool:
        return all(c["status"] == "PASS" for c in self.checks)


def verify_all(
    root: Path | None,
    tok: Tokenizer,
    renderer: Renderer,
    log: Callable[[str], None] = print,
    manifest: Manifest | None = None,
    recipe: Recipe | None = None,
    gguf: dict | None = None,
    special_candidates: list[str] | None = None,
) -> Report:
    root = root or repo_root()
    rep = Report(log)
    recipe = recipe or load_recipe(root / "configs/workloads/recipe.toml")
    manifest = manifest or load_manifest(manifest_path(root))
    gguf = gguf or read_gguf_info(model_path(root))

    # -- identity and settings
    raw = dump(manifest)
    long = long_strings(json.loads(raw))
    size = len(raw.encode())
    rep.add(
        "manifest holds no long strings",
        not long and size <= MAX_MANIFEST_BYTES,
        f"{size} bytes, strings <= {MAX_STRING_CHARS} chars" if not long else str(long[:3]),
    )
    model = load_model()
    t = manifest.tokenize
    rep.add(
        "tokenize settings match the GGUF",
        (t.add_bos_token, t.bos_token_id, t.bos_token, t.add_special, t.parse_special)
        == (
            gguf["add_bos_token"],
            gguf["bos_token_id"],
            gguf["bos_token"],
            gguf["add_bos_token"],
            True,
        ),
        f"add_bos_token={t.add_bos_token} bos={t.bos_token_id} parse_special={t.parse_special}",
    )
    rep.add(
        "model and template identity",
        manifest.identity.model_sha256 == model.sha256
        and manifest.identity.embedded_template_sha256 == gguf["template_sha256"],
        f"model {manifest.identity.model_sha256[:12]}, template {gguf['template_sha256'][:12]}",
    )
    rep.add(
        "recipe and manifest agree",
        (manifest.seed, manifest.K, manifest.append_tokens)
        == (recipe.seed, recipe.K, recipe.append_tokens)
        and [(s.name, s.url, s.commit, s.spdx) for s in manifest.sources]
        == [(s.name, s.url, s.commit, s.spdx) for s in recipe.sources],
        f"seed {recipe.seed}, K {recipe.K}, append {recipe.append_tokens}",
    )

    # -- special-token strings and sources
    candidates = (
        vocab_special_candidates(model_path(root))
        if special_candidates is None
        else special_candidates
    )
    specials = parsed_special_strings(candidates, tok)
    rep.add(
        "special-token strings from the vocabulary",
        specials == manifest.special_token_strings["strings"]
        and sha256_text("\n".join(specials)) == manifest.special_token_strings["sha256"],
        f"{len(candidates)} candidates, {len(specials)} parsed as control tokens",
    )
    corpus = Corpus(recipe, root)
    for src in manifest.sources:
        head = corpus.head(src.name)
        lic = corpus.license_hashes(src.name)
        rep.add(
            f"{src.name}: pinned commit and license files",
            head == src.commit and lic == src.license_files,
            f"{head[:12]}, {len(lic)} license file(s) {src.spdx}",
        )
        files, skipped = corpus.eligible(src.name, tok, specials)
        pools = make_pools(files, recipe.seed, src.name)
        got = [[[f.path, f.tokens, f.sha16] for f in p] for p in pools]
        rep.add(
            f"{src.name}: eligible files and pools reproduced",
            got == src.pools and skipped == src.excluded,
            f"{len(files)} files, {sum(f.tokens for f in files)} tokens, 6 pools",
        )

    # -- prompts, appends, pairs
    builder = Builder(recipe, corpus, tok, renderer, pools_from_manifest(manifest), specials)
    n_text = n_tokens = 0
    bad: list[str] = []
    for rec in (p for p in manifest.prompts if p.kind != "B"):
        text, system, user = builder.regenerate_prompt(rec)
        tokens = tok.tokenize(text)
        if rec.nonce != nonce(recipe.seed, rec.kind, rec.variant, rec.length, rec.repetition):
            bad.append(f"{rec.id}: nonce")
        if rec.seed != sampling_seed(
            recipe.seed, rec.kind, rec.variant, rec.length, rec.repetition
        ):
            bad.append(f"{rec.id}: seed")
        if sha256_text(text) != rec.text_sha256:
            bad.append(f"{rec.id}: text hash")
        if len(tokens) != rec.token_count or len(tokens) != rec.length:
            bad.append(f"{rec.id}: tokens {len(tokens)} vs {rec.token_count}/{rec.length}")
        if tokens_sha256(tokens) != rec.tokens_sha256:
            bad.append(f"{rec.id}: token hash")
        real = renderer.render(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            bool(rec.generation_prompt),
        )
        if real != text:
            bad.append(f"{rec.id}: differs from the real chat template")
        n_text += 1
        n_tokens += len(tokens)
    rep.add(
        "prompt texts, token counts and hashes reproduced",
        not bad,
        f"{n_text} prompts, {n_tokens} tokens counted with /tokenize"
        + (f"; {bad[:4]}" if bad else ""),
    )

    bad = []
    for ap in manifest.appends:
        text, _ = builder.regenerate_append(ap)
        tokens = tok.tokenize(text, bos=False)
        if sha256_text(text) != ap.text_sha256 or tokens_sha256(tokens) != ap.tokens_sha256:
            bad.append(f"{ap.id}: hash")
        if len(tokens) != ap.token_count or len(tokens) != recipe.append_tokens:
            bad.append(f"{ap.id}: tokens {len(tokens)}")
    rep.add(
        "append chunks reproduced",
        not bad,
        f"{len(manifest.appends)} chunks of exactly {recipe.append_tokens} tokens"
        + (f"; {bad}" if bad else ""),
    )

    bad = []
    n_pairs = 0
    for b in (p for p in manifest.prompts if p.kind == "B"):
        a_rec, ap_rec = manifest.prompt(b.a_id), manifest.append(b.append_id)
        try:
            a_text, system, user = builder.regenerate_prompt(a_rec)
            ap_text, tool = builder.regenerate_append(ap_rec)
            from .builder import BuiltAppend, BuiltPrompt

            a = BuiltPrompt(a_rec, a_text, tok.tokenize(a_text), system, user)
            ap = BuiltAppend(ap_rec, ap_text, tok.tokenize(ap_text, bos=False), tool)
            pair = builder.make_pair(a, ap)
            if (
                pair.b_record.text_sha256 != b.text_sha256
                or pair.b_record.tokens_sha256 != b.tokens_sha256
                or len(pair.b_tokens) != a_rec.length + recipe.append_tokens
                or pair.b_record.nonce != a_rec.nonce
            ):
                bad.append(f"{b.id}: hashes or length")
        except (PackingError, ValueError) as e:
            bad.append(f"{b.id}: {e}")
        n_pairs += 1
    rep.add(
        "prefix property: A is a prefix of B, B adds exactly 3000 tokens",
        not bad,
        f"{n_pairs} pairs checked with /apply-template and whole-text /tokenize"
        + (f"; {bad[:3]}" if bad else ""),
    )

    # -- policies
    table = {c: [d for d in recipe.depths_for_context(int(c))] for c in recipe.contexts}
    unfit = [(c, d) for c, ds in table.items() for d in ds if not fits(d, int(c))]
    rep.add(
        "context-fit table",
        not unfit,
        "d + 3000 + 400 <= C for "
        + ", ".join(f"C={c}: {max(ds) + 3400}" for c, ds in table.items()),
    )
    keys = plan_sweep(recipe, 5)
    nonces = [nonce(recipe.seed, *k) for k in keys]
    rep.add(
        "nonces unique over the planned 5-repetition sweep",
        len(set(nonces)) == len(nonces),
        f"{len(nonces)} fresh requests, {len(set(nonces))} distinct",
    )
    manifest_nonces = [p.nonce for p in manifest.prompts if p.kind != "B"]
    rep.add(
        "nonces unique in the manifest",
        len(set(manifest_nonces)) == len(manifest_nonces),
        f"{len(manifest_nonces)} prompts",
    )
    counts = {
        k: sum(p.kind == k for p in manifest.prompts)
        for k in ("A", "B", "short", "warmup", "sanity", "equiv")
    }
    rep.add("summary counts", counts == {k: manifest.summary[k] for k in counts}, str(counts))
    return rep


def write_report(rep: Report, root: Path) -> Path:
    out = root / "data/workloads"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"verify-{time.strftime('%Y-%m-%d', time.gmtime())}.json"
    path.write_text(json.dumps({"ok": rep.ok, "checks": rep.checks}, indent=1) + "\n")
    return path
