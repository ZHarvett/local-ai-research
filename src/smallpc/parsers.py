"""Parsers for llama-server log text (pinned build b12208). Pure functions: no network, no GPU.

The formats come from the real startup logs of the pinned build (fixtures in
``tests/fixtures/logs/``) and, for lines that only appear in particular scenarios, from the format
strings in the llama.cpp source. Every line carries a timestamp/level prefix such as
``0.02.846.495 I llama_context: ...``; the patterns do not depend on it.

Most of what is parsed here is only logged at ``-lv 4`` (``--fit`` decisions, buffer sizes, the
prompt-cache and checkpoint trace), not at the default level 3.
"""

from __future__ import annotations

import re
from collections import defaultdict

_F = r"([\d.]+)"


def scrub_log(text: str, home: str, extra: tuple[str, ...] = ()) -> str:
    """Replace the home directory by ``~`` (and any ``extra`` strings by ``<scrubbed>``)."""
    if home:
        text = text.replace(home.rstrip("/"), "~")
    for s in extra:
        if s:
            text = text.replace(s, "<scrubbed>")
    return text


# --------------------------------------------------------------------------- startup / placement


def parse_fit_placement(log: str) -> dict:
    """Effective context, slots, the placement ``--fit`` chose and buffer sizes.

    ``expert_layers_on_cpu`` is ``n_part`` of the final ``--fit`` state: the number of layers whose
    sparse expert weights are (at least partly) in host memory. In ``common/fit.cpp`` every partial
    layer except the first uses LAYER_FRACTION_MOE (all expert tensors on the CPU); the first
    partial layer keeps attention (+ up, + gate) on the GPU according to ``overflow_type`` (the
    rest of its expert tensors overflow).
    """
    out: dict = {"fit_attempted": "fitting params to device memory" in log}
    out["fit_succeeded"] = "successfully fit params to free device memory" in log

    if m := re.search(r"projected to use (\d+) MiB of device memory vs\. (\d+) MiB of free", log):
        out["initial_projection_mib"] = int(m[1])
        out["free_device_mib_at_fit"] = int(m[2])
    if m := re.search(r"need to reduce device memory by (\d+) MiB", log):
        out["required_reduction_mib"] = int(m[1])
    if m := re.search(r"free memory target of (\d+) MiB", log):
        out["fit_target_mib"] = int(m[1])
    if m := re.search(r"context size set by user to (\d+) -> (.*)", log):
        out["fit_context_note"] = f"set by user to {m[1]} -> {m[2].strip()}"

    finals = re.findall(
        r"(\d+) layers(?: \((\d+) overflowing\))?,\s+(\d+) MiB used,\s+(-?\d+) MiB free", log
    )
    if finals:
        n_layer, overflowing, used, free = finals[-1]
        out["fit_layers"] = int(n_layer)
        out["fit_overflowing_layers"] = int(overflowing or 0)
        out["fit_device_used_mib"] = int(used)
        out["fit_device_free_mib"] = int(free)
    sets = re.findall(
        r"set ngl_per_device\[(\d+)\]\.\(n_layer, n_part(?:, overflow_type)?\)="
        r"\((\d+), (\d+)(?:, (\w+))?\)",
        log,
    )
    if sets:
        _, n_layer, n_part, otype = sets[-1]
        out["n_layer"] = int(n_layer)
        out["expert_layers_on_cpu"] = int(n_part)
        out["first_partial_layer_overflow"] = otype or "MOE"
    if m := re.search(r"offloaded (\d+)/(\d+) layers to GPU", log):
        out["offloaded_layers"] = [int(m[1]), int(m[2])]
    if m := re.search(r"load_tensors: loading model tensors.*\(load_mode = (\w[\w+]*)\)", log):
        out["load_mode"] = m[1]
    out["tensor_overrides_to_cpu"] = "tensor overrides to CPU are used" in log

    buffers: dict[str, dict] = defaultdict(lambda: {"count": 0, "mib": 0.0})
    for name, mib in re.findall(r"load_tensors:\s+(\S+) model buffer size =\s+" + _F + " MiB", log):
        buffers[name]["count"] += 1
        buffers[name]["mib"] = round(buffers[name]["mib"] + float(mib), 2)
    out["model_buffers"] = dict(buffers)

    out["kv_buffers"] = [
        {"device": d, "mib": float(m)}
        for d, m in re.findall(r"llama_kv_cache:\s+(\S+) KV buffer size =\s+" + _F + " MiB", log)
    ]
    if m := re.search(
        r"llama_kv_cache: size =\s+" + _F + r" MiB \(\s*(\d+) cells,\s+(\d+) layers,\s+(\d+)/(\d+) "
        r"seqs\), K \((\w+)\):\s+" + _F + r" MiB, V \((\w+)\):\s+" + _F + " MiB",
        log,
    ):
        out["kv"] = {
            "mib": float(m[1]),
            "cells": int(m[2]),
            "layers": int(m[3]),
            "k_type": m[6],
            "k_mib": float(m[7]),
            "v_type": m[8],
            "v_mib": float(m[9]),
        }
    out["recurrent_state_buffers"] = [
        {"device": d, "mib": float(m)}
        for d, m in re.findall(
            r"llama_memory_recurrent:\s+(\S+) RS buffer size =\s+" + _F + " MiB", log
        )
    ]
    out["compute_buffers"] = [
        {"device": d, "mib": float(m)}
        for d, m in re.findall(
            r"sched_reserve:\s+(\S+) compute buffer size =\s+" + _F + " MiB", log
        )
    ]

    # one entry per llama_context (the MTP draft context is a second one)
    contexts = []
    for block in re.split(r"llama_context: constructing llama_context", log)[1:]:
        block = block[:3000]
        ctx = {}
        for key in ("n_seq_max", "n_ctx", "n_ctx_seq", "n_batch", "n_ubatch", "flash_attn"):
            if m := re.search(rf"llama_context: {key}\s*=\s*(\S+)", block):
                ctx[key] = int(m[1]) if m[1].isdigit() else m[1]
        if m := re.search(r"llama_context: kv_unified\s*=\s*(\S+)", block):
            ctx["kv_unified"] = m[1]
        contexts.append(ctx)
    out["contexts"] = contexts
    if contexts:
        out["n_ctx"] = contexts[0].get("n_ctx")

    if m := re.search(
        r"load_model: initializing, n_slots = (\d+), n_ctx_slot = (\d+), kv_unified = '(\w+)'", log
    ):
        out["n_slots"] = int(m[1])
        out["n_ctx_slot"] = int(m[2])
        out["server_kv_unified"] = m[3]
    if m := re.search(r"prompt cache is enabled, size limit: (\S+(?: MiB)?)", log):
        out["prompt_cache"] = m[1]
    elif "prompt cache is disabled" in log:
        out["prompt_cache"] = "disabled"
    if m := re.search(r"context checkpoints enabled, max = (\d+), min spacing = (\d+)", log):
        out["checkpoints"] = {"max": int(m[1]), "min_spacing": int(m[2])}
    elif "context checkpoints disabled" in log:
        out["checkpoints"] = "disabled"
    out["warnings"] = [
        line.split(" W ", 1)[1].strip()
        for line in log.splitlines()
        if " W " in line and "unused tensor" not in line
    ]
    return out


