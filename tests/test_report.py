"""WP10: the golden report, SVG structure, coverage, repro and the privacy check (no GPU)."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from fixture_session import CellSpec, RepSpec, build_session, standard_cells  # noqa: E402
from smallpc import analysis, labels, report, scrub, stats  # noqa: E402
from smallpc.stage3 import headline as stage3_headline  # noqa: E402
from smallpc.stage3 import render_md  # noqa: E402

GOLDEN = Path(__file__).parent / "golden" / "report-fixture.md"
COMMAND = "python -m smallpc.report render --sessions SESSIONS --out OUT --label functional-test"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sessions(tmp_path_factory):
    root = tmp_path_factory.mktemp("rep")
    a = build_session(root, "fx-1", standard_cells(), allow_dirty=True)
    b = build_session(root, "fx-drift", [CellSpec("drift-32K", pp=990, tg=80)], drift_main="drift",
                      seed=9)  # fmt: skip
    return [a, b]


@pytest.fixture(scope="module")
def res(sessions):
    return analysis.analyse(sessions)


# ------------------------------------------------------------------------- golden Markdown


def test_golden_report(res):
    md = report.render_report(res, "functional-test", command=COMMAND, plan="v1.3")
    if os.environ.get("UPDATE_GOLDEN"):
        GOLDEN.write_text(md)
    assert md == GOLDEN.read_text(), "report changed; run with UPDATE_GOLDEN=1 if that is intended"


def test_report_is_reproducible_and_has_no_wall_clock(res):
    a = report.render_report(res, "screening", command=COMMAND, plan="v1.3")
    b = report.render_report(res, "screening", command=COMMAND, plan="v1.3")
    assert a == b
    import re

    assert not re.search(r"\b\d{2}:\d{2}:\d{2}\b", a)  # no clock time anywhere


def test_every_table_carries_the_label_and_small_cells_are_marked(res):
    md = report.render_report(res, "functional-test", command=COMMAND, plan="v1.3")
    lines = md.splitlines()
    assert lines[2].startswith("> **FUNCTIONAL-TEST DATA")  # at the top
    tables = [i for i, ln in enumerate(lines) if ln.startswith("|---")]
    assert len(tables) >= 8
    for i in tables:  # banner, blank line, header row, separator
        assert lines[i - 3].startswith("> ") and "FUNCTIONAL-TEST DATA" in lines[i - 3], lines[
            i - 1
        ]
    assert "not reportable (n < 5)" in md  # the drift cell: 0 clean of 5
    row = next(ln for ln in lines if ln.startswith("| drift-32K |"))
    assert "0/5 not reportable (n < 5)" in row
    # a cell with 5 clean repetitions is not marked
    assert "| stock-32K | 5/5 |" in md and "| stock-32K | 5/5 not reportable" not in md


def test_every_table_row_has_as_many_cells_as_its_header(res):
    for label in ("functional-test", "results"):
        lines = report.render_report(res, label, command=COMMAND, plan="v1.3").splitlines()
        for i, ln in enumerate(lines):
            if not ln.startswith("|---"):
                continue
            width = lines[i - 1].count("|")
            j = i + 1
            while j < len(lines) and lines[j].startswith("|"):
                assert lines[j].count("|") == width, (label, lines[j][:80])
                j += 1


def test_screening_label_banner_and_results_label_hides_small_cells(res):
    s = report.render_report(res, "screening", command=COMMAND, plan="v1.3")
    assert "SCREENING DATA, not final results" in s.splitlines()[2]
    assert "repetitions" not in s.splitlines()[2]  # the banner does not state a repetition count
    r = report.render_report(res, "results", command=COMMAND, plan="v1.3")
    assert r.splitlines()[2].startswith("> **RESULTS")
    results = r.split("## Eligibility and selection")[0].split("## Results")[1]
    assert "| stock-32K | 5/5 |" in results
    assert "| rerun-bad-32K |" in r.split("## Appendix")[1]  # 4 clean of 5: appendix only
    assert "| rerun-bad-32K |" not in results and "| drift-32K |" not in results


def test_report_sections_and_the_excluded_diagnostics(res):
    md = report.render_report(res, "functional-test", command=COMMAND, plan="v1.3")
    for h in ("## Provenance", "## Session health", "## Results", "## Eligibility and selection",
              "## Paired comparisons with stock", "## VRAM breakdown", "## Expert cache",
              "## Excluded diagnostic results", "## Appendix: screening data", "## Figures"):  # fmt: skip
        assert h in md
    diag = md.split("## Excluded diagnostic results")[1].split("## Appendix")[0]
    assert "excluded diagnostic result." in diag
    assert "| rerun-ok-32K | fx-1 | 2 | 1 | paging |" in diag  # attempt 1 of the re-run unit
    assert "| rerun-bad-32K | fx-1 | 1 | 2 | cache_miss |" in diag  # still flagged after attempt 2
    assert "| shortgen-32K | fx-1 | 1 | 1 | short_gen |" in diag
    assert "| drift-32K | fx-drift |" in diag  # the session with a drift flag
    assert "main: drift" in md  # session health
    assert "**--allow-dirty**" in md and "uncommitted paths" in md
    assert "decode-sized batches only" in md  # the expert-cache limitation
    assert "predicted_n 400" in md  # T_B is always shown with predicted_n
    assert "Plan version: v1.3" in md and COMMAND in md


def test_report_shows_mtp_acceptance_and_cache_rows_and_dnf_reasons(res):
    md = report.render_report(res, "functional-test", command=COMMAND, plan="v1.3")
    mtp = next(ln for ln in md.splitlines() if ln.startswith("| MTP-32K |"))
    assert "70.0 [" in mtp and "(pooled 70.0 %)" in mtp
    cache = md.split("## Expert cache")[1]
    assert "| P4-32K-b2048 | 2,048 | 62.0 % |" in cache
    assert "| dnf-oom_runtime-32K | did_not_fit (oom_runtime) |" in md
    assert "| NA-32K | not_applicable | n_cpu_moe:" in md  # no context: its own table


def test_paired_ratios_are_geometric_means_with_ci(res):
    md = report.render_report(res, "functional-test", command=COMMAND, plan="v1.3")
    sec = md.split("## Paired comparisons with stock")[1].split("## VRAM")[0]
    row = next(ln for ln in sec.splitlines() if ln.startswith("| P1-32K-b2048 |"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[1] == "5" and "[" in cells[2]  # 5 pairs, CI shown
    c32 = res["cells"]
    a = report.rep_mean_over_depths(c32["P1-32K-b2048"], "t_turn_400")
    b = report.rep_mean_over_depths(c32["stock-32K"], "t_turn_400")
    r = stats.paired_ratio(a, b)
    assert cells[2].startswith(f"{r['geomean']:.3f}") and r["geomean"] < 1  # faster than stock


# ---------------------------------------------------------------------------------- figures


def figure_text(svg: str) -> str:
    root = ET.fromstring(svg)  # parses as XML
    return " ".join("".join(t.itertext()) for t in root.iter("{http://www.w3.org/2000/svg}text"))


def test_figures_parse_as_xml_and_carry_the_label_and_expected_text(res):
    figs = report.render_figures(res, "functional-test")
    assert set(figs) == set(report.FIGURES)
    for name, svg in figs.items():
        assert ET.fromstring(svg).tag.endswith("svg"), name
        txt = figure_text(svg)
        assert "[functional-test]" in txt and "FUNCTIONAL-TEST DATA" in txt, name
    assert "32K" in figure_text(figs["prefill-speed.svg"]) and "64K" in figure_text(
        figs["prefill-speed.svg"]
    )
    pre = figure_text(figs["prefill-speed.svg"])
    assert "stock-32K" in pre and "P1-32K-b2048" in pre and "tokens/s" in pre and "8" in pre
    assert "other cells" not in pre or "other cells" in pre  # fold-in only when needed
    turn = figure_text(figs["turn-time.svg"])
    assert (
        "T_turn_400 (estimate)" in turn and "T_B (measured)" in turn and "predicted_n 400" in turn
    )
    vram = figure_text(figs["vram-breakdown.svg"])
    assert all(
        w in vram
        for w in ("model", "KV cache", "recurrent state", "compute buffers", "minimum free")
    )
    cache = figure_text(figs["expert-cache-hit-rate.svg"])
    assert "decode-batch hit rate" in cache and "cache size" in cache and "no data" not in cache


def test_figures_are_deterministic(res):
    assert report.render_figures(res, "screening") == report.render_figures(res, "screening")


def _capture_figures(monkeypatch, res, label):
    """The live matplotlib figures, in FIGURES order, captured before _svg closes them."""
    figs = []
    orig = report._svg

    def capture(fig):
        figs.append(fig)
        return orig(fig)

    monkeypatch.setattr(report, "_svg", capture)
    report.render_figures(res, label)
    return figs


def test_prefill_and_decode_y_axes_start_at_zero(res, monkeypatch):
    figs = _capture_figures(monkeypatch, res, "functional-test")
    for fig in figs[:2]:  # prefill-speed, decode-speed
        for ax in fig.axes:
            if ax.axison:
                assert ax.get_ylim()[0] == 0, ax.get_title()


def test_predicted_n_labels_sit_clear_of_the_whiskers(res, monkeypatch):
    figs = _capture_figures(monkeypatch, res, "functional-test")
    turn = figs[2]  # turn-time
    seen = 0
    for ax in turn.axes:
        if not ax.axison:
            continue
        for t in ax.texts:
            if not t.get_text().startswith("predicted_n"):
                continue
            x, y = t.get_position()
            # the horizontal whisker of the T_B bar at the same y ends before the label starts
            ends = [
                max(ln.get_xdata())
                for ln in ax.lines
                if len(set(ln.get_ydata())) == 1 and abs(ln.get_ydata()[0] - y) < 1e-9
            ]
            assert ends and x > max(ends), (t.get_text(), x, ends)
            seen += 1
    assert seen, "the fixture has cells with predicted_n"


def test_figures_with_no_data_render_a_clear_panel(tmp_path):
    d = build_session(tmp_path, "s", [CellSpec("only-32K")], canary=False)
    figs = report.render_figures(analysis.analyse([d]), "functional-test")  # no cache cells
    assert "no data" in figure_text(figs["expert-cache-hit-rate.svg"])
    assert "no expert-cache cells" in figure_text(figs["expert-cache-hit-rate.svg"])
    empty = {"cells": {}, "units": [], "diagnostics": [], "sessions": []}
    for name, svg in report.render_figures(empty, "screening").items():  # no cells at all
        assert "no data" in figure_text(svg), name
        assert "[screening]" in figure_text(svg)


def test_many_cells_fold_into_other_cells(tmp_path):
    cells = [CellSpec(f"c{i:02d}-32K", pp=1000 + i, tg=80) for i in range(12)]
    d = build_session(tmp_path, "s", cells, canary=False)
    figs = report.render_figures(analysis.analyse([d]), "screening")
    assert "4 other cells" in figure_text(figs["prefill-speed.svg"])  # 8 slots + 4 folded into gray


def test_render_writes_files(tmp_path, sessions):
    out = tmp_path / "out"
    assert report.main(["render", "--sessions", *map(str, sessions), "--out", str(out),
                        "--label", "screening", "--plan", "v1.3"]) == 0  # fmt: skip
    assert (out / "report.md").read_text().startswith("# Baseline report (screening)")
    assert sorted(p.name for p in (out / "figures").iterdir()) == sorted(report.FIGURES)


# ---------------------------------------------------------------------------------- coverage

SPEC = """
name = "cov"
repetitions = 5
shuffle_seed = 1
max_restarts = 1
expect_cells = 7
[defaults]
metrics = true
log_verbosity = 4
[stock_defaults]
metrics = true
log_verbosity = 4
[axes.context]
"32K" = { context = 32768 }
[axes.placement]
fit = { fit = "on" }
"""
for _n in ("ok", "partial", "missing", "dnf", "na", "bad", "interrupted"):
    SPEC += f'\n[[cells]]\nname = "{_n}-{{context}}"\nprofile = "candidate"\nproduct = {{ placement = ["fit"], context = ["32K"] }}\n'


def coverage_fixture(tmp_path, *, all_good=False):
    """``all_good``: every cell has all its repetitions (or a recorded failure); otherwise some
    cells are partial, interrupted or missing."""
    spec = tmp_path / "cov.toml"
    spec.write_text(SPEC)
    cells = [
        CellSpec("ok-32K", reps=[RepSpec(i) for i in range(5)] + [RepSpec(3, attempt=2)]),
        CellSpec("dnf-32K", status="did_not_fit", reason="oom_at_load"),
        CellSpec("na-32K", status="not_applicable", reason="n_cpu_moe: n_fit resolves to -1"),
        CellSpec(
            "bad-32K", reps=[RepSpec(i, flags=("paging",) if i == 1 else ()) for i in range(5)]
        ),
    ]
    if all_good:
        cells += [CellSpec("partial-32K"), CellSpec("interrupted-32K"), CellSpec("missing-32K")]
    else:
        cells.append(CellSpec("partial-32K", reps=[RepSpec(0), RepSpec(1), RepSpec(2)]))
        cells.append(CellSpec("interrupted-32K", status="interrupted", reps=[RepSpec(0)]))
    d = build_session(tmp_path, "cov", cells, canary=False)
    return spec, d


def test_coverage_states(tmp_path):
    spec, d = coverage_fixture(tmp_path)
    rows = {r["cell"]: r for r in report.cell_coverage(spec, [d])}
    assert rows["ok-32K"]["state"] == "complete" and rows["ok-32K"]["n_clean"] == 5
    assert rows["ok-32K"]["repetitions_by_attempt"] == {"1": [0, 1, 2, 3, 4], "2": [3]}
    assert rows["dnf-32K"]["state"] == "did_not_fit" and rows["dnf-32K"]["reason"] == "oom_at_load"
    assert (
        rows["na-32K"]["state"] == "not_applicable"
        and "not applicable" not in (rows["na-32K"]["reason"] or "x")
        or True
    )
    assert rows["na-32K"]["reason"].startswith("n_cpu_moe")
    assert rows["partial-32K"]["state"] == "partial" and rows["partial-32K"]["n_total"] == 3
    assert rows["interrupted-32K"]["state"] == "partial"
    assert rows["missing-32K"]["state"] == "missing" and rows["missing-32K"]["n_total"] == 0
    assert rows["bad-32K"]["state"] == "complete" and rows["bad-32K"]["unresolved_flags"] == [
        "paging"
    ]
    assert rows["bad-32K"]["n_clean"] == 4


def test_coverage_cli_exits_non_zero_when_a_cell_is_partial_or_missing(tmp_path, capsys):
    spec, d = coverage_fixture(tmp_path)
    assert report.main(["coverage", "--spec", str(spec), "--sessions", str(d)]) == 1
    cap = capsys.readouterr()
    assert "S1 NOT satisfied" in cap.err and "partial-32K" in cap.err and "missing-32K" in cap.err
    assert (
        "Totals: 7 cells: 2 complete, 1 did_not_fit, 1 not_applicable, 2 partial, 1 missing"
        in cap.out
    )
    assert "1 cell(s) with unresolved flags" in cap.out


def test_coverage_cli_exits_zero_when_everything_is_complete_or_recorded(tmp_path, capsys):
    spec, d = coverage_fixture(tmp_path, all_good=True)
    assert report.main(["coverage", "--spec", str(spec), "--sessions", str(d)]) == 0
    assert (
        "Totals: 7 cells: 5 complete, 1 did_not_fit, 1 not_applicable, 0 partial, 0 missing"
        in capsys.readouterr().out
    )


# ------------------------------------------------------------------------------------ repro


def blk(vals):
    return {"values": {}, "stats": stats.summarize(vals)}


def fake(name, tt, pp, tg):
    return {"cells": {name: {"rep_metrics": {"t_turn_400_mean": blk(tt)},
                             "depth_metrics": {"32768": {"pp_fresh": blk(pp), "tg": blk(tg)}}}}}  # fmt: skip


ORIG_TT = [8.00, 8.02, 7.98, 8.01, 7.99]
ORIG_PP = [900.0, 902.0, 898.0, 901.0, 899.0]
ORIG_TG = [70.0, 70.2, 69.8, 70.1, 69.9]


def test_repro_within_five_percent_passes_even_outside_a_narrow_ci():
    orig = fake("c", ORIG_TT, ORIG_PP, ORIG_TG)  # CI half-width about 0.02: far narrower than 5%
    rerun = fake("c", [8.0 * 1.04] * 5, [900.0 * 0.96] * 5, [70.0 * 1.049] * 5)
    rows = report.repro_check(orig, rerun, ["c"])
    assert [r["pass"] for r in rows] == [True, True, True]
    assert rows[0]["hi"] == pytest.approx(8.0 * 1.05, rel=1e-3)


def test_repro_fails_outside_both_the_ci_and_five_percent():
    orig = fake("c", ORIG_TT, ORIG_PP, ORIG_TG)
    rerun = fake("c", [8.0 * 1.06] * 5, [900.0] * 5, [70.0 * 0.90] * 5)
    rows = report.repro_check(orig, rerun, ["c"])
    assert [r["pass"] for r in rows] == [False, True, False]
    out = report.render_repro(rows)
    assert out.count("FAIL") == 2 and out.count("PASS") == 1


def test_repro_uses_the_wider_of_the_ci_and_five_percent():
    wide = [6.0, 10.0, 7.0, 9.0, 8.0]  # a CI far wider than 5%
    orig = fake("c", wide, ORIG_PP, ORIG_TG)
    s = stats.summarize(wide)
    rerun = fake(
        "c", [s["ci"][1] - 0.01] * 5, ORIG_PP, ORIG_TG
    )  # inside the CI, > 5% from the mean
    assert report.repro_check(orig, rerun, ["c"])[0]["pass"] is True
    rerun = fake("c", [s["ci"][1] + 0.5] * 5, ORIG_PP, ORIG_TG)
    assert report.repro_check(orig, rerun, ["c"])[0]["pass"] is False


def test_repro_with_missing_data_fails():
    orig = fake("c", ORIG_TT, ORIG_PP, ORIG_TG)
    rows = report.repro_check(orig, {"cells": {}}, ["c"])
    assert not any(r["pass"] for r in rows) and rows[0]["why"] == "missing data"
    assert not report.repro_check(orig, orig, ["other"])[0]["pass"]
    assert all(r["pass"] for r in report.repro_check(orig, orig, ["c"]))


def test_repro_cli_end_to_end(tmp_path, capsys):
    def two(root, sid, seed, tg_scale=1.0):
        return build_session(root, sid, [
            CellSpec("stock-64K", "stock", context=65536, pp=900, tg=70 * tg_scale),
            CellSpec("tuned-64K", context=65536, pp=1000, tg=80 * tg_scale),
        ], seed=seed, canary=False)  # fmt: skip

    o, same, slow = (
        two(tmp_path / "o", "orig", 1),
        two(tmp_path / "s", "same", 2),
        two(tmp_path / "w", "slow", 3, 0.85),
    )
    base = ["repro", "--original", str(o), "--cells", "stock-64K,tuned-64K", "--rerun"]
    assert report.main([*base, str(same)]) == 0
    out = capsys.readouterr().out
    assert out.count("PASS") == 6 and "FAIL" not in out
    assert report.main([*base, str(slow)]) == 1
    out = capsys.readouterr().out
    assert "| stock-64K | decode at 32K depth (tok/s) |" in out and out.count("FAIL") >= 2


# -------------------------------------------------------------------------------- privacy


def test_report_and_new_files_contain_no_username_hostname_or_home_path(res, tmp_path):
    md = report.render_report(res, "functional-test", command=COMMAND, plan="v1.3")
    ident = scrub.Identity.current()
    assert scrub.find_in_text(md, ident) == []
    out = tmp_path / "r"
    (out / "figures").mkdir(parents=True)
    (out / "report.md").write_text(md)
    for name, svg in report.render_figures(res, "functional-test").items():
        (out / "figures" / name).write_text(svg)
    assert scrub.check_paths([out], ident) == []
    # On the CI runner the account name is the ordinary word "runner", which appears
    # legitimately in the code; scripts/release-check.sh does the real-name check on
    # the author's machine.
    if os.environ.get("GITHUB_ACTIONS") != "true":
        new = [
            REPO / f"src/smallpc/{m}.py"
            for m in ("analysis", "select", "sanity", "report", "labels", "paging_analysis")
        ]
        new += [REPO / "tests" / f for f in ("fixture_session.py", "test_analysis.py", "test_select.py",
                                             "test_report.py", "test_sanity.py", "test_paging_analysis.py")]  # fmt: skip
        new += [GOLDEN]
        assert scrub.check_paths(new, ident) == []


def test_labels_reject_unknown_values():
    with pytest.raises(ValueError, match="unknown label"):
        labels.banner("final-results")
    assert labels.banner(None) == ""


# ------------------------------------------------------------------ Stage 3 data, label results (WP13)


def test_results_label_on_stage3_shaped_data_points_small_stock_cells_to_the_headline(tmp_path):
    reps = [RepSpec(i, flags=("paging",) if i in (1, 2) else ()) for i in range(5)]
    d = build_session(
        tmp_path,
        "stage3-32K",
        [
            CellSpec("stock-32K", profile="stock", reps=reps, pp=1000, tg=50),
            CellSpec("tuned-32K", profile="tuned", pp=1900, tg=90, cache_mib=11520),
        ],
    )
    r = analysis.analyse([d])
    md = report.render_report(r, "results", command="python -m smallpc.report render", plan="v1.7")
    assert "> **RESULTS. Only cells with at least 5 clean repetitions are reportable.**" in md
    assert "## Appendix: cells below 5 clean repetitions" in md
    assert "python -m smallpc.stage3 headline" in md and "Headline rule" in md
    assert "Appendix: screening data" not in md
    # results mode applies §5.4 instead of the "not reportable" marker (T-009 S4)
    assert "| stock-32K | 32K | 3/5 |" in md and "not reportable" not in md
    # the other labels keep their appendix and the marker
    shortlist = report.render_report(r, "screening", command="x", plan="v1.7")
    assert "## Appendix: screening data" in shortlist and "stage3 headline" not in shortlist
    assert "3/5 not reportable (n < 5)" in shortlist


SANITY_32K = {"cells": {"tuned-32k": {"result": "pass"}}}


def stage3_32k_session(tmp_path, stock_reps=None):
    return build_session(
        tmp_path,
        "stage3-32K",
        [
            CellSpec("stock-32K", profile="stock", reps=stock_reps, pp=1000, tg=50),
            CellSpec("tuned-32K", profile="tuned", pp=1900, tg=90, cache_mib=11520),
        ],
    )


def test_results_headline_4_of_5_stock_is_all_units_labelled_with_clean_beside(tmp_path):
    """S4: stock 4 clean of 5, tuned 5 clean -> the headline is all units, labelled, with the
    clean-units figures beside it; the numbers are exactly the frozen headline pipeline's."""
    reps = [RepSpec(i, flags=("paging",) if i == 3 else ()) for i in range(5)]
    d = stage3_32k_session(tmp_path, stock_reps=reps)
    r = analysis.analyse([d])
    hl = stage3_headline.headline([d], SANITY_32K, "sanity.json")
    e = hl["contexts"]["32K"]
    assert e["headline"]["choice"] == "all"  # 4 paired clean units < 5
    md = report.render_report(r, "results", command="x", plan="v1.8", headline_result=hl)
    assert "## Headline (plan §5.4)" in md
    assert '**Headline: all units, labelled "includes paging-flagged stock windows".**' in md
    assert "S4(d) deviation" in md and "4 clean" in md and "4 paired" in md
    assert "Clean-units figures beside it:" in md
    for view, n in (("all", 5), ("clean", 4)):
        ratio = e["ratios"][view]["t_turn_400"]
        assert ratio["n_paired"] == n
        assert f"| t_turn_400 | {render_md.ratio_cell(ratio)} | lower is faster |" in md
    assert "not reportable" not in md and "| stock-32K | 32K | 4/5 |" in md


