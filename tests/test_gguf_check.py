"""gguf_check on synthetic tensors: no model file, runs in CI."""

from __future__ import annotations

import json

import numpy as np
import pytest

from smallpc import gguf_check as gc

SHAPE = (256, 512)  # rows x row_len of every synthetic matrix
N_MATRICES = 12  # the real blk.40 has 12 weight matrices


def gaussian(rng, std=0.02, shape=SHAPE):
    return rng.normal(0.0, std, shape).astype(np.float32)


def heavy(rng, std=0.02, df=5, shape=SHAPE):
    # Student-t rescaled to the requested std: kurtosis 3 + 6/(df-4) = 9 (far from 3).
    t = rng.standard_t(df, shape)
    return (t * std / np.sqrt(df / (df - 2))).astype(np.float32)


def stat(name, arr, kind=None):
    arr = np.asarray(arr)
    kind = kind or gc.classify(name, arr.ndim)
    return gc.compute_stat(name, kind, list(arr.shape[::-1]), "F32", gc.ArraySource(arr))


def head(matrices, norms):
    out = [stat(f"blk.40.m{i}.weight", m, "matrix") for i, m in enumerate(matrices)]
    out += [stat(f"blk.40.n{i}_norm.weight", n, "norm") for i, n in enumerate(norms)]
    return out


def good_norms(rng):
    return [rng.normal(1.0, 0.1, 2048).astype(np.float32) for _ in range(4)]


# ---------------------------------------------------------------- the five required cases


def test_gaussian_matrices_are_a_fresh_init_fail():
    rng = np.random.default_rng(0)
    scr = gc.screen_head(head([gaussian(rng) for _ in range(N_MATRICES)], good_norms(rng)))
    assert scr.verdict == "FAIL"
    assert scr.n_fresh_like == N_MATRICES
    assert any("fresh random initialisation" in r for r in scr.reasons)


def test_student_t_matrices_pass():
    rng = np.random.default_rng(1)
    scr = gc.screen_head(head([heavy(rng) for _ in range(N_MATRICES)], good_norms(rng)))
    assert scr.verdict == "PASS", scr.reasons
    assert scr.n_fresh_like == 0


@pytest.mark.parametrize("bad", [np.nan, np.inf, 1e31])
def test_garbage_norms_fail(bad):
    rng = np.random.default_rng(2)
    norms = good_norms(rng)
    norms[1][5] = bad
    scr = gc.screen_head(head([heavy(rng) for _ in range(N_MATRICES)], norms))
    assert scr.verdict == "FAIL"
    assert scr.reasons


def test_all_1e31_norms_fail():
    rng = np.random.default_rng(3)
    norms = [np.full(2048, 1e31, np.float32) for _ in range(4)]
    scr = gc.screen_head(head([heavy(rng) for _ in range(N_MATRICES)], norms))
    assert scr.verdict == "FAIL"
    assert any("median" in r for r in scr.reasons)


def test_norms_around_0_02_fail():
    rng = np.random.default_rng(4)
    norms = [rng.normal(0.02, 0.001, 2048).astype(np.float32) for _ in range(4)]
    scr = gc.screen_head(head([heavy(rng) for _ in range(N_MATRICES)], norms))
    assert scr.verdict == "FAIL"
    assert any("median" in r for r in scr.reasons)


@pytest.mark.parametrize("n_gauss", [1, 2, 3, 4, 5])
def test_mostly_heavy_tailed_with_a_few_near_gaussian_passes(n_gauss):
    # No false rejection: up to 5 of 12 (42%) near-Gaussian matrices must not trip the rule.
    rng = np.random.default_rng(10 + n_gauss)
    mats = [gaussian(rng) for _ in range(n_gauss)] + [
        heavy(rng) for _ in range(N_MATRICES - n_gauss)
    ]
    scr = gc.screen_head(head(mats, good_norms(rng)))
    assert scr.verdict == "PASS", scr.reasons
    assert scr.n_fresh_like == n_gauss


# ---------------------------------------------------------------- boundaries and robustness


def test_fresh_fraction_boundary_is_ninety_percent():
    rng = np.random.default_rng(20)
    # 11 of 12 = 91.7% -> FAIL; 10 of 12 = 83.3% -> PASS
    for n_gauss, verdict in ((11, "FAIL"), (10, "PASS")):
        mats = [gaussian(rng) for _ in range(n_gauss)] + [
            heavy(rng) for _ in range(N_MATRICES - n_gauss)
        ]
        assert gc.screen_head(head(mats, good_norms(rng))).verdict == verdict


