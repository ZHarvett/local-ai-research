"""Exact sizes from a GGUF: bytes per expert, KV-cache bytes per token, recurrent state.

    python -m smallpc.sizes <gguf> [--out data/microbench/model-sizes.json]

Bytes per expert: for every layer, the bytes of ``ffn_gate_exps``, ``ffn_up_exps`` and
``ffn_down_exps`` each divided by the expert count, summed over the three. The MTP head block
(``block_count - nextn_predict_layers`` and up) is listed but kept out of the headline statistics,
because the sweeps place trunk experts.

KV bytes per token: ``n_full_attention_layers * n_head_kv * (key_length + value_length) * bytes
per element`` (f16 = 2, q8_0 = 34/32: 32 int8 values plus one fp16 scale per block). Recurrent
state per sequence (Gated DeltaNet layers): conv state ``(conv_kernel - 1) * (inner_size + 2 *
group_count * state_size)`` plus SSM state ``state_size * inner_size`` elements, both f32.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .config import repo_root

GIB = 1024**3
MIB = 1024**2
PLAN_EXPERT_BYTES = 1.8e6  # project plan: "about 1.8 MB each (about 550 experts per GB of VRAM)"
PLAN_EXPERTS_PER_GB = 550
PLAN_KV_PER_TOKEN = {"f16": 20_000, "q8_0": 10_000}  # "about 20 KB ... about 10 KB at 8-bit"
BYTES_PER_ELEMENT = {"f16": 2.0, "q8_0": 34 / 32, "f32": 4.0}
EXPERT_TENSORS = ("ffn_gate_exps", "ffn_up_exps", "ffn_down_exps")
LOG_FIXTURE = "tests/fixtures/logs/startup-health64k.txt"


def _scalar(reader, key: str):
    f = reader.get_field(key)
    if f is None:
        return None
    v = f.contents()
    return v.item() if hasattr(v, "item") else v


def expert_bytes_per_layer(reader, n_expert: int) -> list[dict]:
    layers: dict[int, dict] = {}
    for t in reader.tensors:
        m = re.fullmatch(r"blk\.(\d+)\.(ffn_(?:gate|up|down)_exps)\.weight", t.name)
        if not m:
            continue
        shape = [int(x) for x in t.shape]
        if shape[-1] != n_expert:
            raise ValueError(f"{t.name}: last dim {shape[-1]} != expert_count {n_expert}")
        n_bytes = int(t.n_bytes)
        if n_bytes % n_expert:
            raise ValueError(f"{t.name}: {n_bytes} bytes not divisible by {n_expert} experts")
        layers.setdefault(int(m[1]), {})[m[2]] = {
            "type": t.tensor_type.name,
            "tensor_bytes": n_bytes,
            "bytes_per_expert": n_bytes // n_expert,
        }
    out = []
    for blk in sorted(layers):
        parts = layers[blk]
        missing = [n for n in EXPERT_TENSORS if n not in parts]
        if missing:
            raise ValueError(f"blk.{blk}: missing expert tensors {missing}")
        out.append(
            {
                "layer": blk,
                "bytes_per_expert": sum(parts[n]["bytes_per_expert"] for n in EXPERT_TENSORS),
                "types": {n: parts[n]["type"] for n in EXPERT_TENSORS},
                "parts": {n: parts[n]["bytes_per_expert"] for n in EXPERT_TENSORS},
            }
        )
    return out


def _stats(values: list[int]) -> dict:
    mean = sum(values) / len(values)
    return {
        "n_layers": len(values),
        "min": min(values),
        "mean": mean,
        "max": max(values),
        "experts_per_gib_at_mean": GIB / mean,
        "experts_per_gb_at_mean": 1e9 / mean,
    }


def kv_and_recurrent(reader, trunk_layers: int) -> dict:
    arch = _scalar(reader, "general.architecture")
    g = lambda k: _scalar(reader, f"{arch}.{k}")  # noqa: E731
    n_head_kv, key_len, val_len = g("attention.head_count_kv"), g("attention.key_length"), None
    val_len = g("attention.value_length")
    interval = g("full_attention_interval")
    attn_from_meta = (
        sum(1 for il in range(trunk_layers) if (il + 1) % interval == 0) if interval else None
    )
    attn_from_tensors = sorted(
        int(m[1])
        for t in reader.tensors
        if (m := re.fullmatch(r"blk\.(\d+)\.attn_k\.weight", t.name)) and int(m[1]) < trunk_layers
    )
    n_attn = len(attn_from_tensors)
    elems_per_token = n_attn * n_head_kv * (key_len + val_len)
    out = {
        "full_attention_layers": n_attn,
        "full_attention_layers_from_metadata": attn_from_meta,
        "full_attention_layer_indices": attn_from_tensors,
        "n_head_kv": n_head_kv,
        "key_length": key_len,
        "value_length": val_len,
        "elements_per_token": elems_per_token,
        "bytes_per_token": {
            "f16": elems_per_token * BYTES_PER_ELEMENT["f16"],
            "q8_0": elems_per_token * BYTES_PER_ELEMENT["q8_0"],
        },
    }
    conv_k, d_state, groups, inner = (
        g("ssm.conv_kernel"),
        g("ssm.state_size"),
        g("ssm.group_count"),
        g("ssm.inner_size"),
    )
    if None not in (conv_k, d_state, groups, inner):
        n_rec = trunk_layers - n_attn
        conv = (conv_k - 1) * (inner + 2 * groups * d_state)
        ssm = d_state * inner
        out["recurrent_state"] = {
            "recurrent_layers": n_rec,
            "conv_elements_per_layer": conv,
            "ssm_elements_per_layer": ssm,
            "bytes_per_sequence": n_rec * (conv + ssm) * BYTES_PER_ELEMENT["f32"],
            "r_bytes": n_rec * conv * 4,
            "s_bytes": n_rec * ssm * 4,
            "note": "f32; independent of context length",
        }
    return out


def log_reference(root: Path) -> dict | None:
    """KV and recurrent-state sizes from the WP5 startup log (64K, q8_0, no MTP)."""
    p = root / LOG_FIXTURE
    if not p.exists():
        return None
    text = p.read_text(errors="replace")
    kv = re.search(r"llama_kv_cache: size =\s+([\d.]+) MiB \(\s*(\d+) cells,\s+(\d+) layers", text)
    rs = re.search(
        r"llama_memory_recurrent: size =\s+([\d.]+) MiB.*?"
        r"R \(f32\):\s+([\d.]+) MiB, S \(f32\):\s+([\d.]+) MiB",
        text,
    )
    if not kv or not rs:
        return None
    return {
        "source": LOG_FIXTURE,
        "kv_mib": float(kv[1]),
        "kv_cells": int(kv[2]),
        "kv_layers": int(kv[3]),
        "recurrent_mib": float(rs[1]),
        "recurrent_r_mib": float(rs[2]),
        "recurrent_s_mib": float(rs[3]),
    }


def analyze(path: str | Path, root: Path | None = None) -> dict:
    from gguf import GGUFReader

    root = root or repo_root()
    reader = GGUFReader(str(path))
    arch = _scalar(reader, "general.architecture")
    n_expert = int(_scalar(reader, f"{arch}.expert_count"))
    block_count = int(_scalar(reader, f"{arch}.block_count"))
    nextn = int(_scalar(reader, f"{arch}.nextn_predict_layers") or 0)
    trunk = block_count - nextn

    layers = expert_bytes_per_layer(reader, n_expert)
    for layer in layers:
        layer["mtp_head"] = layer["layer"] >= trunk
    trunk_bytes = [layer["bytes_per_expert"] for layer in layers if not layer["mtp_head"]]
    all_bytes = [layer["bytes_per_expert"] for layer in layers]
    type_sets = sorted({json.dumps(layer["types"], sort_keys=True) for layer in layers})
    stats = _stats(trunk_bytes)
    stats["vs_plan_estimate_pct"] = (stats["mean"] - PLAN_EXPERT_BYTES) / PLAN_EXPERT_BYTES * 100
    stats["experts_per_gb_vs_plan_pct"] = (
        (stats["experts_per_gb_at_mean"] - PLAN_EXPERTS_PER_GB) / PLAN_EXPERTS_PER_GB * 100
    )

    kv = kv_and_recurrent(reader, trunk)
    for typ, est in PLAN_KV_PER_TOKEN.items():
        kv.setdefault("vs_plan_pct", {})[typ] = (kv["bytes_per_token"][typ] - est) / est * 100

    ref = log_reference(root)
    if ref:
        kv_pred = kv["bytes_per_token"]["q8_0"] * ref["kv_cells"] / MIB
        rs_pred = kv.get("recurrent_state", {}).get("bytes_per_sequence", 0) / MIB
        ref["metadata_prediction"] = {
            "kv_mib_q8_0": kv_pred,
            "recurrent_mib": rs_pred,
            "kv_difference_mib": kv_pred - ref["kv_mib"],
            "recurrent_difference_mib": rs_pred - ref["recurrent_mib"],
        }
        ref["verdict"] = (
            "metadata calculation and log agree"
            if abs(kv_pred - ref["kv_mib"]) < 0.01 and abs(rs_pred - ref["recurrent_mib"]) < 0.01
            else "DISAGREE: see metadata_prediction"
        )

    return {
        "model_file": Path(path).name,
        "architecture": arch,
        "block_count": block_count,
        "trunk_layers": trunk,
        "nextn_predict_layers": nextn,
        "expert_count": n_expert,
        "expert": {
            "bytes_per_expert_stats_trunk_layers": stats,
            "bytes_per_expert_stats_all_layers_incl_mtp_head": _stats(all_bytes),
            "distinct_quantization_layouts": [json.loads(s) for s in type_sets],
            "plan_estimate": {
                "bytes_per_expert": PLAN_EXPERT_BYTES,
                "experts_per_gb": PLAN_EXPERTS_PER_GB,
            },
            "per_layer": layers,
        },
        "kv": kv,
        "log_reference_64k_q8_0": ref,
        "plan_kv_estimate_bytes_per_token": PLAN_KV_PER_TOKEN,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.sizes")
    ap.add_argument("gguf")
    ap.add_argument("--out", default=str(repo_root() / "data/microbench/model-sizes.json"))
    a = ap.parse_args(argv)
    res = analyze(a.gguf)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + "\n")
    s = res["expert"]["bytes_per_expert_stats_trunk_layers"]
    print(
        f"bytes/expert min {s['min']} mean {s['mean']:.1f} max {s['max']} "
        f"({s['experts_per_gib_at_mean']:.1f} experts/GiB, "
        f"{s['vs_plan_estimate_pct']:+.1f}% vs plan)"
    )
    kvb = res["kv"]["bytes_per_token"]
    print(
        f"KV bytes/token f16 {kvb['f16']:.0f} q8_0 {kvb['q8_0']:.0f}; wrote {out}", file=sys.stderr
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
