"""The Stage 3 and Stage 4 rule text of the plan, read from ``docs/plans/step-0-baseline.md`` at run
time (so it is verbatim by construction) and the constants the tools apply."""

from __future__ import annotations

import re
from pathlib import Path

from ..config import repo_root
from ..stage2.rules import PLAN_PATH, plan_version

MIN_CLEAN_PAIRED = 5  # headline rule: clean, paired units per cell for the clean-units headline
STOCK_LABEL = "includes paging-flagged stock windows"
RULE_NAMES = (
    "Configurations",
    "Sessions",
    "Re-runs",
    "Stock paging",
    "Headline rule",
    "Tuned cells",
    "Reported figures",
)
S4D = (
    "No selected or recommended configuration, and no headline number, rests on a measurement "
    "with an unresolved flag."
)

__all__ = ["MIN_CLEAN_PAIRED", "STOCK_LABEL", "RULE_NAMES", "S4D", "plan_version", "stage_rules"]


def stage_rules(root: Path | None = None) -> dict[str, str]:
    """``{rule name: text}`` of the Stage 3 bullets and ``"Stage 4"``, verbatim from the plan."""
    lines = (Path(root) if root else repo_root()).joinpath(PLAN_PATH).read_text().splitlines()
    out: dict[str, str] = {}
    for line in lines:
        for name in RULE_NAMES:
            if line.startswith(f"- **{name}.**"):
                out[name] = line
        if line.startswith("Stock-64K and tuned-64K, 5 repetitions each"):
            out["Stage 4"] = line
    missing = [n for n in (*RULE_NAMES, "Stage 4") if n not in out]
    if missing:
        raise ValueError(f"{PLAN_PATH}: Stage 3/4 rule(s) not found: {missing}")
    return out


def s4d_text() -> str:
    return re.sub(r"\s+", " ", S4D)
