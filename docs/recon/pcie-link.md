# PCIe link: evidence and under-load verification (T-020)

Task T-020 (E-008 decision, option A): restore and verify the GPU's PCIe Gen4 x8 link before
Stage 4 run 2 (T-021). Run 1 (session id `stage4`, `docs/recon/stage4-session.txt`) ran at
Gen3 x8 for the whole session and is superseded (R5, `docs/decisions.md`, DECISION E-008).
This file records the read-only evidence (S1), the post-repair idle state (S2), the under-load
verification (S3) and the result (S4).

<!-- sources: docs/progress-log.md, docs/environment.md, docs/stage3-conditions.md, docs/stage4-conditions.md, docs/recon/T-001.md, data/microbench/pcie.json, data/raw/stage4/snapshots/574cd25c8118710e.json, data/raw/stage3-32K/snapshots/66c04f6c276af71a.json, data/raw/stage3-64K/snapshots/66c04f6c276af71a.json, data/raw/stage3-128K/snapshots/66c04f6c276af71a.json, escalations/E-008.md, docs/decisions.md, src/smallpc/microbench.py, tools/pcie_bw.cu, configs/model.toml -->

## S1 — Read-only evidence for run 1 and Stage 3 (2026-11-14, before the repair gate)

### What the conditions logs record

- `docs/stage4-conditions.md` (run 1): records `nvidia-smi` memory.used and compute processes at
  the start and at every poll, plus quiet checks, MemAvailable and swap. It does **not** record
  the PCIe link generation or width anywhere — not at the start, not at any poll, not at the end.
- `docs/stage3-conditions.md` (Stage 3, all three sessions and the Phase 0 check): same template,
  `nvidia-smi` memory only. It also does **not** record the PCIe link generation or width.
- The link evidence for both stages is therefore in the raw sweep metadata (environment snapshots
  and the 2 Hz telemetry), not in the conditions logs.

### Stage 4 run 1 (session `stage4`, 2026-11-13 22:42 to 23:37 UTC): Gen3 x8 throughout

- Snapshot `data/raw/stage4/snapshots/574cd25c8118710e.json` (`state.timestamp_utc`
  2026-11-13T22:42:47Z): `identity.gpu.pcie_gen_max` "3", `pcie_gen_gpu_max` "5",
  `pcie_gen_host_max` "4", `pcie_width_max` "8"; `state.gpu.pcie_gen_current` "3",
  `pcie_width_current` "8". The negotiated maximum itself was Gen3 — not an idle downshift.
- Telemetry (`data/raw/stage4/telemetry/*.csv.gz`, columns `pcie_gen`,`pcie_width`, every row):
  all measured-cell rows are Gen3 x8 — stock-64K 2,463 rows; tuned-64K 1,037 rows (attempt 1)
  and 627 rows (re-run). The four canaries never exceed Gen3 (397 / 396 / 401 / 397 rows), apart
  from 2 idle Gen1 x8 rows at the start and end of each canary file. **No Gen4 sample anywhere
  in the session.** Full per-file histogram in the fenced block below.
- This matches E-008 §3 and R5: run 1 is invalid for S2 and is reported as an excluded diagnostic.

### Stage 3 (sessions `stage3-32K`, `stage3-64K`, `stage3-128K`, 2026-11-12): Gen4 x8 throughout

- Snapshots (all three `snapshots/66c04f6c276af71a.json`; `state.timestamp_utc` 11:53:38Z,
  12:25:27Z, 13:10:18Z): `identity.gpu.pcie_gen_max` "4" in all three, `pcie_gen_gpu_max` "5",
  `pcie_gen_host_max` "4", `pcie_width_max` "8". The link's negotiated ceiling was Gen4 x8 on
  every Stage 3 session day. `state.gpu.pcie_gen_current` at the session-start capture: Gen2 x8
  for stage3-32K, Gen4 x8 for stage3-64K and stage3-128K. The Gen2 reading is an idle downshift:
  the snapshot's own `identity.pcie_note` says the link downshifts at idle (Gen1 in P8) and the
  current link is only meaningful under load.
