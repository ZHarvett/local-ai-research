"""smallpc.smoke: probe verdicts, event summaries and the independent verification."""

from __future__ import annotations

import json
import shutil
import sys

from conftest import FIXTURES
from smallpc import smoke

TOY = FIXTURES / "toy-task"


def oc_tool(tool, status, error=None, output="x"):
    part = {
        "tool": tool,
        "state": {"status": status, "input": {}, "error": error, "output": output},
    }
    return json.dumps({"type": "tool_use", "part": part})


RULE = "The user has specified a rule which prevents you from using this specific tool call."


def test_probe_script_matches_the_expectations_and_is_valid_json():
    for kind, probe in smoke.PROBES.items():
        script = smoke.probe_script(kind)
        assert len(script) == len(probe) and script[-1] == {"text": "done"}
        json.dumps(script)


def test_opencode_probe_verdicts_pass_and_fail_closed_when_a_deny_is_missed():
    expected = [e for _, e, _ in smoke.OPENCODE_PROBE if e != "-"]
    lines = []
    for e in expected:
        if e == "ok":
            lines.append(oc_tool("bash", "completed"))
        else:
            lines.append(oc_tool("bash", "error", RULE))
    summ = smoke.opencode_summary("\n".join(lines))
    checks = smoke.probe_checks("opencode", summ)
    assert all(c["pass"] for c in checks), [c for c in checks if not c["pass"]]
    # a denied command that actually ran is reported as a failure
    lines[expected.index("denied")] = oc_tool("bash", "completed")
    bad = smoke.probe_checks("opencode", smoke.opencode_summary("\n".join(lines)))
    assert [c["check"] for c in bad if not c["pass"]] == ["curl"]


def test_prompts_in_a_real_probe_are_counted_from_the_debug_log():
    log = 'level=INFO run=1 message=asking id=per_1 permission=bash patterns="[]"\n'
    summ = smoke.opencode_summary("", log + "! permission requested: bash; auto-rejecting\n")
    assert summ["permission_asks"] == 1 and summ["auto_rejected"] == 1
    checks = smoke.probe_checks("opencode", summ)
    assert [c["pass"] for c in checks if c["check"] == "permission prompts raised"] == [False]


def test_ask_probe_expects_exactly_one_prompt_and_a_rejection():
    ev = oc_tool("bash", "error", "The user rejected permission to use this specific tool call.")
    log = " message=asking id=per_9 permission=bash\nauto-rejecting\n"
    checks = smoke.probe_checks("opencode-ask", smoke.opencode_summary(ev, log))
    assert all(c["pass"] for c in checks), checks


def test_dsh_summary_and_probe_outcomes():
    ev = "\n".join(
        json.dumps(e)
        for e in [
            {"type": "status", "phase": "step_start", "step": 1},
            {"type": "tool_call", "callId": "c1", "tool": "write", "input": {}},
            {
                "type": "tool_result",
                "callId": "c1",
                "status": "error",
                "result": "Error: sandbox escalation requires approval, but no approval channel is "
                "available",
            },
            {"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}},
            {"type": "final", "text": "done"},
        ]
    )
    s = smoke.dsh_summary(ev)
    assert s["steps"] == 1 and s["final_text"] == "done" and s["turn_end"] == {"kind": "completed"}
    assert smoke._outcome(s["tool_uses"][0], "dsh") == "rejected"


def test_verify_requires_green_pytest_and_an_untouched_test_file(tmp_path):
    scratch = tmp_path / "s"
    shutil.copytree(TOY, scratch)
    red = smoke.verify(scratch, TOY, sys.executable)
    assert not red["pass"] and red["test_file_byte_identical"] and not red["pytest_green"]
    mod = scratch / "movavg.py"
    mod.write_text(mod.read_text().replace("len(values) - window)", "len(values) - window + 1)"))
    green = smoke.verify(scratch, TOY, sys.executable)
    assert green["pass"] and green["changed_files"] == ["movavg.py"]
    (scratch / "test_movavg.py").write_text("def test_x():\n    pass\n")  # cheating
    cheat = smoke.verify(scratch, TOY, sys.executable)
    assert cheat["pytest_green"] and not cheat["test_file_byte_identical"] and not cheat["pass"]


def test_merge_patterns_keeps_the_label(tmp_path):
    p = tmp_path / "a.json"
    p.write_text(json.dumps({"harness": "opencode"}))
    m = smoke.merge_patterns([str(p)])
    assert m["label"] == "smoke-task data, not representative of real agent turns"
    assert m["runs"] == [{"harness": "opencode"}]
