"""`python -m smallpc.stage3 repro`: the S2 check with the all-units fallback for a cell with too
few clean units on either day (plan v1.7, Stage 4)."""

from __future__ import annotations

from fixture_session import CellSpec, RepSpec, build_session
from smallpc import analysis, report
from smallpc.stage3 import cli, repro


def cells(flag=(), slow=1.0, pp=1000.0):
    reps = [
        RepSpec(i, flags=("paging",) if i in flag else (), slow=slow if i in flag else 1.0)
        for i in range(5)
    ]
    return [
        CellSpec(name="stock-64K", profile="stock", context=65536, pp=pp, tg=50.0, reps=reps),
        CellSpec(
            name="tuned-64K", profile="tuned", context=65536, pp=1900.0, tg=90.0, cache_mib=9472
        ),
    ]


def test_clean_days_use_clean_units_and_equal_report_repro(tmp_path):
    o = build_session(tmp_path, "stage3-64K", cells())
    r = build_session(tmp_path, "stage4", cells(), seed=8)
    out = repro.build([o], [r], ["stock-64K", "tuned-64K"])
    assert out["all_units_fallback"] == {} and out["pass"]
    assert {x["evaluated_on"] for x in out["rows"]} == {"clean units"}
    ref = report.repro_check(
        analysis.analyse([o]), analysis.analyse([r]), ["stock-64K", "tuned-64K"]
    )
    assert [(x["cell"], x["metric"], x["pass"], x["lo"], x["hi"]) for x in out["rows"]] == [
        (x["cell"], x["metric"], x["pass"], x["lo"], x["hi"]) for x in ref
    ]
    assert "evaluated on all units" not in repro.render(out)


def test_too_few_clean_units_on_either_day_evaluates_stock_on_all_units(tmp_path):
    o = build_session(tmp_path, "stage3-64K", cells(flag=(1, 2)))  # stock: 3 clean of 5
    r = build_session(tmp_path, "stage4", cells(), seed=8)
    out = repro.build([o], [r], ["stock-64K", "tuned-64K"])
    assert list(out["all_units_fallback"]) == ["stock-64K"]
    assert "original has 3 clean of 5" in out["all_units_fallback"]["stock-64K"]
    on = {x["cell"]: x["evaluated_on"] for x in out["rows"]}
    assert on == {"stock-64K": "all units", "tuned-64K": "clean units"}
    text = repro.render(out)
    assert text.startswith("**S2 evaluated on ALL units (flagged units included) for: stock-64K")
    # the original mean now includes the flagged units, so it is not the clean-units mean
    plain = report.repro_check(analysis.analyse([o]), analysis.analyse([r]), ["stock-64K"])[0]
    row = next(
        x for x in out["rows"] if x["cell"] == "stock-64K" and x["metric"] == plain["metric"]
    )
    assert row["original"]["n"] == 5 and plain["original"]["n"] == 3


def test_the_rerun_day_with_too_few_clean_units_also_falls_back(tmp_path):
    o = build_session(tmp_path, "stage3-64K", cells())
    r = build_session(tmp_path, "stage4", cells(flag=(0, 1, 2)), seed=8)
    out = repro.build([o], [r], ["stock-64K"])
    assert "re-run has 2 clean of 5" in out["all_units_fallback"]["stock-64K"]


def test_a_missing_cell_fails_with_missing_data_and_the_command_line_returns_one(tmp_path, capsys):
    o = build_session(tmp_path, "stage3-64K", cells())
    r = build_session(tmp_path, "stage4", cells()[:1], seed=8)
    out = repro.build([o], [r], ["tuned-64K"])
    assert not out["pass"] and out["rows"][0]["why"] == "missing data"
    rc = cli.main(["repro", "--original", str(o), "--rerun", str(r), "--cells", "tuned-64K"])
    assert rc == 1 and "missing data" in capsys.readouterr().out
    assert cli.main(["repro", "--original", str(o), "--rerun", str(o), "--cells", "stock-64K"]) == 0
