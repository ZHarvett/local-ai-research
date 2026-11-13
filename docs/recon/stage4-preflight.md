# T-019 — Stage 4 pre-flight (no GPU)

<!-- sources: docs/runbook-stage3.md, docs/runbook-stage1.md, docs/recon/commands.env, docs/recon/stage3-commit.txt, docs/recon/T-001.md, docs/plans/step-0-baseline.md, configs/sweeps/stage4.toml, configs/sweeps/stage3.toml, configs/machine.toml, configs/model.toml, data/env/build-info.json, data/raw/stage3-64K/cells/stock-64K-22dc1178.json, data/raw/stage3-64K/cells/tuned-64K-f9b81a84.json, data/raw/stage3-64K/resolved/stock-64K.toml, data/raw/stage3-64K/resolved/tuned-64K.toml, scripts/run-sweep.sh, scripts/check-quiet.sh, scripts/sweep-status.sh, scripts/run-detached.sh, scripts/with-gpu-lock.sh, scripts/_common.sh, src/smallpc/sweep/runner.py, src/smallpc/sweep/session.py, src/smallpc/sweep/core.py, src/smallpc/sweep/spec.py, src/smallpc/sweep/provenance.py, src/smallpc/render.py, src/smallpc/stage3/cli.py, src/smallpc/stage3/gate.py, src/smallpc/stage3/repro.py, src/smallpc/report.py, PLAN.md -->

