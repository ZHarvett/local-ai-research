"""Check that every decimal number in a doc traces to a named source file (T-005).

    uv run python tools/check_doc_numbers.py reports/baseline-report.md

A doc declares its sources on one or more lines, repo-root-relative (or absolute):

    <!-- sources: data/analysis/stage3/headline.md, configs/model.toml -->

Every decimal number outside fenced code blocks -- digits with a decimal point, thousands
separators allowed -- must either appear in one of those source files (separators removed on
both sides) or sit on a line that carries a ``<!-- derived: ... -->`` marker. Numbers inside
HTML comments (the sources and derived markers themselves) are never checked. Each failing
number is printed with its line number. Exit code: 0 all pass, 1 some numbers unverified,
2 usage or IO error (unreadable doc or source, or numbers present with no sources declared).

Only the standard library is used.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# A decimal number: a decimal point is required; thousands separators (commas) are allowed in
# the integer part. Integers without a decimal point (counts, MiB figures, "5", "128K") are not
# matched. The leading digit run is greedy, so "10.705" is one token, not "0.705".
NUMBER_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)\.\d+")
SOURCES_RE = re.compile(r"<!--\s*sources:\s*(.*?)\s*-->")
DERIVED_RE = re.compile(r"<!--\s*derived:.*?-->")
COMMENT_RE = re.compile(r"<!--.*?-->")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def normalize(num: str) -> str:
    """Canonical form of a number token: thousands separators removed."""
    return num.replace(",", "")


def _fence_marker(line: str) -> str | None:
    m = FENCE_RE.match(line)
    return m.group(1) if m else None


def scan(lines: list[str]) -> tuple[list[str], list[tuple[int, str, str]]]:
    """Return (source paths, numbers) for a doc's lines.

    numbers is a list of (line number, raw token, normalized token). Fenced code blocks, lines
    carrying a derived marker, and the content of HTML comments are skipped.
    """
    sources: list[str] = []
    numbers: list[tuple[int, str, str]] = []
    fence: tuple[str, int] | None = None
    for lineno, line in enumerate(lines, start=1):
        marker = _fence_marker(line)
        if fence is not None:
            ch, length = fence
            if marker and marker[0] == ch and len(marker) >= length and line.strip() == marker:
                fence = None
            continue
        if marker:
            fence = (marker[0], len(marker))
            continue
        # Outside fenced code: a sources marker here is a real declaration (one inside a fence
        # is an example, not a source). A derived marker exempts the whole line.
        for m in SOURCES_RE.finditer(line):
            sources.extend(p.strip() for p in m.group(1).split(",") if p.strip())
        if DERIVED_RE.search(line):
            continue
        content = COMMENT_RE.sub("", line)
        for m in NUMBER_RE.finditer(content):
            raw = m.group(0)
            numbers.append((lineno, raw, normalize(raw)))
    return sources, numbers


def source_numbers(paths: list[str]) -> set[str]:
    """Normalized decimal tokens found anywhere in the source files (separators removed)."""
    known: set[str] = set()
    for s in paths:
        path = Path(s)
        if not path.is_absolute():
            path = Path.cwd() / path
        text = path.read_text(encoding="utf-8")
        for m in NUMBER_RE.finditer(text):
            known.add(normalize(m.group(0)))
    return known


def check(doc: Path) -> int:
    try:
        lines = doc.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"check_doc_numbers: cannot read {doc}: {e}", file=sys.stderr)
        return 2
    sources, numbers = scan(lines)
    if not numbers:
        print(f"check_doc_numbers: {doc}: no decimal numbers to check")
        return 0
    if not sources:
        print(
            f"check_doc_numbers: {doc}: decimal numbers present but no <!-- sources: --> line",
            file=sys.stderr,
        )
        return 2
    try:
        known = source_numbers(sources)
    except OSError as e:
        print(f"check_doc_numbers: cannot read source: {e}", file=sys.stderr)
        return 2
    fails = [(ln, raw) for ln, raw, norm in numbers if norm not in known]
    for ln, raw in fails:
        print(f"{doc}:{ln}: {raw} not found in sources")
    if fails:
        print(f"check_doc_numbers: {doc}: {len(fails)} of {len(numbers)} numbers unverified")
        return 1
    print(f"check_doc_numbers: {doc}: {len(numbers)} numbers verified, {len(sources)} sources")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("doc", type=Path, help="the markdown doc to check")
    a = ap.parse_args(argv)
    return check(a.doc)


if __name__ == "__main__":
    sys.exit(main())