# --------------------------------------------------------------------------- expert cache


def parse_moe_cache_stats(log: str) -> dict:
    """Expert-cache statistics printed at shutdown, plus the cache configuration lines.

    ``classes`` has one entry per batch class (``ubatch <= 8`` decode-sized, ``ubatch > 8``
    prefill-sized); ``overall_hit_rate_pct`` is computed from the summed hits and misses.
    """
    classes = []
    for m in re.finditer(
        r"llama_moe_cache: (ubatch\s*[<>]=?\s*\d+): hits = (\d+), misses = (\d+) "
        r"\((\d+) on the CPU\), hit rate = " + _F + r"%, uploaded = " + _F + " MiB",
        log,
    ):
        classes.append(
            {
                "name": re.sub(r"\s+", " ", m[1]),
                "hits": int(m[2]),
                "misses": int(m[3]),
                "cpu": int(m[4]),
                "hit_rate_pct": float(m[5]),
                "uploaded_mib": float(m[6]),
            }
        )
    out: dict = {"present": bool(classes), "classes": classes}
    hits = sum(c["hits"] for c in classes)
    total = hits + sum(c["misses"] for c in classes)
    out["overall_hit_rate_pct"] = round(100.0 * hits / total, 2) if total else None
    if m := re.search(
        r"llama_moe_cache: large batches: (\d+) experts copied from the cache, " + _F + " MiB", log
    ):
        out["large_batch_copies"] = {"experts": int(m[1]), "mib": float(m[2])}
    if m := re.search(
        r"MoE cache size =\s+" + _F + " MiB for " + _F + r" MiB of host experts, (\d+)% of the "
        r"misses on the CPU",
        log,
    ):
        out["config"] = {
            "cache_mib": float(m[1]),
            "host_expert_mib": float(m[2]),
            "cpu_share_pct": int(m[3]),
        }
    return out