Session date: 2026-11-13 (UTC). Lane 1, main checkout. This file is the pre-review of T-007
(Stage 4 session): S1 lists every command Stage 4 will run with its pass signature and stop
rules; S2 records the eight pre-flight checks. **No server was started and the GPU was not
used**: every check below is a file read, a `--help`/`check` invocation, a git query, or a
lock probe. P8 initially FAILed (T-017's uncommitted edits in the main checkout); the owning
lane committed them mid-session and the redo-safe re-check passes — the full sequence is
recorded in §2.8. <!-- derived: internal section cross-reference --> All eight checks PASS in the final record.

## 1. S1 — the Stage 4 command list (runbook §6, with §1–§5)

Stage 4 is **one session of two cells** (`stock-64K`, `tuned-64K`), 5 repetitions each, start
and end canaries, **no `--only`** (runbook §6). Gate G3 (§2) applies in full; the rules of §1
apply (clean committed tree, never `--allow-dirty`, session id `stage4`, one session at a
time, stock keeps llama.cpp's defaults including `--cache-ram 8192` — reported, never hidden,
never fails the gate). Expected duration (§7): 804 + 403 + 370 = 1,577 s = **26 min; 29 min
with 10%**, upper bound with a worst-case re-run pass **44 min**.

### 1.1 Before the session — G3 quiet-machine checklist (§2)

| # | command | expected pass signature | stop rule |
|---|---|---|---|
| 0 | `cd /mnt/data/local-ai-research` | repo root | — |
| 1 | `git status --short` | prints nothing. Kit bookkeeping (`.workflow/state.json`, `PROGRESS.md`) is exempt from the sweep's own dirty check, which looks only at `src configs scripts` (`scripts/run-sweep.sh:55-61`; T-001 A15). Any OTHER dirty path stops the start (P8). | §5.4: anything needing `--allow-dirty` stops |
| 2 | `scripts/check-quiet.sh` | exit 0 = quiet (blocklist `configs/quiet-check.toml`, process names only). Prints the CPU idle figure as information; warns above 1.5 GiB resident. Paste its output into `docs/stage3-conditions.md`. | exit 1 = a blocklisted app runs: close it; if it cannot be closed, stop (§5.2). exit 2 = usage error |
| 3 | `grep MemAvailable /proc/meminfo` | 24 GiB or more expected; record it in `docs/stage3-conditions.md` | the runner aborts below 20 GiB (§2); below 20 GiB stops (§5.2) |
| 4 | `nvidia-smi` (memory line) | only a few MiB used; record the line in `docs/stage3-conditions.md` | a foreign GPU process stops (§5.2) |
| 5 | `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader` | prints nothing | any compute app stops (§5.2) |
| 6 | `pgrep -a llama-server` | prints nothing | a leftover server: runbook-stage1.md §5.4/§5.6 (resume stops it, or close what holds the GPU) |
| 7 | (optional full picture) `ps -eo comm= \| sort \| uniq -c \| sort -rn \| head -40` | names only, never window titles/URLs/command lines | — |

Non-command boxes (§2): browser, IDE/editors, music/chat, system monitors, games/VMs all
closed; mains power; no sleep/suspend/reboot/log-out until `state=complete`; **the PC is not
used during the session** — look at `scripts/sweep-status.sh` from the terminal only. One
terminal with Claude Code stays open. The runner's own per-cell idle gate needs below 10%
busy over 10 s before every cell (§2; `src/smallpc/sweep/session.py` precondition_step).

### 1.2 The session (§6)

| # | command | expected pass signature | stop rule |
|---|---|---|---|
| 8 | `uv run python -m smallpc.sweep check configs/sweeps/stage4.toml` | exit 0; JSON `"cells": 2`, `"cells_in_spec": 2`, one stock + one tuned, both `context=64K`, `"repetitions": 5`, `"canary": true` (verified in P2 below) | `SpecError`/validation → exit 2 with `smallpc.sweep: …` on stderr; stop, do not edit the spec (§5.4) |
| 9 | `scripts/run-sweep.sh configs/sweeps/stage4.toml --session-id stage4` | prints `session: stage4`, `session dir: data/raw/stage4`, `job dir: data/logs/jobs/sweep-stage4-<stamp>`, `status: scripts/sweep-status.sh stage4` and returns at once (detached). Internally: spec check → dirty check (`src configs scripts`) → `systemd-inhibit` test → `run-detached.sh --gpu` → `with-gpu-lock.sh` (flock on `.locks/gpu.lock`, fd 9) → `systemd-inhibit --what=sleep:idle --mode=block` → `uv run --frozen python -m smallpc.sweep run … --inhibit-tag …`. Servers start only through `scripts/launch-server.sh`, stop through `scripts/stop-server.sh` (`src/smallpc/sweep/server.py:1-2`). | refuses: dirty `src/ configs/ scripts/` (never pass `--allow-dirty`); `data/raw/stage4` already exists (use `--resume`); `systemd-inhibit` refused (stops, never runs unprotected); GPU lock held → exit 75. Any refusal: stop and report (§5) |
| 10 | `scripts/sweep-status.sh stage4` | read-only status; wait until `state=complete`. Runner exits 0 and the state is `complete` (gate criterion a). | if it stops: `docs/runbook-stage1.md` §5 word for word — wait while `updated` is fresh; `kill -INT <pid>` only after >20 min without movement (never `kill -9` first); resume with `--resume` and the same `--session-id` (Stage 4 has no `--only`); a provenance refusal (spec/manifest/sampling changed) is never worked around (§5.3); sleep/reboot mid-session → §5.2 + stage1 §5 |
| 11 | `uv run python -m smallpc.stage3 gate --session data/raw/stage4 --spec configs/sweeps/stage4.toml` | **exit 0 = pass** (`src/smallpc/stage3/cli.py:50`); with `--json`: `"pass": true`, `"failed": []` (`gate.py:149-163`). Criteria a–e (Stage 2 gate): runner exit 0 + complete; every cell has a final record; no `accounting`/`warm_prefill`/`cache_miss` flag; no `thermal`/`drift` flag; no `did_not_fit` with reason `startup_failure`/`startup_timeout`/`crash_mid_cell`/`oom_runtime`. Criterion f: at most **40%** of the attempt-1 windows of the **tuned cells and canaries** paging-flagged, and no flagged window above **1,024 MiB** swap growth; **stock paging is printed and never fails the gate** (`gate.py:26-27,90-131`). | any failed criterion: **stop and report; do not continue** (§5.1). **R2**: if the gate fails ONLY because of tuned-64K paging and every flagged unit re-runs clean, accept with a recorded deviation — a `docs/decisions.md` line starting `- R2 applied: Stage 4`. Any other gate failure is escalated. |
| 12 | `scripts/run-sweep.sh configs/sweeps/stage4.toml --rerun-flagged stage4` | **once, only if a unit is flagged**: re-runs every flagged unit once (attempt 2 on a fresh server, with its own canaries); never twice. Takes the stored `--only` (none for Stage 4). Then re-run the gate (row 11) on the re-run session data. | a second re-run pass is forbidden (§3); any new failure: stop and report |
| 13 | `git add data/raw/stage4 docs/stage3-conditions.md && git commit -m "WP13: Stage 4 session"` | commit after the gate and the one re-run pass; `data/raw/` is append-only, never edited or deleted | — |

### 1.3 The S2 check (§6)

| # | command | expected pass signature | stop rule |
|---|---|---|---|
| 14 | `uv run python -m smallpc.stage3 repro --original data/raw/stage3-64K --rerun data/raw/stage4 --cells stock-64K,tuned-64K` | **exit 0 = all PASS** (`cli.py:60`). Metrics (`report.py` REPRO_METRICS, T-001 A4): `T_turn_400 (s)`, fresh prefill at 32K `(tok/s)`, decode at 32K depth `(tok/s)`; each re-measured mean inside its original 95% CI **or within 5%, whichever is wider**. Clean units only, EXCEPT a cell with fewer than 5 clean units on either day is evaluated on **all units** and the first line says so: `**S2 evaluated on ALL units (flagged units included) for: <cell> (<day> has <n> clean of <m> unit(s))…**` (`repro.py:16-38,43-48`); every metric line ends `- <cell>, <metric>: evaluated on clean units\|all units`. Record the table in `docs/decisions.md` and the progress log. | **R4: an S2 failure is reported and escalated, never re-measured automatically.** **R1**: tuned-64K gets stock's fallback — fewer than 5 clean units after its re-run → S2 on all units, labelled, recorded as an S4(d) deviation. |

### 1.4 Stop rules and human decisions (summary)

**Stop (§5):** (1) a failed gate criterion a–f; (2) `check-quiet.sh` exit 1 with an app that
cannot be closed, MemAvailable below 20 GiB, a foreign GPU process, sleep/reboot mid-session;
(3) a resume refused with a provenance error — never work around it; (4) anything needing
`--allow-dirty`, `sudo`, or a code/config change. **No code or config changes once the session
has started** (runbook header); the shared-rule code freeze holds until T-008 is accepted.

**A human decides (§5, tools report and change nothing):** a tuned cell not eligible in final
mode; the two headline versions disagreeing; a sanity failure or reference warning; an
all-units headline (the `S4(d) deviation for this context` line is recorded in
`docs/decisions.md`, the step lead confirms); a swap sensitivity that changes a headline
comparison. Stage 4 additions (card, declared 12 November 2026): **R1** tuned-64K all-units
fallback; **R2** tuned-64K-paging-only gate failure accepted with a recorded deviation when
every flagged unit re-runs clean; **R3** Stage 4 runs on 13 November 2026 or later from the
frozen code state (checked in P7); **R4** S2 failures escalate, never auto-re-measure.

## 2. S2 — pre-flight checks (no server, no GPU)

| P1 | PASS | every runbook-named script exists and is executable; GPU lock path present and free (§2.1) |
| P2 | PASS | stage4.toml renders, for BOTH cells, argv byte-identical to the Stage 3 64K records: equal sha256, equal config_hash, byte-equal resolved TOML (§2.2) |
| P3 | PASS | `sweep run --help` lists `--resume`, `--rerun-flagged`, `--only`; the wrapper usage lists the same (§2.3) |
| P4 | PASS | `data/raw/stage4` does not exist (§2.4) |
| P5 | PASS | free 152,697,622,528 B ≥ 2 × 775,006 B (largest Stage 3 session) (§2.5) |
| P6 | PASS | `bash -n docs/recon/commands.env` exit 0; every named tool and subcommand exists (§2.6) |
| P7 | PASS | R3 check exits 0 at HEAD; date 2026-11-13 satisfies "13 November 2026 or later" (§2.7) <!-- derived: internal section cross-reference --> |
| P8 | PASS | re-check at HEAD `ca1d5ad`: `git status --porcelain` empty, sweep dirty check empty; the initial FAIL (T-017's uncommitted loop edits) was resolved by lane 3's own commit `bc8e0c3` (§2.8, §2.9) <!-- derived: internal section cross-reference --> |

### 2.1 P1 — scripts and the GPU lock

Re-run: `for f in scripts/check-quiet.sh scripts/sweep-status.sh scripts/run-detached.sh scripts/run-sweep.sh scripts/with-gpu-lock.sh scripts/launch-server.sh scripts/stop-server.sh; do test -x "$f" && echo "EXECUTABLE $f"; done`

All seven printed `EXECUTABLE`. `scripts/_common.sh` has no exec bit, which is correct: it is
a sourced library (`source "$here/_common.sh"`, e.g. `run-sweep.sh:25`), never executed.
GPU lock path (`scripts/_common.sh:7`): `.locks/gpu.lock` — exists, 0 bytes, and the
non-blocking probe `( exec 8>.locks/gpu.lock; flock -n 8 )` succeeded → **free** (the same
probe `run-detached.sh:37-40` uses; it creates the file if absent and holds nothing).

### 2.2 P2 — Stage 4 spec renders the Stage 3 argument lists (both cells)

**Runbook check first:** `uv run --frozen --quiet python -m smallpc.sweep check configs/sweeps/stage4.toml`
→ exit 0 (this is exactly what `run-sweep.sh:53` runs internally):

```json
{ "name": "stage4", "cells": 2, "cells_in_spec": 2, "stock_cells": 1,
  "by_context": { "64K": 2 },
  "by_axis": { "profile": { "stock": 1, "tuned": 1 } },
  "repetitions": 5, "canary": true,
  "first_in_order": [ "tuned-64K", "stock-64K" ] }
```

**How the argument lists were obtained.** Through the runner's own code path, with no server
and no GPU: `load_sweep` → `spec.expand` (merges `[defaults]`/`[stock_defaults]` under the
config file via `apply_defaults`, `spec.py:117-160`) → `ServerConfig.model_validate` →
`render.render_argv(cfg, machine, model)` with `configs/machine.toml` + `configs/model.toml`
— exactly `Session.prepare_job` (`session.py:315-325`) and `default_env` (`core.py:125-127`).
The effective TOML is `spec.render_toml(profile, cfg.effective().model_dump(exclude_none=True))`
as `session.py:321-324` writes it. A scratch script (inlined below) ran this via
`uv run --frozen python -I /tmp/t019-preflight/render_check.py` and compared against the
recorded Stage 3 cells. **Checksum definition:** sha256 of the compact JSON of the argv list,
`json.dumps(argv, separators=(",", ":"))` encoded UTF-8, applied identically to the rendered
and the recorded list. `config_hash` is `provenance.config_hash(argv, model_sha256,
llama_cpp_commit)` (`provenance.py:69-73`) computed with the model sha256 and llama.cpp commit
**recorded in the Stage 3 cell records**.

| cell | argv sha256 (rendered = recorded) | config_hash (rendered = recorded) | resolved TOML sha256 (rendered = recorded) |
|---|---|---|---|
| stock-64K | `ab87c02dba7672e82c55e99a3fa5e31a0daee9888cfe1e61edaededf75e04b7f` | `22dc1178c8d9b555` | `a427277018951471ccb9c8e6deb1599623b01b193b49afaeda88d1387ed42bbd` |
| tuned-64K | `4775ccde4104da0e14f17d28b2495eeaf4c8f5f1d2e338d3b785a9a30e86ef31` | `f9b81a840bab20cf` | `735f0aebb7fb7330a8313dca3f65e44e771b4c2c336e7767dc469597cf093ffb` |

<!-- derived: checksums computed by the inlined render_check.py from configs/sweeps/stage4.toml + configs/machine.toml + configs/model.toml (rendered) and the named data/raw/stage3-64K records (recorded); rendered == recorded for every value, argv list equality and resolved-TOML byte equality also true -->

Records compared: `data/raw/stage3-64K/cells/stock-64K-22dc1178.json` and
`data/raw/stage3-64K/cells/tuned-64K-f9b81a84.json` (`argv`, `config_hash`, `model_sha256`,
`llama_cpp_commit`, `resolved_config`); resolved TOMLs
`data/raw/stage3-64K/resolved/{stock,tuned}-64K.toml`. The script's summary:
`"env_matches_records": true, "all_equal": true` — the current `configs/model.toml` declared
sha256 (`42739874…`) and `data/env/build-info.json` commit (`57d04820…`) equal the recorded
values in both cells, so the comparison holds against the CURRENT environment, not only the
stored records. Rendered argv (stock): binary, `-m <model>`, `--host 127.0.0.1`, `--port 8080`,
`-c 65536`, `--metrics`, `-lv 4` (12 items; no `--cache-ram`, i.e. llama.cpp's default).
Rendered argv (tuned): the same head plus `-cmoe`, `--moe-cache-mib 9472`, `-b 4096`,
`-ub 4096`, `-ctk f16`, `-ctv f16`, `-fa on`, `-np 1`, `--spec-type draft-mtp`,
`--spec-draft-n-max 1`, `--cache-ram 2048`, `--metrics`, `-lv 4` (33 items).

**Independent cross-check (repo CLI only):** for each cell,
`uv run --frozen --quiet python -m smallpc.render data/raw/stage3-64K/resolved/<cell>.toml`
printed exactly `shlex.join(recorded argv)` → `True` for both cells.

**Spec identity:** `diff configs/sweeps/stage3.toml configs/sweeps/stage4.toml` differs only
in the header comment, `name`, `expect_cells` (6 vs 2), the four non-64K cell blocks and one
comment line above `[canary]`; the two 64K cell blocks, `[defaults]`, `[stock_defaults]` and
`[canary]` are identical (T-001 A3). The canary therefore renders identically too; its
recorded cells all carry the same config hash suffix `debea778`.

Re-run script (scratch, read-only; writes nothing into the repo):

```python
# /tmp/t019-preflight/render_check.py — run: uv run --frozen python -I /tmp/t019-preflight/render_check.py
import hashlib, json
from pathlib import Path
from smallpc.config import ServerConfig, load_machine, load_model, load_sweep
from smallpc.render import render_argv
from smallpc.sweep import provenance
from smallpc.sweep import spec as sp

ROOT = Path("/mnt/data/local-ai-research")
SESS = ROOT / "data/raw/stage3-64K"

def sha_argv(argv):
    return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()

spec = load_sweep(ROOT / "configs/sweeps/stage4.toml")
cells = sp.expand(spec, ROOT)
sp.validate_cells(cells)
machine = load_machine(ROOT / "configs/machine.toml")
model = load_model(ROOT / "configs/model.toml")
build = json.loads((ROOT / "data/env/build-info.json").read_text())
out = {"cells": {}}
for c in cells:
    rec = json.loads(next((SESS / "cells").glob(f"{c.name}-*.json")).read_text())
    cfg = ServerConfig.model_validate({"profile": c.profile, **c.overrides})
    argv = render_argv(cfg, machine, model)
    eff = cfg.effective().model_dump(exclude_none=True); eff.pop("profile", None)
    toml_bytes = sp.render_toml(c.profile, eff).encode()
    resolved_bytes = (SESS / rec["resolved_config"]).read_bytes()
    out["cells"][c.name] = {
        "argv_equal": argv == rec["argv"],
        "argv_sha256_rendered": sha_argv(argv),
        "argv_sha256_recorded": sha_argv(rec["argv"]),
        "config_hash_rendered": provenance.config_hash(argv, rec["model_sha256"], rec["llama_cpp_commit"]),
        "config_hash_recorded": rec["config_hash"],
        "resolved_toml_equal": toml_bytes == resolved_bytes,
        "resolved_toml_sha256_rendered": hashlib.sha256(toml_bytes).hexdigest(),
        "resolved_toml_sha256_recorded": hashlib.sha256(resolved_bytes).hexdigest(),
    }
out["env_matches_records"] = all(
    model.sha256 == json.loads(next((SESS / "cells").glob(f"{n}-*.json")).read_text())["model_sha256"]
    and build["commit"] == json.loads(next((SESS / "cells").glob(f"{n}-*.json")).read_text())["llama_cpp_commit"]
    for n in out["cells"])
out["all_equal"] = all(e["argv_equal"] and e["argv_sha256_rendered"] == e["argv_sha256_recorded"]
    and e["config_hash_rendered"] == e["config_hash_recorded"] and e["resolved_toml_equal"]
    for e in out["cells"].values())
print(json.dumps(out, indent=1))
```

### 2.3 P3 — the sweep tool's re-run options

Re-run: `uv run --frozen --quiet python -m smallpc.sweep --help` (lists subcommands
`{check,run,status,latest}`), `uv run --frozen --quiet python -m smallpc.sweep run --help`,
and `bash scripts/run-sweep.sh --help`. Verbatim from `run --help`:

```
usage: python -m smallpc.sweep run [-h] --session-id SESSION_ID [--resume]
                                   [--rerun-flagged] [--only ONLY]
                                   [--allow-dirty] [--inhibit-tag INHIBIT_TAG] ...
```

and from the wrapper usage: `--resume`, `--rerun-flagged <sid>` ("re-run, once, the
repetitions flagged in session <sid> (attempt 2)"), `--only axis=value`. All three options
the runbook uses (§3 `--only`, §6 `--rerun-flagged`, §1.4 `--resume`) are present, in the
module and in the wrapper that forwards them (`run-sweep.sh:86-90`).

### 2.4 P4 — output location

Re-run: `test ! -e data/raw/stage4; echo $?` → `0`. No `data/raw/stage4*` path exists.
`run-sweep.sh:77` would refuse an existing session directory anyway.

### 2.5 P5 — free disk vs one Stage 3 session

Re-run: `df -B1 --output=avail /mnt/data/local-ai-research` and
`du -sb data/raw/stage3-32K data/raw/stage3-64K data/raw/stage3-128K`.

```
Avail (btrfs /mnt/data): 152697622528
data/raw/stage3-32K:   647211
data/raw/stage3-64K:   746917
data/raw/stage3-128K:  775006
```

Requirement: at least twice ONE Stage 3 session. Taken conservatively as the largest
(the 128K session, 775,006 B): 2 × 775,006 = 1,550,012 B <!-- derived: 2 * du -sb data/raw/stage3-128K -->.
Free space 152,697,622,528 B ≥ 1,550,012 B — PASS by a wide margin (the Stage 4 counterpart
session, stage3-64K at 746,917 B, gives the same verdict). Session data is small because the
server logs live under `data/logs/`, not `data/raw/`; the check is as the card states it.

### 2.6 P6 — commands.env parses and every tool exists

Re-run: `bash -n docs/recon/commands.env` → exit 0. Sourcing it
(`bash -c 'source docs/recon/commands.env; …'`) sets `SESSION=stage4` and the six variables
`GATE_CMD COVERAGE_CMD REPRO_CMD REPORT_CMD SCRUB_CMD CI_CMD` (single-quoted, `$SESSION`
expands at eval time). Every tool they name exists:

```
/usr/bin/uv            (uv sync --help: subcommand exists)
/usr/bin/shellcheck
uv run --frozen ruff --version   → ruff 0.17.4
uv run --frozen pytest --version → pytest 9.2.0
python -m smallpc.stage3 --help  → {headline,gate,repro}   (GATE_CMD, REPRO_CMD)
python -m smallpc.stats --help   → {coverage}             (COVERAGE_CMD)
python -m smallpc.report --help  → {render,coverage,repro}(REPORT_CMD)
python -m smallpc.scrub --help   → [--check] paths ...    (SCRUB_CMD)
```

(`python` = the project venv through `uv run`; `.venv` exists. The modules were invoked with
`uv run --frozen --quiet python -m … --help` — help only, no GPU.) The file's pass signatures
match the code: gate exit 0 = pass (`cli.py:50`), repro exit 0 = all PASS (`cli.py:60`),
scrub exit 0 = clean / exit 1 = findings (`scrub.py`, T-001 A9).

### 2.7 P7 — R3 (code freeze + date) <!-- derived: internal section number -->

Re-run (verbatim from the shared rules):

```
S3=$(cat docs/recon/stage3-commit.txt) && git cat-file -e "$S3^{commit}" && \
! git diff --name-only "$S3" HEAD -- src configs scripts pyproject.toml uv.lock CLAUDE.md .gitignore \
  | grep -vxE 'CLAUDE\.md|\.gitignore|scripts/wf(-[A-Za-z0-9_.-]+)?\.sh|scripts/_wf\.py'
```

→ exit **0** (no surviving path). `docs/recon/stage3-commit.txt` =
`80964618df8ff8bba88c784298e4fae3cf712f05` (E-001: the earliest Stage 3 session commit; the
three sessions ran from one verified code state, T-001 A5). The full filtered diff list is
12 paths, all kit-install or kit-permitted: `.gitignore`, `CLAUDE.md`, `scripts/_wf.py`,
`scripts/wf-{card,decision,escalate,guard,loop,merge-lanes,plan-import,progress}.sh`,
`scripts/wf.sh`. Date: `date -u +%F` → `2026-11-13`, satisfying "13 November 2026 or later".

### 2.8 P8 — tree state: initial FAIL, resolved by lane 3 mid-session; re-check PASS <!-- derived: internal section number -->

**Initial observation (FAIL).** `git status --porcelain` at HEAD `de6d586`, before this
file was written:

```
 M .workflow/state.json
 M PROGRESS.md
 M docs/recon/loop-design.md
 M docs/recon/loop-states.md
```

- `.workflow/state.json` and `PROGRESS.md` are tracked kit bookkeeping (this task's
  claim/start) — the exempt kind (T-001 A15).
- `docs/recon/loop-design.md` (+18/−1 lines) and `docs/recon/loop-states.md` (+2/−1) are
  **T-017's files** (card T-017 `files_write`, PLAN.md), lane 3, then `changes-requested`.
  The uncommitted edits were review-address work: an E-004 option B decision note, the F-1
  pre-review gap note, the F-5 review-exhausted ordering note, and a D8 home-path scrub.
  `bash scripts/wf.sh lane-status 3` → `lane 3: no lock | worktree - | no file`: the edits
  sat uncommitted in the MAIN checkout, with no lane-3 worktree or lock.
- The sweep's own dirty check was already empty (`git status --porcelain -- src configs
  scripts` prints nothing, so `run-sweep.sh` would start), but P8 requires "clean apart
  from workflow bookkeeping", and two task-work files that are not bookkeeping broke that.
  No decision on record covered them (`docs/decisions.md` checked). This session could not
  fix it: lane discipline forbids touching another lane's files, and T-019's `files_write`
  is only this file and the progress log.

**Resolution (by the owning lane, not by this session).** While this pre-flight was being
written, the concurrent lane-3 session committed exactly those edits and finished its work:

```
bc8e0c3  T-017: address review cycle 1 — F-2/F-3/F-4/F-5 doc fixes   (17:50:11Z)
1ba3bf9  T-017: escalate F-1 as E-006 (decision); acceptance run 3, dispositions  (17:52:46Z)
```

`git show --stat bc8e0c3` carries the loop-design/loop-states edits (F-2 D8 scrub, F-3
decision addendum, F-5 ordering note); T-017 is now `blocked-decision` on its own E-006
(the loop's inert pre-review branch — unrelated to Stage 4; T-007 is post-review per
PLAN.md v1.2, and a blocked-decision task does not stop other ready tasks). This session's
commit `ca1d5ad` (17:57:03Z) contains only its own three files (this doc, `.workflow/state.json`,
`PROGRESS.md`); it did not touch T-017's files.

**Re-check (PASS).** At HEAD `ca1d5ad`, 17:58:14Z: `git status --porcelain` → EMPTY (not
even bookkeeping dirty); `git status --porcelain -- src configs scripts` → empty;
`.workflow/state.json` and `PROGRESS.md` are tracked (`git ls-files`). No state-changing wf
command is needed between this clean check and T-007's session start: claim/start and
accept/done mutate only the exempt bookkeeping, and lane 3 has no worktree to merge. The
R3 check re-run at the new HEAD still exits 0 (§2.7); <!-- derived: internal section cross-reference --> `pgrep -x llama-server` empty; GPU
lock probe free.

### 2.9 Escalation decision

The card says to escalate once if any check FAILs. P8's FAIL was real when observed, and it
is recorded above with its cause; before any escalation was filed, the owning lane removed
the cause through its own legitimate commits, and the redo-safe re-check passes. The final
record has **no failing check**, so there is nothing to escalate: filing an escalation for a
resolved transient state would block T-019 (and T-007 behind it) for a decision no longer
needed. No workaround was applied by this session — no other lane's file was committed,
reverted or stashed here. T-017's own E-006 remains open for the planning chat on its own
merits.

Result: all checks PASS