"""`python -m smallpc.stage3 headline` on fixture sessions: every branch of the headline rule,
the disagreement statement, the swap sensitivity, eligibility and the refusals (WP13)."""

from __future__ import annotations

import json

import pytest

from conftest import REPO
from fixture_session import CellSpec, RepSpec, build_session
from smallpc.stage2 import eligibility
from smallpc.stage3 import cli, headline, rules

SANITY = {"cells": {"tuned-32k": {"result": "pass"}}}


def stock(reps=None, **kw):
    return CellSpec(name="stock-32K", profile="stock", pp=1000.0, tg=50.0, reps=reps, **kw)


def tuned(reps=None, **kw):
    kw = {"pp": 1900.0, "tg": 90.0, "cache_mib": 11520} | kw
    return CellSpec(name="tuned-32K", profile="tuned", reps=reps, **kw)


def run(tmp_path, cells, sanity=SANITY, sid="stage3-32K", **kw):
    d = build_session(tmp_path, sid, cells, **kw)
    return headline.headline([d], sanity, "sanity.json", allow_ineligible=False), d


def stock_flagged(*reps, slow=1.0, attempt2=False):
    out = []
    for i in range(5):
        if i in reps:
            out.append(RepSpec(i, flags=("paging",), slow=slow, faults=2500, swap_mib=700.0))
            if attempt2:
                out.append(RepSpec(i, attempt=2, flags=("paging",), slow=slow))
        else:
            out.append(RepSpec(i))
    return out


# ---------------------------------------------------------------- branch 1: clean headline


def test_clean_stock_gives_the_clean_units_headline(tmp_path):
    res, _ = run(tmp_path, [stock(), tuned()])
    e = res["contexts"]["32K"]
    assert e["tuned_eligibility"]["eligible"] and e["paired_clean_units"] == 5
    h = e["headline"]
    assert h["choice"] == "clean" and h["label"] is None and h["deviation"] is None
    r = e["ratios"]["clean"]
    assert 0.5 < r["t_turn_400"]["geomean"] < 0.7  # tuned is faster per turn
    assert r["pp_fresh@16384"]["geomean"] > 1.5 and r["tg@16384"]["n_paired"] == 5
    assert set(r) >= {"t_turn_400", "t_reread", "pp_fresh@8192", "tg@24576", "ttft@16384"}
    assert not e["disagreement"]["disagree"] and res["disagreeing_contexts"] == []
    # the same units are clean in both views, so the two ratio sets are identical
    assert e["ratios"]["all"]["t_turn_400"]["geomean"] == r["t_turn_400"]["geomean"]
    fig = e["cells"]["tuned"]["clean"]
    assert fig["n_clean"] == fig["n_total"] == 5 and fig["t_turn_400"]["ci"] is not None
    assert (
        fig["min_free_vram_mib"] == 1200.0 and fig["per_depth"]["8192"]["predicted_n"]["mean"] > 0
    )
    assert res["human_decision_needed"] == []


def test_markdown_of_the_clean_branch(tmp_path):
    res, _ = run(tmp_path, [stock(), tuned()])
    out = tmp_path / "o" / "headline"
    j, m = headline.write_outputs(res, out)
    md = m.read_text()
    assert "RESULTS" in md and "**Headline: clean units**" in md and "S4(d) deviation" not in md
    assert md.splitlines()[4].startswith("The clean-units and all-units versions agree")
    assert "tuned / stock" in md and "T_B (s)" in md and "predicted_n" in md
    assert json.loads(j.read_text())["contexts"]["32K"]["headline"]["choice"] == "clean"


# ---------------------------------------------------------------- branch 2: all-units headline


def test_two_flagged_stock_units_after_the_rerun_give_the_all_units_headline(tmp_path):
    res, _ = run(tmp_path, [stock(reps=stock_flagged(1, 2, attempt2=True)), tuned()])
    e = res["contexts"]["32K"]
    assert (
        e["cells"]["stock"]["clean"]["n_clean"] == 3
        and e["cells"]["stock"]["clean"]["n_total"] == 5
    )
    assert e["cells"]["stock"]["all"]["n_clean"] == 5  # all units counted in that view
    h = e["headline"]
    assert h["choice"] == "all" and h["label"] == "includes paging-flagged stock windows"
    assert h["deviation"].startswith("S4(d) deviation for this context")
    assert "stage3-32K:1" in h["deviation"] and "paging" in h["deviation"]
    assert [u["unit"] for u in e["cells"]["stock"]["all"]["flagged_units"]] == [
        "stage3-32K:1",
        "stage3-32K:2",
    ]
    assert e["ratios"]["clean"]["t_turn_400"]["n_paired"] == 3
    assert e["ratios"]["all"]["t_turn_400"]["n_paired"] == 5
    assert e["tuned_eligibility"]["eligible"]  # the tuned cell is clean: only stock is flagged
    md = headline.write_outputs(res, tmp_path / "h")[1].read_text()
    assert 'labelled "includes paging-flagged stock windows"' in md
    assert "S4(d) deviation for this context" in md and "Clean-units figures beside it" in md
    assert "Units with an unresolved flag (counted in this view)" in md