- Telemetry (`data/raw/stage3-*/telemetry/*.csv.gz`, every row): **every measured-cell row is
  Gen4 x8** — stock-32K 895 + 211 rows, tuned-32K 450; stock-64K 1,565, tuned-64K 779 + 619;
  stock-128K 3,307 + 1,354, tuned-128K 1,401. Canaries are Gen4 x8 apart from a few Gen1/Gen2 x8
  rows at cell start and end (the idle downshift before load / after unload). **No Gen3 row
  anywhere in Stage 3.** Full per-file histogram below.
- **Conclusion: Stage 3 ran at Gen4 x8.** No evidence says Stage 3 ran at Gen3, so the S1
  escalation trigger (a Gen3 Stage 3 would change the baseline, not only Stage 4) does not fire.

### Stage 1 corroboration: the 14.3 GB/s reference

- The card points to `docs/recon/T-001.md` for the measured 14.3 GB/s. **T-001.md does not record
  it**: it is the smoke-test and recon record (A1–A16) and has no PCIe or bandwidth section. The
  figure is recorded in `docs/progress-log.md` (WP6 entry, line 148) and in
  `data/microbench/pcie.json` (`reference_gbps` 14.3): pinned host-to-device 14.29 GB/s
  (expert-sized, 1,904,640 B), 14.38 (16 MiB), 14.39 (256 MiB); the link read Gen4 x8 in 182 of
  182 samples taken during transfers (Gen1 x8 in the 2 idle samples before); run
  2026-11-08T17:36:48Z to 17:38:44Z, decimal GB/s (1e9 bytes/s), CUDA events.
- 14.3 GB/s is only consistent with Gen4 x8: Gen3 x8 tops out near 7.9 GB/s and Gen4 x8 near
  15.8 GB/s (E-008 §3, per-lane rates ×8 lanes ×128b/130b). The Stage 1 microbench therefore
  verifies Gen4 x8 under transfer load on this machine before Stage 3.
- Stage 1 sweep telemetry (`data/raw/stage1-*/telemetry/*.csv.gz`, every row checked): all loaded
  rows Gen4 x8; only the 2 idle rows at canary start/end read Gen1 x8.
- `docs/environment.md` (WP-era idle snapshot) records `pcie_gen_current` 1, `pcie_gen_max` 4,
  width 8 of 8, with the note that the link may downshift at idle and WP6 measures it under load —
  consistent with the idle readings above, and with Gen4 as the machine's normal ceiling.

### Where the bandwidth-check command is recorded (for S3)

- The card says the Stage 1 host-to-device bandwidth command is in `docs/recon/T-001.md` or the
  runbook. **Neither records it** (no bandwidth/PCIe section in either). It is recorded in
  `data/microbench/pcie.json` (`tool` `tools/pcie_bw.cu`, `build_command` with nvcc) and in
  `src/smallpc/microbench.py` (`run_pcie_once`, lines 116–123): the invocation is
  `pcie_bw --dir h2d --mem pinned --bytes N`, Stage 1 used 5 repetitions plus one discarded
  warm-up invocation per configuration, sizes expert 1,904,640 B / 16 MiB / 256 MiB, and the tool
  itself does at least 0.7 s of untimed copies inside every invocation. The prebuilt binary
  `build/tools/pcie_bw` (built 2026-11-08, gitignored) exists and `tools/pcie_bw.cu` is unchanged
  since, so no rebuild is needed. S3 runs that same tool and protocol directly (not
  `scripts/run-microbench.sh`, which would overwrite the Stage 1 results in `data/microbench/`).

### Change window (E-008 §3, verified against the raw data above)

Last Gen4 observation: 2026-11-12 14:14:15Z (stage3-128K re-run end; telemetry all Gen4).
First Gen3 observation: 2026-11-13 22:42:47Z (stage4 snapshot). Cause unknown; nothing in the
repo changed the link (machine tuning frozen). The repair gate (card T-020) asks Zack for a
full power-off with the mains lead out 30 s, a GPU seating check, and the BIOS GPU-slot PCIe
speed set to Gen4 rather than Auto, before this session tests the link under load.

### Telemetry histograms (verbatim, every row of every file)

Command (per session): `for f in data/raw/<session>/telemetry/*.csv.gz; do zcat "$f" | awk -F,
'NR>1 {c[$13","$14]++} END {for (k in c) printf "%s x%d; ", k, c[k]}'; done` — columns 13,14 are
`pcie_gen`,`pcie_width`; counts are samples at 2 Hz.

