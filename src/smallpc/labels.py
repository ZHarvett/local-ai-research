"""Data labels shown at the top of a report and over every table (step plan 5.5 / WP10).

Screening and functional-test data are never reported as results: the label says so wherever
numbers appear. ``MIN_REPORTABLE_N`` is the repetition count below which a cell is marked
"not reportable".
"""

from __future__ import annotations

LABELS = ("functional-test", "screening", "results")
MIN_REPORTABLE_N = 5

BANNER = {
    "functional-test": "FUNCTIONAL-TEST DATA. Produced to test the tooling. Not a result of this "
    "study; do not quote these numbers.",
    "screening": "SCREENING DATA (2 repetitions). Used only for shortlisting, never reported as "
    "results.",
    "results": "RESULTS. Only cells with at least 5 clean repetitions are reportable.",
}
SHORT = {"functional-test": "functional-test", "screening": "screening", "results": "results"}
NOT_REPORTABLE = f"not reportable (n < {MIN_REPORTABLE_N})"


def banner(label: str | None) -> str:
    if label is None:
        return ""
    if label not in BANNER:
        raise ValueError(f"unknown label {label!r}; use one of {', '.join(LABELS)}")
    return BANNER[label]
