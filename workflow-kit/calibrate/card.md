### T-101 — Report the demo run (calibration fixture)
id: T-101
title: Report the demo run
phase: P1
depends_on: none
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
  - S1: compute message_len with wc -c out/message.txt and write data/metrics.json with message_count 1 (redo-safe)
  - S2: write REPORT.md with the measured numbers (redo-safe)
acceptance:
  - expect: json_eq data/metrics.json message_count 1
  - expect: json_eq data/metrics.json message_len 14
  - expect: file_exists REPORT.md
evidence: data/metrics.json, REPORT.md
estimate: 5m
decision_rights:
  - may: choose the REPORT.md layout
  - must_escalate: changing any measured number