```
stage3-32K
  canary-end-debea778-i0.csv.gz:        1.0,8.0 x2; 4.0,8.0 x285
  canary-rerun-end-debea778-i0.csv.gz:  1.0,8.0 x2; 4.0,8.0 x285
  canary-rerun-start-debea778-i0.csv.gz: 1.0,8.0 x2; 4.0,8.0 x290
  canary-start-debea778-i0.csv.gz:      1.0,8.0 x5; 2.0,8.0 x3; 4.0,8.0 x281
  stock-32K-acee236c-i0.csv.gz:         1.0,8.0 x2; 2.0,8.0 x2; 4.0,8.0 x895
  stock-32K-acee236c-i1.csv.gz:         4.0,8.0 x211
  tuned-32K-e7a90f1c-i0.csv.gz:         4.0,8.0 x450
stage3-64K
  canary-end-debea778-i0.csv.gz:        1.0,8.0 x2; 4.0,8.0 x286
  canary-rerun-end-debea778-i0.csv.gz:  1.0,8.0 x2; 2.0,8.0 x2; 4.0,8.0 x282
  canary-rerun-start-debea778-i0.csv.gz: 1.0,8.0 x2; 2.0,8.0 x2; 4.0,8.0 x286
  canary-start-debea778-i0.csv.gz:      1.0,8.0 x4; 2.0,8.0 x6; 4.0,8.0 x278
  stock-64K-22dc1178-i0.csv.gz:         4.0,8.0 x1565
  tuned-64K-f9b81a84-i0.csv.gz:         4.0,8.0 x779
  tuned-64K-f9b81a84-i1.csv.gz:         4.0,8.0 x619
stage3-128K
  canary-end-debea778-i0.csv.gz:        1.0,8.0 x2; 2.0,8.0 x2; 4.0,8.0 x284
  canary-rerun-end-debea778-i0.csv.gz:  1.0,8.0 x2; 4.0,8.0 x284
  canary-rerun-start-debea778-i0.csv.gz: 1.0,8.0 x2; 2.0,8.0 x1; 4.0,8.0 x288
  canary-start-debea778-i0.csv.gz:      1.0,8.0 x2; 2.0,8.0 x2; 4.0,8.0 x282
  stock-128K-139ecd8b-i0.csv.gz:        4.0,8.0 x3307
  stock-128K-139ecd8b-i1.csv.gz:        4.0,8.0 x1354
  tuned-128K-db2cb799-i0.csv.gz:        4.0,8.0 x1401
stage4 (run 1, superseded)
  canary-end-debea778-i0.csv.gz:        1.0,8.0 x2; 3.0,8.0 x397
  canary-rerun-end-debea778-i0.csv.gz:  1.0,8.0 x2; 3.0,8.0 x396
  canary-rerun-start-debea778-i0.csv.gz: 1.0,8.0 x2; 3.0,8.0 x401
  canary-start-debea778-i0.csv.gz:      1.0,8.0 x2; 3.0,8.0 x397
  stock-64K-22dc1178-i0.csv.gz:         3.0,8.0 x2463
  tuned-64K-f9b81a84-i0.csv.gz:         3.0,8.0 x1037
  tuned-64K-f9b81a84-i1.csv.gz:         3.0,8.0 x627
stage1-32K / stage1-64K / stage1-128K (spot check, every file)
  all loaded rows 4.0,8.0; only the 2 idle rows at canary start/end read 1.0,8.0
```

## S2 — Post-gate idle state, kernel/driver, and boot-log search (2026-11-14)

### Gate release, with a recorded deviation

Zack replied "go" at about 11:45Z and released the gate with a deviation: he **skipped the cold
power-off (mains lead out 30 s) and the BIOS step** (no GPU-slot speed setting found in the BIOS),
because the boot at 13:37 SAST (11:37Z) already trained the link at Gen4 and the fault was a
runtime drop, not a boot-time negotiation. The under-load test (S3) is the arbiter: if it reads
anything but Gen4 x8, S4 is FAIL and the task escalates. The current boot's Gen4 training is
verified below, so the skipped steps are not needed to explain the present state.

### Live record (idle, before the load test)

