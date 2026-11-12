---
description: Show plan status, readiness, escalations and reviews
---
Print, in this order, and add nothing else:

1. `bash scripts/wf-guard.sh` (if it fails, print the GUARD lines and stop).
2. `bash scripts/wf.sh status`
3. `bash scripts/wf.sh ready`
4. `bash scripts/wf.sh lane-status`
5. The last 5 events from `PROGRESS.md`.

Interpret one thing only: if a task is `blocked-decision`, say which escalation
it waits for (`escalations/E-NNN.md`) and that the reply is recorded with
`bash scripts/wf-decision.sh E-NNN --reply-file F`. If the review queue is
non-empty, name the task and cycle and say "/address-review T-xxx" or
"/review T-xxx" as appropriate.
