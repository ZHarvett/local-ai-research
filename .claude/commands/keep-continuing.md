---
description: Run the plan unattended for N hours (detached wf-loop.sh)
argument-hint: <hours>
---
Start the unattended workflow loop for `$ARGUMENTS` hours, detached. Do exactly
this, nothing more:

1. If `$ARGUMENTS` is empty or not a positive number, print the usage
   (`bash scripts/wf-loop.sh --help`) and stop.
2. Start the loop detached from the main checkout, with the hours argument
   substituted for `<hours>` (its log stays in /tmp, never in the repo):
   ```bash
   stamp=$(date -u +%Y%m%dT%H%M%SZ)
   log=/tmp/wf-loop-$stamp.log
   WF_LOOP_LOG="$log" setsid nohup bash scripts/wf-loop.sh <hours> >/dev/null 2>&1 </dev/null &
   echo "wf-loop started: pid $! — log: $log"
   ```
   Do not use `run-detached.sh`: its job log lands inside the repo
   (`data/logs/jobs/`), and the loop's log must stay in /tmp. Do not run the
   loop in the foreground, and do not start a second one (its lock refuses).
3. Tell Zack, with the actual pid and log path from step 2:
   - follow it: `tail -f /tmp/wf-loop-<stamp>.log`
   - stop it early: `kill <pid>` stops **only the loop**, not a session it has
     already launched: an in-flight claude session (a child of `timeout`) keeps
     running to completion and still obeys the kit protocol, so let it finish (or
     kill that child pid separately) before starting another loop. The loop also
     stops by itself at the deadline, or on the first gate, escalation, blocked
     decision or other human-needed state — the final log line names the reason
     and the task id.
   - **Make the first real run a supervised one of about 1 hour while awake**
     (decision E-004): watch the log and be ready to answer gates and
     escalations in a normal session.
4. Stop. The loop runs its own sessions; do not run /continue yourself.