Kernel `7.3.4-1-cachyos`, NVIDIA driver `620.70.06`. <!-- derived: uname -r and nvidia-smi driver_version, fenced output below; both differ from Stage 3 / run 1 (kernel 7.3.1, driver 615.78.08) because of the 14 November 02:37 SAST upgrade, see the confound note -->
Idle link: Gen1 x8 current, **Gen4 max**, width 8 of 8 — the idle downshift of S1, with the
negotiated ceiling back at Gen4 (run 1's snapshot had max Gen3).

```
$ date -u +%Y-%m-%dT%H:%M:%SZ
2026-11-14T11:46:21Z
$ uname -r
7.3.4-1-cachyos
$ nvidia-smi --query-gpu=name,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max --format=csv
name, pcie.link.gen.current, pcie.link.gen.max, pcie.link.width.current, pcie.link.width.max
NVIDIA GeForce RTX 5060 Ti, 1, 4, 8, 8
$ nvidia-smi --query-gpu=driver_version --format=csv,noheader
620.70.06
```

### Planning-chat note (facts from Zack's journal), and what was verified read-only

The note (2026-11-14, no plan change) states: Stage 3 and run 1 ran inside one boot,
`04c03a02a7b44641ad5fedc19ed022e6` (2026-11-08 17:25 to 2026-11-14 02:40 SAST), no reboot between
them; at that boot the kernel logged the GPU (0000:01:00.0, behind root port 0000:00:01.1) as <!-- derived: PCI addresses from the journal training lines recorded below -->
limited by a 16 GT/s x8 link (Gen4), so the Gen3 drop was a runtime event; pacman shows no nvidia
or kernel upgrade between 2026-11-04 and 2026-11-14 02:37 SAST, so both stages ran on
linux-cachyos 7.3.1 and nvidia 615.78.08; the upgrade at 02:37 SAST on 14 November (kernel 7.3.4,
nvidia-utils 620.70.06) came after run 1. <!-- derived: planning-chat note pasted by Zack; journal facts, not repo files -->

Verified read-only against the journal:

```
$ journalctl --list-boots | tail -8   (hostname never appears in this output)
IDX BOOT ID                          FIRST ENTRY                  LAST ENTRY
 -6 82871e8fc20e4a26a6949de0a833a5b4 Sat 2026-11-07 11:48:04 SAST Sat 2026-11-07 11:48:05 SAST
 -5 89efdae56a614718a1ef2ef66adc2c08 Sat 2026-11-07 11:48:37 SAST Sun 2026-11-08 17:05:59 SAST
 -4 04c03a02a7b44641ad5fedc19ed022e6 Sun 2026-11-08 17:25:17 SAST Sat 2026-11-14 02:40:56 SAST
 -3 fde1c2bf7dd3418a8e51c866d1f4591d Sat 2026-11-14 02:41:53 SAST Sat 2026-11-14 02:42:21 SAST
 -2 7dd850a818bc4a6aa79585e23b584bfd Sat 2026-11-14 11:26:22 SAST Sat 2026-11-14 12:47:08 SAST
 -1 4a2e70c7f9324e72a25f36dfff8c85a7 Sat 2026-11-14 13:07:38 SAST Sat 2026-11-14 13:36:44 SAST
  0 8aee92be6704471f96c64339666cfd30 Sat 2026-11-14 13:37:09 SAST Sat 2026-11-14 13:45:38 SAST

Old boot (-4), first line (kernel version) and GPU link-training line, UTC, hostname scrubbed:
2026-11-08T15:25:17+00:00 <hostname> kernel: Linux version 7.3.1-1-cachyos (linux-cachyos@cachyos) (clang version 23.1.4, LLD 23.1.4) #1 SMP PREEMPT_DYNAMIC Sat, 31 Oct 2026 06:43:52 +0000
2026-11-08T15:25:17+00:00 <hostname> kernel: pci 0000:01:00.0: 126.024 Gb/s available PCIe bandwidth, limited by 16.0 GT/s PCIe x8 link at 0000:00:01.1 (capable of 252.056 Gb/s with 32.0 GT/s PCIe x8 link)
2026-11-08T15:25:19+00:00 <hostname> kernel: NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  615.78.08  Release Build  (notroot@)  Sat Oct 31 07:08:24 UTC 2026

Current boot (0), GPU link-training line and NVRM load, UTC, hostname scrubbed:
2026-11-14T11:37:09+00:00 <hostname> kernel: pci 0000:01:00.0: 126.024 Gb/s available PCIe bandwidth, limited by 16.0 GT/s PCIe x8 link at 0000:00:01.1 (capable of 252.056 Gb/s with 32.0 GT/s PCIe x8 link)
2026-11-14T13:37:10 <hostname> kernel: NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  620.70.06  Release Build  (notroot@)  Thu Nov 12 08:58:36 UTC 2026
```

The current boot therefore trained the GPU at Gen4 x8 (16 GT/s), as Zack said; the card is
Gen5-capable (32 GT/s) and the host root port limits it to Gen4. The old boot ran kernel 7.3.1
and driver 615.78.08 throughout (one NVRM load line, at boot; no driver reload before run 1).

### Current-boot kernel messages (the card's S2 command, verbatim, hostname scrubbed)

`journalctl -k -b | grep -iE 'pcie|aer|nvrm|downgrad' | tail -n 30` — all 30 lines are boot-time
enumeration at 13:37:09–13:37:17 SAST plus the NVRM load; no runtime PCIe error since boot.

```
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:02.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:03.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:04.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:05.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:06.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:07.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:08.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:0c.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:04:0d.0: [1022:43f5] type 01 class 0x060400 PCIe Switch Downstream Port
Nov 14 13:37:09 <hostname> kernel: pci 0000:06:00.0: [10ec:8168] type 00 class 0x020000 PCIe Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:07:00.0: [8086:2725] type 00 class 0x028000 PCIe Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:0e:00.0: [1022:43f7] type 00 class 0x0c0330 PCIe Legacy Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:0f:00.0: [1022:43f6] type 00 class 0x010601 PCIe Legacy Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:10:00.0: [1c5c:174a] type 00 class 0x010802 PCIe Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:10:00.0: 15.752 Gb/s available PCIe bandwidth, limited by 8.0 GT/s PCIe x2 link at 0000:00:03.1 (capable of 31.504 Gb/s with 8.0 GT/s PCIe x4 link)
Nov 14 13:37:09 <hostname> kernel: pci 0000:11:00.0: [1002:13c0] type 00 class 0x030000 PCIe Legacy Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:11:00.1: [1002:1640] type 00 class 0x040300 PCIe Legacy Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:11:00.2: [1022:1649] type 00 class 0x108000 PCIe Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:11:00.3: [1022:15b6] type 00 class 0x0c0330 PCIe Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:11:00.4: [1022:15b7] type 00 class 0x0c0330 PCIe Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:11:00.6: [1022:15e3] type 00 class 0x040300 PCIe Legacy Endpoint
Nov 14 13:37:09 <hostname> kernel: pci 0000:12:00.0: [1022:15b8] type 00 class 0x0c0330 PCIe Endpoint
Nov 14 13:37:09 <hostname> kernel: pcieport 0000:00:01.1: PME: Signaling with IRQ 32
Nov 14 13:37:09 <hostname> kernel: pcieport 0000:00:01.2: PME: Signaling with IRQ 33
Nov 14 13:37:09 <hostname> kernel: pcieport 0000:00:02.1: PME: Signaling with IRQ 34
Nov 14 13:37:09 <hostname> kernel: pcieport 0000:00:03.1: PME: Signaling with IRQ 35
Nov 14 13:37:09 <hostname> kernel: pcieport 0000:00:08.1: PME: Signaling with IRQ 36
Nov 14 13:37:09 <hostname> kernel: pcieport 0000:00:08.3: PME: Signaling with IRQ 37
Nov 14 13:37:10 <hostname> kernel: NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  620.70.06  Release Build  (notroot@)  Thu Nov 12 08:58:36 UTC 2026
Nov 14 13:37:17 <hostname> kernel: amdgpu 0000:11:00.0: [drm] PCIE GART of 1024M enabled (table at 0x000000F41FC00000).
```

### Earlier boot (04c03a02…): runtime-event search

Method: `journalctl -k -b 04c03a02a7b44641ad5fedc19ed022e6 --utc --no-pager -o short-iso`,
hostname scrubbed, saved to `/tmp/local-ai-research-t020/oldboot-kernel.log` (8,829 lines,
2026-11-08T15:25:17Z to 2026-11-14T00:40:55Z). Reference points: Stage 3 end 2026-11-12T14:14:15Z
(stage3-128K re-run end, E-008); run 1 start 2026-11-13T22:42:47Z (stage4 snapshot).

**Suspend/resume — 4 cycles (8 lines), verbatim:**

```
2026-11-08T22:25:40+00:00 <hostname> kernel: PM: suspend entry (deep)
2026-11-09T07:45:10+00:00 <hostname> kernel: PM: suspend exit
2026-11-09T14:04:02+00:00 <hostname> kernel: PM: suspend entry (deep)
2026-11-09T18:01:27+00:00 <hostname> kernel: PM: suspend exit
2026-11-11T22:10:18+00:00 <hostname> kernel: PM: suspend entry (deep)
2026-11-12T08:26:27+00:00 <hostname> kernel: PM: suspend exit
2026-11-12T23:09:17+00:00 <hostname> kernel: PM: suspend entry (deep)
2026-11-12T23:09:27+00:00 <hostname> kernel: PM: suspend exit
```

The first three cycles precede Stage 3 (which started 2026-11-12T11:53Z and ran at Gen4 x8, so
those resumes did not leave the link at Gen3). **The fourth is the only runtime power event in
the change window**: suspend entry 2026-11-12T23:09:17Z, resume exit 23:09:27Z (a 10-second S3
sleep), 8 h 55 min after Stage 3 end and 23 h 33 min before run 1 start. <!-- derived: journal lines above minus E-008's last-Gen4 (2026-11-12T14:14:15Z) and first-Gen3 (2026-11-13T22:42:47Z) observations -->
The resume re-enabled the GPU (`nvidia 0000:01:00.0: Enabling HDA controller` at 23:09:26Z) but
the kernel logs no PCIe link speed at resume, so the log cannot prove the link retrained at Gen3
there. It is the only candidate event in the window — a hypothesis, not a controlled experiment.

**AER / corrected errors — none at runtime.** The only match in the whole boot is the boot-time
ACPI negotiation: `2026-11-08T15:25:17 … acpi PNP0A08:00: _OSC: OS now controls [PCIeHotplug
SHPCHotplug PME AER PCIeCapability LTR DPC]`. No AER event, no corrected-error report, anywhere
in the boot.

**NVRM / Xid — no GPU Xid, no NVRM error in the change window.** All 4 matches, verbatim
(the r8169 line is the Realtek NIC's own XID, not a GPU Xid; MAC redacted):

```
2026-11-08T15:25:19+00:00 <hostname> kernel: NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  615.78.08  Release Build  (notroot@)  Sat Oct 31 07:08:24 UTC 2026
2026-11-08T15:25:25+00:00 <hostname> kernel: r8169 0000:06:00.0 eth0: RTL8168h/8111h, <mac-address>, XID 541, IRQ 152
2026-11-11T10:38:47+00:00 <hostname> kernel: NVRM: GPU0 nvCheckOkFailedNoLog: Check failed: Out of memory [NV_ERR_NO_MEMORY] (0x00000051) returned from _memdescAllocInternal(pMemDesc) @ mem_desc.c:1348
2026-11-11T10:38:47+00:00 <hostname> kernel: NVRM: GPU0 _kgmmuClientShadowFaultBufferPagesAllocate: Allocation failed with big page size, retrying with default page size
```

The two NVRM allocation lines are 2026-11-11 (Stage 2 era), before Stage 3 and outside the
change window; the driver recovered (retry) and Stage 3 ran clean at Gen4 afterwards.

**Link-speed change — none logged.** The only GPU link-speed record in the boot is the boot-time
16 GT/s x8 training line above; no runtime upgrade/downgrade message for 0000:01:00.0 or its root
port 0000:00:01.1 exists in the log. <!-- derived: PCI addresses from the journal training lines recorded above --> A full scan of the change window (285 kernel lines,
2026-11-12T14:14Z to 2026-11-13T22:43Z) shows, besides the suspend/resume machinery: spurious
APIC interrupts at resume (routine on this platform), the amdgpu **iGPU** resume with LTTPR
DisplayPort link-training errors (0000:11:00.0 — the AMD iGPU's display links, not the NVIDIA
PCIe link), xHCI re-init and NVMe re-init. Nothing touches the NVIDIA PCIe link.

**Summary of the search:** no AER, no GPU Xid, no NVRM link error, no logged link-speed change.
The single candidate cause of the runtime Gen4→Gen3 drop is the 10-second S3 suspend/resume at
2026-11-12T23:09Z; the journal neither confirms nor refutes it (no link speed is logged at
resume). This is consistent with the planning-chat note's reading that the drop was a runtime
event, and with Zack's decision to skip the cold power-off and BIOS steps.

### Confound note for T-021 (planning-chat note)

Run 2 will run on kernel 7.3.4-1-cachyos and driver 620.70.06, where Stage 3 and run 1 ran on <!-- derived: planning-chat note; versions from the live record and old-boot journal above -->
7.3.1 and 615.78.08. T-021's conditions log must record the kernel and driver again; if run 2
fails S2 with the link verified Gen4 x8 at the start and at every poll, the escalation brief
names this kernel/driver change as a confound.

## S3 — Under-load verification (2026-11-14, ~11:50–11:56Z)

### Preconditions and launch

- `scripts/check-quiet.sh` (exit 0): `quiet-machine check: 408 processes (names only)`; `no
  blocklisted app is running`; `CPU idle check (informational): busy 0.2% over 10 s`;
  `RESULT: QUIET`. `pgrep -x llama-server`: empty. GPU lock (`.locks/gpu.lock`, `flock -n`): free.
- Launch (the runbook's tuned-64K config through the sanctioned launcher; logs in /tmp per the
  card, via `SMALLPC_LOG_ROOT`, not in `data/` or the repo):

```
$ SMALLPC_LOG_ROOT=/tmp/local-ai-research-t020/logs bash scripts/launch-server.sh --run-id t020-link-check configs/server/tuned-64k.toml
server healthy: pid=4054 http://127.0.0.1:8080
run-dir: /tmp/local-ai-research-t020/logs/t020-link-check
```

  Rendered argv (run-dir `argv.txt`): `llama-server -m
  /mnt/data/local-ai-research/models/Ornith-1.5-35B-Q4_K_M.gguf --host 127.0.0.1 --port 8080
  -c 65536 -cmoe --moe-cache-mib 9472 -b 4096 -ub 4096 -ctk f16 -ctv f16 -fa on -np 1
  --spec-type draft-mtp --spec-draft-n-max 1 --cache-ram 2048`. The launcher holds the GPU lock
  for the server's lifetime.

### The load request

The runbook probes' own prompt: Request A at the 64K cell's deepest depth, cached as
`data/cache/workloads/A-v0-49152-r0.{txt,u32}` (the sweep's repetition-1 A@49152). Verified
against `configs/workloads/manifest.json` before use: token_count 49152, tokens_sha256
`3c54f62eab7c824ef8c73ba65fd0c3c190cfb8eae45f07e9c4c48634d16781a7`, text_sha256
`66ffe5fda5c6bebfcfa7e912005f0377b632e18a3d57197727d975ee10eed94a` — both equal to the manifest.
Request shape as the frozen sweep client (`src/smallpc/sweep/client.py`): `POST /completion`,
`prompt` = the token array, `n_predict` 400 (the card's "about 400 tokens"; the recipe's
`n_predict_b`), `seed` 1045909815 (the manifest's seed for this prompt), sampling
temperature 0.6 / top_p 0.95 / top_k 20 (`configs/model.toml` `[sampling.general]`).

### Attempt 1 — ten samples, first one caught the pre-load idle state

Request start 2026-11-14T11:52:00Z (`cache_prompt: true`). Samples (the card's exact query, one
per second, started in the same second as the POST):

```
11:52:00 1, 8
11:52:02 4, 8
11:52:03 4, 8
11:52:04 4, 8
11:52:05 4, 8
11:52:06 4, 8
11:52:07 4, 8
11:52:08 4, 8
11:52:09 4, 8
11:52:10 4, 8
```

Response (`timings`): prompt_n 49152, prompt_ms 32136.427 (about 1,529 tok/s), predicted_n 400, <!-- derived: /completion response, attempt 1 (response.json in /tmp) -->
predicted_ms 5035.244 (about 79 tok/s), cache_n 0, draft_n_accepted 188 of 210. <!-- derived: same response -->

Sample 1 read Gen1 x8 because it was taken **before the server started generating** — the POST
and the first query share the second 11:52:00, and the link was still in the idle downshift
(S2). Samples 2–10, all inside the 32-second prefill, read Gen4 x8. R7's stop condition is
"anything other than 4, 8 **while a server is generating**"; it did not fire. To satisfy S3's
"while it is generating" unambiguously, the ten samples were retaken with the sampling window
synchronised into confirmed generation (attempt 2). Both attempts are recorded; nothing is
averaged or discarded silently.

### Attempt 2 — the definitive ten samples, all under confirmed generation

Same prompt and parameters, `cache_prompt: false` for a fresh prefill (response `cache_n` 0).
Request start 2026-11-14T11:53:23Z; sampling started 3 s later, inside the 26-second prefill:

```
11:53:26 4, 8
11:53:27 4, 8
11:53:28 4, 8
11:53:29 4, 8
11:53:30 4, 8
11:53:31 4, 8
11:53:32 4, 8
11:53:33 4, 8
11:53:34 4, 8
11:53:35 4, 8
```

Mid-window load check (after sample 5): `utilization.gpu` 95 %, `power.draw` about 100 W — the
server was generating while the samples were taken. Response (`timings`): prompt_n 49152,
prompt_ms 26222.758 (about 1,874 tok/s), predicted_n 400, predicted_ms 4600.791 (about 87 tok/s), <!-- derived: /completion response, attempt 2 (response2.json in /tmp) -->
cache_n 0, draft_n_accepted 188 of 210. **All ten samples read "4, 8".**

### Stop and lock

```
$ SMALLPC_LOG_ROOT=/tmp/local-ai-research-t020/logs bash scripts/stop-server.sh --timeout 30 t020-link-check
stopped: method=sigint exit_code=0 (/tmp/local-ai-research-t020/logs/t020-link-check/stop-status.json)
stop-status.json: stopped_utc 2026-11-14T11:54:17Z, pid 4054, method sigint, exit_code 0, waited_s 2
$ pgrep -x llama-server        # empty
$ flock -n .locks/gpu.lock true && echo "GPU lock free"
GPU lock free
```

### Host-to-device bandwidth check (the Stage 1 tool and protocol)

`build/tools/pcie_bw` (built 2026-11-08 from `tools/pcie_bw.cu`, unchanged; no rebuild), run
under `scripts/with-gpu-lock.sh`: per size, one discarded warm-up invocation then 5 measured
repetitions of `pcie_bw --dir h2d --mem pinned --bytes N`, sizes 1,904,640 / 16,777,216 /
268,435,456 B — the Stage 1 protocol (`src/smallpc/microbench.py`, `data/microbench/pcie.json`;
the tool does its own ≥ 0.7 s of untimed copies per invocation). Decimal GB/s, CUDA events —
the tool's own output, verbatim (`gb_per_s` per rep):

```
bytes 1904640  (expert): 14.2877  14.2883  14.2882  14.2875  14.2887
bytes 16777216 (16 MiB): 14.3726  14.3726  14.3724  14.3739  14.3723
bytes 268435456 (256 MiB): 14.3835  14.3850  14.3842  14.3835  14.3847
```

All 15 reps between 14.2875 and 14.3850 GB/s — every size ≥ 13 GB/s, and each within 1% of the <!-- derived: min/max of the pcie_bw reps recorded above; Stage 1 reference 14.3 GB/s from data/microbench/pcie.json -->
Stage 1 reference 14.3 GB/s (Stage 1 pinned H2D: 14.29 / 14.38 / 14.39). Link samples at 2 Hz
during the whole bandwidth block (44 samples): 43 read "4, 8"; the 1 "1, 8" is the first sample,
taken before the first transfer started (the same idle-before-load state as attempt 1's first
sample). Raw outputs: `/tmp/local-ai-research-t020/{pcie-bw-h2d.jsonl,bw-link-samples.txt,
link-samples.txt,link-samples-2.txt,response.json,response2.json}`; server log, argv and
stop-status in `/tmp/local-ai-research-t020/logs/t020-link-check/`.

## S4 — Result

- The ten under-load samples (attempt 2, all during confirmed generation, GPU 95% busy): all
  read "4, 8". Attempt 1's pre-load first sample is documented above and is not an under-load
  reading.
- Bandwidth: all 15 pinned host-to-device reps ≥ 13 GB/s (14.2875 to 14.3850 GB/s), matching the <!-- derived: pcie_bw output recorded in S3 -->
  Stage 1 reference within 1%.
- The link is restored to Gen4 x8 under load on kernel 7.3.4-1-cachyos / driver 620.70.06. <!-- derived: live record in S2 -->
  Stage 4 run 2 (T-021) may proceed, with R7 link checks at the start and every poll, and the
  kernel/driver confound note above carried into its conditions log.

Result: link PASS