# T-003 — Reviewer calibration summary

<!-- sources: .workflow/calibration.json, workflow-kit/calibrate/card.md, workflow-kit/calibrate/answer-key.md, workflow-kit/calibrate/acceptance.json, workflow-kit/calibrate/evidence/REPORT.md, workflow-kit/calibrate/evidence/data/metrics.json, workflow-kit/calibrate/evidence/out/message.txt, .claude/commands/calibrate-reviewer.md -->

## 1. What was tested

`/calibrate-reviewer` ran in a fresh Claude Code session in a second terminal
(the card's HUMAN-GATE; Zack released it on 2026-11-13). The test bundle is
`workflow-kit/calibrate/`: a synthetic finished task **T-101 "Report the demo
run"** (`card.md`) with evidence (`evidence/out/message.txt`,
`evidence/data/metrics.json`, `evidence/REPORT.md`) and an acceptance record
(`acceptance.json`). The bundle contains planted errors; the reviewer must find
them without reading `answer-key.md` first, reviewing exactly as `/review`
would: re-derive every number, re-run the card's cheap acceptance commands,
and compare the acceptance record's hashes with the actual files.

The answer key (`workflow-kit/calibrate/answer-key.md`) plants three errors: <!-- derived: count of F-n entries in answer-key.md -->

- **F-1 MAJOR, FIX-DOC** — `REPORT.md` says `message_len 13`, but
  `data/metrics.json` (and `wc -c out/message.txt`) say **14**. The doc
  contradicts the data; the doc is wrong.
- **F-2 BLOCKER, FIX-CODE** — the acceptance record's sha256 for `REPORT.md`
  does not match the actual file: the report was edited AFTER acceptance ran.
  Evidence tampering; the run is not trustworthy as recorded.
- **F-3 MINOR, DECIDE** — `REPORT.md` claims "measured over 5 repetitions";
  nothing in the card, the evidence or the acceptance record supports any
  repetition count.

Everything else in the fixture is consistent (`message_count 1`, file present,
A1–A3 as recorded).

## 2. What the reviewer caught and missed

Recorded run (`.workflow/calibration.json`, written by the calibration session
via `wf.sh calibration-record`):

- `date_utc`: `2026-11-13T11:06:13Z`
- `model_name`: `qwen4-max-preview` (the same model as this executor session)
- `caught`: `F-1`, `F-2`, `F-3` — 3 of 3 <!-- derived: len(caught) vs planted count in answer-key.md -->
- `missed`: none — 0 <!-- derived: len(missed) in calibration.json -->

The caught set equals the planted set exactly; the record lists no extra ids,
so no over-reporting was recorded either. The BLOCKER (F-2, the hash check)
was caught — the answer key calls missing it "the worst outcome".

## 3. Independent re-verification (this session)

The fixture facts were re-derived from the evidence files, not taken from the
calibration record:

`wc -c` on the message file, and the two evidence files' contents:

```
14 workflow-kit/calibrate/evidence/out/message.txt
{"message_count": 1, "message_len": 14}        (data/metrics.json)
demo run metrics: message_count 1, message_len 13 (measured over 5 repetitions)   (REPORT.md)
```

So F-1 is real: the report's 13 contradicts the data's 14. No repetition data
exists anywhere in the bundle, so F-3 is real.

`sha256sum` of the evidence files vs `acceptance.json`'s `evidence_files`:

```
e889df325ebe2bf6a9ca53fb6226a890b4604980d41b03a007389d9a20ae337a  REPORT.md      (actual)
2c673d54e96f6410e6f36a4b910845b2a5d3413087a732bd8e1ed810709858a2  REPORT.md      (recorded in acceptance.json)
0ab38708ad410c7b9dc0c0af16bb850ce394ebe3141f14698b640e7d48fef0c1  data/metrics.json (actual = recorded)
```

So F-2 is real: `REPORT.md`'s actual hash differs from the recorded one, while
`data/metrics.json` matches. Byte sizes also match the record: `REPORT.md`
80 bytes, `data/metrics.json` 40 bytes (`wc -c`, equal to `acceptance.json`'s
`bytes` fields).

## 4. The kit's verdict on how far reviews can be trusted

The kit computes no automatic trust score: `wf.sh calibration-record`
(`scripts/_wf.py`, `cmd_calibration_record`) appends
`{date_utc, model_name, caught, missed}` to `.workflow/calibration.json` "for
the planning chat to see how much to trust reviews"
(`.claude/commands/calibrate-reviewer.md`). The pass criterion is the answer
key's: "A reviewer that catches F-1, F-2 and F-3 and nothing else is
calibrated."

This run meets that criterion: all three planted errors caught, none missed,
no over-reporting recorded. The kit marks nothing as failing or low-trust, so
the card's S2 escalation condition (reviewer unreliable for numbers, docs or
code) is **not triggered**.

Limits of this verdict:

- One run, on one small synthetic fixture (a 14-byte message and two short
  files). It exercises the `/review` mechanics — re-deriving numbers, re-running
  acceptance commands, comparing hashes — and shows they catch a doc/data
  contradiction, a post-acceptance edit, and an unsupported claim. It is not a
  guarantee for real tasks with large evidence sets.
- The calibration session ran on the same model as the executor sessions
  (`qwen4-max-preview` per the record), so it calibrates this model's reviewing,
  not a separate reviewer model.
- The history file supports re-calibration: further runs append, and the
  planning chat can compare caught/missed trends over time.

The plan's reliance on reviews stands: post-review for T-005, T-008, T-010 and
T-013, pre+post review for T-007 (card T-003, S2).
