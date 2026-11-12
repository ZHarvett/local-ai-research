"""Lint the slash commands: every script they call exists, every subcommand
they use is in wf.sh's help, frontmatter parses, and shellcheck passes."""

import re
import shutil
import subprocess

import pytest

from conftest import KIT, SCRIPTS

COMMANDS = KIT / ".claude" / "commands"
EXPECTED_COMMANDS = [
    "continue.md",
    "lane.md",
    "review.md",
    "address-review.md",
    "escalate.md",
    "status.md",
    "calibrate-reviewer.md",
]


def test_all_commands_present():
    files = sorted(p.name for p in COMMANDS.glob("*.md"))
    assert files == sorted(EXPECTED_COMMANDS)


@pytest.mark.parametrize("name", EXPECTED_COMMANDS)
def test_frontmatter_has_description(name):
    text = (COMMANDS / name).read_text()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{name}: frontmatter block missing"
    fields = dict(re.findall(r"^([a-z-]+):\s*(.*)$", m.group(1), re.M))
    assert fields.get("description"), f"{name}: no description"
    if name == "lane.md":
        assert "argument-hint" in fields


def test_no_command_reads_plan_whole():
    for name in EXPECTED_COMMANDS:
        text = (COMMANDS / name).read_text()
        assert "cat PLAN.md" not in text
        assert "Read PLAN.md" not in text


def test_every_referenced_script_exists():
    for name in EXPECTED_COMMANDS:
        text = (COMMANDS / name).read_text()
        for match in re.findall(r"scripts/(wf[-\w]*\.(?:sh|py))", text):
            assert (SCRIPTS / match).is_file(), f"{name}: scripts/{match} missing"


def test_every_subcommand_is_in_wf_help():
    help_text = subprocess.run(
        ["bash", str(SCRIPTS / "wf.sh"), "--help"],
        capture_output=True,
        text=True,
    ).stdout
    subcommands = set(re.findall(r"^    (\S+)", help_text, re.M))
    for name in EXPECTED_COMMANDS:
        text = (COMMANDS / name).read_text()
        for call in re.findall(r"wf\.sh ([a-z-]+)", text):
            assert call in subcommands, f"{name}: wf.sh {call} is not a subcommand"
        for call in re.findall(r"wf-(\w+)\.sh", text):
            wrapper = SCRIPTS / f"wf-{call}.sh"
            if wrapper.is_file():  # wf.sh matches wf-*.sh loosely; only check real ones
                body = wrapper.read_text()
                m = re.search(r"wf\.sh ([a-z-]+)", body)
                assert m and m.group(1) in subcommands


def test_all_commands_start_with_guard():
    for name in ("continue.md", "lane.md", "status.md", "review.md"):
        text = (COMMANDS / name).read_text()
        assert "wf-guard.sh" in text, f"{name}: must start with the guard"


def test_shellcheck_passes():
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed")
    scripts = sorted(SCRIPTS.glob("*.sh")) + [KIT / "bootstrap.sh", KIT / "sync.sh"]
    for script in scripts:
        proc = subprocess.run(["shellcheck", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{script}:\n{proc.stdout}{proc.stderr}"


def test_wrappers_exec_the_right_subcommand():
    cases = {
        "wf-card.sh": "card",
        "wf-plan-import.sh": "plan-import",
        "wf-guard.sh": "guard",
        "wf-progress.sh": "render",
        "wf-escalate.sh": "escalate",
        "wf-decision.sh": "decision",
        "wf-merge-lanes.sh": "merge-lanes",
    }
    for wrapper, sub in cases.items():
        body = (SCRIPTS / wrapper).read_text()
        assert f"wf.sh {sub}" in body, wrapper


def test_review_command_prints_model_and_limits_cycles():
    text = (COMMANDS / "review.md").read_text()
    assert "Running as" in text
    assert "What I did not verify" in text
    assert "RE-MEASURE" in text and "DECIDE" in text


def test_address_review_enforces_disposition_rules():
    text = (COMMANDS / "address-review.md").read_text()
    assert "BLOCKER may never be rejected" in text
    assert "RE-MEASURE and DECIDE" in text
    assert "supersede" in text


def test_continue_mentions_lane_question_and_reminder():
    text = (COMMANDS / "continue.md").read_text()
    assert "Start lane 1" in text
    assert "/lane 2" in text and "/lane 3" in text
    assert "max 3" in text
    assert "TASK T-xxx DONE" in text
