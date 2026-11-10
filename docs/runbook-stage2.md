# Runbook: Stage 2 (features), the sessions after WP12 part 1

For Zack. Plan: `docs/plans/step-0-baseline.md` §5.4 (v1.6). Stage 2 runs as several sessions, each one a detached sweep
started with `scripts/run-sweep.sh` from a clean committed tree. The rules that decide each step are declared in the plan and
implemented by `python -m smallpc.stage2` (rules and interpretations: `docs/decisions.md`, "WP12 decisions"). The data is the
measurement: **never edit or delete anything under `data/raw/`.**

Order: **2f, 2a, 2a2, 2b, 2c, 2d, sanity check, 2e.** One session at a time (the GPU lock allows only one anyway).

## 1. Rules for every session
1. **Start from a clean committed tree, never `--allow-dirty`.** `git status --short` must print nothing. A generated spec lives
   in `configs/sweeps/`, so generate it, run `check`, and **commit it before the session** (`run-sweep.sh` refuses a dirty
   `src/`, `configs/` or `scripts/`). Any change of code or config between sessions is committed first and mentioned to Claude.
2. **Machine state.** Your desktop apps stay open for Stage 2 (G3 is not met, as in Stage 1: they are idle; the runner's idle gate
   checks the CPU before every cell). Plug in, do not reboot or log out until `state=complete`. **Stage 3 and Stage 4 need a quiet
   machine** (browser and IDE closed).
3. **Session ids** (so the tools and labels work): `s2f`, `s2a-32K`, `s2a-64K`, `s2a-128K`, `s2a2-32K`, ..., `s2b`, `s2c`, `s2d`.
   Never start an id with `ft-` (that prefix marks functional-test runs, which `decide` refuses).
4. **No `--rerun-flagged` before the 2f decision** (it reads the attempt-1 windows, and a re-run would be a second look). After
   2f, re-runs follow the Stage 1 rule (once, attempt 2).
5. After each session: run the **gate** (section 3), then **decide**, then commit the session data and the decision files
   (`data/raw/<id>`, `data/analysis/stage2/`), one commit per session: `WP12: <stage> session and decision`.
6. If a session stops, `docs/runbook-stage1.md` §5 applies word for word (resume with the same `--only` and `--session-id`).

## 2. The sessions
`$` is the repo root. All Python through `uv run`.

### 2f Host prompt cache (`--cache-ram`), first
Six cells, one session, 5 repetitions: the top placement at 128K with `--cache-ram` 8192, 4096, 2048 and 0, and at 64K with 8192 and 2048.
```
uv run python -m smallpc.stage2 spec --stage 2f --out configs/sweeps/stage2-2f.toml
uv run python -m smallpc.sweep check configs/sweeps/stage2-2f.toml        # expect 6 cells
git add configs/sweeps/stage2-2f.toml && git commit -m "WP12: stage 2f spec"
scripts/run-sweep.sh configs/sweeps/stage2-2f.toml --session-id s2f
scripts/sweep-status.sh s2f
uv run python -m smallpc.stage2 gate --stage 2f --session data/raw/s2f
uv run python -m smallpc.stage2 decide --stage 2f --sessions data/raw/s2f --out data/analysis/stage2/2f
```
**Automatic by rule:** the largest tested value with no paging-flagged window in any of its 5 repetitions, unless its mean T_turn_400
is more than 3% above the mean of the 8192 cell's clean units; the default stays if 8192 is clean; stop if no value is clean.
Output `status`:
- `decided`: `chosen_cache_ram` (null = the default 8192 stays). Go on to 2a.
- `needs_human`: the contexts chose different values; the proposal is the smallest. **A human confirms**, then passes `--cache-ram N`
  (or `default`) to the 2a spec by hand.
- `no_automatic_decision`: the 8192 cell has no clean unit (the 3% test cannot run) or every clean value is more than 3% slower. **A human decides.**
- `stop`: no tested value is clean: the cause is not the host cache. **Stop and report; do not start 2a.**

