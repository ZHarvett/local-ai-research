"""Screen a GGUF file's MTP (nextn) head for known broken-head signatures.

    uv run python -m smallpc.gguf_check <model.gguf> [--template FILE] [--out FILE]

Writes ``data/health/model-check.json`` and prints a report. Exit status 0 = PASS, 1 = FAIL.

What this can and cannot show
-----------------------------
* The tensor LAYOUT (``blk.<N>.*``) shows the head is present and complete. A trained head and a
  randomly initialised one have identical layouts, so layout alone proves nothing about training.
* The SCREEN looks for three known failure signatures. PASS means only "no known failure
  signature". It does not prove the head works: WP5's draft-acceptance and equivalence tests do.

Known broken-head signatures (any one is a FAIL)
------------------------------------------------
1. Non-finite values (NaN/Inf) anywhere in a head tensor.
2. A norm weight whose median is outside [0.2, 5], or any value above 1e4 in magnitude. This
   catches norms left at ~0.02 as well as the reported ~1e31 / NaN garbage.
3. Fresh random initialisation: at least 90% of the weight matrices have Pearson kurtosis within
   3 +/- 0.3 AND a standard deviation within 0.015-0.025 (N(0, 0.02) looks exactly like that).

Everything else (kurtosis, std, max/sigma for each matrix, next to the last trunk block) is a
diagnostic, not a threshold.

Memory: tensors are dequantized in row chunks of at most ~8M values. The non-finite scan covers
every value; the moment statistics use an evenly strided row subsample of at most 50M values per
tensor (all of it for smaller tensors).
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

# ---- thresholds (step plan WP4) ---------------------------------------------------------------
NORM_MEDIAN_RANGE = (0.2, 5.0)
NORM_MAX_ABS = 1e4
FRESH_KURTOSIS = (3.0, 0.3)  # centre, half-width
FRESH_STD = (0.015, 0.025)
FRESH_FRACTION = 0.90
MAX_SAMPLE_VALUES = 50_000_000
CHUNK_VALUES = 8_000_000

NEXTN_SUFFIXES = (
    "nextn.eh_proj.weight",
    "nextn.enorm.weight",
    "nextn.hnorm.weight",
    "nextn.shared_head_norm.weight",
)

PASS_MEANS = (
    "PASS means only: no known failure signature was found. It does not show that the MTP head is "
    "trained or works. The layout of a trained head and a random one is identical; WP5's "
    "draft-acceptance and equivalence tests are what prove the head works."
)
LAYOUT_MEANS = (
    "The blk.<head> tensor list shows the head is present and complete (same tensors as the last "
    "trunk layer plus the nextn.* ones). It cannot tell a trained head from a random one."
)


# ---- statistics ----------------------------------------------------------------------------


class RowSource(Protocol):
    """A tensor seen as ``n_rows`` rows of ``row_len`` values; ``read`` returns float32 rows."""

    n_rows: int
    row_len: int

    def read(self, start: int, stop: int) -> np.ndarray: ...


class ArraySource:
    """Row source over an in-memory array (tests, synthetic tensors)."""

    def __init__(self, array: np.ndarray):
        a = np.asarray(array, dtype=np.float32)
        self.shape = tuple(a.shape)
        self._rows = a.reshape(-1, a.shape[-1]) if a.ndim > 1 else a.reshape(1, -1)
        self.n_rows, self.row_len = self._rows.shape

    def read(self, start: int, stop: int) -> np.ndarray:
        return self._rows[start:stop]


@dataclass
class TensorStat:
    name: str
    kind: str  # "norm" | "matrix" | "other"
    shape: list[int]  # GGUF order (ne0 first)
    qtype: str
    n_values: int
    n_sampled: int
    n_nonfinite: int
    mean: float | None
    std: float | None
    kurtosis: float | None  # Pearson (normal = 3)
    max_over_sigma: float | None  # max |x - mean| / std
    abs_max: float | None
    median: float | None = None  # norms only


def classify(name: str, ndim: int) -> str:
    """norm: 1-D ``*norm.weight``; matrix: >=2-D ``.weight``; other: everything else."""
    if name.endswith("norm.weight") and ndim == 1:
        return "norm"
    if name.endswith(".weight") and ndim >= 2:
        return "matrix"
    return "other"


def _num(x: float) -> float | None:
    return float(x) if math.isfinite(x) else None


def compute_stat(
    name: str,
    kind: str,
    shape: Sequence[int],
    qtype: str,
    source: RowSource,
    max_sample: int = MAX_SAMPLE_VALUES,
    chunk_values: int = CHUNK_VALUES,
) -> TensorStat:
    """Scan every value for non-finites; compute moments on a strided row subsample."""
    n_rows, row_len = source.n_rows, source.row_len
    total = n_rows * row_len
    stride = max(1, math.ceil(total / max_sample))
    rows_per_chunk = max(1, chunk_values // max(row_len, 1))
    n_nonfinite = n_sampled = 0
    shift: float | None = None
    s1 = s2 = s3 = s4 = 0.0  # power sums of (x - shift) over finite sampled values
    lo, hi = math.inf, -math.inf
    keep_for_median: list[np.ndarray] = []
    for start in range(0, n_rows, rows_per_chunk):
        stop = min(start + rows_per_chunk, n_rows)
        chunk = source.read(start, stop)
        finite = np.isfinite(chunk)
        n_nonfinite += int(chunk.size - np.count_nonzero(finite))
        # rows whose global index is a multiple of the stride
        first = (-start) % stride
        sample = chunk[first::stride]
        if sample.size == 0:
            continue
        v = sample[np.isfinite(sample)].astype(np.float64).ravel()
        if v.size == 0:
            continue
        if shift is None:
            shift = float(v.mean())
        d = v - shift
        s1 += float(d.sum())
        d2 = d * d
        s2 += float(d2.sum())
        s3 += float((d2 * d).sum())
        s4 += float((d2 * d2).sum())
        n_sampled += v.size
        lo, hi = min(lo, float(v.min())), max(hi, float(v.max()))
        if kind == "norm":
            keep_for_median.append(v)
    if n_sampled == 0:
        return TensorStat(
            name, kind, list(shape), qtype, total, 0, n_nonfinite, None, None, None, None, None
        )
    n = float(n_sampled)
    m1, m2c, m3c, m4c = s1 / n, s2 / n, s3 / n, s4 / n
    var = m2c - m1 * m1
    mean = (shift or 0.0) + m1
    std = math.sqrt(var) if var > 0 else 0.0
    if var > 0:
        mu4 = m4c - 4 * m1 * m3c + 6 * m1 * m1 * m2c - 3 * m1**4
        kurt = mu4 / (var * var)
        mos = max(abs(hi - mean), abs(lo - mean)) / std
    else:
        kurt, mos = math.nan, math.nan
    median = float(np.median(np.concatenate(keep_for_median))) if keep_for_median else None
    return TensorStat(
        name, kind, list(shape), qtype, total, n_sampled, n_nonfinite,
        _num(mean), _num(std), _num(kurt), _num(mos), _num(max(abs(lo), abs(hi))), median,
    )  # fmt: skip


def is_fresh_init(s: TensorStat) -> bool:
    return (
        s.kurtosis is not None
        and s.std is not None
        and abs(s.kurtosis - FRESH_KURTOSIS[0]) <= FRESH_KURTOSIS[1]
        and FRESH_STD[0] <= s.std <= FRESH_STD[1]
    )


@dataclass
class Screen:
    verdict: str
    reasons: list[str] = field(default_factory=list)
    n_matrices: int = 0
    n_fresh_like: int = 0
    fresh_fraction: float | None = None


def screen_head(stats: Iterable[TensorStat]) -> Screen:
    """Apply the three known-broken-head signatures to the head's tensor statistics."""
    stats = list(stats)
    reasons: list[str] = []
    if not stats:
        return Screen("FAIL", ["no head tensors to screen"])
    for s in stats:
        if s.n_nonfinite:
            reasons.append(f"non-finite values in {s.name}: {s.n_nonfinite} of {s.n_values}")
    for s in stats:
        if s.kind != "norm":
            continue
        if s.median is None or not (NORM_MEDIAN_RANGE[0] <= s.median <= NORM_MEDIAN_RANGE[1]):
            reasons.append(
                f"norm {s.name}: median {s.median} outside [{NORM_MEDIAN_RANGE[0]}, "
                f"{NORM_MEDIAN_RANGE[1]}]"
            )
        if s.abs_max is not None and s.abs_max > NORM_MAX_ABS:
            reasons.append(f"norm {s.name}: |value| up to {s.abs_max:.3g} > {NORM_MAX_ABS:g}")
    mats = [s for s in stats if s.kind == "matrix"]
    fresh = [s for s in mats if is_fresh_init(s)]
    frac = len(fresh) / len(mats) if mats else None
    if mats and frac is not None and frac >= FRESH_FRACTION:
        reasons.append(
            f"{len(fresh)} of {len(mats)} weight matrices ({frac:.0%}) have kurtosis within "
            f"{FRESH_KURTOSIS[0]} +/- {FRESH_KURTOSIS[1]} and std within "
            f"{FRESH_STD[0]}-{FRESH_STD[1]}: the signature of a fresh random initialisation"
        )
    return Screen("FAIL" if reasons else "PASS", reasons, len(mats), len(fresh), frac)


