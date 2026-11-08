from __future__ import annotations

import numpy as np
import pytest
from gguf import GGMLQuantizationType as Q
from gguf import GGUFWriter
from gguf.constants import GGML_QUANT_SIZES

from smallpc import sizes

E, ROWS, COLS = 4, 2, 256  # experts, rows per expert, columns (one Q4_K / Q6_K super-block)


def q_bytes(qtype, rows=ROWS, cols=COLS):
    block, tsize = GGML_QUANT_SIZES[qtype]
    return rows * (cols // block) * tsize


def add_quant(w, name, qtype):
    row_bytes = (COLS // GGML_QUANT_SIZES[qtype][0]) * GGML_QUANT_SIZES[qtype][1]
    raw = np.zeros((E, ROWS, row_bytes), dtype=np.uint8)
    w.add_tensor(name, raw, raw_dtype=qtype)


@pytest.fixture
def tiny(tmp_path):
    """3 blocks: 0 and 1 are trunk, 2 is the MTP head. Layer 1 has full attention (interval 2)."""
    path = tmp_path / "tiny.gguf"
    w = GGUFWriter(str(path), "qwen35moe")
    w.add_block_count(3)
    for k, v in {
        "nextn_predict_layers": 1,
        "expert_count": E,
        "expert_used_count": 2,
        "attention.head_count_kv": 2,
        "attention.key_length": 16,
        "attention.value_length": 16,
        "full_attention_interval": 2,
        "ssm.conv_kernel": 4,
        "ssm.state_size": 8,
        "ssm.group_count": 2,
        "ssm.inner_size": 16,
    }.items():
        w.add_uint32(f"qwen35moe.{k}", v)
    # gate/up Q4_K everywhere; down Q6_K in layers 0 and 2, Q4_K in layer 1.
    for blk, down in ((0, Q.Q6_K), (1, Q.Q4_K), (2, Q.Q6_K)):
        add_quant(w, f"blk.{blk}.ffn_gate_exps.weight", Q.Q4_K)
        add_quant(w, f"blk.{blk}.ffn_up_exps.weight", Q.Q4_K)
        add_quant(w, f"blk.{blk}.ffn_down_exps.weight", down)
        # a shared-expert tensor must not be counted as an expert
        w.add_tensor(f"blk.{blk}.ffn_up_shexp.weight", np.zeros((8, 8), np.float32))
    for blk in (1, 2):
        w.add_tensor(f"blk.{blk}.attn_k.weight", np.zeros((8, 8), np.float32))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()
    return path


def test_known_quant_sizes():
    assert q_bytes(Q.Q4_K) == 2 * 144 and q_bytes(Q.Q6_K) == 2 * 210  # block sizes of ggml


def test_expert_bytes_per_layer(tiny, tmp_path):
    res = sizes.analyze(tiny, root=tmp_path)
    layers = {entry["layer"]: entry for entry in res["expert"]["per_layer"]}
    assert layers[0]["bytes_per_expert"] == 2 * 288 + 420 == 996
    assert layers[1]["bytes_per_expert"] == 3 * 288 == 864
    assert layers[2]["bytes_per_expert"] == 996 and layers[2]["mtp_head"] is True
    assert layers[0]["types"] == {
        "ffn_gate_exps": "Q4_K",
        "ffn_up_exps": "Q4_K",
        "ffn_down_exps": "Q6_K",
    }
    assert layers[1]["parts"]["ffn_down_exps"] == 288
    assert res["expert_count"] == E and res["trunk_layers"] == 2


def test_stats_exclude_the_mtp_head_from_the_headline(tiny, tmp_path):
    ex = sizes.analyze(tiny, root=tmp_path)["expert"]
    s = ex["bytes_per_expert_stats_trunk_layers"]
    assert (s["n_layers"], s["min"], s["max"], s["mean"]) == (2, 864, 996, 930.0)
    assert s["experts_per_gib_at_mean"] == pytest.approx(2**30 / 930)
    assert s["vs_plan_estimate_pct"] == pytest.approx((930 - 1.8e6) / 1.8e6 * 100)
    a = ex["bytes_per_expert_stats_all_layers_incl_mtp_head"]
    assert a["n_layers"] == 3 and a["mean"] == pytest.approx((996 + 864 + 996) / 3)
    assert len(ex["distinct_quantization_layouts"]) == 2


def test_kv_and_recurrent_state(tiny, tmp_path):
    kv = sizes.analyze(tiny, root=tmp_path)["kv"]
    assert kv["full_attention_layers"] == 1 == kv["full_attention_layers_from_metadata"]
    assert kv["full_attention_layer_indices"] == [1]  # the MTP head's attn_k is not counted
    assert kv["elements_per_token"] == 1 * 2 * (16 + 16) == 64
    assert kv["bytes_per_token"]["f16"] == 128
    assert kv["bytes_per_token"]["q8_0"] == pytest.approx(64 * 34 / 32)
    rs = kv["recurrent_state"]
    assert rs["recurrent_layers"] == 1
    assert rs["conv_elements_per_layer"] == 3 * (16 + 2 * 2 * 8) == 144
    assert rs["ssm_elements_per_layer"] == 8 * 16 == 128
    assert rs["bytes_per_sequence"] == (144 + 128) * 4


def test_wrong_expert_count_is_an_error(tiny, tmp_path):
    from gguf import GGUFReader

    reader = GGUFReader(str(tiny))
    with pytest.raises(ValueError, match="expert_count"):
        sizes.expert_bytes_per_layer(reader, E + 1)


def test_cli_writes_json(tiny, tmp_path, capsys):
    out = tmp_path / "o" / "sizes.json"
    assert sizes.main([str(tiny), "--out", str(out)]) == 0
    assert out.exists() and "bytes/expert" in capsys.readouterr().out


def test_log_reference_parses_the_wp5_startup_log():
    ref = sizes.log_reference(sizes.repo_root())
    assert ref["kv_mib"] == 680.0 and ref["kv_cells"] == 65536 and ref["kv_layers"] == 10
    assert ref["recurrent_mib"] == pytest.approx(62.81)
