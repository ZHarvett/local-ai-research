<!-- DRAFT — NOT FILED. Prepared 2026-11-15 by task T-011 for review before anything is posted upstream. -->
<!-- sources: data/sanity/stage2-all.json, data/sanity/stage2-32K.json, data/sanity/diagnostic-32K.json, data/sanity/diagnostic-32K-repeat.json, data/sanity/diagnostic-32K-inspect.json, data/sanity/diagnostic-64K.json, data/env/build-info.json, src/smallpc/sanity_runner.py, docs/plans/step-0-baseline.md -->

# Issue draft for ggml-org/llama.cpp — MTP draft length 2 repeated phrase

**Suggested title:** MTP draft length 2: deterministic repeated 8-gram in greedy output on a MoE model (b12208, CUDA)

**Status:** draft, not filed. Filing is a later, gated step (T-015/T-016 handle publication);
this file only collects the evidence and a proposed text.

## Summary

With MTP (`--spec-type draft-mtp`) at draft length 2, greedy continuations of one of three
fixed sanity prompts deterministically contain an 8-token phrase that repeats 8 times, while
the MTP-off reference repeats its most common 8-gram only 1 to 2 times. The same prompt fails
on four configurations (two expert placements, both KV cache types, 32K and 64K context).
Draft length 1 is bit-identical to MTP off on all three prompts, and draft length 3 passes the
same check. It is unresolved whether this is a fault in the speculative path at draft length 2
or an artifact of our repetition threshold (see below); we excluded draft length 2 from our
tuned configurations and report it here in case it is a real defect.

## Environment

- Build: llama.cpp tag b12208, commit `57d04820dfef7a3519aac276d018a6fd71251895`, built
  2026-11-08 with `-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_NATIVE=ON
  -DCMAKE_BUILD_TYPE=Release` (full flags and tool versions: `data/env/build-info.json`;
  CUDA 13.4, gcc 16.2.1).
- GPU: NVIDIA RTX 5060 Ti, 16 GB (sm_120). 32 GB host RAM, zram swap.
- Model: Ornith-1.5-35B-A3B, Q4 GGUF, MoE with MTP draft heads; sparse experts partly on
  CPU (`--cpu-moe` with a VRAM expert cache) or `--fit` placement, as below.
- Server: single slot (`-np 1`), flash attention on, greedy decoding (temperature 0, top_k 1),
  512-token continuations of 2048-token prompts, seed 20261110
  (`src/smallpc/sanity_runner.py`).

## Observed behaviour

The sanity check compares greedy 512-token outputs against the plain `--fit` MTP-off cell at
the same context. The failing rule (declared before measurement, plan v1.6 section 5.6): a
prompt fails if some 8-gram repeats 8 or more times (non-overlapping) while the reference's
maximum is below 8.

Four configurations fail, all on the same prompt (`sanity-v5-2048-r0`); the other two prompts
pass on every cell:

| Cell | Placement | Context | KV | Max 8-gram repeat (candidate / reference) |
|---|---|---|---|---|
| s2a-P6-32K-b4096-mtp2 | P6 (CPU experts + VRAM expert cache) | 32768 | q8_0 | 8 / 2 |
| s2a2-P2-32K-b4096-mtp2 | P2 (`--fit`) | 32768 | q8_0 | 8 / 2 |
| s2b-P6-32K-b4096-mtp2-kvf16 | P6 | 32768 | f16 | 8 / 2 |
| s2a-P6-64K-b4096-mtp2 | P6 | 65536 | q8_0 | 8 / 1 |

Details (counts and token indices only; our records deliberately store no generated text):

- The repeated 8-gram occurs 8 times, clustered in the second half of the 512-token output.
  For the two 32K cells inspected, start indices are 324–450 and 359–497, with gaps of
  13–24 tokens between occurrences (`data/sanity/diagnostic-32K-inspect.json`).
- First divergence from the reference: token 27 on the 32K cells, token 93 on the 64K cell.
  The repetition itself only starts after token ~320.
