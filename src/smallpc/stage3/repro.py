"""The Stage 4 S2 check with the all-units fallback (plan 5.4, Stage 4).

``report repro`` evaluates the clean units only. If a cell has fewer than 5 clean units on either
day, S2 is evaluated for it on all units (the flag-based exclusion lifted, as in the headline's
all-units view) and the output says so. Other cells use ``report.repro_check`` unchanged.
"""

from __future__ import annotations

from pathlib import Path

from .. import report
from . import rules, views


def build(original: list[Path], rerun: list[Path], cells: list[str]) -> dict:
    o, r = views.Data(original), views.Data(rerun)
    o_all, r_all = o.all_cells(), r.all_cells()
    fallback: dict[str, str] = {}
    res_o, res_r = {"cells": dict(o.res["cells"])}, {"cells": dict(r.res["cells"])}
    for name in cells:
        co, cr = o.res["cells"].get(name), r.res["cells"].get(name)
        few = [
            f"{day} has {c['n_clean']} clean of {c['n_total']} unit(s)"
            for day, c in (("original", co), ("re-run", cr))
            if c is not None and c["n_clean"] < rules.MIN_CLEAN_PAIRED
        ]
        if few and co is not None and cr is not None:
            res_o["cells"][name], res_r["cells"][name] = o_all[name], r_all[name]
            fallback[name] = "; ".join(few)
    rows = report.repro_check(res_o, res_r, cells)
    for row in rows:
        if row["cell"] in fallback:
            row["evaluated_on"] = "all units"
            row["why"] = row["why"] or ""
        else:
            row["evaluated_on"] = "clean units"
    return {"rows": rows, "all_units_fallback": fallback, "pass": all(x["pass"] for x in rows)}


def render(out: dict) -> str:
    L = []
    if out["all_units_fallback"]:
        L.append(
            "**S2 evaluated on ALL units (flagged units included) for: "
            + "; ".join(f"{c} ({why})" for c, why in out["all_units_fallback"].items())
            + ".** The other cells use clean units."
        )
        L.append("")
    L.append(report.render_repro(out["rows"]))
    L.append("")
    L += [f"- {x['cell']}, {x['metric']}: evaluated on {x['evaluated_on']}" for x in out["rows"]]
    return "\n".join(L)
