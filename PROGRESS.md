# PROGRESS — GENERATED, DO NOT EDIT BY HAND

Rendered by `wf-progress.sh render` from `.workflow/state.json` and the lane
files; change them through the scripts only.

**Plan:** Step 0, remaining work: Stage 4, release v0.1.0, completion report  
**Phase:** P2

## Tasks

| id | title | status | lane | review |
|---|---|---|---|---|
| T-001 | Smoke test and recon (read-only) | done ⚠ re-acknowledge | 1 | none |
| T-002 | Record Stage 3 decisions and merge CLAUDE.md | done | 1 | none |
| T-003 | Reviewer calibration | done | 1 | none |
| T-004 | README draft | done | 1 | none |
| T-005 | Baseline report draft and number checker | accepted (judgement) | 2 | post |
| T-006 | Write-up draft | done | 1 | none |
| T-007 | Stage 4 session | accepted ⚠ re-acknowledge (judgement) | 1 | post |
| T-008 | S2 check and Stage 4 analysis | todo ⚠ re-acknowledge | 1 | post |
| T-009 | Post-Stage-4 code fixes | todo | 1 | none |
| T-010 | Final README, report, write-up and changelog | todo | 1 | post |
| T-011 | Plan v1.9, upstream drafts, methodology | todo | 2 | none |
| T-012 | README walkthrough from a clean shell | todo | 1 | none |
| T-013 | Scrub and release checks | todo ⚠ re-acknowledge | 1 | post |
| T-014 | Completion report and planning-chat review | todo | 1 | none |
| T-015 | Private repo, CI and tag v0.1.0 | todo | 1 | none |
| T-016 | Publish v0.1.0 | todo | 1 | none |
| T-017 | Unattended loop (wf-loop.sh) | accepted (judgement) | 3 | post |
| T-019 | Stage 4 pre-flight (no GPU) | accepted (judgement) | 1 | post |
| T-020 | Restore and verify the PCIe Gen4 link (hands-on) | in-progress | 1 | none |
| T-021 | Stage 4 session, run 2 | todo | 1 | post |

## READY (grouped by lane)

_(none)_

## Escalation queue

_(none)_

## Review queue

_(none)_

## Lanes

| lane | lock | worktree | tasks |
|---|---|---|---|
| 1 | pid 3828 | - | - |

## Last events

- 2026-11-14T11:28:57Z gate-wait T-020 — PCIe link repair (E-008). Stage 4 run 1 ran with the GPU link at Gen3 x8 instead of Gen4 x8. Before you reply go, do the checks in the escalation reply on your machine: a full power-off (not a reboot) with the mains lead out for 30 seconds, check that the GPU is seated, and in the BIOS set the GPU slot's PCIe speed to Gen4 rather than Auto. Then boot, close every app except one terminal running Claude Code, keep the PC on mains power, and reply go. This session will test the link under load; it is about 10 minutes.
- 2026-11-14T11:46:10Z gate-release T-020 — Zack said go
- 2026-11-14T11:50:15Z step-done T-020 — S2
- 2026-11-14T11:55:59Z step-done T-020 — S3
- 2026-11-14T11:55:59Z step-done T-020 — S4