# ---- chat template -------------------------------------------------------------------------


def normalize_template(text: str) -> str:
    """Collapse every run of whitespace to one space and strip (the recorded normalisation)."""
    return re.sub(r"\s+", " ", text).strip()


def _clip(words: Sequence[str], limit: int = 240) -> str:
    text = " ".join(words)
    return text if len(text) <= limit else text[:limit] + f"... [{len(text)} chars]"


def compare_templates(embedded: str | None, official: str, max_changes: int = 40) -> dict:
    """Compare after whitespace normalisation. ``diff`` lists each change on one line:
    ``<op> official[i:j] -> embedded[k:l]: '<official words>' => '<embedded words>'`` (word
    positions in the normalised text, long runs clipped)."""
    if embedded is None:
        return {"embedded": False, "identical": False, "diff": ["no embedded chat template"]}
    a, b = normalize_template(official).split(" "), normalize_template(embedded).split(" ")
    if a == b:
        return {"embedded": True, "identical": True, "diff": []}
    ops = [
        o
        for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
        if o[0] != "equal"
    ]
    lines = [
        f"{tag} official[{i1}:{i2}] -> embedded[{j1}:{j2}]: "
        f"'{_clip(a[i1:i2])}' => '{_clip(b[j1:j2])}'"
        for tag, i1, i2, j1, j2 in ops[:max_changes]
    ]
    return {
        "embedded": True,
        "identical": False,
        "n_changes": len(ops),
        "words_official": len(a),
        "words_embedded": len(b),
        "diff": lines,
        "diff_truncated": len(ops) > max_changes,
    }