# ---------------------------------------------------------------- checkpoints, speculation


def parse_checkpoints(log: str) -> dict:
    """Context checkpoints created, erased or restored in this log segment."""
    created = re.findall(
        r"created context checkpoint (\d+) of (\d+) \(pos_min = (-?\d+), pos_max = (-?\d+), "
        r"n_tokens = (\d+), size = " + _F + r" MiB\)",
        log,
    )
    return {
        "created": len(created),
        "created_detail": [
            {
                "index": int(a),
                "max": int(b),
                "pos_min": int(c),
                "pos_max": int(d),
                "n_tokens": int(e),
            }
            for a, b, c, d, e, _ in created
        ],
        "erased": len(re.findall(r"erasing (?:old )?context checkpoint", log)),
        "restored_from_checkpoint": len(re.findall(r"restored context checkpoint \(", log)),
        "speculative_checkpoints_created": len(re.findall(r"created speculative checkpoint", log)),
    }


def parse_spec_stats(log: str) -> list[dict]:
    """``draft acceptance = 0.xxxxx (N accepted / N generated), mean len = x`` lines."""
    return [
        {
            "ratio": float(m[1]),
            "accepted": int(m[2]),
            "generated": int(m[3]),
            "mean_len": float(m[4]),
        }
        for m in re.finditer(
            r"draft acceptance = " + _F + r" \(\s*(\d+) accepted /\s*(\d+) generated\), "
            r"mean len =\s*" + _F,
            log,
        )
    ]


# --------------------------------------------------------------------------- cache source


def parse_cache_source(
    action_log: str,
    completion_log: str,
    cache_n: int | None,
    restored_tokens: int | None = None,
) -> dict:
    """Which mechanism supplied the prefix of a completion that follows a slot action?

    ``action_log``: server-log lines written while the slot restore (or erase) request ran.
    ``completion_log``: lines written while the following ``/completion`` request ran.
    ``cache_n``: the response's ``timings.cache_n`` for that completion.
    ``restored_tokens``: ``n_restored`` from the slot-restore response, if a restore was done (the
    restore itself logs nothing about the main KV state; the draft state / checkpoints are logged).

    Verdicts:
    * ``prompt_cache``: the host-RAM prompt cache loaded a stored state at the start of the
      completion (``- found better prompt`` in the trace);
    * ``slot_restore``: no prompt-cache load, the slot action log shows a restore, ``cache_n > 0``;
    * ``slot_memory``: ``cache_n > 0`` but neither of the above (plain reuse of what the slot held);
    * ``none``: ``cache_n`` is 0 or unknown.
    """
    loaded = re.search(
        r" - found better prompt with f_keep = ([\d.-]+), f_sim = ([\d.-]+)", completion_log
    )
    restored_draft = re.search(r"restored the draft state \(" + _F + r" MiB\)", action_log)
    restored_ckpt = re.search(r"restored (\d+) context checkpoint\(s\)", action_log)
    if loaded:
        verdict = "prompt_cache"
    elif cache_n and (restored_tokens or restored_draft or restored_ckpt):
        verdict = "slot_restore"
    elif cache_n:
        verdict = "slot_memory"
    else:
        verdict = "none"
    return {
        "verdict": verdict,
        "prompt_cache_load": bool(loaded),
        "prompt_cache_f_keep": float(loaded[1]) if loaded else None,
        "prompt_cache_f_sim": float(loaded[2]) if loaded else None,
        "draft_state_restored_from_slot_file": bool(restored_draft),
        "draft_state_mib": float(restored_draft[1]) if restored_draft else None,
        "checkpoints_restored_from_slot_file": int(restored_ckpt[1]) if restored_ckpt else 0,
        "prompt_cache_updates": len(re.findall(r"updating prompt cache", completion_log)),
        "restored_tokens": restored_tokens,
        "cache_n": cache_n,
    }
