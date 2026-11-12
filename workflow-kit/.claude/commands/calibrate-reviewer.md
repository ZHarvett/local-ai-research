---
description: Reviewer self-test on a finished task with planted errors
---
You are calibrating the reviewer. A finished task is bundled in
`calibrate/` (card, evidence files, an acceptance record); it contains planted
errors. You must find them WITHOUT looking at `calibrate/answer-key.md` first.

1. Review exactly as `/review` would: read `calibrate/card.md`,
   `calibrate/evidence/` and `calibrate/acceptance.json`; re-derive every
   number; re-run the card's cheap acceptance commands against
   `calibrate/evidence/` (they are plain shell commands; run them with
   `cd calibrate/evidence`); compare the acceptance record's hashes with the
   actual files. Do NOT read `calibrate/answer-key.md` yet.
2. Write your findings (id, severity, evidence, action) as a short list.
3. Now read `calibrate/answer-key.md` and compare: which planted errors did you
   catch (F-n), which did you miss, which did you over-report?
4. Record the result:
   `bash scripts/wf.sh calibration-record --caught F-1 F-3 --missed F-2
   --model-name "<your model>"`
   (adjust the lists to your result). The history lands in
   `.workflow/calibration.json` for the planning chat to see how much to trust
   reviews.
5. Report honestly: the point of calibration is to expose misses, not to pass.
   If you missed a BLOCKER, say so in your reply.
