# Stage 3 and Stage 4 machine conditions

Records the machine conditions of the Stage 3 and Stage 4 sessions (WP13). Gate G3 applies in full here: the desktop apps are closed
(`scripts/check-quiet.sh`, blocklist in `configs/quiet-check.toml`). Only process **names** are recorded, never window titles, URLs or
command-line arguments. Fill one block per session **before** it starts (copy the template), and add the end-of-session line when it is complete.

## Template (copy for each session)
```
## Session <id> (<what>), <date>, before the start
- `scripts/check-quiet.sh` output, verbatim (exit code <0|1>):
  <paste: "quiet-machine check: N processes (names only)", offenders, warnings, the CPU idle line, RESULT>
- `pgrep -a llama-server`: <empty>. GPU lock (`.locks/gpu.lock`): <free>.
- `nvidia-smi`: memory.used <N> MiB of 16,311 MiB; compute processes: <none>.
- MemAvailable: <N> GiB. Swap in use: <N> GiB. Mains power: <yes>. `git status --short`: <empty>. Code commit: <hash>.
- Anything else running (names): <none besides the terminal with Claude Code>.

## Session <id>, end
- Duration <min> (estimate <min>); runner exit <0>; state <complete>; gate (`stage3 gate`): <PASS|FAIL, criteria>; re-run pass: <units re-run, clean/flagged after>.
- Stock windows paging-flagged (reported only): <n of N>; tuned and canary windows: <n of N>.
```

(No session has been run yet. The Part C functional checks of WP13 used the desktop apps open and are not recorded here: they are functional-test data.)
