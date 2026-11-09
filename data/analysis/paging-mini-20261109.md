# Paging analysis of `mini-20261109`

**Functional-test data (WP9 mini-sweep), not results.** This is an investigation; `flags.paging` is unchanged.

## Per-window table

VmSwap and RSS in MiB. `nature`: state = swap already there at the window's first sample, activity = it grew. Speeds are tokens/s: PP_fresh at the 16K pair (Request A) and TG of the 16K Request B (and the mean TG of all B requests).

| cell | segment | inst | VmSwap start | end | max | change | nature | major faults | pswpin | MemAvail min | RSS start→end | PP_fresh 16K | TG 16K | TG B mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| canary-end | server start | 0 | 0 | 0 | 0 | 0 | none | - | 690 | 24,239 | 20,470→20,470 | - | - | - |
| canary-end | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 29,083 | 23,896 | 20,654→21,072 | 1,040.6 | 86.0 | - |
| canary-end | window r103 | 0 | 0 | 0 | 0 | 0 | none | 0 | 5,766 | 23,188 | 21,072→21,658 | 1,020.9 | 78.8 | 78.8 |
| canary-end | window r104 | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,767 | 22,586 | 21,658→22,362 | 1,014.2 | 80.0 | 80.0 |
| canary-end | window r105 | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,064 | 22,100 | 22,362→23,066 | 1,007.8 | 80.0 | 80.0 |
| canary-start | server start | 0 | 0 | 0 | 0 | 0 | none | - | 4,808 | 23,731 | 20,396→20,396 | - | - | - |
| canary-start | warm-up | 0 | 0 | 0 | 0 | 0 | none | 4 | 2,069 | 23,727 | 20,579→20,973 | 1,039.2 | 85.9 | - |
| canary-start | window r100 | 0 | 0 | 71 | 71 | 71 | activity | 0 | 42,419 | 22,910 | 20,932→21,408 | 1,019.3 | 80.2 | 80.2 |
| canary-start | window r101 | 0 | 71 | 141 | 142 | 71 | state+activity | 158 | 4,939 | 22,307 | 21,408→22,032 | 1,011.8 | 80.0 | 80.0 |
| canary-start | window r102 | 0 | 141 | 751 | 751 | 610 | state+activity | 357 | 1,567 | 21,683 | 22,032→22,040 | 1,017.7 | 79.8 | 79.8 |
| fit-q8-32K | server start | 0 | 0 | 0 | 0 | 0 | none | - | 220 | 24,817 | 20,452→20,452 | - | - | - |
| fit-q8-32K | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 16,657 | 24,305 | 20,640→21,055 | 1,028.3 | 86.0 | - |
| fit-q8-32K | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 10,780 | 22,713 | 21,203→22,606 | 1,014.8 | 79.6 | 79.7 |
| fit-q8-32K | server start | 1 | 0 | 0 | 0 | 0 | none | - | 3 | 24,850 | 20,452→20,452 | - | - | - |
| fit-q8-32K | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 1,009 | 24,309 | 20,640→21,055 | 1,031.9 | 86.3 | - |
| fit-q8-32K | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 12,002 | 22,644 | 21,199→22,433 | 1,001.6 | 80.2 | 80.3 |
| stock-32K | server start | 0 | 0 | 0 | 0 | 0 | none | - | 4 | 24,050 | 20,456→20,456 | - | - | - |
| stock-32K | warm-up | 0 | 0 | 0 | 0 | 0 | none | 5 | 747 | 23,704 | 20,643→21,149 | 956.5 | 83.2 | - |
| stock-32K | window r0 | 0 | 0 | 0 | 0 | 0 | none | 3 | 5,619 | 21,919 | 21,366→22,953 | 937.2 | 79.2 | 79.6 |
| stock-32K | window r1 | 0 | 0 | 4,143 | 4,146 | 4,143 | activity | 1,692 | 59,071 | 19,807 | 23,524→19,127 | 921.9 | 76.5 | 78.4 |

Rows named *warm-up* show the warm-up requests' speeds (8K prompts, 128 tokens) instead. On *server start* rows the swap columns are the first telemetry sample, and `pswpin` is the system-wide change from the environment snapshot to that sample.

