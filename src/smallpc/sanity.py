"""Output sanity check of step plan section 5.6 (thresholds: docs/decisions.md, WP10 decision 5).

Pure functions over generated token ids; nothing here talks to a server or the GPU. The inputs are
the token ids a candidate generated for a prompt and the token ids the reference (the plain
``--fit`` cell at the same context) generated for the same prompt, greedy, 512 tokens.

Computed per output: the length; the distinct 4-gram ratio (distinct 4-grams / all 4-grams); the
longest run of one repeated token; the highest repeat count of any 8-gram (non-overlapping
occurrences). A prompt FAILS if any of:

* length < min(100, half the reference length);
* distinct 4-gram ratio < half the reference's;
* the longest repeated-token run is 16 or more while the reference's is below 16;
* some 8-gram repeats 8 or more times while the reference's maximum is below 8.

A candidate passes if none of its prompts fails. The index of the first divergence from the
reference is information only: different placements and KV types can legitimately diverge.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

MIN_LENGTH = 100  # absolute floor of the length rule ...
LENGTH_FRACTION = 0.5  # ... and the fraction of the reference length, whichever is lower
DISTINCT_4GRAM_FRACTION = 0.5  # of the reference's distinct 4-gram ratio
RUN_LIMIT = 16  # one token repeated this many times in a row
NGRAM_REPEAT_LIMIT = 8  # one 8-gram occurring this many times
NGRAM_N = 8


def distinct_ngram_ratio(tokens: Sequence[int], n: int = 4) -> float:
    """Distinct n-grams divided by all n-grams; 0.0 if the output is shorter than n."""
    total = len(tokens) - n + 1
    if total <= 0:
        return 0.0
    return len({tuple(tokens[i : i + n]) for i in range(total)}) / total


def longest_run(tokens: Sequence[int]) -> int:
    """Length of the longest run of one repeated token (0 for no tokens)."""
    best = cur = 0
    prev = None
    for t in tokens:
        cur = cur + 1 if t == prev else 1
        prev = t
        best = max(best, cur)
    return best


def max_ngram_repeat(tokens: Sequence[int], n: int = NGRAM_N) -> int:
    """The highest number of times any n-gram occurs, counting non-overlapping occurrences only
    (greedy from the left), so a run of 15 identical tokens is one repeat of its 8-gram, not
    eight; 0 if the output is shorter than n."""
    total = len(tokens) - n + 1
    if total <= 0:
        return 0
    count: Counter = Counter()
    next_free: dict[tuple, int] = {}
    for i in range(total):
        g = tuple(tokens[i : i + n])
        if i >= next_free.get(g, 0):
            count[g] += 1
            next_free[g] = i + n
    return max(count.values())


def first_divergence(candidate: Sequence[int], reference: Sequence[int]) -> int | None:
    """Index of the first token that differs; the shorter length if one output is a prefix of the
    other; None if they are identical."""
    for i, (a, b) in enumerate(zip(candidate, reference, strict=False)):
        if a != b:
            return i
    return None if len(candidate) == len(reference) else min(len(candidate), len(reference))


def metrics(tokens: Sequence[int]) -> dict:
    return {
        "length": len(tokens),
        "distinct_4gram_ratio": distinct_ngram_ratio(tokens, 4),
        "longest_run": longest_run(tokens),
        "max_8gram_repeat": max_ngram_repeat(tokens, NGRAM_N),
    }


def check_prompt(candidate: Sequence[int], reference: Sequence[int]) -> dict:
    """One prompt: ``ok``, the ``reasons`` it failed (empty if ok), both metric sets and the
    first divergence (information only)."""
    c, r = metrics(candidate), metrics(reference)
    reasons = []
    floor = min(MIN_LENGTH, LENGTH_FRACTION * r["length"])
    if c["length"] < floor:
        reasons.append(f"length {c['length']} is below {floor:g}")
    if c["distinct_4gram_ratio"] < DISTINCT_4GRAM_FRACTION * r["distinct_4gram_ratio"]:
        reasons.append(
            f"distinct 4-gram ratio {c['distinct_4gram_ratio']:.3f} is below half the "
            f"reference's {r['distinct_4gram_ratio']:.3f}"
        )
    if c["longest_run"] >= RUN_LIMIT and r["longest_run"] < RUN_LIMIT:
        reasons.append(
            f"one token repeated {c['longest_run']} times in a row (reference {r['longest_run']})"
        )
    if c["max_8gram_repeat"] >= NGRAM_REPEAT_LIMIT and r["max_8gram_repeat"] < NGRAM_REPEAT_LIMIT:
        reasons.append(
            f"an 8-gram repeats {c['max_8gram_repeat']} times (reference {r['max_8gram_repeat']})"
        )
    return {
        "ok": not reasons,
        "reasons": reasons,
        "candidate": c,
        "reference": r,
        "first_divergence": first_divergence(candidate, reference),
    }


def check_candidate(
    candidate: Mapping[str, Sequence[int]], reference: Mapping[str, Sequence[int]]
) -> dict:
    """All prompts of one candidate (``{prompt_id: token_ids}``) against the reference's.

    ``result`` is ``pass`` (no prompt failed), ``fail`` (at least one did) or ``not run`` (no
    prompts, or a prompt of the reference is missing from the candidate).
    """
    missing = sorted(set(reference) - set(candidate))
    if not reference or missing:
        return {"result": "not run", "missing_prompts": missing, "prompts": {}}
    prompts = {pid: check_prompt(candidate[pid], reference[pid]) for pid in sorted(reference)}
    failed = [pid for pid, p in prompts.items() if not p["ok"]]
    return {
        "result": "fail" if failed else "pass",
        "failed_prompts": failed,
        "missing_prompts": [],
        "prompts": prompts,
    }