# ---- GGUF access ---------------------------------------------------------------------------


class GgufTensorSource:
    """Row source over one tensor of a GGUF file, dequantized on demand."""

    def __init__(self, tensor):
        from gguf import GGMLQuantizationType as Q

        self.t = tensor
        self.qtype = tensor.tensor_type
        self.shape = [int(x) for x in tensor.shape]  # ne0 first
        self.row_len = self.shape[0]
        self.n_rows = int(np.prod(self.shape[1:], dtype=np.int64)) if len(self.shape) > 1 else 1
        self._is_float = self.qtype in (Q.F32, Q.F16)

    def read(self, start: int, stop: int) -> np.ndarray:
        from gguf import quants

        data = np.asarray(self.t.data)
        data = data.reshape(self.n_rows, -1)[start:stop]
        if self._is_float:
            return np.asarray(data, dtype=np.float32).reshape(stop - start, self.row_len)
        out = quants.dequantize(np.ascontiguousarray(data), self.qtype)
        return np.asarray(out, dtype=np.float32).reshape(stop - start, self.row_len)


def _field_value(reader, key: str):
    f = reader.get_field(key)
    return None if f is None else f.contents()


def read_metadata(reader) -> dict:
    arch = _field_value(reader, "general.architecture")
    meta: dict = {"architecture": arch}
    meta["block_count"] = _field_value(reader, f"{arch}.block_count")
    nextn_keys = [k for k in reader.fields if k.endswith("nextn_predict_layers")]
    meta["nextn_predict_layers_key"] = nextn_keys[0] if nextn_keys else None
    meta["nextn_predict_layers"] = _field_value(reader, nextn_keys[0]) if nextn_keys else None
    meta["expert_keys"] = {
        k: _field_value(reader, k) for k in reader.fields if "expert" in k and k.startswith(arch)
    }
    meta["file_type"] = _field_value(reader, "general.file_type")
    meta["chat_template_embedded"] = reader.get_field("tokenizer.chat_template") is not None
    for k in ("full_attention_interval",):
        meta[k] = _field_value(reader, f"{arch}.{k}")
    return meta


