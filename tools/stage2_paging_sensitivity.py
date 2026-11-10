"""Read-only sensitivity of a Stage 2 decision to paging (WP12 part 2d, step C.2).

Recomputes the 2a (or 2a2) decision with every cell that is ineligible ONLY because of
paging-flagged units (no VRAM, status or sanity reason; every flagged unit flagged ``paging``;
at least 2 clean units) treated as eligible on its clean units, and compares it with the decision
by the rule. Information only: the rule's result stands. Writes nothing to data/raw/.

    uv run python tools/stage2_paging_sensitivity.py --stage 2a \\
        --sessions data/raw/s2a-32K data/raw/s2a-64K data/raw/s2a-128K \\
        --out data/analysis/stage2/2a-paging-sensitivity
"""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from smallpc import select
from smallpc.stage2 import decide

_ORIGINAL = select.eligibility


def paging_only(cell: dict, el: dict) -> bool:
    """Ineligible, and the only reasons are the flagged units and the clean-unit shortfall they
    cause, all of the ``paging`` kind."""
    if el["eligible"] or not cell["flagged_units"] or cell["n_clean"] < 2:
        return False
    if set(cell["unit_flags"]) != {"paging"}:
        return False
    return all(r.startswith(("flagged unit", "n_clean ")) for r in el["reasons"])


def make_patched(treated: dict[str, dict]):
    def patched(cell: dict, mode: str, sanity: dict | None = None) -> dict:
        el = _ORIGINAL(cell, mode, sanity)
        if paging_only(cell, el):
            treated[cell["name"]] = {
                "reasons": el["reasons"],
                "n_clean": cell["n_clean"],
                "n_total": cell["n_total"],
            }
            return {**el, "eligible": True, "reasons": []}
        return el

    return patched


def summary_2a(res: dict) -> dict:
    out = {}
    for ctx, e in res["contexts"].items():
        m = e.get("mtp_vs_off")
        out[ctx] = {
            "best_draft_length": e["draft_length"]["best_n"],
            "tied_draft_lengths": e["draft_length"].get("tied"),
            "mtp_wins_on_t_turn_400": None if not m else m["mtp_wins_on_t_turn_400"],
            "mtp_vs_off_winner": None if not m else m["winner"],
            "off_minus_mtp": None if not m else m["t_turn_400_difference_off_minus_mtp"],
            "top_config_mtp": e["top_config"]["mtp"],
            "second_mtps": e["input_2a2"].get("second_mtps"),
            "borrowed_draft_lengths": e.get("borrowed_draft_lengths", []),
            "human_decision_needed": e["human_decision_needed"],
        }
    return out


def summary_2a2(res: dict) -> dict:
    out = {}
    for ctx, e in res["contexts"].items():
        out[ctx] = {
            "status": e["status"],
            "winner": e.get("winner"),
            "runner_up": e.get("runner_up"),
            "decision": (e.get("decision") or {}).get("step")
            if isinstance(e.get("decision"), dict)
            else e.get("decision"),
            "tied_with_winner": e.get("tied_with_winner"),
        }
    return out


KEYS_2A = (
    "best_draft_length",
    "mtp_wins_on_t_turn_400",
    "mtp_vs_off_winner",
    "top_config_mtp",
    "second_mtps",
)
KEYS_2A2 = ("status", "winner", "runner_up", "tied_with_winner")


def sensitivity(stage: str, sessions: list[Path], **decide_kw) -> dict:
    """The decision by the rule and with paging-only cells treated as eligible, and the differences."""
    summarize, keys = (summary_2a, KEYS_2A) if stage == "2a" else (summary_2a2, KEYS_2A2)
    base = decide.decide(stage, sessions, **decide_kw)
    treated: dict[str, dict] = {}
    select.eligibility = make_patched(treated)  # type: ignore[assignment]
    try:
        alt = decide.decide(stage, sessions, **decide_kw)
    finally:
        select.eligibility = _ORIGINAL
    sb, sa = summarize(base), summarize(alt)
    changes = {
        ctx: {
            k: {"by_rule": sb[ctx][k], "if_treated_eligible": sa[ctx][k]}
            for k in keys
            if sb[ctx][k] != sa[ctx][k]
        }
        for ctx in sb
    }
    changes = {c: v for c, v in changes.items() if v}
    return {
        "stage": stage,
        "sessions": [str(x) for x in sessions],
        "keys": list(keys),
        "treated_as_eligible": treated,
        "by_rule": sb,
        "if_treated_eligible": sa,
        "changes": changes,
        "decision_changes": bool(changes),
        "note": "information only; the declared rule's result stands",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", required=True, choices=["2a", "2a2"])
    ap.add_argument("--sessions", nargs="+", required=True, type=Path)
    ap.add_argument("--out", type=Path, required=True, help="base name; writes .json and .md")
    a = ap.parse_args(argv)
    out = sensitivity(a.stage, a.sessions)
    treated, sb, sa, changes, keys = (
        out["treated_as_eligible"], out["by_rule"], out["if_treated_eligible"], out["changes"], out["keys"],
    )  # fmt: skip
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.with_suffix(".json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    md = [
        f"# Stage {a.stage}: sensitivity to paging-flagged cells",
        "",
        "Read-only recomputation (`tools/stage2_paging_sensitivity.py`). Every cell that is ineligible only because of paging-flagged units is treated as eligible on its clean units. Information only: the declared rule's result stands.",
        "",
    ]
    md += ["## Cells treated as eligible", ""]
    if treated:
        md += ["| cell | n_clean/n_total | reasons by the rule |", "|---|---|---|"]
        md += [
            f"| `{c}` | {t['n_clean']}/{t['n_total']} | {'; '.join(t['reasons'])} |"
            for c, t in treated.items()
        ]
    else:
        md += ["None: no cell is ineligible only because of paging."]
    md += [
        "",
        "## Decision by context",
        "",
        "| context | " + " | ".join(keys) + " |",
        "|---|" + "---|" * len(keys),
    ]
    for ctx in sb:
        cells = []
        for k in keys:
            x, y = sb[ctx][k], sa[ctx][k]
            cells.append(f"{x}" if x == y else f"**{x} -> {y}**")
        md.append(f"| {ctx} | " + " | ".join(cells) + " |")
    md += ["", f"**Any decision changes: {'YES' if changes else 'no'}.**", ""]
    if changes:
        md += ["```json", json.dumps(changes, indent=1, default=str), "```", ""]
    a.out.with_suffix(".md").write_text("\n".join(md))
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