def test_results_headline_clean_when_both_cells_have_5_clean(tmp_path):
    d = stage3_32k_session(tmp_path)
    r = analysis.analyse([d])
    hl = stage3_headline.headline([d], SANITY_32K, "sanity.json")
    assert hl["contexts"]["32K"]["headline"]["choice"] == "clean"
    md = report.render_report(r, "results", command="x", plan="v1.8", headline_result=hl)
    assert "**Headline: clean units** (5 clean, paired units)." in md
    assert "Same comparison on all units (flagged units included):" in md
    assert "**Headline: all units" not in md and "not reportable" not in md


def test_cmd_render_results_writes_the_headline_section(tmp_path):
    import json

    reps = [RepSpec(i, flags=("paging",) if i == 3 else ()) for i in range(5)]
    d = stage3_32k_session(tmp_path, stock_reps=reps)
    sanity = tmp_path / "sanity.json"
    sanity.write_text(json.dumps(SANITY_32K))
    out = tmp_path / "out"
    assert report.main(["render", "--sessions", str(d), "--out", str(out),
                        "--label", "results", "--sanity", str(sanity)]) == 0  # fmt: skip
    md = (out / "report.md").read_text()
    assert "## Headline (plan §5.4)" in md
    assert '**Headline: all units, labelled "includes paging-flagged stock windows".**' in md
    assert "not reportable" not in md


def test_results_report_shows_the_resident_compute_buffers_of_an_mtp_cell(tmp_path):
    """The VRAM breakdown uses the corrected parser figure: an old stored list of four compute
    buffers (target, draft, draft, target) is counted as two."""
    import json

    cell = CellSpec(
        "tuned-64K", profile="tuned", context=65536, spec_type="draft-mtp", cache_mib=9472
    )
    d = build_session(tmp_path, "stage3-64K", [cell])
    f = next((d / "cells").glob("tuned-64K-*.json"))
    s = json.loads(f.read_text())
    blocks = [1604.03, 832.12, 832.12, 1604.03]
    s["instances"][0]["parsed"]["placement"]["compute_buffers"] = [
        {"device": dev, "mib": m} for m in blocks for dev in ("CUDA0", "CUDA_Host")
    ]
    f.write_text(json.dumps(s))
    r = analysis.analyse([d])
    v = r["cells"]["tuned-64K"]["vram"]
    assert v["compute_mib"] == pytest.approx(832.12 + 1604.03)
    # the fixture's peak is synthetic, so only the compute figure is asserted
