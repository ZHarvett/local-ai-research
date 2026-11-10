"""tools/stage2_paging_sensitivity.py on fixture sessions (WP12 part 2d, C.2)."""

from __future__ import annotations

import importlib.util

from conftest import REPO
from fixture_session import RepSpec
from smallpc import select
from test_stage2_decide import c2a, fake_git, second_for, session_2a, top_for  # noqa: F401

spec = importlib.util.spec_from_file_location(
    "stage2_paging_sensitivity", REPO / "tools" / "stage2_paging_sensitivity.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def reps_with_paging_unit():
    return [RepSpec(i, flags=("paging",) if i == 4 else (), faults=1500 if i == 4 else 40)
            for i in range(5)]  # fmt: skip


def cells(ctx, *, mtp1_flagged, mtp1_free=1200.0):
    top, sec = top_for(ctx), second_for(ctx)
    out = [c2a(ctx, top, 0, tg=80.0)]
    kw = dict(reps=reps_with_paging_unit()) if mtp1_flagged else {}
    out.append(c2a(ctx, top, 1, tg=125.0, min_free=mtp1_free, **kw))
    out += [c2a(ctx, top, 2, tg=100.0), c2a(ctx, top, 3, tg=90.0), c2a(ctx, sec, 0, tg=80.0)]
    return out


def test_a_paging_only_cell_is_treated_as_eligible_and_the_decision_can_change(tmp_path):
    d = session_2a(tmp_path, {"32K": cells("32K", mtp1_flagged=True)})
    out = tool.sensitivity("2a", [d], root=REPO, git=fake_git)
    assert list(out["treated_as_eligible"]) == ["s2a-P6-32K-b4096-mtp1"]
    assert out["by_rule"]["32K"]["best_draft_length"] == 2  # mtp1 is out by the rule
    assert out["if_treated_eligible"]["32K"]["best_draft_length"] == 1
    assert out["decision_changes"] and "best_draft_length" in out["changes"]["32K"]
    assert select.eligibility is tool._ORIGINAL  # the patch is always removed


def test_a_cell_ineligible_for_vram_as_well_is_not_treated(tmp_path):
    d = session_2a(tmp_path, {"32K": cells("32K", mtp1_flagged=True, mtp1_free=400.0)})
    out = tool.sensitivity("2a", [d], root=REPO, git=fake_git)
    assert out["treated_as_eligible"] == {} and not out["decision_changes"]


def test_no_paging_cell_no_change(tmp_path):
    d = session_2a(tmp_path, {"32K": cells("32K", mtp1_flagged=False)})
    out = tool.sensitivity("2a", [d], root=REPO, git=fake_git)
    assert out["treated_as_eligible"] == {} and out["changes"] == {}
