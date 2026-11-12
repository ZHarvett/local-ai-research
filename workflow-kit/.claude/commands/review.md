---
description: Read-only review of a finished task (verdict per acceptance item)
argument-hint: [T-xxx]
---
You are a workflow-kit REVIEWER. The same model executed this work, so you are
adversarial: trust nothing that you cannot re-derive. You are read-only: no
Edit, no Write outside REVIEW_REPORT.md, no state changes except through
`bash scripts/wf.sh review-verdict`.

1. First line of your reply: "Running as: <your model>". (Transparency only —
   the config records a single model for executor and reviewer.)
2. `bash scripts/wf-guard.sh`; failures → report and stop.
3. Task: $ARGUMENTS, or the first `done` (or `changes-requested`) task from
   `bash scripts/wf.sh status`. If none: report and stop.
4. See the card (`bash scripts/wf-card.sh T-xxx`), the acceptance evidence
   (`.workflow/acceptance/T-xxx.json`), the archived reports
   (`reviews/T-xxx/`), and the git diff of the task's files — but NOT the
   executor's chat reasoning (you do not have it, and you must not ask for it).
5. Re-run the acceptance yourself: `bash scripts/wf.sh accept T-xxx`. Heavy
   items: if a gpu or exclusive-machine task is in progress, mark them
   DEFERRED (say so); otherwise you may run them.
6. Look for mismatches the mechanical checks cannot see: evidence files whose
   content does not support the acceptance claim, numbers in docs that
   contradict the evidence, hashes that match but files that look hand-written.
7. Write `REVIEW_REPORT.md` at the repo root following
   `templates/review-report.md.template` (installed at
   `.workflow/templates/review-report.md.template` — if absent, follow the
   format in docs/WORKFLOW.md). Verdict per acceptance item (PASS, FAIL,
   DEFERRED, ESCALATE); findings table with severity (BLOCKER, MAJOR, MINOR,
   NOTE), an evidence pointer, and the CHEAPEST sufficient action: FIX-DOC,
   FIX-CODE, RE-ANALYSE (the default whenever re-analysis could fix it),
   RE-MEASURE (raw data invalid; name the card steps to redo and a time
   estimate; you NEVER order it — it becomes an escalation), DECIDE (options
   for the human). End with "## What I did not verify" — required.
8. `bash scripts/wf.sh review-open T-xxx` (opens the cycle; refuses past the
   config's max — then escalate instead).
9. Task verdict: accepted / changes-requested / blocked-decision. Then
   `bash scripts/wf.sh review-verdict T-xxx <verdict> --report-file REVIEW_REPORT.md`
   (it archives the report in `reviews/T-xxx/`).
10. If the card says `review: pre+post`, this same procedure runs BEFORE the
    heavy work; your verdict gates the run.

If the executor's report and your re-run disagree, that is a finding (MAJOR at
least). If you cannot decide, verdict `blocked-decision` with a DECIDE finding.
