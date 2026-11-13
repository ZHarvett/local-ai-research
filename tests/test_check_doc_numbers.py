"""tools/check_doc_numbers.py (T-005, S1)."""

from __future__ import annotations

import importlib.util

from conftest import REPO

spec = importlib.util.spec_from_file_location(
    "check_doc_numbers", REPO / "tools" / "check_doc_numbers.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def _doc(tmp_path, text, name="doc.md"):
    p = tmp_path / name
    p.write_text(text)
    return p


def _src(tmp_path, text, name="source.md"):
    p = tmp_path / name
    p.write_text(text)
    return p


# --- token extraction ---------------------------------------------------------------------


def test_number_regex_requires_a_decimal_point():
    found = tool.NUMBER_RE.findall("5 128K 1,379 0.705 8.339 1,379.5 14,926.0 21,713,463,040")
    assert found == ["0.705", "8.339", "1,379.5", "14,926.0"]


def test_number_regex_keeps_the_whole_leading_run():
    assert tool.NUMBER_RE.findall("10.705 and 0.705") == ["10.705", "0.705"]
    assert tool.NUMBER_RE.findall("0.705.") == ["0.705"]  # trailing sentence dot is not part


def test_normalize_removes_thousands_separators():
    assert tool.normalize("1,379.5") == "1379.5"
    assert tool.normalize("14,926.0") == "14926.0"
    assert tool.normalize("0.705") == "0.705"


def test_scan_skips_fenced_code():
    lines = [
        "real 0.705 here",
        "```",
        "hidden 9.999 inside fence",
        "```",
        "tail 8.339",
    ]
    _, numbers = tool.scan(lines)
    assert [raw for _, raw, _ in numbers] == ["0.705", "8.339"]


def test_scan_skips_fenced_code_with_info_string_and_tildes():
    lines = ["a 1.5", "```python", "x 9.999", "```", "b 2.5", "~~~", "y 8.888", "~~~", "c 3.5"]
    _, numbers = tool.scan(lines)
    assert [raw for _, raw, _ in numbers] == ["1.5", "2.5", "3.5"]


def test_scan_derived_line_is_exempt():
    lines = ["point 0.705 <!-- derived: ratio of two source means -->", "plain 8.339"]
    _, numbers = tool.scan(lines)
    assert [raw for _, raw, _ in numbers] == ["8.339"]


def test_scan_ignores_numbers_inside_comments():
    lines = ["<!-- sources: a.md, b.md -->", "value 0.705 <!-- note 9.999 -->", "x 1.25"]
    sources, numbers = tool.scan(lines)
    assert sources == ["a.md", "b.md"]
    assert [raw for _, raw, _ in numbers] == ["0.705", "1.25"]


def test_scan_collects_multiple_sources_lines():
    lines = ["<!-- sources: a.md, b.md -->", "text", "<!-- sources: c.md -->"]
    sources, _ = tool.scan(lines)
    assert sources == ["a.md", "b.md", "c.md"]


def test_scan_ignores_sources_marker_inside_fenced_code():
    lines = ["<!-- sources: real.md -->", "```", "<!-- sources: example.md -->", "```", "x 1.5"]
    sources, numbers = tool.scan(lines)
    assert sources == ["real.md"]
    assert [raw for _, raw, _ in numbers] == ["1.5"]


def test_scan_reports_line_numbers():
    lines = ["first 0.705", "", "third 8.339"]
    _, numbers = tool.scan(lines)
    assert [(ln, raw) for ln, raw, _ in numbers] == [(1, "0.705"), (3, "8.339")]


# --- end-to-end check ---------------------------------------------------------------------


def test_pass_when_number_appears_in_source(tmp_path):
    src = _src(tmp_path, "t_turn_400 ratio 0.705 [0.672, 0.739]")
    doc = _doc(tmp_path, f"<!-- sources: {src} -->\nThe ratio is 0.705 [0.672, 0.739].\n")
    assert tool.check(doc) == 0


def test_fail_when_number_missing_prints_line_number(tmp_path, capsys):
    src = _src(tmp_path, "ratio 0.705")
    doc = _doc(tmp_path, f"<!-- sources: {src} -->\nline one\nratio 0.999 here\n")
    assert tool.check(doc) == 1
    out = capsys.readouterr().out
    assert "doc.md:3: 0.999 not found in sources" in out


def test_thousands_separators_removed_on_both_sides(tmp_path):
    src = _src(tmp_path, "minimum free VRAM 1379.0 MiB")
    doc = _doc(tmp_path, f"<!-- sources: {src} -->\nminimum free VRAM 1,379.0 MiB\n")
    assert tool.check(doc) == 0
    # and the other direction: comma in the source, plain in the doc
    src2 = _src(tmp_path, "peak 14,926.0 MiB", name="source2.md")
    doc2 = _doc(tmp_path, f"<!-- sources: {src2} -->\npeak 14926.0 MiB\n", name="doc2.md")
    assert tool.check(doc2) == 0


def test_derived_number_passes_without_a_source_match(tmp_path):
    src = _src(tmp_path, "sessions 90 minutes, re-runs 38 minutes")
    doc = _doc(
        tmp_path,
        f"<!-- sources: {src} -->\nStage 3 took 2.1 hours <!-- derived: (90+38)/60 -->\n",
    )
    assert tool.check(doc) == 0


def test_fenced_code_number_is_not_required(tmp_path):
    src = _src(tmp_path, "ratio 0.705")
    doc = _doc(
        tmp_path,
        f"<!-- sources: {src} -->\nratio 0.705\n```\nllama-server -c 32768 --moe-cache-mib 11520.5\n```\n",
    )
    assert tool.check(doc) == 0


def test_number_in_second_source_passes(tmp_path):
    s1 = _src(tmp_path, "ratio 0.705", name="s1.md")
    s2 = _src(tmp_path, "peak 14926.0", name="s2.md")
    doc = _doc(tmp_path, f"<!-- sources: {s1}, {s2} -->\nratio 0.705 peak 14926.0\n")
    assert tool.check(doc) == 0


def test_relative_source_resolved_against_cwd(tmp_path, monkeypatch):
    _src(tmp_path, "ratio 0.705", name="source.md")
    doc = _doc(tmp_path, "<!-- sources: source.md -->\nratio 0.705\n")
    monkeypatch.chdir(tmp_path)
    assert tool.check(doc) == 0


def test_missing_source_file_is_error(tmp_path):
    doc = _doc(tmp_path, f"<!-- sources: {tmp_path / 'nope.md'} -->\nratio 0.705\n")
    assert tool.check(doc) == 2


def test_numbers_with_no_sources_line_is_error(tmp_path):
    doc = _doc(tmp_path, "ratio 0.705 with no sources declared\n")
    assert tool.check(doc) == 2


def test_no_numbers_passes(tmp_path):
    doc = _doc(tmp_path, "just text, counts like 5 and 128K, no decimals\n")
    assert tool.check(doc) == 0


def test_unreadable_doc_is_error(tmp_path):
    assert tool.check(tmp_path / "missing.md") == 2


def test_main_returns_check_code(tmp_path):
    src = _src(tmp_path, "ratio 0.705")
    doc = _doc(tmp_path, f"<!-- sources: {src} -->\nratio 0.705\n")
    assert tool.main([str(doc)]) == 0