def test_four_clean_pairs_is_not_enough_for_the_clean_headline(tmp_path):
    res, _ = run(tmp_path, [stock(reps=stock_flagged(3, attempt2=True)), tuned()])
    assert res["contexts"]["32K"]["headline"]["choice"] == "all"  # n_clean 4 < 5


# ---------------------------------------------------------------- the two versions disagree


def test_the_two_versions_disagreeing_are_stated_in_the_first_paragraph(tmp_path):
    # tuned is a little slower than stock on the clean units (ratio below 1), but the two flagged
    # stock units are half as fast, so the all-units geometric mean goes above 1
    cells = [
        stock(reps=stock_flagged(1, 2, slow=0.3, attempt2=True)),
        tuned(pp=950.0, tg=49.0),
    ]
    res, _ = run(tmp_path, cells)
    e = res["contexts"]["32K"]
    d = e["disagreement"]
    assert d["disagree"] and res["disagreeing_contexts"] == ["32K"]
    kinds = {i["metric"]: i["kinds"] for i in d["items"]}
    assert "sign" in kinds["pp_fresh@16384"] and "sign" in kinds["tg@16384"]
    assert "DISAGREE" in d["statement"]
    c, a = e["ratios"]["clean"]["pp_fresh@16384"], e["ratios"]["all"]["pp_fresh@16384"]
    assert c["geomean"] < 1.0 < a["geomean"]
    md = headline.write_outputs(res, tmp_path / "h")[1].read_text()
    first = md.split("\n\n")[2]  # the paragraph after the title and the banner
    assert (
        first.startswith("**The clean-units and all-units versions disagree**") and "32K" in first
    )


def test_an_interval_that_excludes_one_in_only_one_version_is_a_disagreement(tmp_path):
    from smallpc.stage3 import views

    a = {"m": {"n_paired": 5, "geomean": 1.10, "ci": [1.02, 1.18], "ci_method": "t"}}
    b = {"m": {"n_paired": 5, "geomean": 1.08, "ci": [0.97, 1.20], "ci_method": "t"}}
    (item,) = views.disagreements(a, b)
    assert item["kinds"] == ["interval"]
    assert views.disagreements(a, a) == []


# ---------------------------------------------------------------- tuned cell not eligible


def test_an_ineligible_tuned_cell_is_reported_and_nothing_is_substituted(tmp_path):
    res, _ = run(tmp_path, [stock(), tuned(min_free=300.0)])
    e = res["contexts"]["32K"]
    el = e["tuned_eligibility"]
    assert not el["eligible"] and any("below 512" in x for x in el["reasons"])
    assert e["headline"]["choice"] is None and "no headline" in e["headline"]["note"]
    assert any(
        "not eligible" in h and "nothing is substituted" in h for h in res["human_decision_needed"]
    )
    assert e["cells"]["tuned"]["name"] == "tuned-32K"  # the figures are still reported
    assert e["swap_sensitivity"]["computed"] is False
    md = headline.write_outputs(res, tmp_path / "h")[1].read_text()
    assert "NOT ELIGIBLE" in md and "**Headline:** none" in md and "Human decision needed" in md


def test_sanity_missing_failed_or_for_another_file_version_makes_the_tuned_cell_ineligible(
    tmp_path,
):
    cs = [stock(), tuned()]
    for i, san in enumerate(
        [
            None,
            {"cells": {"tuned-32k": {"result": "fail"}}},
            {"cells": {"tuned-32k": {"result": "pass", "config_sha256": "0" * 64}}},
        ]
    ):
        res, _ = run(tmp_path, [CellSpec(**vars(c)) for c in cs], sanity=san, sid=f"s{i}")
        el = res["contexts"]["32K"]["tuned_eligibility"]
        assert not el["eligible"] and ("sanity" in " ".join(el["reasons"]))
    assert "different version" in el["sanity_note"]


def test_a_flagged_tuned_unit_after_the_rerun_makes_it_ineligible(tmp_path):
    reps = [RepSpec(i, flags=("paging",) if i == 2 else ()) for i in range(5)]
    res, _ = run(tmp_path, [stock(), tuned(reps=reps)])
    el = res["contexts"]["32K"]["tuned_eligibility"]
    assert not el["eligible"] and any("flagged unit" in x for x in el["reasons"])


# ---------------------------------------------------------------- swap sensitivity


def test_swap_sensitivity_removes_units_and_calls_few_pairs_inconclusive(tmp_path):
    reps = [RepSpec(i, swap_mib=300.0 if i < 4 else 1.0) for i in range(5)]
    res, _ = run(tmp_path, [stock(), tuned(reps=reps)])
    sw = res["contexts"]["32K"]["swap_sensitivity"]
    assert [u["unit"] for u in sw["removed"]] == [f"stage3-32K:{i}" for i in range(4)]
    assert sw["paired_units_left"] == 1 and sw["inconclusive"] is True and sw["changes"] == []
    assert "inconclusive: 1 paired unit(s) left, fewer than 2" in sw["note"]


