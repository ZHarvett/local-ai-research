---
description: Continue one lane — same as /continue with the lane pre-selected
argument-hint: <lane-number>
---
You are a workflow-kit executor session for lane $ARGUMENTS. Follow /continue's
procedure exactly (guard, blocked-decision first, card only, preconditions,
steps with step-done, gates, accept, done, commit), with these differences:

- The lane is pre-selected: among the READY tasks pick the one whose lane is
  $ARGUMENTS (the `ready` output groups by lane). No question to Zack.
- `bash scripts/wf.sh claim T-xxx --lane $ARGUMENTS`, then `start`.
- Lane 1 works in the main checkout. Lanes 2 and 3: the claim prints the
  worktree path (`.workflow/worktrees/lane-N`); all file work, acceptance runs
  and commits happen there, with absolute paths.
- If no ready task exists in this lane, report `bash scripts/wf.sh
  lane-status $ARGUMENTS` and STOP.
- Never touch another lane's tasks or files; conflict checks will refuse, and
  so should you.
- If your lane's work is finished (no active tasks left in the lane), tell
  Zack: "Lane $ARGUMENTS is done; run `bash scripts/wf.sh merge-lanes
  $ARGUMENTS` in the main checkout."