## Three candidate rules

- **R0**: v1.3 as is: majflt > 1,000 or VmSwap > 0 at any sample.
- **R1**: majflt > 1,000 or VmSwap growth > 64 MiB in the window.
- **R2**: majflt > 1,000 or absolute VmSwap change > 64 MiB in the window.

| window | growth | abs. change | faults | R0 | R1 | R2 | recorded flag |
|---|---|---|---|---|---|---|---|
| canary-end-57efb62a-r103-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-end-57efb62a-r104-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-end-57efb62a-r105-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-start-57efb62a-r100-a1 | 71 | 71 | 0 | **FLAG** | **FLAG** | **FLAG** | paging |
| canary-start-57efb62a-r101-a1 | 71 | 71 | 158 | **FLAG** | **FLAG** | **FLAG** | paging |
| canary-start-57efb62a-r102-a1 | 610 | 610 | 357 | **FLAG** | **FLAG** | **FLAG** | paging |
| fit-q8-32K-57efb62a-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| fit-q8-32K-57efb62a-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| stock-32K-acee236c-r0-a1 | 0 | 0 | 3 | - | - | - | - |
| stock-32K-acee236c-r1-a1 | 4,146 | 4,146 | 1,692 | **FLAG** | **FLAG** | **FLAG** | paging |
| **windows flagged (of 10)** | | | | **4** | **4** | **4** | |

R0 reproduces the paging flag the runner recorded on 10 of 10 windows (check of this script against the recorded data).

## Which requests the activity belongs to: `stock-32K-acee236c-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.1 | 7.0 | 0 | 309 | 0 | 0 | 0 | 0 | 926.0 | 958.9 |
| 1 | A 24K | 6.8 | 26.8 | 0 | 13,272 | 78 | 0 | 0 | 78 | 917.5 | 925.6 |
| 2 | B 24K | 33.6 | 8.7 | 26 | 5,783 | 451 | 0 | 0 | 529 | 77.0 | 77.4 |
| 3 | A 16K | 42.3 | 18.6 | 604 | 13,479 | 3,038 | 0 | 0 | 3,566 | 921.9 | 937.2 |
| 4 | B 16K | 61.0 | 8.7 | 199 | 19,293 | 579 | 0 | 0 | 4,146 | 76.5 | 79.2 |
| 5 | A 8K | 69.6 | 8.8 | 843 | 4,397 | -3 | 0 | 0 | 4,143 | 939.1 | 950.1 |
| 6 | B 8K | 78.5 | 8.2 | 20 | 2,538 | 0 | 0 | 0 | - | 81.7 | 82.2 |

## Speed next to paging (anecdotal)

Windows of one configuration, split by the R0 flag. Different server instances and times; 10 windows in all.

| config | cells | flagged / not | PP_fresh 16K flagged vs not | TG 16K flagged vs not |
|---|---|---|---|---|
| `57efb62a` | canary-end, canary-start, fit-q8-32K | 3 / 5 | 1016.3 vs 1011.9 (+0.4%) | 80.0 vs 79.7 (+0.4%) |
| `acee236c` | stock-32K | 1 / 1 | 921.9 vs 937.2 (-1.6%) | 76.5 vs 79.2 (-3.4%) |

## What the data cannot show

- Ten windows from one session on one machine: no causal claim is possible, and every speed comparison below is anecdotal.
- This run has `VmSwap` and `VmRSS` but not `RssAnon`, `RssFile` or `RssShmem`, so it cannot show what sits in the swapped pages (anonymous heap, shared memory, or something else).
- Telemetry starts at the first warm-up request: the model load and the prefetch are not sampled. The 'server start' rows hold the first sample plus the snapshot's system counters.
- `pswpin` is system-wide (other processes swap too) and `pswpout` is not in this run's CSVs; the per-process view is `VmSwap` and the major faults of llama-server only.
- Sampling is 2 Hz: a swap burst shorter than half a second between two samples is seen only through the next sample's value.
- Windows of different server instances differ in everything the OS decided at that moment (page cache, what was swapped before), so a within-cell comparison also compares instances.