### 2a MTP (three sessions, one per context)
Per context five cells: both shortlisted placements with MTP off, the top placement with draft lengths 1, 2 and 3. MTP cells of P6
are probed fresh (the draft context costs VRAM); P6 cells with MTP off reuse the Stage 1 probe.
```
uv run python -m smallpc.stage2 spec --stage 2a --from-2f data/analysis/stage2/2f.json --out configs/sweeps/stage2-2a.toml
#   (or --cache-ram N|default after a human decision)
uv run python -m smallpc.sweep check configs/sweeps/stage2-2a.toml        # expect 15 cells
git add configs/sweeps/stage2-2a.toml && git commit -m "WP12: stage 2a spec"
scripts/run-sweep.sh configs/sweeps/stage2-2a.toml --only context=32K  --session-id s2a-32K
scripts/run-sweep.sh configs/sweeps/stage2-2a.toml --only context=64K  --session-id s2a-64K     # after the 32K gate
scripts/run-sweep.sh configs/sweeps/stage2-2a.toml --only context=128K --session-id s2a-128K
uv run python -m smallpc.stage2 gate --stage 2a --session data/raw/s2a-32K      # and the other two
uv run python -m smallpc.stage2 decide --stage 2a --sessions data/raw/s2a-32K data/raw/s2a-64K data/raw/s2a-128K --out data/analysis/stage2/2a
```
**Automatic by rule:** eligibility and §3.3 per context; the best draft length (best mean; among the draft lengths not
distinguishable from it by §3.3 steps 1 and 2, the smallest); MTP against the same placement with MTP off (MTP joins only if it
wins on T_turn_400, i.e. §3.3 step 1). Reported: acceptance per draft length, the paired effect on PP_fresh and TG, swap sensitivity.
Writes `data/analysis/stage2/2a-2a2-input.json`. **Human:** anything under "Human decision needed" (for example §3.3 step 2 preferring another draft length).