def test_gaussian_with_a_different_std_is_not_flagged():
    rng = np.random.default_rng(21)
    mats = [gaussian(rng, std=0.05) for _ in range(N_MATRICES)]
    assert gc.screen_head(head(mats, good_norms(rng))).verdict == "PASS"


def fake_q4(a, block=32):
    """Round-to-nearest 4-bit blockwise quantization, then dequantization."""
    flat = a.reshape(-1, block)
    scale = np.abs(flat).max(axis=1, keepdims=True) / 7.0
    q = np.clip(np.round(flat / scale), -8, 7)
    return (q * scale).reshape(a.shape).astype(np.float32)


def test_quantized_gaussian_is_still_detected():
    rng = np.random.default_rng(22)
    mats = [fake_q4(gaussian(rng)) for _ in range(N_MATRICES)]
    assert gc.screen_head(head(mats, good_norms(rng))).verdict == "FAIL"


def test_quantized_heavy_tails_still_pass():
    rng = np.random.default_rng(23)
    mats = [fake_q4(heavy(rng)) for _ in range(N_MATRICES)]
    assert gc.screen_head(head(mats, good_norms(rng))).verdict == "PASS"


def test_nan_in_a_matrix_fails():
    rng = np.random.default_rng(24)
    mats = [heavy(rng) for _ in range(N_MATRICES)]
    mats[3][10, 10] = np.nan
    scr = gc.screen_head(head(mats, good_norms(rng)))
    assert scr.verdict == "FAIL"
    assert any("non-finite" in r for r in scr.reasons)


def test_empty_head_fails():
    assert gc.screen_head([]).verdict == "FAIL"


def test_chunking_and_subsampling():
    rng = np.random.default_rng(25)
    a = heavy(rng, shape=(512, 256))
    full = gc.compute_stat("m.weight", "matrix", [256, 512], "F32", gc.ArraySource(a))
    chunked = gc.compute_stat(
        "m.weight", "matrix", [256, 512], "F32", gc.ArraySource(a), chunk_values=1000
    )
    assert chunked.std == pytest.approx(full.std, rel=1e-9)
    assert chunked.kurtosis == pytest.approx(full.kurtosis, rel=1e-9)
    # exact reference
    x = a.astype(np.float64).ravel()
    assert full.std == pytest.approx(x.std(), rel=1e-6)
    assert full.kurtosis == pytest.approx(((x - x.mean()) ** 4).mean() / x.var() ** 2, rel=1e-6)
    assert full.max_over_sigma == pytest.approx(np.abs(x - x.mean()).max() / x.std(), rel=1e-6)
    # a strided subsample (cap 20000 of 131072 values) is close, and a NaN is still found
    a[400, 3] = np.nan
    sub = gc.compute_stat(
        "m.weight", "matrix", [256, 512], "F32", gc.ArraySource(a), max_sample=20_000
    )
    assert sub.n_sampled < full.n_sampled
    assert sub.n_nonfinite == 1
    assert sub.std == pytest.approx(full.std, rel=0.1)


def test_classify():
    assert gc.classify("blk.40.attn_norm.weight", 1) == "norm"
    assert gc.classify("blk.40.nextn.shared_head_norm.weight", 1) == "norm"
    assert gc.classify("blk.40.attn_q.weight", 2) == "matrix"
    assert gc.classify("blk.40.ffn_up_exps.weight", 3) == "matrix"
    assert gc.classify("blk.40.ffn_gate_inp_shexp.weight", 1) == "other"


# ---------------------------------------------------------------- chat template


def test_template_comparison():
    official = "{%- set a = 1 %}\n  {{ a }}\n"
    same = compare = gc.compare_templates("{%- set a = 1 %} {{ a }}", official)
    assert same["identical"] and compare["diff"] == []
    other = gc.compare_templates("{%- set a = 2 %} {{ a }}", official)
    assert not other["identical"]
    assert other["n_changes"] == 1
    assert other["diff"] == ["replace official[4:5] -> embedded[4:5]: '1' => '2'"]
    assert not gc.compare_templates(None, official)["embedded"]


# ---------------------------------------------------------------- end to end on a tiny GGUF


