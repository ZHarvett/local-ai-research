---
description: Escalate a decision, problem or mismatch to the planning chat
argument-hint: [--task T-xxx] [--type decision|problem|assumption-mismatch|review-disagreement]
---
You are stopping work to escalate. The planning chat cannot see this repo, so
the brief must be one self-contained page.

1. Write the brief to a scratch file (in the repo, e.g.
   `escalations/.draft.md` — never outside the repo) following
   `templates/escalation-brief.md.template` (or the format in
   docs/WORKFLOW.md): id placeholder `E-NNN`, task, type, What happened (facts
   with file paths and key numbers), Why it cannot proceed, Options A/B/C with
   consequences and cost, Recommendation with confidence, What is blocked and
   what can proceed in parallel, The exact question.
   - Unexpected error / tool bug → type `problem`.
   - Plan assumption that turned out wrong → type `assumption-mismatch`.
   - Review disagreement / RE-MEASURE / DECIDE finding → type `decision` or
     `review-disagreement`.
   NEVER fix a bug in the tooling you are using for measurements before
   escalating; that is always a `problem` escalation.
2. Create it and block the task:
   `bash scripts/wf-escalate.sh --task T-xxx --type <type> --brief-file
   escalations/.draft.md` (the script assigns E-NNN, moves the brief into
   `escalations/`, and marks the task blocked-decision).
3. Tell Zack, in one short block:
   - the escalation id and the one-line subject,
   - "The task is blocked-decision. Bring `escalations/E-NNN.md` to the
     planning chat. Its reply (starting with 'DECISION E-NNN') is recorded with
     `bash scripts/wf-decision.sh E-NNN --reply-file <file>`."
4. Stop. Do not continue the task, do not start another one in the same lane
   (the guard and PROGRESS.md show what may proceed elsewhere).
