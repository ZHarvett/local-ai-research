"""Statistics of step plan section 5.5.

``summarize(values)`` gives mean, n, min, max, a 95% percentile-bootstrap CI (10,000 resamples,
fixed seed) and a 95% t-interval. With n = 5 bootstrap intervals come out too narrow, so the wider
of the two is reported as the CI to use ("ci"); both are kept.

WP10 adds the paired comparisons: ``paired_difference`` (per-repetition differences, same two
intervals) and ``paired_ratio`` (geometric mean of per-repetition ratios; since plan v1.4 the wider
of the bootstrap CI and a t-interval on the log ratios, back-transformed), and
``simulate_coverage``, which measures how often each interval covers the true mean on simulated
data (see ``tests/test_stats_coverage.py`` and ``docs/decisions.md``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

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


# ------------------------------------------------------------------------------ paired data


def _paired_values(a: Any, b: Any) -> tuple[list[Any], list[float], list[float]]:
    """Match two series on their repetition keys.

    ``a`` and ``b`` are either mappings (key -> value; the keys present in both are used, in sorted
    order) or equally long sequences (matched by position). Returns (keys, a-values, b-values).
    """
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        keys = sorted(set(a) & set(b), key=repr)
        return keys, [float(a[k]) for k in keys], [float(b[k]) for k in keys]
    if isinstance(a, Mapping) or isinstance(b, Mapping):
        raise TypeError("pass two mappings (matched on keys) or two sequences, not one of each")
    xa, xb = [float(v) for v in a], [float(v) for v in b]
    if len(xa) != len(xb):
        raise ValueError(f"unpaired sequences of different length ({len(xa)} and {len(xb)})")
    return list(range(len(xa))), xa, xb


def paired_difference(a: Any, b: Any) -> dict:
    """Per-repetition differences ``a - b`` on matching repetition keys.

    Returns ``n``, ``mean``, the ``keys`` and ``differences`` used, both intervals and ``ci`` (the
    wider of the bootstrap and the t interval, as ``summarize``), and ``excludes_zero``: True or
    False when a CI exists (n >= 2), None otherwise. With no matching key ``n`` is 0 and
    everything else is None.
    """
    keys, xa, xb = _paired_values(a, b)
    diffs = [p - q for p, q in zip(xa, xb, strict=True)]
    if not diffs:
        return {
            "n": 0, "mean": None, "keys": [], "differences": [], "bootstrap_ci": None,
            "t_ci": None, "ci": None, "ci_method": "unavailable (no matching repetitions)",
            "excludes_zero": None,
        }  # fmt: skip
    s = summarize(diffs)
    ci = s["ci"]
    return {
        "n": s["n"],
        "mean": s["mean"],
        "keys": keys,
        "differences": diffs,
        "bootstrap_ci": s["bootstrap_ci"],
        "t_ci": s["t_ci"],
        "ci": ci,
        "ci_method": s["ci_method"],
        "excludes_zero": None if ci is None else (ci[0] > 0 or ci[1] < 0),
    }


def paired_ratio(a: Any, b: Any) -> dict:
    """Geometric mean of the per-repetition ratios ``a / b`` with a 95% interval (plan v1.4, 5.5).

    The interval is the wider of two: the percentile-bootstrap CI of the geometric mean (10,000
    resamples, fixed seed) and a t-interval on the log ratios, back-transformed with exp. Both
    are returned (``bootstrap_ci``, ``t_ci``) and ``ci_method`` says which one is ``ci``. The ratios
    must be positive: zero or negative input raises ``ValueError`` naming the offending side. The
    intervals are None for n < 2.
    """
    keys, xa, xb = _paired_values(a, b)
    for name, vals in (("a", xa), ("b", xb)):
        bad = [v for v in vals if not v > 0]  # also catches NaN
        if bad:
            raise ValueError(f"paired_ratio needs positive values; {name} has {bad[0]!r}")
    logs = [math.log(p / q) for p, q in zip(xa, xb, strict=True)]
    if not logs:
        return {"n": 0, "geomean": None, "keys": [], "ratios": [], "ci": None,
                "bootstrap_ci": None, "t_ci": None,
                "ci_method": "unavailable (no matching repetitions)"}  # fmt: skip
    out: dict = {
        "n": len(logs),
        "geomean": math.exp(sum(logs) / len(logs)),
        "keys": keys,
        "ratios": [math.exp(v) for v in logs],
        "bootstrap_ci": None,
        "t_ci": None,
        "ci": None,
        "ci_method": "unavailable (n < 2)",
    }
    boot, tci = bootstrap_ci(logs), t_interval(logs)
    if boot is None or tci is None:
        return out
    out["bootstrap_ci"] = [math.exp(boot[0]), math.exp(boot[1])]
    out["t_ci"] = [math.exp(tci[0]), math.exp(tci[1])]
    # the wider one as reported, i.e. on the ratio scale
    t_w = out["t_ci"][1] - out["t_ci"][0]
    b_w = out["bootstrap_ci"][1] - out["bootstrap_ci"][0]
    if t_w >= b_w:
        out["ci"], out["ci_method"] = out["t_ci"], "t"
    else:
        out["ci"], out["ci_method"] = out["bootstrap_ci"], "bootstrap"
    return out


# ------------------------------------------------------------------------- coverage simulation

# name -> what it models. The skewed ones are stress cases: step-0 timing data has a spread of about
# 1 to 2% between repetitions, where lognormal(sigma 0.02) is indistinguishable from normal.
COVERAGE_DISTRIBUTIONS = {
    "normal": "symmetric",
    "lognormal-0.1": "mild right skew (skewness 0.30, CV 10%)",
    "lognormal-0.5": "strong right skew (skewness 1.75, CV 53%)",
    "exponential": "very strong right skew (skewness 2)",
}


def _draw(dist: str, rng: np.random.Generator, shape: tuple[int, int]) -> tuple[np.ndarray, float]:
    """Samples and the true mean of the distribution."""
    if dist == "normal":
        return rng.normal(10.0, 1.0, size=shape), 10.0
    if dist.startswith("lognormal-"):
        sigma = float(dist.split("-", 1)[1])
        return rng.lognormal(0.0, sigma, size=shape), math.exp(sigma**2 / 2)
    if dist == "exponential":
        return rng.exponential(1.0, size=shape), 1.0
    raise ValueError(f"unknown distribution {dist!r}")


def simulate_coverage(
    n: int, dist: str, experiments: int, resamples: int = 1000, seed: int = 1, chunk: int = 250
) -> dict:
    """How often each 95% interval of the mean covers the true mean.

    ``experiments`` independent samples of size ``n`` are drawn from ``dist``; for each, the
    percentile-bootstrap interval (``resamples`` resamples), the t interval and the wider of the two
    (what ``summarize`` reports) are computed with the same formulas as ``summarize``, vectorised
    over experiments. Returns the coverage fractions and the mean widths.
    """
    rng = np.random.default_rng(seed)
    hit = {"bootstrap": 0, "t": 0, "wider": 0}
    boot_wider = 0
    width = {"bootstrap": 0.0, "t": 0.0, "wider": 0.0}
    done = 0
    while done < experiments:
        e = min(chunk, experiments - done)
        x, truth = _draw(dist, rng, (e, n))
        idx = rng.integers(0, n, size=(e, resamples, n))
        means = np.take_along_axis(x[:, None, :], idx, axis=2).mean(axis=2)
        lo_b, hi_b = np.percentile(means, [2.5, 97.5], axis=1)
        m = x.mean(axis=1)
        half = t_critical(n - 1) * x.std(axis=1, ddof=1) / math.sqrt(n)
        lo_t, hi_t = m - half, m + half
        use_t = (hi_t - lo_t) >= (hi_b - lo_b)
        boot_wider += int((~use_t).sum())
        lo_w, hi_w = np.where(use_t, lo_t, lo_b), np.where(use_t, hi_t, hi_b)
        for name, lo, hi in (("bootstrap", lo_b, hi_b), ("t", lo_t, hi_t), ("wider", lo_w, hi_w)):
            hit[name] += int(((lo <= truth) & (truth <= hi)).sum())
            width[name] += float((hi - lo).sum())
        done += e
    return {
        "n": n,
        "distribution": dist,
        "experiments": experiments,
        "resamples": resamples,
        "seed": seed,
        "coverage": {k: v / experiments for k, v in hit.items()},
        "mean_width": {k: v / experiments for k, v in width.items()},
        "bootstrap_was_wider_fraction": boot_wider / experiments,
    }


def simulate_ratio_coverage(
    n: int, sigma: float, experiments: int, resamples: int = 1000, seed: int = 1,
    true_ratio: float = 0.8, chunk: int = 250,
) -> dict:  # fmt: skip
    """How often the reported paired-ratio interval covers the true geometric-mean ratio.

    Each experiment draws ``n`` log ratios ~ Normal(log(true_ratio), sigma) (log-normal noise on the
    ratios), forms the percentile-bootstrap interval of their mean (``resamples`` resamples) and the
    t interval, and takes the wider, exactly as ``paired_ratio`` does on the log scale. Coverage is
    whether ``log(true_ratio)`` lies inside. Vectorised like ``simulate_coverage``.
    """
    rng = np.random.default_rng(seed)
    mu = math.log(true_ratio)
    hit = {"bootstrap": 0, "t": 0, "wider": 0}
    boot_wider = done = 0
    while done < experiments:
        e = min(chunk, experiments - done)
        x = rng.normal(mu, sigma, size=(e, n))
        idx = rng.integers(0, n, size=(e, resamples, n))
        means = np.take_along_axis(x[:, None, :], idx, axis=2).mean(axis=2)
        lo_b, hi_b = np.percentile(means, [2.5, 97.5], axis=1)
        m_ = x.mean(axis=1)
        half = t_critical(n - 1) * x.std(axis=1, ddof=1) / math.sqrt(n)
        lo_t, hi_t = m_ - half, m_ + half
        use_t = (hi_t - lo_t) >= (hi_b - lo_b)
        boot_wider += int((~use_t).sum())
        lo_w, hi_w = np.where(use_t, lo_t, lo_b), np.where(use_t, hi_t, hi_b)
        for name, lo, hi in (("bootstrap", lo_b, hi_b), ("t", lo_t, hi_t), ("wider", lo_w, hi_w)):
            hit[name] += int(((lo <= mu) & (mu <= hi)).sum())
        done += e
    return {
        "n": n, "sigma": sigma, "true_ratio": true_ratio, "experiments": experiments,
        "resamples": resamples, "seed": seed,
        "coverage": {k: v / experiments for k, v in hit.items()},
        "bootstrap_was_wider_fraction": boot_wider / experiments,
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    """``python -m smallpc.stats coverage [--experiments N]``: the coverage table of section 5.5."""
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="python -m smallpc.stats")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("coverage", help="coverage of the bootstrap, t and wider intervals")
    c.add_argument("--experiments", type=int, default=20000)
    c.add_argument("--resamples", type=int, default=1000)
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--json", action="store_true")
    c.add_argument("--ratio", action="store_true", help="paired-ratio coverage (plan v1.4, 5.5)")
    a = ap.parse_args(argv)
    if a.ratio:
        rows = [
            simulate_ratio_coverage(n, sg, a.experiments, a.resamples, a.seed)
            for n in (5, 10)
            for sg in (0.05, 0.2)
        ]
        if a.json:
            print(json.dumps(rows, indent=1))
            return 0
        print(f"paired ratios: {a.experiments} experiments per row, {a.resamples} resamples")
        print("| n | sigma (log ratio) | bootstrap | t | reported (wider) | bootstrap was wider |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            cv = r["coverage"]
            print(
                f"| {r['n']} | {r['sigma']} | {cv['bootstrap']:.1%} | {cv['t']:.1%} "
                f"| {cv['wider']:.1%} | {r['bootstrap_was_wider_fraction']:.1%} |"
            )
        return 0
    rows = [
        simulate_coverage(n, d, a.experiments, a.resamples, a.seed)
        for d in COVERAGE_DISTRIBUTIONS
        for n in (5, 10)
    ]
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    print(f"{a.experiments} experiments per row, {a.resamples} bootstrap resamples, seed {a.seed}")
    print("| distribution | n | bootstrap | t | reported (wider) | bootstrap was wider |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        cv = r["coverage"]
        print(
            f"| {r['distribution']} | {r['n']} | {cv['bootstrap']:.1%} | {cv['t']:.1%} "
            f"| {cv['wider']:.1%} | {r['bootstrap_was_wider_fraction']:.1%} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
