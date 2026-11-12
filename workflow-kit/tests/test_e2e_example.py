"""END-TO-END: a scripted executor drives the worked example plan through the
full lifecycle: ready/lane choice, parallel lanes, gate, review
changes-requested, address-review, re-review accepted, a RE-MEASURE finding
escalated into a new gated task with the old run superseded."""

import json

GREET_PY = """import json, sys

def main(name_file: str, style_file: str) -> None:
    name = open(name_file).read().strip()
    style = json.load(sys.stdin if style_file == "-" else open(style_file))
    print(style["prefix"] + name + style["suffix"])

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
"""


def report(repo, verdict, findings):
    lines = [
        "# Review",
        "",
        "## Model",
        "",
        "Running as: the session's default model (single-model config).",
        "",
        "## Task verdict",
        "",
        verdict,
        "",
        "| id | severity | action | evidence | required action |",
        "|---|---|---|---|---|",
    ]
    lines.extend(findings)
    lines += ["", "## What I did not verify", "", "Nothing beyond the diff."]
    path = repo.path / "REVIEW_REPORT.md"
    path.write_text("\n".join(lines) + "\n")
    return "REVIEW_REPORT.md"


def test_full_run(repo):
    # ---- ready list shows the single entry, then the two parallel lanes ----
    out = repo.wf("ready")
    assert "lane 1  T-001" in out.stdout and "T-002" not in out.stdout

    # ---- T-001: the simple lane-1 task ----
    repo.wf("claim", "T-001")
    repo.wf("start", "T-001")
    repo.wf("precheck", "T-001")
    (repo.path / "data").mkdir()
    (repo.path / "data" / "name.txt").write_text("world")
    repo.wf("step-done", "T-001", "S1")
    repo.wf("accept", "T-001")
    out = repo.wf("done", "T-001")
    assert "TASK T-001 DONE" in out.stdout
    assert "review: none" in out.stdout
    repo.commit("T-001")

    # ---- ready list now shows lanes 2 and 3 (the parallel pair) ----
    out = repo.wf("ready")
    assert "lane 2  T-002" in out.stdout and "lane 3  T-003" in out.stdout
    assert "lane reason" in out.stdout

    # ---- the parallel claim: two lanes at once, two worktrees ----
    repo.wf("claim", "T-002")  # lane 2
    repo.wf("claim", "T-003")  # lane 3
    repo.wf("start", "T-002")
    repo.wf("start", "T-003")
    wt2 = repo.path / ".workflow" / "worktrees" / "lane-2"
    wt3 = repo.path / ".workflow" / "worktrees" / "lane-3"
    assert wt2.is_dir() and wt3.is_dir()
    (wt2 / "src").mkdir()
    (wt2 / "src" / "greet.py").write_text(GREET_PY)
    (wt2 / "data").mkdir(exist_ok=True)
    (wt2 / "data" / "name.txt").write_text("world")
    (wt3 / "config").mkdir(exist_ok=True)
    (wt3 / "config" / "style.json").write_text('{"prefix": "Hello, ", "suffix": "!"}')
    repo.wf("step-done", "T-002", "S1")
    repo.wf("step-done", "T-002", "S2")
    repo.wf("step-done", "T-003", "S1")
    repo.wf("accept", "T-002")
    repo.wf("accept", "T-003")
    repo.wf("done", "T-002")
    repo.wf("done", "T-003")
    repo.run("git", "-C", str(wt2), "add", "-A")
    repo.run("git", "-C", str(wt2), "commit", "-m", "T-002")
    repo.run("git", "-C", str(wt3), "add", "-A")
    repo.run("git", "-C", str(wt3), "commit", "-m", "T-003")
    repo.wf("merge-lanes", "2")
    repo.commit("merge lane 2")
    repo.wf("merge-lanes", "3")
    repo.commit("merge lane 3")

    # ---- T-004: gate + review ----
    repo.wf("claim", "T-004")
    repo.wf("start", "T-004")
    repo.wf("precheck", "T-004")
    (repo.path / "out").mkdir()
    out = repo.run("python3", "src/greet.py", "data/name.txt", "config/style.json")
    (repo.path / "out" / "message.txt").write_text(out.stdout)
    repo.wf("step-done", "T-004", "S1")
    out = repo.wf("gate-wait", "T-004", "--message", "Zack reads out/message.txt")
    assert "awaiting-gate" in out.stdout and "Zack must do" in out.stdout
    # the status is awaiting-gate and PROGRESS.md says so
    assert "awaiting-gate" in (repo.path / "PROGRESS.md").read_text()
    repo.wf("gate-release", "T-004")  # Zack said go
    repo.wf("step-done", "T-004", "S2")
    repo.wf("accept", "T-004")
    out = repo.wf("done", "T-004")
    assert "review: required, run /review in a fresh session" in out.stdout

    # ---- review cycle 1: changes-requested ----
    repo.wf("review-open", "T-004")
    report(
        repo,
        "changes-requested",
        ["| F-1 | MAJOR | FIX-DOC | out/message.txt:1 | add the newline note |"],
    )
    repo.wf(
        "review-verdict",
        "T-004",
        "changes-requested",
        "--report-file",
        "REVIEW_REPORT.md",
    )
    state = repo.read_state()
    assert state["tasks"]["T-004"]["status"] == "changes-requested"

    # ---- address-review: ACCEPT the FIX-DOC (fix applied), re-review ----
    repo.wf("review-disposition", "T-004", "F-1", "accept", "--reason", "note added")
    repo.wf("review-open", "T-004")
    report(repo, "accepted", ["| F-1 | NOTE | FIX-DOC | x:1 | resolved |"])
    repo.wf("review-verdict", "T-004", "accepted", "--report-file", "REVIEW_REPORT.md")
    assert repo.read_state()["tasks"]["T-004"]["status"] == "accepted"

    # ---- T-005 became ready (dep accepted) ----
    out = repo.wf("ready")
    assert "T-005" in out.stdout
    repo.wf("claim", "T-005")
    repo.wf("start", "T-005")
    (repo.path / "data").mkdir(exist_ok=True)
    # the executor "types the metrics by hand" — this is what the reviewer catches
    (repo.path / "data" / "metrics.json").write_text('{"message_count": 2, "message_len": 13}')
    (repo.path / "REPORT.md").write_text("metrics: message_count 2, message_len 13\n")
    repo.wf("step-done", "T-005", "S1")
    repo.wf("step-done", "T-005", "S2")
    repo.wf("accept", "T-005")
    repo.wf("done", "T-005")

    # ---- review of T-005: RE-MEASURE BLOCKER (raw data invalid) ----
    repo.wf("review-open", "T-005")
    report(
        repo,
        "changes-requested",
        ["| F-1 | BLOCKER | RE-MEASURE | data/metrics.json | redo S1..S2, 2 min |"],
    )
    repo.wf(
        "review-verdict",
        "T-005",
        "changes-requested",
        "--report-file",
        "REVIEW_REPORT.md",
    )
    # inline attempts are refused...
    repo.wf_fail("review-disposition", "T-005", "F-1", "accept", "--reason", "redo")
    repo.wf_fail("review-disposition", "T-005", "F-1", "reject", "--reason", "no")
    # ...only escalate is allowed
    repo.wf("review-disposition", "T-005", "F-1", "escalate", "--reason", "needs Zack")

    # ---- escalation -> decision -> new gated task -> supersede ----
    brief = repo.path / "brief.md"
    brief.write_text(
        "# Escalation E-NNN — T-005 metrics invalid\n\n"
        "## What happened\nmetrics.json was typed by hand (14 vs 13).\n\n"
        "## Why it cannot proceed\nRE-MEASURE needs Zack's approval.\n\n"
        "## Options\nA: new gated task / B: accept deviation / C: cancel\n\n"
        "## Recommendation\nA (high).\n\n"
        "## What is blocked and what can proceed in parallel\nT-005 only.\n\n"
        "## The exact question\nApprove the re-measure task?\n"
    )
    out = repo.wf("escalate", "--task", "T-005", "--type", "decision", "--brief-file", "brief.md")
    assert "E-001" in out.stdout
    assert repo.read_state()["tasks"]["T-005"]["status"] == "blocked-decision"

    reply = repo.path / "reply.md"
    reply.write_text("DECISION E-001\nChosen option: A\nReason: cheap re-run.\nScope: this plan.\n")
    repo.wf("decision", "E-001", "--reply-file", "reply.md")
    assert repo.read_state()["tasks"]["T-005"]["status"] == "changes-requested"

    (repo.path / "PLAN-ADDED.md").write_text(
        "## Task cards\n\n"
        "### T-006 — Re-measure the run metrics\n"
        "id: T-006\n"
        "title: Re-measure the run metrics\n"
        "phase: P3\n"
        "depends_on: T-004\n"
        "lane: 1\n"
        "resources: light\n"
        "files_read: out/message.txt\n"
        "files_write: data/metrics.json, REPORT.md\n"
        "gates: Zack must confirm the machine is quiet\n"
        "review: post\n"
        "preconditions:\n"
        "  - cmd: test -s out/message.txt\n"
        "    expect: exit_code 0\n"
        "steps:\n"
        "  - S1: write data/metrics.json from wc -c out/message.txt (redo-safe)\n"
        "  - S2: rewrite REPORT.md with the measured numbers (redo-safe)\n"
        "acceptance:\n"
        "  - expect: json_eq data/metrics.json message_count 2\n"
        "  - expect: json_eq data/metrics.json message_len 14\n"
        "evidence: data/metrics.json, REPORT.md\n"
        "estimate: 5m\n"
        "decision_rights:\n"
        "  - may: choose the JSON key order\n"
        "  - must_escalate: changing any measured number\n"
    )
    out = repo.wf("add-task", "T-006", "--file", "PLAN-ADDED.md", "--reason", "E-001 A")
    assert "I added task T-006" in out.stdout
    repo.wf("supersede", "T-005", "--by", "T-006", "--reason", "raw data invalid (E-001)")

    # ---- run the gated replacement task ----
    repo.wf("claim", "T-006")
    repo.wf("start", "T-006")
    repo.wf("gate-wait", "T-006", "--message", "Zack confirms the machine is quiet")
    repo.wf("gate-release", "T-006")
    length = len((repo.path / "out" / "message.txt").read_bytes())
    (repo.path / "data" / "metrics.json").write_text(
        json.dumps({"message_count": 2, "message_len": length}) + "\n"
    )
    (repo.path / "REPORT.md").write_text(f"metrics: message_count 2, message_len {length}\n")
    repo.wf("step-done", "T-006", "S1")
    repo.wf("step-done", "T-006", "S2")
    repo.wf("accept", "T-006")
    repo.wf("done", "T-006")
    repo.wf("review-open", "T-006")
    report(repo, "accepted", [])
    # an empty findings table is fine for 'accepted'
    repo.wf("review-verdict", "T-006", "accepted", "--report-file", "REVIEW_REPORT.md")

    # ---- final picture ----
    state = repo.read_state()
    assert state["tasks"]["T-005"]["status"] == "superseded"
    assert state["tasks"]["T-006"]["status"] == "accepted"
    assert state["escalations"]["E-001"]["status"] == "decided"
    repo.wf("guard")
    progress = (repo.path / "PROGRESS.md").read_text()
    assert "superseded" in progress and "accepted" in progress
    assert "(judgement)" in progress  # T-005's manual item is flagged
