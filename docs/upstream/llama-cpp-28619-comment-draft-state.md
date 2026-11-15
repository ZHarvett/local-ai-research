<!-- DRAFT COMMENT — NOT FILED. Prepared 2026-11-15 by task T-011 for review before anything is posted upstream. -->
<!-- sources: data/health/endpoints-2026-11-08.json, tests/fixtures/logs/cache-source-slot-restore.txt, tests/fixtures/logs/cache-source-prompt-cache.txt, docs/progress-log.md, docs/decisions.md, data/env/build-info.json, configs/server/examples/mtp-64k.toml, scripts/healthcheck.sh -->

# Comment draft for llama.cpp #28619 — MTP draft state survives save/restore on b12208

**Status:** draft, not filed. #28619 is referenced in our step plan and decisions as the
report that MTP draft state is lost across slot save/restore and host prompt-cache restore
(a Step 3b starter PR that our Step 5 depends on). This comment reports our measurements on
the pinned build; filing is a later, gated step.

## Proposed comment text

Tested on b12208 (commit `57d04820dfef7a3519aac276d018a6fd71251895`, CUDA 13.4, RTX 5060 Ti
sm_120) with a MoE model (Ornith-1.5-35B-A3B, Q4 GGUF) and MTP draft length 2, `-np 1`,
`-c 65536`. One fresh server per arm, four arms:

1. control (no save/restore),
2. control repeat (fresh server, same conversation),
3. slot files (`--slot-save-path`, save / erase / restore),
4. host prompt cache (default `--cache-ram 8192`).

Two history lengths, 181 and 3,191 tokens; measured the third turn's
`cache_n` / `draft_n` / `draft_n_accepted`:

| History | control | control repeat | slot files | prompt cache |
|---|---|---|---|---|
| 181 tokens | 180/46/42 | 180/46/42 | 180/46/42 | 180/46/42 |
| 3,191 tokens | 3190/46/43 | 3190/46/43 | 3190/46/43 | 3190/46/43 |

Continuation tokens were identical to the control in every arm. Acceptance in the restore
arms was 0.913 against 0.913 / 0.913 in the two controls (tolerance 0.020). The logs confirm
the draft state actually moved through the mechanism under test, so the arms are not
confounded:

- slot files: `restored the draft state (0.364 MiB / 6.311 MiB)` at restore, and the restored
  prefix is attributed to `slot_restore`;
- prompt cache: `prompt_save: - saving prompt with length 180, total state size = 65.041 MiB
  (draft: 0.356 MiB)` before the restore turn, and a prompt-cache load at turn 3.

**Finding: on b12208 neither mechanism loses the MTP draft state**, up to 8,192 tokens of
history.

Caveats, stated plainly:

- **No negative control.** We could not make the server drop the draft state, so the evidence
  is the log lines plus identical statistics in all four arms at two history lengths — not a
  demonstrated failure-and-recovery.
- **No history above 8,192 tokens** was tested.
- Context checkpoints are created at prompt ends at any length on this build (the premise
  that none exist below `--checkpoint-min-step` 8192 does not hold); the restore turn itself
  used no checkpoint (`restored_from_checkpoint` 0).

If #28619 describes draft state lost across these mechanisms, it may already be fixed on
b12208. Suggest confirming against the original reproduction and closing with a regression
test, or pointing at a configuration where it still reproduces.

## Reproduction (in the baseline repo)

The save/restore checks are phase C of the health suite (`scripts/healthcheck.sh` usage
header; every server is started through `scripts/launch-server.sh` under the GPU lock):

```bash
scripts/healthcheck.sh --phases C --detach
```

The draft-2 server config with slot saving is `configs/server/examples/mtp-64k.toml`
(`spec_type = "draft-mtp"`, `spec_draft_n_max = 2`, `slot_save_path` under
`/dev/shm/local-ai-research-slots`). The committed record of the run is
`data/health/endpoints-2026-11-08.json`, checks `8.mtp_save_restore.slot_files[short]`,
`8.mtp_save_restore.prompt_cache[short]`, `8.mtp_save_restore.slot_files[long]`,
`8.mtp_save_restore.prompt_cache[long]` (all PASS, `FINDING: draft_state_preserved`).

## Evidence paths (repo-relative)

- `data/health/endpoints-2026-11-08.json` — the four check records with request, response and
  evidence fields
- `tests/fixtures/logs/cache-source-slot-restore.txt`,
  `tests/fixtures/logs/cache-source-prompt-cache.txt` — scrubbed log excerpts showing the
  draft-state save/restore lines and the prefix source
- `docs/progress-log.md` — the 2026-11-08 WP5 entry (full results and open issues)
- `docs/decisions.md` — "MTP draft state across restore" decision note
- `data/env/build-info.json` — build tag, commit, flags, binary hashes