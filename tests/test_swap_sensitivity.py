"""Plan v1.4 (5.5): swap activity of a unit, the sensitivity analysis without swap-heavy units, and
its verdict. Synthetic sessions only (no GPU)."""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fixture_session import CellSpec, RepSpec, build_session  # noqa: E402
from smallpc import analysis, report, telemetry  # noqa: E402


def cells(swap: dict[int, float] | None, slow: float = 0.7, others_swap: float | None = 0.0):
    swap = swap or {}
    stock = CellSpec("stock-32K", "stock", pp=950, tg=78, kv_type="f16",
                     reps=[RepSpec(i, swap_mib=others_swap) for i in range(5)])  # fmt: skip
    cand = CellSpec("cand-32K-b2048", pp=1000, tg=84, placement="P1", batch="b2048",
                    reps=[RepSpec(i, swap_mib=swap.get(i, others_swap), slow=slow if i in swap else 1.0)
                          for i in range(5)])  # fmt: skip
    return [stock, cand]


def analyse(tmp_path, cs):
    return analysis.analyse([build_session(tmp_path, "s", cs, canary=False)])


def test_nothing_above_the_threshold_gives_identical_versions(tmp_path):
    res = analyse(tmp_path, cells({0: 64.0}))  # exactly 64 MiB is not "above"
    alt = res["swap_alt"]
    assert alt["removed"] == [] and alt["cells"] is res["cells"]
    v = report.swap_verdict(res)
    assert v == {"removed": 0, "sign_changes": [], "interval_changes": []}
    md = "\n".join(report.render_swap_sensitivity(res, "BANNER"))
    assert "both versions are identical" in md and "No unit was removed" in md


def test_removal_that_flips_a_ratio_is_a_sign_change_and_a_material_interval_change(tmp_path):
    res = analyse(tmp_path, cells({1: 300.0, 2: 250.0, 4: 310.0}))
    alt = res["swap_alt"]
    assert [(r["repetition"], r["source"]) for r in alt["removed"]] == [
        (1, "summary"), (2, "summary"), (4, "summary"),
    ]  # fmt: skip
    assert res["cells"]["cand-32K-b2048"]["n_clean"] == 5
    assert alt["cells"]["cand-32K-b2048"]["n_clean"] == 2
    v = report.swap_verdict(res)
    assert any("T_turn_400 ratio" in s and "->" in s for s in v["sign_changes"])
    assert any("T_turn_400 interval" in s for s in v["interval_changes"])
    md = "\n".join(report.render_swap_sensitivity(res, "BANNER"))
    assert "**YES**" in md and "cand-32K-b2048, s, 1" in md


def test_small_removal_changes_nothing_materially(tmp_path):
    # the swap-heavy repetition is as fast as the others (slow = 1): the numbers do not move much
    res = analyse(tmp_path, cells({3: 500.0}, slow=1.0))
    v = report.swap_verdict(res)
    assert v["removed"] == 1 and v["sign_changes"] == []
    md = "\n".join(report.render_swap_sensitivity(res, "BANNER"))
    assert "changed sign: no." in md


def test_flagged_swap_heavy_units_are_not_removed_again(tmp_path):
    cs = cells(None)
    cs[1].reps[2] = RepSpec(2, swap_mib=900.0, flags=("paging",))
    res = analyse(tmp_path, cs)
    alt = res["swap_alt"]
    assert alt["removed"] == []  # already excluded by its flag
    assert [(u["cell"], u["repetition"]) for u in alt["already_excluded"]] == [
        ("cand-32K-b2048", 2)
    ]


def test_units_without_swap_information_are_kept_and_reported(tmp_path):
    cs = cells({1: 400.0}, others_swap=None)
    cs[0].reps = [RepSpec(i) for i in range(5)]  # the stock cell has no swap figure
    res = analyse(tmp_path, cs)
    # the candidate's four other repetitions have no figure either; only its repetition 1 does
    gone = {(u["cell"], u["repetition"]) for u in res["swap_alt"]["unavailable"]}
    assert ("cand-32K-b2048", 1) not in gone and ("stock-32K", 0) in gone
    assert {u["cell"] for u in res["swap_alt"]["unavailable"]} == {"stock-32K", "cand-32K-b2048"}
    assert res["cells"]["stock-32K"]["n_clean"] == res["swap_alt"]["cells"]["stock-32K"]["n_clean"]
    md = "\n".join(report.render_swap_sensitivity(res, "BANNER"))
    assert "not available" in md and "stock-32K s (5)" in md


def _telemetry_session(tmp_path, vmswap_kib: list[float]) -> Path:
    """A session whose summaries have no swap figures (like the mini-sweep) but a telemetry CSV."""
    d = build_session(tmp_path, "old", cells(None, others_swap=None), canary=False)
    f = next((d / "cells").glob("cand-32K-b2048-*.json"))
    summ = json.loads(f.read_text())
    ins = summ["instances"][0]
    t0 = 1000.0
    for w in ins["windows"]:
        w["t0_epoch"], w["t1_epoch"] = t0 + w["repetition"] * 100, t0 + w["repetition"] * 100 + 50
    rel = "telemetry/cand-i0.csv.gz"
    (d / "telemetry").mkdir()
    with gzip.open(d / rel, "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=telemetry.COLUMNS)
        w.writeheader()
        for rep in range(5):
            for i, v in enumerate(vmswap_kib if rep == 3 else [0.0, 0.0, 0.0]):
                w.writerow({"t_epoch": t0 + rep * 100 + 10 * i, "server_vmswap_kib": v})
    ins["telemetry"] = {"file": rel}
    f.write_text(json.dumps(summ))
    return d


def test_swap_activity_of_an_older_session_is_derived_from_the_telemetry(tmp_path):
    d = _telemetry_session(tmp_path, [1024.0, 80 * 1024.0, 200 * 1024.0])
    res = analysis.analyse([d])
    u = {x["repetition"]: x for x in res["units"] if x["cell"] == "cand-32K-b2048"}
    assert u[3]["swap_source"] == "telemetry" and u[3]["swap_activity_mib"] == pytest.approx(199.0)
    assert u[0]["swap_activity_mib"] == 0.0
    assert [r["repetition"] for r in res["swap_alt"]["removed"]] == [3]
    assert res["swap_alt"]["removed"][0]["source"] == "telemetry"


def test_swap_activity_not_available_without_summary_value_or_telemetry(tmp_path):
    d = build_session(tmp_path, "old2", cells(None, others_swap=None), canary=False)
    res = analysis.analyse([d])
    assert all(u["swap_activity_mib"] is None and u["swap_source"] == "not available"
               for u in res["units"])  # fmt: skip
    assert res["swap_alt"]["removed"] == [] and len(res["swap_alt"]["unavailable"]) == 10


def test_mini_sweep_session_derives_its_swap_from_the_telemetry():
    mini = Path(__file__).resolve().parents[1] / "data/raw/mini-20261109"
    if not mini.exists():
        pytest.skip("mini-sweep data not present")
    res = analysis.analyse([mini])
    stock1 = next(u for u in res["units"] if u["cell"] == "stock-32K" and u["repetition"] == 1)
    assert stock1["swap_source"] == "telemetry" and stock1["swap_activity_mib"] > 1000
    assert not stock1["clean"]  # flagged for 1,692 faults: reported as already excluded
    assert res["swap_alt"]["already_excluded"][0]["cell"] == "stock-32K"
