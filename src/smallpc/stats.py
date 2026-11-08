"""Statistics of step plan section 5.5 (WP6 subset; WP10 extends it).

``summarize(values)`` gives mean, n, min, max, a 95% percentile-bootstrap CI (10,000 resamples,
fixed seed) and a 95% t-interval. With n = 5 bootstrap intervals come out too narrow, so the wider
of the two is reported as the CI to use ("ci"); both are kept.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261108
CONFIDENCE = 0.95

# Two-sided 95% critical values of Student's t, df 1..30 (standard table).
T_CRIT_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}  # fmt: skip
T_CRIT_LARGE = 1.96  # df > 30


def t_critical(df: int) -> float:
    if df < 1:
        raise ValueError("df must be >= 1")
    return T_CRIT_95.get(df, T_CRIT_LARGE)


def bootstrap_ci(
    values: Sequence[float],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float] | None:
    """95% percentile bootstrap CI of the mean; None for n < 2."""
    x = np.asarray(values, dtype=float)
    if x.size < 2:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(resamples, x.size))
    means = x[idx].mean(axis=1)
    lo, hi = np.percentile(means, [100 * (1 - CONFIDENCE) / 2, 100 * (1 + CONFIDENCE) / 2])
    return float(lo), float(hi)


def t_interval(values: Sequence[float]) -> tuple[float, float] | None:
    """95% t-interval of the mean (sample standard deviation, df = n - 1); None for n < 2."""
    x = np.asarray(values, dtype=float)
    n = x.size
    if n < 2:
        return None
    half = t_critical(n - 1) * float(x.std(ddof=1)) / math.sqrt(n)
    m = float(x.mean())
    return m - half, m + half


def summarize(values: Sequence[float]) -> dict:
    """Mean, n, min, max, both intervals and ``ci``, the wider of the two.

    For n < 2 the CI is unavailable: ``ci`` and both intervals are None and ``ci_method`` says why.
    """
    x = [float(v) for v in values]
    if not x:
        raise ValueError("summarize() needs at least one value")
    out: dict = {
        "n": len(x),
        "mean": float(np.mean(x)),
        "min": min(x),
        "max": max(x),
        "bootstrap_ci": None,
        "t_ci": None,
        "ci": None,
        "ci_method": "unavailable (n < 2)",
    }
    boot, tci = bootstrap_ci(x), t_interval(x)
    if boot is None or tci is None:
        return out
    out["bootstrap_ci"], out["t_ci"] = list(boot), list(tci)
    if (tci[1] - tci[0]) >= (boot[1] - boot[0]):
        out["ci"], out["ci_method"] = list(tci), "t"
    else:
        out["ci"], out["ci_method"] = list(boot), "bootstrap"
    return out


def ci_halfwidth(s: dict) -> float | None:
    """Half the width of the CI in a summarize() result; None if unavailable."""
    return None if s["ci"] is None else (s["ci"][1] - s["ci"][0]) / 2