def _block_tensors(reader, block: int) -> dict[str, object]:
    prefix = f"blk.{block}."
    return {t.name[len(prefix) :]: t for t in reader.tensors if t.name.startswith(prefix)}


def stats_for_block(reader, block: int, progress=None) -> list[TensorStat]:
    out = []
    for _, t in sorted(_block_tensors(reader, block).items()):
        src = GgufTensorSource(t)
        kind = classify(t.name, len(src.shape))
        if progress:
            progress(f"  {t.name} {src.shape} {src.qtype.name}")
        out.append(compute_stat(t.name, kind, src.shape, src.qtype.name, src))
    return out


# ---- report --------------------------------------------------------------------------------


def _f(x: float | None, spec: str) -> str:
    return "-" if x is None else format(x, spec)


def comparison_rows(head: list[TensorStat], ref: list[TensorStat], hb: int, rb: int) -> list[dict]:
    rmap = {s.name[len(f"blk.{rb}.") :]: s for s in ref}
    rows = []
    for s in head:
        suffix = s.name[len(f"blk.{hb}.") :]
        r = rmap.get(suffix)
        rows.append({
            "tensor": suffix, "kind": s.kind, "shape": s.shape, "type": s.qtype,
            "head": {k: getattr(s, k) for k in ("mean", "std", "kurtosis", "max_over_sigma",
                                                "median", "abs_max", "n_nonfinite")},
            "ref": None if r is None else {k: getattr(r, k) for k in (
                "mean", "std", "kurtosis", "max_over_sigma", "median", "abs_max", "n_nonfinite")},
        })  # fmt: skip
    return rows


def _cells(d: dict, kind: str) -> str:
    if kind == "norm":
        return f"median {_f(d.get('median'), '.4g'):>8} absmax {_f(d.get('abs_max'), '.4g'):>8}"
    return (
        f"std {_f(d.get('std'), '.5f'):>8} kurt {_f(d.get('kurtosis'), '.2f'):>7}"
        f" max/sigma {_f(d.get('max_over_sigma'), '.1f'):>6}"
    )


def render_table(rows: list[dict], hb: int, rb: int) -> str:
    """Plain-text table: each head tensor next to the same tensor of the reference trunk layer."""
    lines = [f"{'tensor':32} {'kind':6} {'type':5} | blk.{hb} (head) | blk.{rb} (trunk reference)"]
    lines.append("-" * 130)
    for r in rows:
        head_cells = _cells(r["head"], r["kind"])
        ref_cells = _cells(r["ref"], r["kind"]) if r["ref"] else "(not in the reference layer)"
        lines.append(f"{r['tensor']:32} {r['kind']:6} {r['type']:5} | {head_cells} | {ref_cells}")
    return "\n".join(lines)


