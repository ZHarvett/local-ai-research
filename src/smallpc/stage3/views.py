"""The two views of the same units that the Stage 3 headline rule compares, and the paired ratios.

* the **clean view** is ``smallpc.analysis.analyse`` as it is (flagged units excluded);
* the **all-units view** is the same ``analysis._cell_entry`` run on the final units with the
  flag-based exclusion lifted: every final (non-superseded) unit that has all its requests counts.
  Nothing is recomputed here: the statistics are ``smallpc.analysis`` and ``smallpc.stats``.
"""

# ruff: noqa: E501
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .. import analysis, stats

# per-depth metrics whose paired ratio is reported (plan 5.4, "Reported figures")
RATIO_DEPTH_METRICS = ("pp_fresh", "tg", "ttft")
HIGHER_IS_BETTER = {"pp_fresh": True, "tg": True, "ttft": False, "t_turn_400": False,
                    "t_reread": False}  # fmt: skip


class Data:
    """Sessions, every unit, and the clean view; the all-units view is built on demand."""

    def __init__(self, paths: list[Path]):
        self.paths = [Path(p) for p in paths]
        self.sessions = [analysis.load_session(p) for p in self.paths]
        self.units = analysis.build_units(self.sessions)
        self.res = analysis.analyse(self.paths)  # the clean view (and swap_alt)
        self.names = sorted(self.res["cells"])

    def lifted(self, units: list[dict] | None = None) -> list[dict]:
        """Copies of the units where a final unit's flags no longer exclude it. A unit with a
        structural problem (``incomplete``) stays excluded."""
        return [
            dict(u, clean=True) if (not u["superseded"] and not u["problems"]) else u
            for u in (self.units if units is None else units)
        ]

    def cells_from(self, units: list[dict], names: list[str] | None = None) -> dict[str, dict]:
        return {
            n: analysis._cell_entry(n, units, self.sessions)  # noqa: SLF001 (same package family)
            for n in (names or self.names)
        }

    def all_cells(self, names: list[str] | None = None) -> dict[str, dict]:
        return self.cells_from(self.lifted(), names)

    def without(
        self, units: list[dict], drop: Callable[[dict], bool], names: list[str]
    ) -> dict[str, dict]:
        """Cells recomputed from ``units`` with the final units for which ``drop`` is true removed
        (the same removal as ``analysis.swap_alternative``)."""
        gone = {id(u) for u in units if not u["superseded"] and drop(u)}
        return self.cells_from([u for u in units if id(u) not in gone], names)


def trimmed(s: dict | None) -> dict | None:
    """A ``stats.summarize`` result without the two component intervals."""
    if s is None:
        return None
    return {k: s[k] for k in ("n", "mean", "min", "max", "ci", "ci_method") if k in s}


def _ratio(a: dict, b: dict) -> dict:
    """Geometric-mean paired ratio a / b of two ``{unit key: value}`` series."""
    keys = sorted(set(a) & set(b))
    out = {"n_paired": len(keys), "geomean": None, "ci": None, "ci_method": None, "keys": keys}
    if not keys:
        out["ci_method"] = "unavailable (no paired units)"
        return out
    try:
        r = stats.paired_ratio({k: a[k] for k in keys}, {k: b[k] for k in keys})
    except ValueError as e:  # a non-positive value
        out["ci_method"] = f"unavailable ({e})"
        return out
    out.update(geomean=r["geomean"], ci=r["ci"], ci_method=r["ci_method"])
    return out


def ratios(tuned: dict, stock: dict) -> dict[str, dict]:
    """Paired ratios tuned / stock per metric: ``t_turn_400`` and ``t_reread`` (per unit), and
    ``pp_fresh``, ``tg``, ``ttft`` at every depth (``pp_fresh@8192`` ...). Units are paired on their
    ``session:repetition`` key."""
    out: dict[str, dict] = {}
    for key, metric in (("t_turn_400", "t_turn_400_mean"), ("t_reread", "t_reread_mean")):
        out[key] = _ratio(
            tuned["rep_metrics"][metric]["values"], stock["rep_metrics"][metric]["values"]
        )
    depths = sorted(set(tuned["depths"]) & set(stock["depths"]))
    for m in RATIO_DEPTH_METRICS:
        for d in depths:
            out[f"{m}@{d}"] = _ratio(
                tuned["depth_metrics"][str(d)][m]["values"],
                stock["depth_metrics"][str(d)][m]["values"],
            )
    return out


def excludes_one(ci: list[float] | None) -> bool | None:
    return None if ci is None else (ci[0] > 1.0 or ci[1] < 1.0)


def sign_of(geomean: float | None) -> int | None:
    return None if geomean is None else (1 if geomean > 1.0 else -1 if geomean < 1.0 else 0)


def disagreements(a: dict[str, dict], b: dict[str, dict]) -> list[dict]:
    """Metrics where two sets of ratios disagree in sign (the geometric mean is on different sides
    of 1.0) or where one interval excludes 1.0 and the other does not."""
    out = []
    for k in a:
        if k not in b or a[k]["geomean"] is None or b[k]["geomean"] is None:
            continue
        sa, sb = sign_of(a[k]["geomean"]), sign_of(b[k]["geomean"])
        ea, eb = excludes_one(a[k]["ci"]), excludes_one(b[k]["ci"])
        why = []
        if sa != sb:
            why.append("sign")
        if ea is not None and eb is not None and ea != eb:
            why.append("interval")
        if why:
            out.append({"metric": k, "kinds": why, "a": slim(a[k]), "b": slim(b[k])})
    return out


def slim(r: dict) -> dict:
    return {k: r[k] for k in ("n_paired", "geomean", "ci", "ci_method")}
