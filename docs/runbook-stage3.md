# Runbook: Stage 3 (final comparison, three sessions) and Stage 4 (reproducibility)

For Zack. Plan: `docs/plans/step-0-baseline.md` §5.4 (v1.7, "Stage 3: Final" and "Stage 4: Reproducibility"); the rules and how the tools read them:
`docs/decisions.md`, "WP13 decisions". These are the **headline results**, so **gate G3 applies in full: the machine is quiet** (section 2). The data is the
measurement: **never edit or delete anything under `data/raw/`.** No code or config changes once the first session has started; if one is needed, stop and ask.

Stage 3 = **three sessions** (32K, 64K, 128K), each one detached sweep of two cells (`stock-<C>` and `tuned-<C>`, 5 repetitions, start and end canaries), then
**one `--rerun-flagged` pass per session**, then the **sanity check on the three tuned config files**, then the **headline tool** and the **report**.
Stage 4 is **another day**: `stock-64K` and `tuned-64K` again, then the S2 check.

## 1. Rules for every session
1. **Clean committed tree, never `--allow-dirty`.** `git status --short` prints nothing (`run-sweep.sh` refuses a dirty `src/`, `configs/` or `scripts/`). The six cells are the
   committed files `configs/server/{stock,tuned}-{32k,64k,128k}.toml` plus `--metrics -lv 4` from the spec; do not touch them.
2. **Session ids** (the tools and the headline's refusals depend on them): `stage3-32K`, `stage3-64K`, `stage3-128K`, `stage4`. Never start an id with `ft-` (functional-test
   runs; `stage3 headline` refuses them), and never use `--allow-dirty` (also refused).
3. **One session at a time** (the GPU lock allows only one). Do the **gate** (section 4) after each session, then its **one** re-run pass, then the next session.
4. After each session (and its re-run): commit `data/raw/<id>` and the conditions log: `WP13: Stage 3 <C> session`. If a session stops, `docs/runbook-stage1.md` section 5 applies word
   for word (resume with `--resume`, the same `--only` and `--session-id`).
5. Stock keeps llama.cpp's defaults, **including `--cache-ram 8192`**, so its later repetitions may be paging-flagged at 64K and 128K. That is how stock behaves here: it is reported,
   not hidden, and never fails the gate.

## 2. G3: the quiet-machine checklist (before every session, Stage 3 and Stage 4)
Close everything except **one terminal with Claude Code**. Tick each box:
- [ ] **Browser** closed, every window (Chrome, Chromium, Firefox, any other).
- [ ] **IDE and editors** closed (antigravity-ide, kilo, VS Code `code`, Obsidian, any other).
- [ ] **Music and chat apps** closed (Spotify, Discord, Slack, any other).
- [ ] **System monitors** closed (mission center, htop, nvtop, any other left running).
- [ ] **Games and VMs** closed (Steam, QEMU, virt-manager).
- [ ] The PC is on **mains power**; you do not trigger sleep, suspend, reboot or log-out until the session says `state=complete`.
- [ ] **Nothing else on the GPU**: `nvidia-smi` shows only a few MiB used; `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` prints nothing;
      `pgrep -a llama-server` prints nothing.
- [ ] **You do not use the PC during the session** (no browsing, builds, downloads, large copies, other models). Look at `scripts/sweep-status.sh` from the terminal only.
- [ ] `git status --short` prints nothing.