def test_swap_sensitivity_with_enough_pairs_reports_no_change(tmp_path):
    reps = [RepSpec(i, swap_mib=300.0 if i == 0 else 1.0) for i in range(5)]
    res, _ = run(tmp_path, [stock(), tuned(reps=reps)])
    sw = res["contexts"]["32K"]["swap_sensitivity"]
    assert len(sw["removed"]) == 1 and sw["paired_units_left"] == 4 and not sw["inconclusive"]
    # a unit less moves a tight interval by more than its half-width; the sign never changes here
    assert all(c["what"].startswith("interval moved") for c in sw["changes"])
    assert sw["note"].startswith(("headline comparison changes", "no sign change"))


def test_swap_sensitivity_without_heavy_units_has_nothing_to_remove(tmp_path):
    res, _ = run(tmp_path, [stock(), tuned()])
    sw = res["contexts"]["32K"]["swap_sensitivity"]
    assert sw["removed"] == [] and "nothing to remove" in sw["note"]


# ---------------------------------------------------------------- provenance and refusals


def test_provenance_names_sessions_commit_plan_rules_and_config_files(tmp_path):
    res, d = run(tmp_path, [stock(), tuned()])
    p = res["provenance"]
    assert p["plan_version"] == "1.7" and p["sessions"][0]["session_id"] == "stage3-32K"
    assert p["code"]["commit"] and set(p["rule_text"]) == set(rules.RULE_NAMES) | {"Stage 4"}
    assert p["rule_text"]["Headline rule"].startswith(
        "- **Headline rule.** The headline for a context is"
    )
    assert (
        sorted(p["config_file_sha256"])
        == [f"{w}-{k}k.toml" for w in ("stock", "tuned") for k in (128, 32, 64)]
        or len(p["config_file_sha256"]) == 6
    )
    assert p["eligibility_override"] is False and res["label"] == "results"


@pytest.mark.parametrize(
    ("kw", "needle"),
    [
        ({"allow_dirty": True}, "allow_dirty"),
        ({"state": "interrupted"}, "not 'complete'"),
        ({"spec_path": "configs/sweeps/ft-stage3.toml"}, "functional-test"),
    ],
)
def test_sessions_that_may_not_drive_a_headline_are_refused(tmp_path, kw, needle):
    d = build_session(tmp_path, "stage3-32K", [stock(), tuned()], **kw)
    with pytest.raises(eligibility.Refused, match=needle):
        headline.headline([d], SANITY, "s.json")


def test_a_functional_test_session_id_is_refused(tmp_path):
    d = build_session(tmp_path, "ft-stage3-32K", [stock(), tuned()])
    with pytest.raises(eligibility.Refused, match="functional-test prefix"):
        headline.headline([d], SANITY, "s.json")


def test_the_command_line_has_no_way_around_the_refusal(tmp_path, capsys):
    d = build_session(tmp_path, "ft-stage3-32K", [stock(), tuned()])
    san = tmp_path / "sanity.json"
    san.write_text(json.dumps(SANITY))
    rc = cli.main(
        ["headline", "--sessions", str(d), "--sanity", str(san), "--out", str(tmp_path / "o")]
    )
    assert rc == 2 and "refused" in capsys.readouterr().err and not (tmp_path / "o.json").exists()


def test_the_override_for_unit_tests_is_recorded_in_the_output(tmp_path):
    d = build_session(tmp_path, "ft-stage3-32K", [stock(), tuned()])
    res = headline.headline([d], SANITY, "s.json", allow_ineligible=True)
    assert res["provenance"]["eligibility_override"] is True
    assert "override used" in headline.write_outputs(res, tmp_path / "x")[1].read_text()


def test_the_command_line_writes_json_and_markdown_and_prints_the_branch(tmp_path, capsys):
    d = build_session(
        tmp_path, "stage3-32K", [stock(reps=stock_flagged(1, 2, attempt2=True)), tuned()]
    )
    san = tmp_path / "sanity.json"
    san.write_text(json.dumps(SANITY))
    rc = cli.main(
        ["headline", "--sessions", str(d), "--sanity", str(san), "--out", str(tmp_path / "o")]
    )
    out = capsys.readouterr().out
    assert rc == 0 and (tmp_path / "o.json").exists() and (tmp_path / "o.md").exists()
    assert "32K: headline all (includes paging-flagged stock windows)" in out


def test_the_rule_text_is_the_plans_text_verbatim():
    r = rules.stage_rules(REPO)
    plan = (REPO / "docs/plans/step-0-baseline.md").read_text()
    for text in r.values():
        assert text in plan
    assert "at least 5 clean, paired units" in r["Headline rule"]
