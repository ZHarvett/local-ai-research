---
description: Continue the plan — pick the next ready task, run it end to end
argument-hint: [T-xxx]
---
You are a workflow-kit executor session. Follow this procedure EXACTLY; do not
improvise around it. Everything state-related goes through `bash scripts/wf.sh`.

1. Run `bash scripts/wf-guard.sh`. If it fails: STOP, report the GUARD lines
   verbatim, and wait. Never repair state by hand.
2. Run `bash scripts/wf.sh status`. If any task is `blocked-decision`, print the
   open escalations (`bash scripts/wf.sh status`, the escalation queue in
   PROGRESS.md, `escalations/*.md`) and STOP: "Waiting for decisions: E-NNN —
   bring the brief to the planning chat and paste the reply, then run
   `wf-decision.sh`."
3. Run `bash scripts/wf.sh ready`.
   - No ready tasks: report the status and STOP.
   - Exactly one ready task: proceed with it.
   - Several tasks but only one lane: proceed with the first one.
   - Several LANES ready: list them with each card's one-line lane reason
     (printed by `ready`), then ASK: "Start lane 1 (<task T-xxx>?" — wait for
     Zack's yes. Do not start anything before the answer. After he says yes,
     remind him: "Open two more terminals in this repo and run /lane 2 and
     /lane 3 there (max 3 sessions)." Do not run the other lanes yourself.
4. Claim and start: `bash scripts/wf.sh claim T-xxx` then `bash scripts/wf.sh
   start T-xxx`. For lane 2/3 tasks the claim prints the worktree path: ALL
   file work, acceptance runs and git commits happen inside that worktree
   (use absolute paths).
5. Read ONLY this card: `bash scripts/wf-card.sh T-xxx`. Never open PLAN.md.
   Shared rules at the top of the card output apply unconditionally.
6. Preconditions: `bash scripts/wf.sh precheck T-xxx`. Any FAIL: STOP and
   report; never work around.
7. Execute the steps S1..Sn in order. After EACH step run
   `bash scripts/wf.sh step-done T-xxx Sn`. Do the work the step describes;
   within the card's decision rights ("may") you decide; anything under
   "must_escalate" or anything unexpected: STOP, run `/escalate`, wait.
8. HUMAN-GATE: when the card's `gates` require Zack, run
   `bash scripts/wf.sh gate-wait T-xxx --message "<exactly what Zack must do>"`,
   print the message, and WAIT for his "go" (he runs `gate-release` or tells
   you to: then `bash scripts/wf.sh gate-release T-xxx`).
9. Context discipline: if roughly 70% of your context is used, finish the
   current step, `wf.sh step-done` it, commit, and STOP with: "Start a fresh
   session and run /continue."
10. Acceptance: `bash scripts/wf.sh accept T-xxx`. FAIL items: fix and re-run.
    Do not proceed to done with failures.
11. `bash scripts/wf.sh done T-xxx` (it verifies the evidence itself).
12. Commit the task's work in small commits (message prefix from the repo's
    own convention). Include the state changes.
13. Finish with exactly one line:
    `TASK T-xxx DONE | review: required, run /review in a fresh session | next ready: <from wf.sh ready>`
    (or "review: none" when the card says so).

If the task's card says `review: pre+post`, STOP before starting the heavy work
and tell Zack to run /review first.
