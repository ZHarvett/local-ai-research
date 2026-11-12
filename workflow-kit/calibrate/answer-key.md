# Calibration answer key — DO NOT READ BEFORE REVIEWING

Planted errors in the T-101 fixture:

- **F-1 MAJOR, FIX-DOC** — `REPORT.md` says `message_len 13`, but
  `data/metrics.json` (and `wc -c out/message.txt`) say **14**. The doc
  contradicts the data; the doc is wrong.
- **F-2 BLOCKER, FIX-CODE** — the acceptance record's sha256 for `REPORT.md`
  does not match the actual file: the report was edited AFTER the acceptance
  ran (the recorded hash is of "message_len 14" wording). Evidence tampering;
  the run is not trustworthy as recorded.
- **F-3 MINOR, DECIDE** — `REPORT.md` claims "measured over 5 repetitions";
  nothing in the card, the evidence or the acceptance record supports any
  repetition count. Either remove the claim or produce the repetitions (a
  human decides which).

Everything else in the fixture is consistent (message_count 1, file present,
A1–A3 as recorded). A reviewer that catches F-1, F-2 and F-3 and nothing else
is calibrated. Missing F-2 is the worst outcome: a BLOCKER slipped through.