### 2a2 Second placement with MTP, and its comparators (three sessions)
Per context: the second placement with MTP off and with the best draft length, plus the top placement's 2a-best configuration re-run (the
anchor), so the winner and runner-up come from one session. Add `--no-anchor` only if you strike the anchor (the winner is then among
the second placement's cells only, which `decide` says).
```
uv run python -m smallpc.stage2 spec --stage 2a2 --from-2f data/analysis/stage2/2f.json --from-2a data/analysis/stage2/2a-2a2-input.json --out configs/sweeps/stage2-2a2.toml
uv run python -m smallpc.sweep check configs/sweeps/stage2-2a2.toml       # expect 9 cells
git add configs/sweeps/stage2-2a2.toml && git commit -m "WP12: stage 2a2 spec"
scripts/run-sweep.sh configs/sweeps/stage2-2a2.toml --only context=32K --session-id s2a2-32K      # then 64K, 128K
uv run python -m smallpc.stage2 gate --stage 2a2 --session data/raw/s2a2-32K
uv run python -m smallpc.stage2 decide --stage 2a2 --sessions data/raw/s2a2-32K data/raw/s2a2-64K data/raw/s2a2-128K --out data/analysis/stage2/2a2
```
**Automatic:** winner and runner-up per context by §3.3 (sanity pending). `data/analysis/stage2/2a2.json` holds the winner that 2b to 2d use (64K).

### 2b KV type, 2c load mode, 2d threads (64K, one session each, two cells)
```
W=data/analysis/stage2/2a2.json
uv run python -m smallpc.stage2 spec --stage 2b --from-2f data/analysis/stage2/2f.json --winner-from $W --out configs/sweeps/stage2-2b.toml
uv run python -m smallpc.stage2 spec --stage 2c --from-2f data/analysis/stage2/2f.json --winner-from $W --out configs/sweeps/stage2-2c.toml
uv run python -m smallpc.stage2 spec --stage 2d --from-2f data/analysis/stage2/2f.json --winner-from $W --default-threads <N> --out configs/sweeps/stage2-2d.toml
#   2d exits with code 3 ("not needed") when the default is 8 threads: then record it instead of running it:
uv run python -m smallpc.stage2 decide --stage 2d --default-threads 8 --out data/analysis/stage2/2d
```
Check each (expect 2 cells), commit, run `scripts/run-sweep.sh configs/sweeps/stage2-2b.toml --session-id s2b` (then `s2c`, `s2d`),
`gate --stage 2b --session data/raw/s2b`, `decide --stage 2b --sessions data/raw/s2b --out data/analysis/stage2/2b`.
**Automatic:** §3.3 on the two cells (paired T_turn_400, then T_reread, then fewer moving parts, then peak VRAM), the same with the heavy-swap
units removed. **Human:** a verdict that changes without the heavy-swap units, or a cell that is not eligible (for example FP16 KV not fitting).
2b re-probes the P6 cache for the FP16 cell. 2c compares `--load-mode auto` with the alternative recorded in `docs/decisions.md`.

### Sanity check (§5.6), before Stage 3
On the 2a2 winner and runner-up of each context and on the plain `--fit` reference of the same context (`P1-<context>-b2048`).
Detached, under the GPU lock, one run per context:
```
scripts/run-detached.sh --gpu sanity-32K -- uv run --frozen python -m smallpc.sanity run \
    --cells <winner-32K> <runner-up-32K> --reference P1-32K-b2048 --out data/sanity/stage2-32K.json
```
Cell names are looked up in `data/raw/*/resolved/`. The file feeds `python -m smallpc.select --sanity`. **Human:** a `fail` or a reference
warning ("the reference repeats ...") in the file.

### 2e llama-bench cross-check
```
uv run python -m smallpc.stage2 bench-crosscheck --list-expressibility      # which 64K cell llama-bench can express most completely
scripts/run-detached.sh --gpu bench-crosscheck -- uv run --frozen python -m smallpc.stage2 bench-crosscheck \
    --cell P2-64K-b4096 --out data/microbench/crosscheck-P2-64K-b4096.json
```
The default is the Stage 1 64K candidate with the fewest inexpressible fields (P2-64K-b4096: only the context is approximated, through `-fitc`).
Random-token prompts; labelled "cross-check ... never used for a decision"; the fields llama-bench cannot express are listed in the file.

## 3. The gate after every session
The next session may start only if the gate passes: `uv run python -m smallpc.stage2 gate --stage <stage> --session data/raw/<id>`
(exit 0 = pass). Criteria (the Stage 1 gate):
- **a** the runner exited with 0 and the state is `complete`;
- **b** every cell has a final record;
- **c** no `accounting`, `warm_prefill` or `cache_miss` flag;
- **d** no `thermal` or `drift` flag;
- **e** no `did_not_fit` with reason `startup_failure`, `startup_timeout`, `crash_mid_cell` or `oom_runtime` (other reasons, such as `oom_at_load`, are results);
- **f** at most 20% of the measured (attempt-1) windows paging-flagged.

Two changes for Stage 2: **f does not apply to 2f** (paging is what 2f measures: the gate prints the number of flagged windows per cell and the
next step is `decide`, not a stop); **from 2a onward f applies with the chosen `--cache-ram`**, and more than 20% flagged stops everything for a
human: the 2f choice did not hold. Any failed criterion means **stop and report; do not start the next session**.

## 4. Where a human decides (an unattended run stops and reports here)
1. 2f `needs_human`: the contexts chose different `--cache-ram` values (proposal: the smallest).
2. 2f `no_automatic_decision`, or `stop` (no clean value: the cause is not the host cache).
3. A failed gate criterion, in particular f from 2a onward.
4. Anything listed under "Human decision needed" in a decision file (§3.3 step 2 preferring another draft length; a missing or ineligible MTP-off cell; only one
   eligible cell in 2b to 2d; a verdict that changes without the heavy-swap units; no eligible cell in a context).
5. The 2a2 anchor: striking it (`--no-anchor`) is a human decision; the default keeps it.
6. Any combination across contexts that the plan does not state.
7. 2d: the default thread count differs from 8 (then 2d runs) or equals 8 (recorded as skipped).
8. A sanity `fail`, or a reference warning, before Stage 3.
9. Everything that `decide` refuses: a session started with `--allow-dirty`, a functional-test spec or id, or a session that is not complete. There is no flag
   to override this; start the session again from a clean tree.

## 5. Expected duration
PLACEHOLDER (filled in by WP12 part 1, check 8).