def check_gguf(path: str | Path, template_path: str | Path, progress=print) -> dict:
    from gguf import GGUFReader

    reader = GGUFReader(str(path))
    meta = read_metadata(reader)
    n_layers = meta["block_count"]
    n_head = meta["nextn_predict_layers"] or 0
    result: dict = {"file": Path(path).name, "file_size_bytes": Path(path).stat().st_size,
                    "metadata": meta, "limits": {"pass_means": PASS_MEANS,
                                                 "layout_means": LAYOUT_MEANS}}  # fmt: skip
    reasons: list[str] = []

    # chat template
    official = Path(template_path).read_text(encoding="utf-8")
    emb_field = reader.get_field("tokenizer.chat_template")
    embedded = None if emb_field is None else str(emb_field.contents())
    result["chat_template"] = compare_templates(embedded, official)

    if not n_head or not n_layers:
        reasons.append("metadata has no nextn_predict_layers / block_count: no MTP head declared")
        result.update(verdict="FAIL", reasons=reasons)
        return result
    head_block, ref_block = n_layers - n_head, n_layers - n_head - 1
    head_t = _block_tensors(reader, head_block)
    ref_t = _block_tensors(reader, ref_block)
    result["head_block"], result["reference_block"] = head_block, ref_block

    # layout
    layout = {
        "tensors": [
            {"name": f"blk.{head_block}.{k}", "shape": [int(x) for x in t.shape],
             "type": t.tensor_type.name, "n_values": int(t.n_elements)}
            for k, t in sorted(head_t.items())
        ],
        "count": len(head_t),
        "reference_count": len(ref_t),
        "missing_vs_reference": sorted(set(ref_t) - set(head_t)),
        "extra_vs_reference": sorted(set(head_t) - set(ref_t)),
        "missing_nextn": [s for s in NEXTN_SUFFIXES if s not in head_t],
    }  # fmt: skip
    layout["present_and_complete"] = bool(head_t) and not (
        layout["missing_vs_reference"] or layout["missing_nextn"]
    )
    result["layout"] = layout
    if not head_t:
        reasons.append(f"no blk.{head_block}.* tensors: MTP head absent")
        result.update(verdict="FAIL", reasons=reasons)
        return result
    if not layout["present_and_complete"]:
        reasons.append(
            f"head layout incomplete: missing vs reference {layout['missing_vs_reference']}, "
            f"missing nextn {layout['missing_nextn']}"
        )

    # screen
    progress(f"screening blk.{head_block} (head)")
    head_stats = stats_for_block(reader, head_block, progress)
    progress(f"screening blk.{ref_block} (reference trunk layer)")
    ref_stats = stats_for_block(reader, ref_block, progress)
    scr = screen_head(head_stats)
    reasons += scr.reasons
    result["screen"] = asdict(scr)
    result["reference_screen"] = asdict(screen_head(ref_stats))
    result["head_stats"] = [asdict(s) for s in head_stats]
    result["reference_stats"] = [asdict(s) for s in ref_stats]
    rows = comparison_rows(head_stats, ref_stats, head_block, ref_block)
    result["table"] = rows
    result["table_text"] = render_table(rows, head_block, ref_block)
    result["thresholds"] = {
        "norm_median_range": NORM_MEDIAN_RANGE, "norm_max_abs": NORM_MAX_ABS,
        "fresh_kurtosis": FRESH_KURTOSIS, "fresh_std": FRESH_STD,
        "fresh_fraction": FRESH_FRACTION, "max_sample_values": MAX_SAMPLE_VALUES,
    }  # fmt: skip
    result.update(verdict="FAIL" if reasons else "PASS", reasons=reasons)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    from smallpc.config import load_model, repo_root

    ap = argparse.ArgumentParser(
        prog="python -m smallpc.gguf_check", description="Screen a GGUF's MTP head."
    )
    ap.add_argument("gguf")
    ap.add_argument("--template", help="official chat template (default: configs/model.toml)")
    ap.add_argument("--out", help="default: data/health/model-check.json")
    args = ap.parse_args(argv)
    root = repo_root()
    template = args.template or root / load_model().chat_template.file
    out = Path(args.out) if args.out else root / "data/health/model-check.json"
    res = check_gguf(args.gguf, template, progress=lambda m: print(m, file=sys.stderr, flush=True))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + "\n")
    m = res["metadata"]
    print(f"architecture {m['architecture']}, block_count {m['block_count']}, "
          f"{m['nextn_predict_layers_key']} = {m['nextn_predict_layers']}, "
          f"experts {m['expert_keys']}")  # fmt: skip
    ct = res["chat_template"]
    print(f"chat template: embedded={ct['embedded']} identical={ct['identical']}")
    for line in ct["diff"]:
        print("  " + line)
    if "layout" in res:
        lay = res["layout"]
        print(f"head tensors (blk.{res['head_block']}.*): {lay['count']}; "
              f"present_and_complete={lay['present_and_complete']}")  # fmt: skip
        print(LAYOUT_MEANS)
    if "table_text" in res:
        print(res["table_text"])
        sc = res["screen"]
        print(f"matrices fresh-init-like: {sc['n_fresh_like']} of {sc['n_matrices']}")
    for r in res["reasons"]:
        print("FAIL reason:", r)
    print(f"VERDICT: {res['verdict']}")
    print(PASS_MEANS)
    print(f"written: {out}")
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
