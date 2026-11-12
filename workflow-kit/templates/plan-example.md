# Example plan: greeting service

*Version 1.0 · 12 November 2026*

Rules are declared before data. Cards carry machine-checkable acceptance wherever
possible; the same model executes and reviews, so every claim is re-run mechanically.

## Shared rules

- Never use sudo. Nothing destructive. `data/` is append-only.
- One GPU job at a time; heavy tasks take the machine-wide lock.
- Any precondition mismatch, unexpected error or judgement call: STOP and escalate.
  Never work around, never silently re-plan.
- Evidence, not adjectives: every acceptance item names a command and its expected
  result, and every evidence file is recorded with its sha256.
- Sessions may append new cards to PLAN-ADDED.md; PLAN.md is frozen.
- Finish every step with `wf.sh step-done T-xxx Sn`; if context grows past about
  70%, finish the current step, record it, stop, and tell Zack: "Start a fresh
  session and run /continue".

## Assumption register

- A1: a plain-text name file under `data/` is enough for the greeting — checked by T-001
- A2: the style config stays JSON with the keys `prefix` and `suffix` — checked by T-003

## Phases

- P1: inputs
- P2: build
- P3: report

## Task cards

### T-001 — Write the name file
id: T-001
title: Write the name file
phase: P1
depends_on: none
lane: 1
resources: light
files_read: none
files_write: data/name.txt
gates: none
review: none
preconditions:
  - cmd: pwd
    expect: exit_code 0
steps:
  - S1: create data/ if missing and write the single line "world" to data/name.txt (redo-safe)
acceptance:
  - cmd: cat data/name.txt
    expect: stdout_regex ^world$
evidence: data/name.txt
estimate: 5m
decision_rights:
  - may: choose the file encoding (UTF-8 unless a reason exists)
  - must_escalate: anything that writes outside data/

### T-002 — Write the greeting builder
id: T-002
title: Write the greeting builder
phase: P2
depends_on: T-001
lane: 2
lane_reason: independent of T-003 (different files, light, both under 10 minutes alone but more than 30 minutes together)
resources: light
files_read: data/name.txt
files_write: src/greet.py
gates: none
review: none
preconditions:
  - cmd: test -f data/name.txt
    expect: exit_code 0
steps:
  - S1: create src/ and write greet.py: usage `greet.py NAME_FILE STYLE_FILE`; STYLE_FILE `-` reads JSON from stdin; prints PREFIX name SUFFIX (redo-safe)
  - S2: run grep -c "def main" src/greet.py (redo-safe)
acceptance:
  - cmd: echo '{"prefix": "Hello, ", "suffix": "!"}' | python3 src/greet.py data/name.txt -
    expect: stdout_regex Hello, world!
evidence: src/greet.py
estimate: 15m
decision_rights:
  - may: pick the function layout and argument names
  - must_escalate: any dependency on non-stdlib packages

### T-003 — Write the style config
id: T-003
title: Write the style config
phase: P2
depends_on: T-001
lane: 3
lane_reason: independent of T-002 (different files, light, both under 10 minutes alone but more than 30 minutes together)
resources: light
files_read: none
files_write: config/style.json
gates: none
review: none
preconditions:
  - cmd: test -f data/name.txt
    expect: exit_code 0
steps:
  - S1: create config/ and write style.json with prefix "Hello, " and suffix "!" (redo-safe)
acceptance:
  - expect: json_eq config/style.json prefix "Hello, "
evidence: config/style.json
estimate: 5m
decision_rights:
  - may: choose additional style keys
  - must_escalate: changing the prefix or suffix text

### T-004 — Compose the final message
id: T-004
title: Compose the final message
phase: P2
depends_on: T-002, T-003
lane: 1
resources: light
files_read: src/greet.py, config/style.json
files_write: out/message.txt
gates: Zack must read out/message.txt and reply "go" before it is treated as final
review: post
preconditions:
  - cmd: echo '{"prefix": "Hello, ", "suffix": "!"}' | python3 src/greet.py data/name.txt -
    expect: stdout_regex Hello, world!
steps:
  - S1: create out/ and run the builder, writing its stdout to out/message.txt (redo-safe)
  - S2: wait for the gate: Zack reads out/message.txt (not redo-safe)
acceptance:
  - cmd: cat out/message.txt
    expect: stdout_regex Hello, world!
  - cmd: python3 src/greet.py data/name.txt config/style.json | wc -l
    expect: exit_code 0
    heavy: true
evidence: out/message.txt
estimate: 10m
decision_rights:
  - may: re-run the builder as often as needed
  - must_escalate: any wording change to the message itself

### T-005 — Report the run
id: T-005
title: Report the run
phase: P3
depends_on: T-004
lane: 1
resources: light
files_read: out/message.txt
files_write: data/metrics.json, REPORT.md
gates: none
review: post
preconditions:
  - cmd: test -s out/message.txt
    expect: exit_code 0
steps:
  - S1: write data/metrics.json with message_count 2 and message_len equal to wc -c of out/message.txt (redo-safe)
  - S2: write REPORT.md with the metric values (redo-safe)
acceptance:
  - expect: json_eq data/metrics.json message_count 2
  - cmd: test -s REPORT.md
    expect: exit_code 0
  - expect: file_exists REPORT.md
  - expect: manual "REPORT.md states the metric values plainly, no adjectives"
evidence: data/metrics.json, REPORT.md
estimate: 10m
decision_rights:
  - may: choose the REPORT.md layout
  - must_escalate: changing any measured number
