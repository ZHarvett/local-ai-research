"""The rule text the Stage 2 tools quote must be the plan's text, verbatim (plan v1.7)."""

from __future__ import annotations

import pytest

from conftest import REPO
from smallpc.stage2 import rules

PLAN = (REPO / rules.PLAN_PATH).read_text()
NAMES = [n for n in dir(rules) if n.startswith("RULE_")] + ["INTRO", "ORDER"]


@pytest.mark.parametrize("name", NAMES)
def test_every_constant_is_a_verbatim_part_of_the_plan(name):
    text = getattr(rules, name)
    assert text and text in PLAN, name


def test_the_rules_say_what_the_decision_tool_implements():
    assert "no paging-flagged window in any of its 5 repetitions" in rules.RULE_2F
    assert "more than 3% above the mean of the 8192 cell's clean units" in rules.RULE_2F
    assert "If the 8192 cell is already clean, the default stays" in rules.RULE_2F
    assert "If no tested value is clean, stop and report" in rules.RULE_2F
    assert "if the CIs include zero, the smaller draft length wins" in rules.RULE_2A
    assert rules.RULE_TOP == (
        '"Top" means first in the Stage 1 order, even where the pair is too close to call at n = 2.'
    )
    assert "T_reread" in rules.RULE_33 and "prefer fewer moving parts" in rules.RULE_33


def test_the_plan_version_is_read_from_line_3():
    assert rules.plan_version(REPO) == "1.7"
