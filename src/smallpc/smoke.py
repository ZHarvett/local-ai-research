"""Helpers for the harness smoke tests (WP7): permission probes, event summaries, verification.

    python -m smallpc.smoke probe-script opencode|opencode-ask|dsh --out FILE
    python -m smallpc.smoke probe-check opencode|opencode-ask|dsh --events FILE [--log FILE]
    python -m smallpc.smoke summarize opencode|dsh --events FILE [--log FILE]
    python -m smallpc.smoke verify --scratch DIR --original DIR --python PY
    python -m smallpc.smoke scrub IN OUT
    python -m smallpc.smoke merge-patterns OUT FILE...

The probes drive a scripted fake model (tests/fixtures/fake_openai_server.py) so a permission
config is exercised without a GPU: each scripted tool call has an expected outcome, and the
verdict is read from the harness's own JSON events.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .requests import LABEL
from .scrub import scrub_text

# --------------------------------------------------------------------------- probes

# (scripted step, expected outcome, label). Outcomes: "ok" = the tool ran; "denied" = blocked by a
# rule or because the tool is not offered; "rejected" = an ask was auto-rejected.
OPENCODE_PROBE: list[tuple[dict, str, str]] = [
    ({"tool": "bash", "args": {"command": "pytest -q", "description": "t"}}, "ok", "pytest"),
    (
        {"tool": "bash", "args": {"command": "python -m pytest -q", "description": "t"}},
        "ok",
        "python -m pytest",
    ),
    ({"tool": "bash", "args": {"command": "ls", "description": "t"}}, "ok", "ls"),
    ({"tool": "bash", "args": {"command": "cat a.py", "description": "t"}}, "ok", "cat a.py"),
    (
        {"tool": "bash", "args": {"command": "curl -s https://example.com", "description": "t"}},
        "denied",
        "curl",
    ),
    ({"tool": "bash", "args": {"command": "rm -f a.py", "description": "t"}}, "denied", "rm"),
    (
        {"tool": "bash", "args": {"command": "pytest -q && rm -f a.py", "description": "t"}},
        "denied",
        "pytest && rm",
    ),
    (
        {"tool": "bash", "args": {"command": "cat /etc/hostname", "description": "t"}},
        "denied",
        "cat absolute path",
    ),
    (
        {"tool": "bash", "args": {"command": "cat ../x", "description": "t"}},
        "denied",
        "cat parent path",
    ),
    (
        {"tool": "bash", "args": {"command": "cat $(echo a.py)", "description": "t"}},
        "denied",
        "command substitution",
    ),
    ({"tool": "bash", "args": {"command": "ls | head", "description": "t"}}, "denied", "pipe"),
    (
        {"tool": "bash", "args": {"command": "python -c 'print(1)'", "description": "t"}},
        "denied",
        "python -c",
    ),
    (
        {"tool": "webfetch", "args": {"url": "https://example.com", "format": "text"}},
        "denied",
        "webfetch",
    ),
    (
        {"tool": "write", "args": {"filePath": "/tmp/outside-probe.txt", "content": "x"}},
        "denied",
        "write outside the project",
    ),
    (
        {"tool": "write", "args": {"filePath": "b.py", "content": "print(1)\n"}},
        "ok",
        "write inside the project",
    ),
    ({"tool": "read", "args": {"filePath": "/etc/hostname"}}, "denied", "read outside the project"),
    (
        {"tool": "task", "args": {"description": "d", "prompt": "p", "subagent_type": "general"}},
        "denied",
        "task",
    ),
    ({"text": "done"}, "-", "final answer"),
]
# Run with a probe-only config in which one bash pattern is left at "ask" (never a real config).
OPENCODE_ASK_PROBE: list[tuple[dict, str, str]] = [
    (
        {"tool": "bash", "args": {"command": "curl -s http://127.0.0.1:1/x", "description": "t"}},
        "rejected",
        "ask in a non-interactive run",
    ),
    ({"text": "done"}, "-", "final answer"),
]
APPROVAL_TARGET = "/mnt/data/local-ai-research/DSH-APPROVAL-PROBE"
DSH_PROBE: list[tuple[dict, str, str]] = [
    ({"tool": "bash", "args": {"command": "ls", "description": "t"}}, "ok", "ls"),
    (
        {"tool": "write", "args": {"file_path": "b.py", "content": "print(1)\n"}},
        "ok",
        "write inside the workspace",
    ),
    (
        {
            "tool": "write",
            "args": {
                "file_path": APPROVAL_TARGET,
                "content": "x",
                "sandbox_permissions": "danger-full-access",
                "justification": "probe",
            },
        },
        "rejected",
        "operation that needs approval (no approver in headless)",
    ),
    (
        {
            "tool": "bash",
            "args": {"command": "touch /mnt/data/local-ai-research/DSH-PROBE2", "description": "t"},
        },
        "denied",
        "write into the repo",
    ),
    (
        {
            "tool": "bash",
            "args": {
                "command": "curl -s --noproxy '*' --max-time 5 https://example.com",
                "description": "t",
            },
        },
        "denied",
        "network, proxy bypassed",
    ),
    ({"text": "done"}, "-", "final answer"),
]
PROBES = {"opencode": OPENCODE_PROBE, "opencode-ask": OPENCODE_ASK_PROBE, "dsh": DSH_PROBE}


def probe_script(kind: str) -> list[dict]:
    return [step for step, _, _ in PROBES[kind]]


# --------------------------------------------------------------------------- event summaries


def _events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def opencode_summary(events_text: str, debug_log: str = "") -> dict:
    tools, steps, finals = [], 0, []
    for e in _events(events_text):
        if e.get("type") == "tool_use":
            p = e["part"]
            st = p.get("state", {})
            tools.append(
                {
                    "tool": p.get("tool"),
                    "input": st.get("input"),
                    "status": st.get("status"),
                    "error": st.get("error"),
                    "output_head": str(st.get("output", ""))[:200] if st.get("output") else None,
                }
            )
        elif e.get("type") == "step_finish":
            steps += 1
        elif e.get("type") == "text":
            finals.append(e["part"].get("text", ""))
    return {
        "tool_uses": tools,
        "steps": steps,
        "final_text": finals[-1] if finals else None,
        "permission_asks": debug_log.count(" message=asking id="),
        "auto_rejected": debug_log.count("auto-rejecting"),
        "rule_denials": sum(1 for t in tools if "prevents you" in str(t["error"])),
    }


def dsh_summary(events_text: str) -> dict:
    tools, steps, final, end = [], 0, None, None
    for e in _events(events_text):
        t = e.get("type")
        if t == "tool_call":
            tools.append(
                {"tool": e.get("tool"), "input": e.get("input"), "callId": e.get("callId")}
            )
        elif t == "tool_result":
            for call in tools:
                if call["callId"] == e.get("callId"):
                    call["status"], call["result_head"] = (
                        e.get("status"),
                        str(e.get("result"))[:300],
                    )
        elif t == "status" and e.get("phase") == "step_start":
            steps += 1
        elif t == "status" and e.get("phase") == "turn_end":
            end = e.get("reason")
        elif t == "final":
            final = e.get("text")
    return {"tool_uses": tools, "steps": steps, "final_text": final, "turn_end": end}


def _outcome(tool_use: dict, harness: str) -> str:
    err = str(tool_use.get("error") or "")
    res = str(tool_use.get("result_head") or "")
    if harness == "opencode":
        if tool_use.get("status") == "completed":
            return "ok"
        if "rejected permission" in err:
            return "rejected"
        return "denied" if ("prevents you" in err or "unavailable tool" in err) else "error"
    # dsh
    if "no approval channel" in res or "requires approval" in res:
        return "rejected"
    if tool_use.get("status") == "completed" and "[exit code:" not in res and "denied" not in res:
        if "Read-only file system" in res:
            return "denied"
        return "ok"
    return "denied"


def probe_checks(kind: str, summary: dict) -> list[dict]:
    harness = "dsh" if kind == "dsh" else "opencode"
    expected = [(e, label) for _, e, label in PROBES[kind] if e != "-"]
    uses = summary["tool_uses"]
    checks = [
        {
            "check": "every scripted tool call reached the harness",
            "expected": len(expected),
            "actual": len(uses),
            "pass": len(uses) == len(expected),
        }
    ]
    for (want, label), use in zip(expected, uses, strict=False):
        got = _outcome(use, harness)
        checks.append({"check": label, "expected": want, "actual": got, "pass": got == want})
    if harness == "opencode":
        want_asks = 1 if kind == "opencode-ask" else 0
        checks.append(
            {
                "check": "permission prompts raised",
                "expected": want_asks,
                "actual": summary["permission_asks"],
                "pass": summary["permission_asks"] == want_asks,
            }
        )
    return checks


# --------------------------------------------------------------------------- verification

IGNORED = {"__pycache__", ".pytest_cache", ".git"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(scratch: Path, original: Path, python: str) -> dict:
    """Independent of the agent: run pytest in the scratch copy, compare files with the original."""
    r = subprocess.run(
        [python, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(scratch)],
        cwd=scratch,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    changed, same_test = [], None
    for f in sorted(original.iterdir()):
        if f.is_file() and f.suffix == ".py":
            mine = scratch / f.name
            if not mine.exists() or sha256(mine) != sha256(f):
                changed.append(f.name)
    same_test = "test_movavg.py" not in changed
    extra = sorted(
        p.name
        for p in scratch.iterdir()
        if p.name not in IGNORED and not (original / p.name).exists()
    )
    return {
        "pytest_returncode": r.returncode,
        "pytest_green": r.returncode == 0,
        "pytest_tail": r.stdout.strip().splitlines()[-3:],
        "test_file_byte_identical": same_test,
        "test_file_sha256_original": sha256(original / "test_movavg.py"),
        "test_file_sha256_scratch": sha256(scratch / "test_movavg.py")
        if (scratch / "test_movavg.py").exists()
        else None,
        "changed_files": changed,
        "extra_files": extra,
        "pass": r.returncode == 0 and same_test,
    }


def finalize(
    harness: str, verification: dict, summary: dict, pattern: dict, net_events: list[dict]
) -> dict:
    """Verdict of one smoke attempt. A permission prompt or a request cut at the limit fails it."""
    asks = summary.get("permission_asks", 0)
    truncated = bool(pattern.get("any_request_truncated"))
    checks = {
        "pytest_green_independent_of_the_agent": verification["pytest_green"],
        "test_file_byte_identical": verification["test_file_byte_identical"],
        "no_permission_prompt": asks == 0,
        "no_request_hit_the_output_limit": not truncated,
    }
    return {
        "harness": harness,
        "pass": all(checks.values()),
        "checks": checks,
        "steps": summary.get("steps"),
        "requests": pattern["per_turn"]["requests_per_turn"],
        "rule_denials": summary.get("rule_denials"),
        "tool_calls": [
            {"tool": t["tool"], "input": t.get("input"), "status": t.get("status")}
            for t in summary["tool_uses"]
        ],
        "network_attempts_through_proxy": sorted(
            {f"{e['method']} {e['host']}:{e['port']} allowed={e['allowed']}" for e in net_events}
        ),
        "verification": verification,
    }


# --------------------------------------------------------------------------- misc


def merge_patterns(paths: list[str]) -> dict:
    runs = [json.loads(Path(p).read_text()) for p in paths]
    return {
        "label": LABEL,
        "note": "Per-request data of the WP7 smoke runs, one toy task. Smoke-task data: it shows "
        "how "
        "each harness behaves (for example extra title requests), not what real agent turns look "
        "like, and it does not revise the 3,000 + 400 standardised turn (step plan 3.4).",
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m smallpc.smoke")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("probe-script")
    s.add_argument("kind", choices=list(PROBES))
    s.add_argument("--out", required=True)
    c = sub.add_parser("probe-check")
    c.add_argument("kind", choices=list(PROBES))
    c.add_argument("--events", required=True)
    c.add_argument("--log", default="")
    z = sub.add_parser("summarize")
    z.add_argument("harness", choices=["opencode", "dsh"])
    z.add_argument("--events", required=True)
    z.add_argument("--log", default="")
    v = sub.add_parser("verify")
    v.add_argument("--scratch", required=True)
    v.add_argument("--original", required=True)
    v.add_argument("--python", required=True)
    sc = sub.add_parser("scrub")
    sc.add_argument("src")
    sc.add_argument("dst")
    f = sub.add_parser("finalize")
    f.add_argument("harness", choices=["opencode", "dsh"])
    f.add_argument("--verify", required=True)
    f.add_argument("--events", required=True)
    f.add_argument("--log", default="")
    f.add_argument("--pattern", required=True)
    f.add_argument("--net", default="")
    m = sub.add_parser("merge-patterns")
    m.add_argument("out")
    m.add_argument("files", nargs="+")
    a = ap.parse_args(argv)

    if a.cmd == "probe-script":
        Path(a.out).write_text(json.dumps(probe_script(a.kind)))
    elif a.cmd in ("probe-check", "summarize"):
        events = Path(a.events).read_text(errors="replace")
        log = Path(a.log).read_text(errors="replace") if a.log else ""
        kind = a.kind if a.cmd == "probe-check" else a.harness
        summ = dsh_summary(events) if kind == "dsh" else opencode_summary(events, log)
        if a.cmd == "summarize":
            print(json.dumps(summ, indent=2))
        else:
            checks = probe_checks(kind, summ)
            print(json.dumps({"kind": kind, "checks": checks, "summary": summ}, indent=2))
            return 0 if all(x["pass"] for x in checks) else 1
    elif a.cmd == "verify":
        res = verify(Path(a.scratch), Path(a.original), a.python)
        print(json.dumps(res, indent=2))
        return 0 if res["pass"] else 1
    elif a.cmd == "finalize":
        events = Path(a.events).read_text(errors="replace")
        log = Path(a.log).read_text(errors="replace") if a.log else ""
        summ = dsh_summary(events) if a.harness == "dsh" else opencode_summary(events, log)
        net = []
        if a.net and Path(a.net).exists():
            net = [json.loads(x) for x in Path(a.net).read_text().splitlines() if x.strip()]
        res = finalize(
            a.harness,
            json.loads(Path(a.verify).read_text()),
            summ,
            json.loads(Path(a.pattern).read_text()),
            net,
        )
        print(json.dumps(res, indent=2))
        return 0 if res["pass"] else 1
    elif a.cmd == "scrub":
        Path(a.dst).write_text(scrub_text(Path(a.src).read_text(errors="replace")))
    elif a.cmd == "merge-patterns":
        Path(a.out).write_text(json.dumps(merge_patterns(a.files), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
