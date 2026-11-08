"""Live checks against a running llama-server (``configs/server/workload-check-128k.toml``).

1. Equivalence: for the 2K, 8K and 32K ``equiv`` prompts a token-array request and the
   equivalent string request (``cache_prompt`` false, greedy) give equal ``prompt_n`` and equal
   first 16 tokens.
2. Pairs: for every depth (ascending) and variant, Request A (``n_predict`` 0) then Request B
   (``n_predict`` 400). Invariants (server ``prompt_n`` counts processed tokens, ``cache_n``
   reused ones):
   A: ``prompt_n + cache_n == d`` and ``cache_n <= 32``;
   B: ``prompt_n + cache_n == d + 3000``, ``cache_n >= 0.95 d``, ``predicted_n == 400`` and
   ``stop_type == "limit"``.
3. Short points: each 2K prompt generates at least 100 tokens (``short_gen``).

A result that breaks an invariant is a *finding*: it is recorded as observed and no threshold is
changed. The result file holds counts, token ids, hashes, stop types and timings only: never
prompt text, generated text or log lines.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import httpx

from .. import flags
from ..config import load_model
from .api import MAX_CACHE_N_FRESH, MIN_CACHE_FRACTION_B, get_workload
from .manifest import Manifest
from .recipe import Recipe

TIMING_KEYS = (
    "cache_n",
    "prompt_n",
    "prompt_ms",
    "prompt_per_second",
    "predicted_n",
    "predicted_ms",
    "predicted_per_second",
    "draft_n",
    "draft_n_accepted",
)
EQUIV_TOKENS = 16
WARMUP_TOKENS = 128


def card_sampling(seed: int) -> dict:
    s = load_model().sampling.general
    return {"temperature": s.temperature, "top_p": s.top_p, "top_k": s.top_k, "seed": seed}


def request(client: httpx.Client, prompt, n_predict: int, **params) -> dict:
    """One non-streaming ``/completion`` request; returns numbers only (no generated text)."""
    body = {"prompt": prompt, "n_predict": n_predict, "stream": False} | params
    t0 = time.monotonic()
    r = client.post("/completion", json=body)
    r.raise_for_status()
    data = r.json()
    timings = data.get("timings") or {}
    out = {k: timings[k] for k in TIMING_KEYS if k in timings}
    out["stop_type"] = data.get("stop_type")
    out["truncated"] = data.get("truncated")
    out["tokens_evaluated"] = data.get("tokens_evaluated")
    out["tokens_cached"] = data.get("tokens_cached")
    out["wall_s"] = round(time.monotonic() - t0, 3)
    if "tokens" in data:
        out["tokens"] = data["tokens"]
    return out


def judge_a(rec: dict, d: int) -> list[str]:
    out = []
    if rec.get("prompt_n") is None or rec.get("cache_n") is None:
        return ["A: timings missing prompt_n/cache_n"]
    if rec["prompt_n"] + rec["cache_n"] != d:
        out.append(f"A: prompt_n + cache_n = {rec['prompt_n'] + rec['cache_n']}, expected {d}")
    if "warm_prefill" in flags.request_flags("A", rec):
        out.append(f"A: cache_n = {rec['cache_n']} > {MAX_CACHE_N_FRESH} (warm_prefill)")
    return out


def judge_b(rec: dict, d: int, append: int, n_predict: int) -> list[str]:
    out = []
    if rec.get("prompt_n") is None or rec.get("cache_n") is None:
        return ["B: timings missing prompt_n/cache_n"]
    if rec["prompt_n"] + rec["cache_n"] != d + append:
        out.append(
            f"B: prompt_n + cache_n = {rec['prompt_n'] + rec['cache_n']}, expected {d + append}"
        )
    if "cache_miss" in flags.request_flags("B", rec, depth=d):
        out.append(f"B: cache_n = {rec['cache_n']} < {MIN_CACHE_FRACTION_B} * {d} (cache_miss)")
    if rec.get("predicted_n") != n_predict:
        out.append(f"B: predicted_n = {rec.get('predicted_n')}, expected {n_predict}")
    if rec.get("stop_type") != "limit":
        out.append(f"B: stop_type = {rec.get('stop_type')!r}, expected 'limit'")
    return out


def run_checks(
    base_url: str,
    recipe: Recipe,
    manifest: Manifest,
    log: Callable[[str], None] = print,
    root: Path | None = None,
    variants: list[int] | None = None,
    client: httpx.Client | None = None,
) -> dict:
    client = client or httpx.Client(base_url=base_url, timeout=httpx.Timeout(1800.0))
    findings: list[str] = []
    out: dict = {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    n_b = recipe.n_predict_b
    append_n = recipe.append_tokens
    variants = list(range(recipe.variants)) if variants is None else variants

    def get(kind, length, variant=None, rep=0):
        return get_workload(kind, length, variant, rep, base_url=base_url, root=root)

    # -- 1. equivalence (greedy, no cache)
    equiv = []
    for k in recipe.equiv_k:
        w = get("equiv", recipe.tokens(k), 5, 0)
        text = _cached_text(root, w.id, manifest)
        greedy = {"temperature": 0.0, "seed": w.seed, "cache_prompt": False, "return_tokens": True}
        arr = request(client, w.a_tokens, EQUIV_TOKENS, **greedy)
        txt = request(client, text, EQUIV_TOKENS, **greedy)
        same_n = arr.get("prompt_n") == txt.get("prompt_n")
        same_tok = arr.get("tokens", [])[:EQUIV_TOKENS] == txt.get("tokens", [])[:EQUIV_TOKENS]
        row = {
            "id": w.id,
            "length": w.length,
            "prompt_n_array": arr.get("prompt_n"),
            "prompt_n_string": txt.get("prompt_n"),
            "first_tokens_array": arr.get("tokens", [])[:EQUIV_TOKENS],
            "first_tokens_string": txt.get("tokens", [])[:EQUIV_TOKENS],
            "prompt_n_equal": same_n,
            "first_16_equal": same_tok and len(arr.get("tokens", [])) >= EQUIV_TOKENS,
        }
        row["ok"] = row["prompt_n_equal"] and row["first_16_equal"]
        if not row["ok"]:
            findings.append(f"equivalence {w.id}: {row}")
        equiv.append(row)
        log(
            f"equivalence {w.length}: prompt_n {arr.get('prompt_n')} vs {txt.get('prompt_n')}, "
            f"first 16 equal {row['first_16_equal']}"
        )
    out["equivalence"] = equiv

    # -- warm-up (two requests, discarded; reported for completeness)
    out["warmup"] = []
    for r in range(2):
        w = get("warmup", recipe.tokens(recipe.warmup_k), 5, r)
        rec = request(client, w.a_tokens, WARMUP_TOKENS, **card_sampling(w.seed))
        out["warmup"].append({"id": w.id, "length": w.length, **_nums(rec)})

    # -- 3. short points
    shorts = []
    for v in variants:
        w = get("short", recipe.tokens(recipe.short_k), v, v)
        rec = request(client, w.a_tokens, n_b, **card_sampling(w.seed))
        row = {"id": w.id, "variant": v, "length": w.length, **_nums(rec)}
        row["ok"] = rec.get("predicted_n", 0) >= recipe.short_gen_tokens
        if not row["ok"] or "warm_prefill" in flags.request_flags("A", rec):
            findings.append(f"short point {w.id}: {row}")
        shorts.append(row)
        log(f"short v{v}: predicted_n {rec.get('predicted_n')} stop {rec.get('stop_type')}")
    out["short_points"] = shorts

    # -- 2. pairs, depths ascending, variants one after another
    pairs = []
    for d in recipe.depths:
        for v in variants:
            w = get("pair", d, v, v)
            sampling = card_sampling(w.seed)
            a = request(client, w.a_tokens, 0, **sampling)
            b = request(client, w.b_tokens, n_b, **sampling)
            fa, fb = judge_a(a, d), judge_b(b, d, append_n, n_b)
            row = {
                "depth": d,
                "variant": v,
                "id_a": w.id,
                "seed": w.seed,
                "A": _nums(a),
                "B": _nums(b),
                "findings": fa + fb,
                "ok": not (fa or fb),
            }
            pairs.append(row)
            findings.extend(f"{w.id}: {f}" for f in fa + fb)
            log(
                f"d={d} v{v}: A prompt_n {a.get('prompt_n')} cache_n {a.get('cache_n')} | "
                f"B prompt_n {b.get('prompt_n')} cache_n {b.get('cache_n')} "
                f"predicted_n {b.get('predicted_n')} stop {b.get('stop_type')}"
                + ("" if row["ok"] else f"  FINDINGS {fa + fb}")
            )
    out["pairs"] = pairs

    out["summary"] = {
        "equivalence_ok": all(e["ok"] for e in equiv),
        "pairs_total": len(pairs),
        "pairs_ok": sum(p["ok"] for p in pairs),
        "short_points_ok": all(s["ok"] for s in shorts),
        "findings": len(findings),
    }
    out["findings"] = findings
    out["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    client.close()
    return out


def _nums(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k != "tokens"}


def _cached_text(root: Path | None, pid: str, manifest: Manifest) -> str:
    from ..config import repo_root
    from .cache import Cache

    rec = manifest.prompt(pid)
    hit = Cache(root or repo_root()).get(pid, rec.text_sha256, rec.tokens_sha256)
    if hit is None:
        raise RuntimeError(f"{pid} is not in the cache")
    return hit[0]
