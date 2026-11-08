"""Greedy-equivalence analysis: where do two greedy runs first diverge, and is it a near tie?

A divergence between two greedy runs (for example MTP off vs on, or never-saved vs restored) is
acceptable only if the model itself was nearly undecided at that position: the top-2 log-probability
gap is below ``NEAR_TIE_NATS`` (0.5 nats). Everything after the first divergence is ignored, because
the two contexts differ from there on and later tokens carry no information.

The input is the ``completion_probabilities`` list of a ``/completion`` response made with
``n_probs >= 2`` (and ``return_tokens``). Both documented formats are understood:

* default: each item has ``id``, ``logprob`` and ``top_logprobs`` (list of ``{id, logprob}``);
* ``post_sampling_probs``: ``prob`` and ``top_probs`` (a list of ``{id, prob, ...}``).

Pure functions, no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

NEAR_TIE_NATS = 0.5


def first_divergence(a: Sequence[int], b: Sequence[int]) -> int | None:
    """Index of the first position where the two token sequences differ, else None.

    If one sequence is a strict prefix of the other (one run stopped earlier), the divergence is at
    the length of the shorter one.
    """
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        if x != y:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def _logprob_of(entry: dict) -> float | None:
    if "logprob" in entry and entry["logprob"] is not None:
        return float(entry["logprob"])
    p = entry.get("prob")
    if p is None:
        return None
    return math.log(p) if p > 0 else -math.inf


def top2_gap(item: dict | None) -> float | None:
    """Top-1 minus top-2 log-probability (nats, >= 0) for one ``completion_probabilities`` item.

    Returns None when the item is missing or carries fewer than two alternatives.
    """
    if not item:
        return None
    alts = item.get("top_logprobs")
    if alts is None:
        alts = item.get("top_probs")
    if alts is None and "probs" in item:  # nested layout shown in the README
        return top2_gap(item["probs"][0]) if item["probs"] else None
    if not alts or len(alts) < 2:
        return None
    lps = sorted((lp for e in alts if (lp := _logprob_of(e)) is not None), reverse=True)
    if len(lps) < 2:
        return None
    return lps[0] - lps[1]


def gaps_of(completion_probabilities: Sequence[dict] | None) -> list[float | None]:
    return [top2_gap(item) for item in (completion_probabilities or [])]


@dataclass(frozen=True)
class Divergence:
    """Verdict for one pair of greedy runs."""

    identical: bool
    position: int | None = None
    gap_nats: float | None = None
    gap_source: str | None = None  # "run_b" | "run_a" | None
    verdict: str = "identical"  # identical | near_tie | real_divergence | unclassified
    reason: str = ""
    tokens: dict = field(default_factory=dict)  # token ids around the divergence, for the record

    @property
    def ok(self) -> bool:
        return self.verdict in ("identical", "near_tie")

    def as_dict(self) -> dict:
        return {
            "identical": self.identical,
            "position": self.position,
            "gap_nats": None if self.gap_nats is None else round(self.gap_nats, 4),
            "gap_source": self.gap_source,
            "verdict": self.verdict,
            "reason": self.reason,
            "tokens": self.tokens,
        }


def classify(
    tokens_a: Sequence[int],
    tokens_b: Sequence[int],
    gaps_a: Sequence[float | None] = (),
    gaps_b: Sequence[float | None] = (),
    threshold: float = NEAR_TIE_NATS,
    prefer: str = "b",
) -> Divergence:
    """Classify the first divergence of run A against run B.

    ``gaps_a`` / ``gaps_b`` are the per-position top-2 gaps of each run (``gaps_of``). The gap at
    the divergence position is taken from the preferred run (``prefer``: "b" by default, which is
    the MTP-on / restored run by convention), else from the other one; the source is recorded. The
    two runs share the same context up to the divergence, so either gap describes the same
    distribution up to numerical noise. A divergence with no usable gap is "unclassified", which
    does NOT count as a near tie (``ok`` is False).
    """
    pos = first_divergence(tokens_a, tokens_b)
    if pos is None:
        return Divergence(identical=True)
    around = {
        "a": list(tokens_a[pos : pos + 1]),
        "b": list(tokens_b[pos : pos + 1]),
        "a_len": len(tokens_a),
        "b_len": len(tokens_b),
    }
    order = [("run_b", gaps_b), ("run_a", gaps_a)]
    if prefer == "a":
        order.reverse()
    for source, gaps in order:
        if pos < len(gaps) and gaps[pos] is not None:
            gap = float(gaps[pos])
            if gap < threshold:
                return Divergence(
                    False, pos, gap, source, "near_tie", f"gap {gap:.4f} < {threshold}", around
                )
            return Divergence(
                False,
                pos,
                gap,
                source,
                "real_divergence",
                f"gap {gap:.4f} >= {threshold}: not a near tie",
                around,
            )
    return Divergence(
        False,
        pos,
        None,
        None,
        "unclassified",
        "no top-2 gap available at the divergence position in either run",
        around,
    )