def write_tiny_gguf(path, make_matrix, drop_head_tensor=None, template="{{ x }}"):
    from gguf import GGMLQuantizationType, GGUFWriter
    from gguf.quants import quantize

    rng = np.random.default_rng(30)
    w = GGUFWriter(str(path), "qwen35moe")
    w.add_block_count(3)  # blk.0, blk.1 (trunk), blk.2 (head)
    w.add_uint32("qwen35moe.nextn_predict_layers", 1)
    w.add_uint32("qwen35moe.expert_count", 4)
    w.add_uint32("qwen35moe.expert_used_count", 2)
    if template is not None:
        w.add_chat_template(template)
    common = ["attn_q.weight", "attn_k.weight", "attn_norm.weight", "ffn_gate_exps.weight"]
    for blk in (1, 2):
        names = list(common) + (
            [
                "nextn.eh_proj.weight",
                "nextn.enorm.weight",
                "nextn.hnorm.weight",
                "nextn.shared_head_norm.weight",
            ]
            if blk == 2
            else []
        )
        for n in names:
            if blk == 2 and n == drop_head_tensor:
                continue
            full = f"blk.{blk}.{n}"
            if n.endswith("norm.weight"):
                w.add_tensor(full, rng.normal(1.0, 0.1, 64).astype(np.float32))
            elif n == "attn_k.weight":  # quantized, to exercise the dequantizing reader
                q = quantize(make_matrix(rng, (32, 64)), GGMLQuantizationType.Q8_0)
                w.add_tensor(full, q, raw_dtype=GGMLQuantizationType.Q8_0)
            elif n.endswith("exps.weight"):
                w.add_tensor(full, make_matrix(rng, (4, 32, 64)))  # 3-D expert tensor
            else:
                w.add_tensor(full, make_matrix(rng, (32, 64)))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()


@pytest.fixture
def template_file(tmp_path):
    p = tmp_path / "t.jinja"
    p.write_text("{{   x }}\n")
    return p


def test_end_to_end_tiny_gguf_pass_and_json(tmp_path, template_file):
    g = tmp_path / "tiny.gguf"
    write_tiny_gguf(g, lambda rng, shape: heavy(rng, shape=shape))
    res = gc.check_gguf(g, template_file, progress=lambda m: None)
    assert res["verdict"] == "PASS", res["reasons"]
    assert res["metadata"]["architecture"] == "qwen35moe"
    assert res["metadata"]["nextn_predict_layers"] == 1
    assert res["metadata"]["nextn_predict_layers_key"] == "qwen35moe.nextn_predict_layers"
    assert res["metadata"]["expert_keys"]["qwen35moe.expert_count"] == 4
    assert res["chat_template"]["identical"] is True
    assert res["head_block"] == 2 and res["reference_block"] == 1
    assert res["layout"]["count"] == 8 and res["layout"]["present_and_complete"]
    assert {r["tensor"] for r in res["table"]} >= {"attn_q.weight", "nextn.eh_proj.weight"}
    json.dumps(res, allow_nan=False)  # strictly valid JSON


def test_end_to_end_tiny_gguf_gaussian_fails(tmp_path, template_file):
    g = tmp_path / "tiny.gguf"
    write_tiny_gguf(g, lambda rng, shape: gaussian(rng, shape=shape))
    res = gc.check_gguf(g, template_file, progress=lambda m: None)
    assert res["verdict"] == "FAIL"
    assert any("fresh random initialisation" in r for r in res["reasons"])


def test_end_to_end_missing_head_tensor_fails(tmp_path, template_file):
    g = tmp_path / "tiny.gguf"
    write_tiny_gguf(
        g, lambda rng, shape: heavy(rng, shape=shape), drop_head_tensor="nextn.eh_proj.weight"
    )
    res = gc.check_gguf(g, template_file, progress=lambda m: None)
    assert res["verdict"] == "FAIL"
    assert res["layout"]["missing_nextn"] == ["nextn.eh_proj.weight"]


def test_end_to_end_template_mismatch_is_reported(tmp_path, template_file):
    g = tmp_path / "tiny.gguf"
    write_tiny_gguf(g, lambda rng, shape: heavy(rng, shape=shape), template="{{ y }}")
    res = gc.check_gguf(g, template_file, progress=lambda m: None)
    assert res["chat_template"]["identical"] is False
    assert res["chat_template"]["diff"]


def test_cli_writes_json_and_exit_code(tmp_path, template_file):
    g = tmp_path / "tiny.gguf"
    write_tiny_gguf(g, lambda rng, shape: gaussian(rng, shape=shape))
    out = tmp_path / "out" / "check.json"
    rc = gc.main([str(g), "--template", str(template_file), "--out", str(out)])
    assert rc == 1
    assert json.loads(out.read_text())["verdict"] == "FAIL"