**How to check what is still running, by process name** (names only, never window titles, URLs or command lines):
```
cd /mnt/data/local-ai-research
scripts/check-quiet.sh                 # blocklisted apps by name (configs/quiet-check.toml); exit 1 = something must be closed; also warns above 1.5 GiB resident
ps -eo comm= | sort | uniq -c | sort -rn | head -40      # the full picture by name, if you want to see everything
pgrep -a llama-server                  # must print nothing
```
`check-quiet.sh` also prints the CPU idle figure as information (the runner's own idle gate needs below 10% busy over 10 s before every cell). **Run it before every session;
a session does not start while it exits 1.** The desktop environment, the terminal and `claude` are allowed. Paste its output into `docs/stage3-conditions.md` (template in that file),
with MemAvailable (`grep MemAvailable /proc/meminfo`; 24 GiB or more expected, the runner aborts below 20) and the `nvidia-smi` memory line. Record it, then commit with the data.

## 3. The order
`$` is the repo root. Python through `uv run`. Each session starts, prints its id and returns at once (detached; it survives closing the terminal).

### Per session (repeat for 32K, then 64K, then 128K)
```
cd /mnt/data/local-ai-research
git status --short                                   # nothing
scripts/check-quiet.sh                               # exit 0, then record it in docs/stage3-conditions.md
uv run python -m smallpc.sweep check configs/sweeps/stage3.toml --only context=32K    # expect 2 cells (6 in the spec)
scripts/run-sweep.sh configs/sweeps/stage3.toml --only context=32K --session-id stage3-32K
scripts/sweep-status.sh stage3-32K                   # from the terminal; nothing else is open
```
When it says `state=complete`:
```
uv run python -m smallpc.stage3 gate --session data/raw/stage3-32K --spec configs/sweeps/stage3.toml      # section 4; exit 0 = pass
scripts/run-sweep.sh configs/sweeps/stage3.toml --rerun-flagged stage3-32K       # ONE pass per session, only if a unit is flagged (it takes the stored --only)
git add data/raw/stage3-32K docs/stage3-conditions.md && git commit -m "WP13: Stage 3 32K session"
```
`--rerun-flagged` re-runs every flagged unit once (attempt 2 on a fresh server, with its own canaries); never twice. Then the **same for 64K** (`--only context=64K`, `stage3-64K`)
and **128K** (`--only context=128K`, `stage3-128K`). Do not start a session before the previous one's gate passed.

### After the third session: sanity check on the three tuned config FILES (paths, not cell names)
Detached, under the GPU lock, one run per context, against the plain `--fit` reference of the same context:
```
scripts/run-detached.sh --gpu sanity-stage3-32K -- uv run --frozen python -m smallpc.sanity run \
    --cells configs/server/tuned-32k.toml --reference P1-32K-b2048 --out data/sanity/stage3-32K.json
scripts/run-detached.sh --gpu sanity-stage3-64K -- uv run --frozen python -m smallpc.sanity run \
    --cells configs/server/tuned-64k.toml --reference P1-64K-b2048 --out data/sanity/stage3-64K.json
scripts/run-detached.sh --gpu sanity-stage3-128K -- uv run --frozen python -m smallpc.sanity run \
    --cells configs/server/tuned-128k.toml --reference P1-128K-b2048 --out data/sanity/stage3-128K.json
uv run python tools/merge_sanity.py data/sanity/stage3-32K.json data/sanity/stage3-64K.json data/sanity/stage3-128K.json --out data/sanity/stage3-all.json
```
Entries are keyed by file stem (`tuned-32k`) and carry the file's sha256, which the headline tool checks against the file as it is. Expect `pass` for all three and the token
hashes of Stage 2 (`data/sanity/stage2-all.json`, same configs; WP13 part 1 checked this on the three files: all pass, all nine token hashes equal). **A `fail`, or a reference warning, stops everything (section 5).** About 2.5 minutes in all (measured: 143 s for the three runs, reference plus tuned file each).

### The headline and the report
```
uv run python -m smallpc.stage3 headline --sessions data/raw/stage3-32K data/raw/stage3-64K data/raw/stage3-128K \
    --sanity data/sanity/stage3-all.json --out data/analysis/stage3/headline
uv run python -m smallpc.report render --sessions data/raw/stage3-32K data/raw/stage3-64K data/raw/stage3-128K \
    --out reports/stage3 --label results --sanity data/sanity/stage3-all.json
git add data/sanity data/analysis/stage3 reports/stage3 && git commit -m "WP13: Stage 3 analysis"
```
The headline tool prints, per context, which headline was chosen (clean or all units, with its label), any disagreement between the two versions and any **HUMAN DECISION NEEDED**.
It **refuses** a session recorded with `allow_dirty`, with an `ft-` id or a functional-test spec header, or not complete; there is no flag around that.
Read the first paragraph of `headline.md` first.

## 4. The gate after every session
`uv run python -m smallpc.stage3 gate --session data/raw/<id> --spec configs/sweeps/stage3.toml` (exit 0 = pass; `--json` for the full record). It reuses the Stage 2 gate for a to e:
- **a** the runner exited with 0 and the state is `complete`;
- **b** every cell has a final record;
- **c** no `accounting`, `warm_prefill` or `cache_miss` flag (stock and tuned);
- **d** no `thermal` or `drift` flag;
- **e** no `did_not_fit` with reason `startup_failure`, `startup_timeout`, `crash_mid_cell` or `oom_runtime`.

**f (paging), changed for Stage 3:** over the attempt-1 windows of the **TUNED cells and the canaries only**, stop if more than **40%** are paging-flagged, or if any paging-flagged window
shows more than **1,024 MiB** of swap growth. The **STOCK cells' paging and swap figures are printed and never fail the gate** (stock keeps `--cache-ram 8192` and pages on this machine).
Any failed criterion means **stop and report; do not start the next session** (section 5).

## 5. Stop conditions and where a human decides
**Stop (do not continue, report):**
1. A failed gate criterion (a to f) in any session.
2. `check-quiet.sh` exits 1 and the app cannot be closed; MemAvailable below 20 GiB; a foreign GPU process; the machine goes to sleep or reboots mid-session (then `docs/runbook-stage1.md` section 5).
3. A session refuses to resume with a provenance error (spec, manifest or sampling changed): do not work around it.
4. Anything that would need `--allow-dirty`, `sudo`, or a change of code or config.

**A human decides (the tools report it and change nothing):**
1. **A tuned cell is not eligible in final mode** (5 clean units, at least 512 MiB of VRAM free, a sanity pass; the headline prints the reasons). Nothing is substituted; the step lead decides.
2. **The two versions of a headline disagree** (sign, or one interval excludes 1.0 and the other does not): the headline's first paragraph says so; the step lead reads both.
3. **A sanity failure or reference warning** on any tuned config file.
4. The headline uses **all units** for a context (a stock cell with fewer than 5 clean, paired units after the re-run pass): the headline is labelled and the `S4(d) deviation for this context`
   line is recorded in `docs/decisions.md` by Claude; the step lead confirms.
5. A swap sensitivity that changes a headline comparison (reported in the headline output).

## 6. Stage 4, on a different day
Same machine state (section 2). Stage 4 is one session of two cells; there is no `--only`.
```
cd /mnt/data/local-ai-research
git status --short                                   # nothing; the code and the configs are the ones of Stage 3
scripts/check-quiet.sh                               # exit 0; record it in docs/stage3-conditions.md
uv run python -m smallpc.sweep check configs/sweeps/stage4.toml        # expect 2 cells
scripts/run-sweep.sh configs/sweeps/stage4.toml --session-id stage4
uv run python -m smallpc.stage3 gate --session data/raw/stage4 --spec configs/sweeps/stage4.toml
scripts/run-sweep.sh configs/sweeps/stage4.toml --rerun-flagged stage4             # once, only if a unit is flagged
git add data/raw/stage4 docs/stage3-conditions.md && git commit -m "WP13: Stage 4 session"
```
**The S2 check** (T_turn_400, fresh prefill at 32K and decode at 32K depth; each re-measured mean must fall inside its original 95% CI or within 5%, whichever is wider):
```
uv run python -m smallpc.stage3 repro --original data/raw/stage3-64K --rerun data/raw/stage4 --cells stock-64K,tuned-64K
```
`report repro` evaluates clean units only; `stage3 repro` is the same check except that a cell with **fewer than 5 clean units on either day** (typically stock-64K) is evaluated on **all
units**, and the output says so in its first line. Exit 0 = all PASS. Record the table in `docs/decisions.md` and the progress log. (The README walkthrough from a clean shell is a separate WP13 task.)

## 7. Expected durations (computed in WP13 part 1 from the Stage 1 and Stage 2 per-cell times)
Inputs, all measured (seconds, `phases_s` of the cell summaries in `data/raw`): a cell's **fixed time** is everything but the repetitions (idle check, launch, snapshot, warm-up, shutdown, parse),
its **repetition time** is `measure` divided by the repetitions. Stock cells come from Stage 1 (2 repetitions, scaled to 5); tuned cells from the Stage 2 winners (5 repetitions, as measured).

| context | stock: fixed + 5 x repetition | tuned: fixed + 5 x repetition | canaries (start + end) | session |
|---|---|---|---|---|
| 32K  | 34.8 + 5 x (169.8 / 2 = 84.9) = **459** | 25.8 + 5 x (215.4 / 5 = 43.1) = **241** (`s2a-P6-32K-b4096-mtp0`) | 197.8 + 184.9 = **383** | 459 + 241 + 383 = 1,083 s = **18 min** |
| 64K  | 37.9 + 5 x (306.5 / 2 = 153.3) = **804** | 25.7 + 5 x (377.6 / 5 = 75.5) = **403** (`s2b-P6-64K-b4096-mtp1-kvf16`) | 183.8 + 186.2 = **370** | 804 + 403 + 370 = 1,577 s = **26 min** |
| 128K | 45.0 + 5 x (653.7 / 2 = 326.9) = **1,679** | 25.2 + 5 x (690.2 / 5 = 138.0) = **715** (`s2b-P6-128K-b4096-mtp0-kvf16`) | 182.9 + 193.6 = **376** | 1,679 + 715 + 376 = 2,771 s = **46 min** |

- **Three Stage 3 sessions: 1,083 + 1,578 + 2,771 = 5,432 s = 90 min; with 10% for idle waits and cold loads 100 min (1.7 h).** No probing is needed (the cache sizes are fixed numbers in the files),
  which Stage 1 and 2 sessions had; the estimates of those sessions were within 3% of the actual duration (Stage 1: 0.83, 1.20, 2.19 h against 0.85, 1.28, 2.18 h; `s2a-64K` 46.5 against 47 min).
- **Re-run pass** (one per session, only if a unit is flagged): a fresh server per cell with flagged units, `fixed + units x repetition`, plus the re-run canaries (about 190 s each, 6.3 min).
  Worst case with 3 flagged stock units: 32K 35 + 3 x 85 = 290 s + 380 s canaries = 11 min; 64K 38 + 3 x 153 = 497 + 380 = 15 min; 128K 45 + 3 x 327 = 1,026 + 380 = 23 min; 49 min in all.
  **Upper bound for Stage 3: 100 + 49 = 149 min = 2.5 h**, which is the plan's "about 2.5 hours".
- **Sanity check on the three tuned files:** about 2.5 min, **measured in WP13 part 1** (09:05:31Z to 09:07:54Z, 143 s: three runs of two servers each, the reference and the tuned file; Stage 2 needed 70 to 76 s per run with three servers).
- **Functional run of the Stage 3 path** (WP13 part 1, `ft-stage3-32K`: stock-32K and tuned-32K, 1 repetition, 1-repetition canaries): 6.3 min (08:58:44Z to 09:05:04Z), a check of the path, not a timing basis.
- **Stage 4** (one session, `stock-64K` + `tuned-64K` + canaries): 804 + 403 + 370 = 1,577 s = **26 min; 29 min with 10%**, upper bound with a worst-case re-run pass (stock-64K, 3 units: 15 min) **44 min**.
  The plan says about 30 minutes.
- Add the analysis (headline, report, commits): about 10 minutes each time, no GPU. Allow a day for Stage 3 and a different day for Stage 4.
