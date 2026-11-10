"""The rule text of plan v1.6 that the Stage 2 tools apply, quoted verbatim (WP12).

Every constant is a line (or paragraph) of ``docs/plans/step-0-baseline.md``; ``tests/test_stage2_rules.py`` fails
if the plan and these constants drift apart. The spec generator puts the relevant text in the header of
every spec it writes, and the decision tool puts it in every output.
"""

# ruff: noqa: E501  (the constants are the plan's lines, verbatim)
from __future__ import annotations

import re
from pathlib import Path

from ..config import repo_root

PLAN_PATH = "docs/plans/step-0-baseline.md"

RULE_TOP = (
    '"Top" means first in the Stage 1 order, even where the pair is too close to call at n = 2.'
)

INTRO = 'Stage 2 starts from the Stage 1 shortlist: for each context, the two eligible placements with the lowest mean T_turn_400 (all six are `-b 4096`; at 32K and 64K one is P6 and one is P2, and at 128K the pair is P2 and P6 in the same way). "Top" means first in the Stage 1 order, even where the pair is too close to call at n = 2. Every Stage 2 cell is a candidate cell with the §5.4 defaults, `-lv 4` and `--metrics`, runs 5 repetitions, and each sub-stage is its own session with its own start and end canaries. The decision rules below are declared before any Stage 2 measurement.'

RULE_2F = "- **2f Host prompt cache (`--cache-ram`). Runs first.** Reason: in Stage 1, 14 of 38 windows at 128K and one at 64K were paging-flagged, all in the second repetition of a long-running server, in cells with a large memory-mapped model. The 15 re-runs on fresh servers were all clean, and the server's anonymous memory grew in step with its host prompt cache (default 8,192 MiB), which every unique benchmark prompt fills. That points to host-memory pressure on a 32 GB machine, and the benchmark's requests never hit that cache, so it only costs memory here. Cells, with MTP off: the top placement at 128K with `--cache-ram` 8192 (the default), 4096, 2048 and 0; and at 64K with 8192 and 2048. Rule: the chosen value is the largest tested value with no paging-flagged window in any of its 5 repetitions, unless its mean T_turn_400 is more than 3% above the mean of the 8192 cell's clean units. If the 8192 cell is already clean, the default stays. If no tested value is clean, stop and report: the cause is then not the host cache. The chosen value is used in every later candidate cell and in the tuned configs. Stock keeps the default. The trade-off is documented: a small host cache means that switching between conversations re-reads the prompt instead of restoring it (this matters for Step 5)."

RULE_2A = "- **2a MTP.** Per context, 6 cells: both shortlisted placements with MTP off (these are also the 5-repetition measurement of the shortlist), the top placement with draft lengths 1, 2 and 3, and the second placement with the best draft length of the top placement. The best draft length is chosen by the §3.3 rules among the three; if the CIs include zero, the smaller draft length wins. Cache sizes of P6 cells are re-probed with MTP on, because the head and its draft context cost VRAM. Record acceptance, and the effect on decode **and on prefill**. MTP joins a tuned config only if it wins by §3.3 on T_turn_400 and passes the output sanity check."

RULE_2B = "- **2b KV type.** FP16 vs 8-bit KV at 64K, on the 2a winner at 64K, with the cache re-probed for the FP16 cell."

RULE_2C = "- **2c Load mode.** `--load-mode` at 64K on the 2a winner, with paging metrics: `auto` against one alternative chosen from the build's own help text and source. Modes that need `sudo` or a raised memory-lock limit are excluded (the limit here is 8 MiB). The choice and its reasoning are recorded before the run."

RULE_2D = "- **2d Threads (optional).** `-t 8` against the default at 64K, only if the default differs (check the effective thread count in the log); otherwise skipped and recorded."

RULE_2E = "- **2e llama-bench cross-check.** llama-bench at the nearest configuration it supports at 64K, labelled as a cross-check and never used for a decision, to show how far random-token numbers differ from real-prompt numbers. Fields llama-bench cannot express (for example `--moe-cache-mib`) are listed."

RULE_SANITY_STAGE = "- **Output sanity check (§5.6).** On the 2a winner and runner-up of each context and on the plain `--fit` reference of the same context, before Stage 3."

ORDER = "Order: 2f, 2a, 2b, 2c, 2d, then the sanity check and 2e. The 2a spec is generated from the Stage 1 shortlist and the 2f result by a tool, and the second placement's cell from the 2a main result."

RULE_33 = 'A candidate is eligible for a context if:\n- its final cell status is complete (it started without errors and finished);\n- the minimum free VRAM across its measured windows, in the final attempt, is at least 512 MiB;\n- it has no unresolved flagged unit, where a unit is one repetition and an attempt-2 unit replaces the attempt-1 unit it re-ran;\n- it has enough clean units: 2 in screening, 5 in final selection;\n- it has not failed the output sanity check (§5.6). In screening the check may be "not run". In final selection it must have passed.\n\nAmong eligible candidates, order them by the **mean T_turn_400** (the estimated standardised turn, §5.3): the mean over repetitions of each repetition\'s mean over the three depths of §5.3. A repetition counts only if all three depths are clean. Final selection then compares the best-mean candidate with the runner-up, using the paired per-repetition difference of T_turn_400 and its 95% CI (§5.5):\n1. If the CI excludes zero, the best-mean candidate wins.\n2. If the CI includes zero, compare the paired difference of **T_reread** in the same way. If that CI excludes zero, the candidate with the lower mean T_reread wins.\n3. If both CIs include zero, the candidates are tied on speed: prefer fewer moving parts, which means no MTP over MTP, then no expert cache over a cache.\n4. If still tied, prefer the lower peak VRAM use (total minus the minimum free VRAM over its windows).\n\nAny other eligible candidate whose paired T_turn_400 difference from the winner has a CI that includes zero is reported as "statistically tied with the winner", for information only. Screening (2 repetitions) applies no tie-break: its shortlist is simply the two eligible candidates with the lowest mean T_turn_400 per context, and pairs whose means differ by less than the larger of their two ranges are marked "too close to call at n = 2". The stock cell is a reference row and is never shortlisted.'

RULES_BY_STAGE = {
    "2f": (RULE_TOP, RULE_2F),
    "2a": (RULE_TOP, RULE_2A, RULE_33),
    "2a2": (RULE_TOP, RULE_2A, RULE_33),
    "2b": (RULE_2B, RULE_33),
    "2c": (RULE_2C, RULE_33),
    "2d": (RULE_2D, RULE_33),
}


def plan_version(root: Path | None = None) -> str:
    """The plan's version from line 3 (``*Version 1.6 · 10 November 2026*``), e.g. ``1.6``."""
    line = (Path(root) if root else repo_root()).joinpath(PLAN_PATH).read_text().splitlines()[2]
    m = re.match(r"\*Version (\d+\.\d+)\b", line)
    if not m:
        raise ValueError(f"cannot read the plan version from line 3: {line!r}")
    return m.group(1)
