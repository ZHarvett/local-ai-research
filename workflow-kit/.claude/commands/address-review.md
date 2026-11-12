---
description: Address a changes-requested review — dispositions per finding
argument-hint: <T-xxx>
---
You are a workflow-kit executor session addressing a review of $ARGUMENTS.
You must resolve (or escalate) every finding; none may be silently dropped.

1. `bash scripts/wf-guard.sh`; then read the latest archived report
   `reviews/$ARGUMENTS/rN-REVIEW_REPORT.md` (N = the cycle in
   `bash scripts/wf.sh status`).
2. For EVERY finding, choose and record a disposition with
   `bash scripts/wf.sh review-disposition $ARGUMENTS F-n accept|reject|escalate
   --reason "<written reason>"`:
   - **ACCEPT** — do the finding's required action yourself when it is FIX-DOC,
     FIX-CODE or RE-ANALYSE (redo the analysis from the raw data; do not
     re-measure). Fix, then re-run `bash scripts/wf.sh accept $ARGUMENTS`.
   - **REJECT** — only for MINOR/NOTE findings you disagree with, with a
     written reason. A BLOCKER may never be rejected (the script refuses it).
   - **ESCALATE** — required for every RE-MEASURE and DECIDE finding (the
     script refuses anything else). Run `/escalate` with type decision; if
     Zack approves the re-measure, create the new gated task: append its card
     to PLAN-ADDED.md, `bash scripts/wf.sh add-task T-0xx --file
     PLAN-ADDED.md --reason "escalation E-NNN option A"`, then
     `bash scripts/wf.sh supersede $ARGUMENTS --by T-0xx --reason "..."` —
     the old run is superseded, never deleted.
3. If you fixed any BLOCKER or MAJOR finding, re-open review:
   `bash scripts/wf.sh review-open $ARGUMENTS` then tell Zack
   "Run /review in a fresh session" (cycle 2; at most 2 cycles, then it
   escalates by itself).
4. If all findings were MINOR/NOTE rejections or escalations to decisions,
   the task stays `changes-requested` (blocked) until the decisions land —
   say so and stop.
5. Never edit the archived reports, the acceptance criteria, or PLAN.md.
   Record your fixes as commits; dispositions are already in the state.
