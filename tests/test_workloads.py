"""WP8 workloads: CI-safe tests with a fake tokenizer, a fake renderer and fake repositories."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from conftest import REPO
from smallpc.workloads import api, build
from smallpc.workloads import manifest as mf
from smallpc.workloads.builder import Builder
from smallpc.workloads.cache import Cache
from smallpc.workloads.check import run_checks
from smallpc.workloads.packing import PackingError, Unit, pack_exact
from smallpc.workloads.recipe import (
    fits,
    load_recipe,
    nonce,
    plan_sweep,
    sampling_seed,
    variant_for,
)
from smallpc.workloads.sources import Corpus, parsed_special_strings, split_lines
from smallpc.workloads.verify import verify_all
from workload_fakes import FakeLlama, FakeRenderer, FakeTokenizer, make_recipe

REAL_RECIPE = REPO / "configs/workloads/recipe.toml"
GGUF = {
    "add_bos_token": False,
    "bos_token_id": 1,
    "bos_token": "<|endoftext|>",
    "template_sha256": "0" * 64,
}
CANDIDATES = [
    "<|im_start|>",
    "<|im_end|>",
    "<|endoftext|>",
    "<think>",
    "</think>",
    "<tool_response>",
    "</tool_response>",
    "plain",
]  # "plain" is not a control token


@pytest.fixture(scope="module")
def env(tmp_path_factory, monkeypatch_module):
    root = tmp_path_factory.mktemp("wl")
    (root / "data/env").mkdir(parents=True)
    (root / "data/env/build-info.json").write_text(json.dumps({"commit": "c" * 40}))
    recipe = make_recipe(root, REAL_RECIPE)
    tok, renderer = FakeTokenizer(), FakeRenderer()
    monkeypatch_module.setattr(build, "MIN_SOURCE_TOKENS", 1000)
    manifest = build.build_all(
        root,
        tok=tok,
        renderer=renderer,
        gguf=GGUF,
        recipe=recipe,
        log=lambda m: None,
        special_candidates=CANDIDATES,
    )
    return SimpleNamespace(root=root, recipe=recipe, tok=tok, renderer=renderer, manifest=manifest)


@pytest.fixture(scope="module")
def monkeypatch_module():
    with pytest.MonkeyPatch.context() as mp:
        yield mp


def builder_of(env, tok=None, renderer=None) -> Builder:
    tok = tok or env.tok
    corpus = Corpus(env.recipe, env.root)
    specials = parsed_special_strings(CANDIDATES, tok)
    return Builder(
        env.recipe,
        corpus,
        tok,
        renderer or env.renderer,
        build.pools_from_manifest(env.manifest),
        specials,
    )


# ------------------------------------------------------------------ policies on the real recipe


def test_variant_policy_r_mod_5():
    assert [variant_for(r) for r in range(12)] == [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1]
    assert {variant_for(r) for r in range(2)} == {0, 1}  # 2-repetition screening
    assert {variant_for(r) for r in range(5)} == {0, 1, 2, 3, 4}


def test_k_is_1024_and_lengths():
    r = load_recipe(REAL_RECIPE)
    assert r.K == 1024
    assert r.tokens(96) == 98_304
    assert [r.tokens(k) for k in r.lengths_k] == [
        2048,
        8192,
        16384,
        24576,
        32768,
        49152,
        65536,
        98304,
    ]
    assert r.append_tokens == 3000 and r.n_predict_b == 400


def test_context_fit_table():
    r = load_recipe(REAL_RECIPE)
    for c, depths in (
        (32768, [8192, 16384, 24576]),
        (65536, [16384, 32768, 49152]),
        (131072, [32768, 65536, 98304]),
    ):
        assert r.depths_for_context(c) == depths
        assert all(fits(d, c) for d in depths)
    assert fits(24576, 32768) and not fits(32768, 32768) and not fits(49152, 32768)
    assert 98304 + 3000 + 400 == 101_704 <= 131072


def test_nonce_deterministic_and_unique_over_a_full_sweep():
    r = load_recipe(REAL_RECIPE)
    keys = plan_sweep(r, 5)
    assert {k[0] for k in keys} == {"short", "A", "warmup"}
    n1 = [nonce(r.seed, *k) for k in keys]
    n2 = [nonce(r.seed, *k) for k in keys]
    assert n1 == n2  # regeneration reproduces it
    assert len(set(n1)) == len(n1) == len(set(keys))
    # kind, variant, length and repetition each matter
    base = ("A", 0, 8192, 0)
    assert (
        len(
            {
                nonce(r.seed, *base),
                nonce(r.seed, "short", 0, 8192, 0),
                nonce(r.seed, "A", 1, 8192, 0),
                nonce(r.seed, "A", 0, 16384, 0),
                nonce(r.seed, "A", 0, 8192, 1),
            }
        )
        == 5
    )
    assert nonce("other seed", *base) != nonce(r.seed, *base)
    # even 20 repetitions stay unique
    assert len({nonce(r.seed, *k) for k in plan_sweep(r, 20)}) == len(plan_sweep(r, 20))
    assert sampling_seed(r.seed, *base) == sampling_seed(r.seed, *base)


# --------------------------------------------------------------------------------- packing


def test_split_lines_keeps_text_exact():
    text = "a\nb\x0cc\n\nlast"
    assert "".join(split_lines(text)) == text


@pytest.mark.parametrize("target", [40, 41, 77, 100, 233])
def test_pack_exact_awkward_boundaries(target):
    tok = FakeTokenizer()
    units = [
        Unit(body=f"line {i} value {i * 37}\n\n" if i % 3 == 0 else f"x{i} = {i}\n")
        for i in range(80)
    ]

    def render(tail):
        return "<|im_start|>system\n[nonce 9a8b7c6d]\n<|im_end|>\n" + tail + "\nTask.\n"

    n, k = pack_exact(units, render, tok.count, target)
    from smallpc.workloads.packing import tail_text

    assert tok.count(render(tail_text(units, n, k))) == target


def test_pack_exact_unreachable_raises():
    units = [Unit(body="abcdefgh\n") for _ in range(10)]
    with pytest.raises(PackingError):
        pack_exact(units, lambda t: t, lambda s: 2 * len(s), 33)  # only even counts exist


def test_every_prompt_has_exact_length_and_nonce_changes_token_cost(env):
    by_len = {}
    for p in env.manifest.prompts:
        if p.kind == "B":
            continue
        assert p.token_count == p.length
        assert (
            len(env.tok.tokenize(Cache(env.root).get(p.id, p.text_sha256, p.tokens_sha256)[0]))
            == p.length
        )
        by_len.setdefault(p.length, []).append(p)
    # the nonce costs a varying number of tokens, yet every prompt is exact
    costs = {env.tok.count(p.nonce) for p in env.manifest.prompts if p.nonce}
    assert len(costs) > 1


def test_determinism_same_recipe_same_hash(env, tmp_path):
    b = builder_of(env)
    first, _ = b.build_prompt("A", 2, env.recipe.tokens(8), 2)
    second, _ = b.build_prompt("A", 2, env.recipe.tokens(8), 2)
    assert (
        first.record.text_sha256
        == second.record.text_sha256
        == env.manifest.prompt(first.record.id).text_sha256
    )
    assert first.tokens == second.tokens
    third, _ = b.build_prompt("A", 2, env.recipe.tokens(8), 7)  # other repetition: other nonce
    assert third.record.text_sha256 != first.record.text_sha256


def test_both_repositories_at_every_length_and_variants_use_disjoint_files(env):
    used: dict[int, set[str]] = {}
    for p in env.manifest.prompts:
        if p.kind in ("A", "short"):
            assert all(p.files[name] for name in ("poetry", "axum")), p.id
            used.setdefault(p.variant, set()).update(
                f"{n}:{u.path}" for n, us in p.files.items() for u in us
            )
    sets = [used[v] for v in range(5)]
    for i in range(5):
        for j in range(i + 1, 5):
            assert not sets[i] & sets[j]


# ---------------------------------------------------------------------------- pairs, prefix


def test_prefix_property_and_append_size(env):
    pairs = [p for p in env.manifest.prompts if p.kind == "B"]
    assert len(pairs) == 35
    cache = Cache(env.root)
    for b in pairs:
        a_rec, ap_rec = env.manifest.prompt(b.a_id), env.manifest.append(b.append_id)
        a_text, a_toks = cache.get(a_rec.id, a_rec.text_sha256, a_rec.tokens_sha256)
        ap_text, ap_toks = cache.get(ap_rec.id, ap_rec.text_sha256, ap_rec.tokens_sha256)
        assert len(a_toks) == a_rec.length and len(ap_toks) == env.recipe.append_tokens
        assert env.tok.tokenize(a_text + ap_text) == a_toks + ap_toks
        assert b.token_count == a_rec.length + env.recipe.append_tokens
        assert b.nonce == a_rec.nonce  # B has no nonce of its own


def test_broken_renderer_is_caught(env):
    b = builder_of(env, renderer=FakeRenderer())
    a, _ = b.build_prompt("A", 0, env.recipe.tokens(8), 0)
    bad = Builder(
        env.recipe, b.corpus, env.tok, FakeRenderer(break_prefix=True), b.pools, b.specials
    )
    with pytest.raises(ValueError, match="not a prefix"):
        bad.skeleton.append_text(0, "x")
    # and building a whole pair with it fails the same way
    with pytest.raises(ValueError, match="not a prefix"):
        bad.make_pair(a, bad.build_append(0))


def test_bos_handling(env):
    bos_tok = FakeTokenizer(add_bos_token=True, bos_id=1)
    plain = FakeTokenizer(add_bos_token=False)
    text = "<|im_start|>system\nhi<|im_end|>\n"
    assert (
        bos_tok.tokenize(text)[0] == 1
        and len(bos_tok.tokenize(text)) == len(plain.tokenize(text)) + 1
    )
    assert bos_tok.tokenize(text, bos=False) == plain.tokenize(text)  # an append never gets a BOS
    b = builder_of(env, tok=bos_tok)
    a, _ = b.build_prompt("A", 1, env.recipe.tokens(8), 1)
    assert a.tokens[0] == 1 and len(a.tokens) == env.recipe.tokens(8)  # the BOS is counted
    ap = b.build_append(1)
    assert ap.tokens[0] != 1 and len(ap.tokens) == env.recipe.append_tokens
    b.make_pair(a, ap)


def test_http_tokenizer_bos_and_special_parsing():
    import httpx

    from smallpc.workloads.tokens import HttpTokenizer

    ft = FakeTokenizer()
    srv = FakeLlama(ft, FakeRenderer())
    for add_bos in (False, True):
        tok = HttpTokenizer(
            srv.client(), add_bos_token=add_bos, bos_token_id=7, bos_token="<|endoftext|>"
        )
        toks = tok.tokenize("<|im_start|>user\nx<|im_end|>\n")
        assert (toks[0] == 7) is add_bos
        assert len(toks) == len(ft.tokenize("<|im_start|>user\nx<|im_end|>\n")) + int(add_bos)
        assert tok.tokenize("a", bos=False) == ft.tokenize("a")
        assert tok.count("a b") == tok.count("a b")  # memoised, stable
    with pytest.raises(ValueError):
        HttpTokenizer(srv.client(), add_bos_token=True).tokenize("x")
    assert isinstance(httpx.Client, type)


# ------------------------------------------------------------------ special-token exclusion


def test_special_token_strings_are_excluded_from_files_and_command_output(env):
    corpus = Corpus(env.recipe, env.root)
    specials = parsed_special_strings(CANDIDATES, env.tok)
    assert "plain" not in specials and "<think>" in specials  # only parsed control tokens
    for name in ("poetry", "axum"):
        files, skipped = corpus.eligible(name, env.tok, specials)
        paths = {f.path for f in files}
        assert not any(p.startswith("special") for p in paths)  # the fake file with a literal
        assert skipped["contains a special-token string"] == 1
        assert not any(
            p.startswith("vendor/") or p.startswith("tiny") or p.startswith("crlf") for p in paths
        )
    from smallpc.workloads.sources import command_lines

    (env.root / "clones/poetry/note.py").write_text("x = 1  # <think> hidden\n" * 20)
    import subprocess

    subprocess.run(["git", "-C", str(env.root / "clones/poetry"), "add", "-A"], check=True)
    lines, dropped = command_lines(
        corpus,
        corpus.sources["poetry"],
        [["git", "grep", "-n", "-I", "-E", "x = 1", "--", "{glob}"]],
        specials,
        1000,
    )
    subprocess.run(
        ["git", "-C", str(env.root / "clones/poetry"), "rm", "-q", "-f", "--cached", "note.py"],
        check=True,
    )
    (env.root / "clones/poetry/note.py").unlink()
    assert dropped >= 20 and not any("<think>" in ln for ln in lines)
    assert env.manifest.special_token_strings["count"] == len(specials)


# ------------------------------------------------------------------------------ manifest


def test_manifest_schema_and_no_repository_text(env, tmp_path):
    path = tmp_path / "manifest.json"
    mf.save_manifest(env.manifest, path)
    again = mf.load_manifest(path)
    assert again.summary == env.manifest.summary
    assert env.manifest.summary == {
        "A": 35,
        "B": 35,
        "short": 5,
        "warmup": 2,
        "sanity": 3,
        "equiv": 3,
        "appends": 5,
        "prompts_total": 83,
    }
    mf.assert_text_free(path, mf.MAX_MANIFEST_BYTES)
    raw = path.read_text()
    corpus = Corpus(env.recipe, env.root)
    sample = []
    for name in ("poetry", "axum"):
        for rel in (
            "pkg0/mod1" + (".py" if name == "poetry" else ".rs"),
            "pkg3/mod33" + (".py" if name == "poetry" else ".rs"),
        ):
            sample += [ln.strip() for ln in corpus.lines(name, rel) if len(ln.strip()) >= 20]
    assert len(sample) > 20 and not [ln for ln in sample if ln in raw]
    # the schema rejects unknown fields and a manifest with a long string is rejected
    data = json.loads(raw)
    data["prompts"][0]["unexpected"] = 1
    with pytest.raises(Exception, match="unexpected|Extra"):
        mf.Manifest.model_validate(data)
    long = tmp_path / "long.json"
    long.write_text(json.dumps({"x": "y" * 201}))
    with pytest.raises(ValueError, match="over 200"):
        mf.assert_text_free(long)
    long.write_text(json.dumps({"x": ["a", {"k": "y" * 200}]}))
    mf.assert_text_free(long)  # exactly 200 is allowed


def test_committed_manifest_and_live_check_hold_no_text():
    path = REPO / "configs/workloads/manifest.json"
    if path.exists():
        mf.assert_text_free(path, mf.MAX_MANIFEST_BYTES)
        mf.load_manifest(path)
    out = REPO / "data/workloads"
    # the environment snapshot is machine notes, not workload data: only live-check and verify files
    for f in [*out.glob("live-check-*.json"), *out.glob("verify-*.json")] if out.exists() else []:
        mf.assert_text_free(f)


def test_verify_reproduces_everything_with_fakes(env):
    rep = verify_all(
        env.root,
        env.tok,
        env.renderer,
        log=lambda m: None,
        manifest=env.manifest,
        recipe=env.recipe,
        gguf=GGUF,
        special_candidates=CANDIDATES,
    )
    failed = [c for c in rep.checks if c["status"] != "PASS"]
    # the committed-manifest size/text check reads the repo path, everything else must pass
    assert [c["name"] for c in failed] <= ["manifest holds no long strings"], failed


def test_verify_detects_a_changed_source_file(env):
    clone = env.root / "clones/poetry"
    target = clone / "pkg0/mod0.py"
    original = target.read_text()
    try:
        target.write_text(original.replace("func_0_1", "func_changed"))
        rep = verify_all(
            env.root,
            env.tok,
            env.renderer,
            log=lambda m: None,
            manifest=env.manifest,
            recipe=env.recipe,
            gguf=GGUF,
            special_candidates=CANDIDATES,
        )
        assert any(c["status"] == "FAIL" for c in rep.checks)
    finally:
        target.write_text(original)


# ----------------------------------------------------------------------------- cache + API


def test_get_workload_from_cache_and_stale_entries(env, monkeypatch):
    monkeypatch.setitem(api._CACHED, str(env.root), (env.recipe, env.manifest))
    d = env.recipe.tokens(16)
    w = api.get_workload("pair", d, repetition=3, root=env.root)
    assert (
        w.variant == 3 and len(w.a_tokens) == d and len(w.b_tokens) == d + env.recipe.append_tokens
    )
    assert w.b_tokens[:d] == w.a_tokens
    assert w.expected["processed_plus_cached"] == {"A": d, "B": d + env.recipe.append_tokens}
    assert w.expected["max_cache_n_fresh"] == 32 and w.expected["min_cache_n_B"] == -(
        -95 * d // 100
    )
    s = api.get_workload("short", env.recipe.tokens(2), repetition=1, root=env.root)
    assert s.b_tokens is None and s.expected["processed_plus_cached"] == {"request": s.length}
    w2 = api.get_workload("warmup", env.recipe.tokens(8), repetition=1, root=env.root)
    assert (
        w2.variant == 5
        and w2.nonce
        != api.get_workload("warmup", env.recipe.tokens(8), repetition=0, root=env.root).nonce
    )
    # stale entry (hash mismatch) is not used; without a server it is a CacheMiss
    rec = env.manifest.prompt(w.id)
    path = Cache(env.root).dir / f"{rec.id}.txt"
    good = path.read_bytes()
    path.write_text("tampered")
    try:
        with pytest.raises(api.CacheMiss):
            api.get_workload("pair", d, repetition=3, root=env.root)
    finally:
        path.write_bytes(good)
    with pytest.raises(ValueError):
        api.get_workload("nope", d, root=env.root)


def test_get_workload_rebuilds_a_missing_entry(env, monkeypatch):
    monkeypatch.setitem(api._CACHED, str(env.root), (env.recipe, env.manifest))
    d = env.recipe.tokens(16)
    monkeypatch.setattr(api, "read_gguf_info", lambda p: GGUF)
    monkeypatch.setattr(api, "_model_path", lambda root: "unused")
    srv = FakeLlama(env.tok, env.renderer)
    from smallpc.workloads import tokens as tk

    def fake_clients(base_url, gguf):
        c = srv.client()
        return tk.HttpTokenizer(c, False, 1, "<|endoftext|>"), tk.HttpRenderer(c), c

    monkeypatch.setattr(api, "make_clients", fake_clients)
    for f in Cache(env.root).dir.glob(f"A-v3-{d}-r3.*"):
        f.unlink()
    w = api.get_workload("pair", d, repetition=3, base_url="http://fake", root=env.root)
    assert w.text_sha256 == env.manifest.prompt(w.id).text_sha256 and len(w.b_tokens) == d + 300
    # a repetition beyond the manifest is built on demand with its own nonce
    w7 = api.get_workload("pair", d, repetition=7, base_url="http://fake", root=env.root)
    assert (
        w7.variant == 2
        and w7.nonce != api.get_workload("pair", d, repetition=2, root=env.root).nonce
    )
    assert len(w7.a_tokens) == d


# --------------------------------------------------------------------- live-check logic


def run_fake_checks(env, monkeypatch, **kw):
    monkeypatch.setitem(api._CACHED, str(env.root), (env.recipe, env.manifest))
    srv = FakeLlama(env.tok, env.renderer, **kw)
    out = run_checks(
        "http://fake",
        env.recipe,
        env.manifest,
        log=lambda m: None,
        root=env.root,
        client=srv.client(),
    )
    return srv, out


def test_live_check_passes_on_a_well_behaved_server(env, monkeypatch):
    srv, out = run_fake_checks(env, monkeypatch)
    assert out["summary"]["findings"] == 0, out["findings"][:3]
    assert out["summary"]["pairs_ok"] == out["summary"]["pairs_total"] == 35
    assert all(e["ok"] for e in out["equivalence"]) and all(s["ok"] for s in out["short_points"])
    depths = [p["depth"] for p in out["pairs"]]
    assert depths == sorted(depths) and [p["variant"] for p in out["pairs"][:5]] == [0, 1, 2, 3, 4]
    row = out["pairs"][0]
    d = row["depth"]
    assert row["A"]["prompt_n"] + row["A"]["cache_n"] == d and row["A"]["cache_n"] <= 32
    assert row["B"]["prompt_n"] + row["B"]["cache_n"] == d + 300 and row["B"]["cache_n"] >= 0.95 * d
    assert row["B"]["predicted_n"] == 400 and row["B"]["stop_type"] == "limit"
    # no text of any kind in the result
    assert "SHOULD NEVER BE STORED" not in json.dumps(out)
    assert not mf.long_strings(out)


def test_live_check_reports_findings_without_adjusting_thresholds(env, monkeypatch):
    _, out = run_fake_checks(env, monkeypatch, cache_bug=True)
    assert out["summary"]["pairs_ok"] == 0 and out["summary"]["findings"] > 0
    assert any("warm_prefill" in f for f in out["findings"])
    _, out = run_fake_checks(env, monkeypatch, stop_early=50)
    assert any("predicted_n = 50" in f for f in out["findings"])
    assert any("stop_type = 'eos'" in f for f in out["findings"])