- The output is otherwise healthy: full 512 tokens, longest single-token run 1, distinct
  4-gram ratio 0.84 against the reference's 0.92 on the failing 32K prompt <!-- derived: rounded from distinct_4gram_ratio 0.8408644400785854 / 0.9174852652259332 in data/sanity/stage2-32K.json -->
  (0.81 against 0.95 on the 64K prompt). <!-- derived: rounded from distinct_4gram_ratio 0.8094302554027505 / 0.9489194499017681 in data/sanity/diagnostic-64K.json -->
- Deterministic across separate server launches: the failing prompt's output token hash is
  identical in the original run and a repeat run on a fresh server
  (`53918080508649e89e7b3f149287b1f025b18e74687b9d4de29b8435b8f47b65`,
  `data/sanity/stage2-32K.json` vs `data/sanity/diagnostic-32K-repeat.json`).

Contrast, same check and prompts (`data/sanity/stage2-all.json`):

- Draft length 1: output token hashes bit-identical to MTP off on all three prompts
  (s2a-P6-32K-b4096-mtp0 vs -mtp1), and passes on every cell.
- Draft length 3: passes (s2a-P6-32K-b4096-mtp3), with different but non-repetitive output.
- MTP off: passes on every cell.

## Why it might be a threshold artifact

The candidate's maximum repeat count is exactly the threshold (8), the repetition is a single
clustered phrase rather than a degenerate loop (longest run 1, 4-gram diversity only mildly
reduced), and the prompts are built from repository source text, where list-like or code-like
structure can legitimately repeat short phrases. Draft-length-2 numerics may simply steer the
continuation into such a structure earlier than the reference. On the other hand, the effect
is deterministic, specific to draft length 2, and appears across placements, KV types and two
context sizes, which is also consistent with a real fault in the draft-2 acceptance path.
We have not distinguished the two; that is the question for upstream.

## Reproduction (in the baseline repo)

The exact prompts are deterministic 2048-token workloads built from repository source
sections (`src/smallpc/workloads/`); the runner is `src/smallpc/sanity_runner.py`. With the
model in place (`configs/model.toml`) and the pinned build installed:

```bash
# one failing cell; the other three resolved configs are listed under Evidence
scripts/run-detached.sh --gpu sanity-draft2 -- uv run --frozen python -m smallpc.sanity run \
    --cells data/raw/s2a-32K/resolved/s2a-P6-32K-b4096-mtp2.toml \
    --reference P1-32K-b2048 --out data/sanity/draft2-repro.json
```

(Command form: `docs/runbook-stage3.md`, sanity section; cell-name form in
`docs/runbook-stage2.md`. The runner starts and stops each server under the GPU lock.)
Expected: `result: fail`, `failed_prompts: ["sanity-v5-2048-r0"]`, reason
"an 8-gram repeats 8 times (reference 2)".

## Evidence paths (repo-relative)

- `data/sanity/stage2-all.json` — all cells, results, per-prompt token hashes
- `data/sanity/stage2-32K.json` — per-prompt metrics and thresholds for the 32K cells
- `data/sanity/diagnostic-32K.json`, `data/sanity/diagnostic-64K.json` — first diagnostic runs
- `data/sanity/diagnostic-32K-repeat.json` — fresh-server repeat (determinism)
- `data/sanity/diagnostic-32K-inspect.json` — repeat counts, start indices, gaps
- `data/raw/s2a-32K/resolved/s2a-P6-32K-b4096-mtp2.toml`,
  `data/raw/s2a2-32K/resolved/s2a2-P2-32K-b4096-mtp2.toml`,
  `data/raw/s2b-32K/resolved/s2b-P6-32K-b4096-mtp2-kvf16.toml`,
  `data/raw/s2a-64K/resolved/s2a-P6-64K-b4096-mtp2.toml` — the exact server configs
- `data/env/build-info.json` — build tag, commit, flags, tool versions, binary hashes

## Questions for the maintainers

1. Is a draft-length-specific repetition like this a known failure mode of the MTP
   acceptance path (e.g. a numerics edge case at exactly 2 draft tokens)?
2. If not, is there interest in the token-level evidence (we can regenerate the output text;
   our committed records keep only counts, indices and hashes)?