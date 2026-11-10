# Paging analysis of `stage1-64K`

**SCREENING DATA (2 repetitions). Used only for shortlisting, never reported as results.** This is an investigation; `flags.paging` is unchanged.

## Per-window table

VmSwap and RSS in MiB. `nature`: state = swap already there at the window's first sample, activity = it grew. Speeds are tokens/s: PP_fresh at the 16K pair (Request A) and TG of the 16K Request B (and the mean TG of all B requests).

| cell | segment | inst | VmSwap start | end | max | change | nature | major faults | pswpin | MemAvail min | RSS start→end | PP_fresh 16K | TG 16K | TG B mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 18 | 26,268 | 20,766→20,766 | - | - | - |
| P1-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 8,615 | 25,353 | 20,987→21,406 | 2,284.0 | 81.9 | - |
| P1-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 1 | 12,302 | 23,426 | 21,555→23,523 | 2,228.2 | 77.0 | 70.3 |
| P1-64K-b2048 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 389 | 12,311 | 21,526 | 23,792→25,506 | 2,222.2 | 77.0 | 70.2 |
| P1-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 142 | 25,625 | 21,156→21,156 | - | - | - |
| P1-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 319 | 25,034 | 21,401→21,829 | 2,932.0 | 79.6 | - |
| P1-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 6,179 | 23,245 | 21,978→23,942 | 2,846.8 | 74.5 | 68.4 |
| P1-64K-b4096 | window r1 | 0 | 0 | 2 | 2 | 2 | activity | 0 | 3,978 | 21,248 | 24,203→25,986 | 2,844.6 | 74.9 | 68.2 |
| P2-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 6 | 25,883 | 20,766→20,766 | - | - | - |
| P2-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,534 | 25,455 | 20,988→21,408 | 2,433.7 | 84.9 | - |
| P2-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 1 | 3,300 | 23,460 | 21,558→23,444 | 2,372.1 | 78.7 | 71.8 |
| P2-64K-b2048 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 3,086 | 21,406 | 23,712→25,504 | 2,357.5 | 78.8 | 72.0 |
| P2-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 271 | 25,916 | 21,156→21,156 | - | - | - |
| P2-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 1 | 2,373 | 25,274 | 21,400→21,828 | 3,064.8 | 82.9 | - |
| P2-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 12,599 | 23,378 | 21,978→23,604 | 2,982.0 | 76.7 | 70.4 |
| P2-64K-b4096 | window r1 | 0 | 0 | 14 | 16 | 14 | activity | 515 | 4,944 | 21,554 | 24,214→25,646 | 2,962.0 | 77.6 | 70.4 |
| P3-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 3 | 25,954 | 20,769→20,769 | - | - | - |
| P3-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 28,044 | 24,922 | 20,990→21,414 | 2,171.6 | 65.9 | - |
| P3-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,331 | 23,076 | 21,564→23,531 | 2,126.7 | 63.1 | 58.4 |
| P3-64K-b2048 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 25,290 | 21,314 | 23,800→25,417 | 2,078.0 | 61.7 | 57.3 |
| P3-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 39 | 25,650 | 21,157→21,157 | - | - | - |
| P3-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 306 | 25,009 | 21,402→21,836 | 2,830.9 | 61.6 | - |
| P3-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 4,652 | 22,939 | 21,985→23,939 | 2,755.8 | 59.5 | 53.7 |
| P3-64K-b4096 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 29,764 | 21,380 | 24,208→25,801 | 2,757.3 | 57.8 | 53.9 |
| P4-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 10 | 26,366 | 20,768→20,768 | - | - | - |
| P4-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,872 | 25,734 | 20,989→21,414 | 2,081.0 | 73.5 | - |
| P4-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 12,904 | 23,821 | 21,564→23,186 | 2,075.3 | 69.3 | 64.6 |
| P4-64K-b2048 | window r1 | 0 | 0 | 359 | 359 | 359 | activity | 3 | 76,090 | 21,230 | 23,796→25,229 | 2,025.8 | 69.0 | 64.7 |
| P4-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 34 | 26,006 | 21,158→21,158 | - | - | - |
| P4-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 951 | 25,354 | 21,406→21,838 | 2,754.4 | 69.1 | - |
| P4-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 4,550 | 23,572 | 21,987→23,609 | 2,728.3 | 70.4 | 62.4 |
| P4-64K-b4096 | window r1 | 0 | 0 | 0 | 0 | 0 | activity | 288 | 8,667 | 21,114 | 24,215→25,750 | 2,630.4 | 66.1 | 61.0 |
| P5-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 11 | 25,729 | 20,769→20,769 | - | - | - |
| P5-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 323 | 25,160 | 20,989→21,416 | 1,888.1 | 86.3 | - |
| P5-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 6,304 | 23,670 | 21,566→23,187 | 1,969.7 | 84.2 | 75.0 |
| P5-64K-b2048 | window r1 | 0 | 0 | 730 | 730 | 730 | activity | 14 | 41,650 | 21,839 | 23,797→24,768 | 1,921.3 | 78.4 | 72.4 |
| P5-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 8 | 25,583 | 21,158→21,158 | - | - | - |
| P5-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 104 | 24,929 | 21,406→21,841 | 2,566.8 | 83.1 | - |
| P5-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,119 | 22,918 | 21,991→23,954 | 2,585.9 | 79.1 | 70.8 |
| P5-64K-b4096 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 5,903 | 21,104 | 24,223→25,666 | 2,616.6 | 76.3 | 70.7 |
| P6-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 215 | 25,791 | 20,770→20,770 | - | - | - |
| P6-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 3,811 | 25,223 | 20,989→21,431 | 1,469.5 | 86.0 | - |
| P6-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 11,726 | 23,397 | 21,581→23,538 | 1,789.6 | 89.0 | 79.2 |
| P6-64K-b2048 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 43 | 27,857 | 21,235 | 23,734→25,462 | 1,759.0 | 86.9 | 77.1 |
| P6-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 16 | 25,546 | 21,157→21,157 | - | - | - |
| P6-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 756 | 24,948 | 21,404→21,847 | 2,186.3 | 82.3 | - |
| P6-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,156 | 22,976 | 21,997→23,959 | 2,463.6 | 89.3 | 77.8 |
| P6-64K-b4096 | window r1 | 0 | 0 | 53 | 53 | 53 | activity | 2 | 35,201 | 21,316 | 24,228→25,791 | 2,461.5 | 83.2 | 75.8 |
| P7-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 8 | 25,902 | 20,770→20,770 | - | - | - |
| P7-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 45 | 25,290 | 20,989→21,431 | 1,410.3 | 80.4 | - |
| P7-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 410 | 23,537 | 21,581→23,202 | 1,588.1 | 79.5 | 71.4 |
| P7-64K-b2048 | window r1 | 0 | 0 | 2,557 | 2,557 | 2,557 | activity | 0 | 8,361 | 21,283 | 23,812→22,993 | 1,515.8 | 75.8 | 68.0 |
| P7-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 28 | 25,661 | 21,157→21,157 | - | - | - |
| P7-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,680 | 25,130 | 21,404→21,847 | 2,094.3 | 75.2 | - |
| P7-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 20,130 | 23,107 | 21,997→23,785 | 2,178.0 | 79.6 | 69.3 |
| P7-64K-b4096 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 3,658 | 21,209 | 24,224→25,662 | 2,263.6 | 73.0 | 66.9 |
| P8-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 10 | 26,176 | 9,064→9,064 | - | - | - |
| P8-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 240 | 25,650 | 9,274→9,702 | 2,049.3 | 81.9 | - |
| P8-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,649 | 23,492 | 9,852→11,646 | 2,008.9 | 75.3 | 68.8 |
| P8-64K-b2048 | window r1 | 0 | 0 | 500 | 500 | 500 | activity | 71 | 8,441 | 22,067 | 12,085→13,083 | 2,009.2 | 75.1 | 68.8 |
| P8-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 17 | 26,019 | 9,973→9,973 | - | - | - |
| P8-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 252 | 25,394 | 10,219→10,645 | 2,745.3 | 78.9 | - |
| P8-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 3,702 | 23,620 | 10,794→12,421 | 2,681.1 | 73.4 | 67.3 |
| P8-64K-b4096 | window r1 | 0 | 0 | 2,665 | 2,665 | 2,665 | activity | 5 | 5,116 | 21,413 | 13,031→12,033 | 2,680.1 | 72.5 | 67.2 |
| P9-64K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 23 | 26,261 | 8,154→8,154 | - | - | - |
| P9-64K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 150 | 25,637 | 8,365→8,793 | 2,193.0 | 84.2 | - |
| P9-64K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,142 | 23,727 | 8,942→10,736 | 2,147.1 | 78.0 | 71.1 |
| P9-64K-b2048 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 9,362 | 21,455 | 11,175→12,887 | 2,097.0 | 77.4 | 70.9 |
| P9-64K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 313 | 25,866 | 8,998→8,998 | - | - | - |
| P9-64K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 665 | 25,335 | 9,245→9,670 | 2,885.2 | 82.2 | - |
| P9-64K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,463 | 23,543 | 9,820→11,338 | 2,814.3 | 76.5 | 69.9 |
| P9-64K-b4096 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 18,499 | 21,327 | 11,948→13,741 | 2,810.3 | 76.5 | 69.8 |
| canary-end | server start | 0 | 0 | 0 | 0 | 0 | none | - | 17,182 | 26,035 | 20,503→20,503 | - | - | - |
| canary-end | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,289 | 25,647 | 20,687→21,105 | 984.2 | 84.2 | - |
| canary-end | window r103 | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,129 | 25,130 | 21,105→21,726 | 965.6 | 78.4 | 78.4 |
| canary-end | window r104 | 0 | 0 | 0 | 0 | 0 | none | 0 | 638 | 24,392 | 21,726→22,468 | 958.9 | 78.7 | 78.7 |
| canary-end | window r105 | 0 | 0 | 0 | 0 | 0 | none | 0 | 415 | 23,710 | 22,468→23,200 | 962.5 | 78.5 | 78.5 |
| canary-rerun-end | server start | 0 | 0 | 0 | 0 | 0 | none | - | 6,193 | 25,168 | 20,500→20,500 | - | - | - |
| canary-rerun-end | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 513 | 25,047 | 20,685→21,106 | 982.8 | 84.2 | - |
| canary-rerun-end | window r113 | 0 | 0 | 0 | 0 | 0 | none | 0 | 355 | 24,636 | 21,106→21,722 | 965.1 | 78.1 | 78.1 |
| canary-rerun-end | window r114 | 0 | 0 | 0 | 0 | 0 | none | 0 | 333 | 23,735 | 21,722→22,443 | 957.3 | 78.2 | 78.2 |
| canary-rerun-end | window r115 | 0 | 0 | 0 | 0 | 0 | none | 0 | 421 | 23,016 | 22,443→23,173 | 961.0 | 78.7 | 78.7 |
| canary-rerun-start | server start | 0 | 0 | 0 | 0 | 0 | none | - | 363 | 24,971 | 20,502→20,502 | - | - | - |
| canary-rerun-start | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 13 | 24,545 | 20,679→21,106 | 972.3 | 84.2 | - |
| canary-rerun-start | window r110 | 0 | 0 | 0 | 0 | 0 | none | 0 | 132 | 23,965 | 21,106→21,723 | 963.0 | 78.4 | 78.4 |
| canary-rerun-start | window r111 | 0 | 0 | 0 | 0 | 0 | none | 0 | 65 | 23,320 | 21,723→22,469 | 955.8 | 78.9 | 78.9 |
| canary-rerun-start | window r112 | 0 | 0 | 0 | 0 | 0 | none | 0 | 66 | 22,716 | 22,469→23,204 | 959.9 | 79.0 | 79.0 |
| canary-start | server start | 0 | 0 | 0 | 0 | 0 | none | - | 170 | 25,941 | 20,500→20,500 | - | - | - |
| canary-start | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 89 | 25,472 | 20,688→21,106 | 978.1 | 84.4 | - |
| canary-start | window r100 | 0 | 0 | 0 | 0 | 0 | none | 0 | 266 | 24,772 | 21,106→21,725 | 957.6 | 78.3 | 78.3 |
| canary-start | window r101 | 0 | 0 | 0 | 0 | 0 | none | 0 | 175 | 24,153 | 21,725→22,467 | 951.6 | 78.5 | 78.5 |
| canary-start | window r102 | 0 | 0 | 0 | 0 | 0 | none | 0 | 361 | 23,432 | 22,467→23,182 | 955.9 | 78.5 | 78.5 |
| stock-64K | server start | 0 | 0 | 0 | 0 | 0 | none | - | 25 | 26,674 | 20,492→20,492 | - | - | - |
| stock-64K | warm-up | 0 | 0 | 0 | 0 | 0 | none | 2 | 452 | 26,032 | 20,679→21,188 | 885.7 | 81.9 | - |
| stock-64K | window r0 | 0 | 0 | 21 | 21 | 21 | activity | 0 | 55,499 | 23,149 | 21,414→23,954 | 868.1 | 77.9 | 73.3 |
| stock-64K | window r1 | 0 | 21 | 6,193 | 6,200 | 6,172 | state+activity | 1,790 | 89,125 | 20,013 | 24,725→19,588 | 860.8 | 77.2 | 73.1 |
| stock-64K | server start | 1 | 0 | 0 | 0 | 0 | none | - | 0 | 25,515 | 20,489→20,489 | - | - | - |
| stock-64K | warm-up | 1 | 0 | 0 | 0 | 0 | none | 2 | 103 | 24,908 | 20,677→21,185 | 884.9 | 81.2 | - |
| stock-64K | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 1,491 | 22,343 | 21,410→23,952 | 852.7 | 78.0 | 73.4 |

Rows named *warm-up* show the warm-up requests' speeds (8K prompts, 128 tokens) instead. On *server start* rows the swap columns are the first telemetry sample, and `pswpin` is the system-wide change from the environment snapshot to that sample.

## Three candidate rules

- **R0**: v1.3 as is: majflt > 1,000 or VmSwap > 0 at any sample.
- **R1**: majflt > 1,000 or VmSwap growth > 64 MiB in the window.
- **R2**: majflt > 1,000 or absolute VmSwap change > 64 MiB in the window.

| window | growth | abs. change | faults | R0 | R1 | R2 | recorded flag |
|---|---|---|---|---|---|---|---|
| P1-64K-b2048-e3922ae5-r0-a1 | 0 | 0 | 1 | - | - | - | - |
| P1-64K-b2048-e3922ae5-r1-a1 | 0 | 0 | 389 | - | - | - | - |
| P1-64K-b4096-cf46edc6-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P1-64K-b4096-cf46edc6-r1-a1 | 2 | 2 | 0 | **FLAG** | - | - | - |
| P2-64K-b2048-ea955cc1-r0-a1 | 0 | 0 | 1 | - | - | - | - |
| P2-64K-b2048-ea955cc1-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| P2-64K-b4096-9f88f731-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P2-64K-b4096-9f88f731-r1-a1 | 16 | 16 | 515 | **FLAG** | - | - | - |
| P3-64K-b2048-33699515-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P3-64K-b2048-33699515-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| P3-64K-b4096-6c2e8884-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P3-64K-b4096-6c2e8884-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| P4-64K-b2048-3f2ad999-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P4-64K-b2048-3f2ad999-r1-a1 | 359 | 359 | 3 | **FLAG** | **FLAG** | **FLAG** | - |
| P4-64K-b4096-2b09cb5c-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P4-64K-b4096-2b09cb5c-r1-a1 | 0 | 0 | 288 | **FLAG** | - | - | - |
| P5-64K-b2048-5c4ca840-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P5-64K-b2048-5c4ca840-r1-a1 | 730 | 730 | 14 | **FLAG** | **FLAG** | **FLAG** | - |
| P5-64K-b4096-caba1345-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P5-64K-b4096-caba1345-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| P6-64K-b2048-8f495caa-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P6-64K-b2048-8f495caa-r1-a1 | 0 | 0 | 43 | - | - | - | - |
| P6-64K-b4096-1276046f-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P6-64K-b4096-1276046f-r1-a1 | 53 | 53 | 2 | **FLAG** | - | - | - |
| P7-64K-b2048-8956b017-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P7-64K-b2048-8956b017-r1-a1 | 2,557 | 2,557 | 0 | **FLAG** | **FLAG** | **FLAG** | - |
| P7-64K-b4096-2f4ca7f1-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P7-64K-b4096-2f4ca7f1-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| P8-64K-b2048-ccfc870c-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P8-64K-b2048-ccfc870c-r1-a1 | 500 | 500 | 71 | **FLAG** | **FLAG** | **FLAG** | - |
| P8-64K-b4096-8815d72e-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P8-64K-b4096-8815d72e-r1-a1 | 2,665 | 2,665 | 5 | **FLAG** | **FLAG** | **FLAG** | - |
| P9-64K-b2048-d395dc46-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P9-64K-b2048-d395dc46-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| P9-64K-b4096-97f86f28-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P9-64K-b4096-97f86f28-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-end-debea778-r103-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-end-debea778-r104-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-end-debea778-r105-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-end-debea778-r113-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-end-debea778-r114-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-end-debea778-r115-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-start-debea778-r110-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-start-debea778-r111-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-start-debea778-r112-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-start-debea778-r100-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-start-debea778-r101-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-start-debea778-r102-a1 | 0 | 0 | 0 | - | - | - | - |
| stock-64K-22dc1178-r0-a1 | 21 | 21 | 0 | **FLAG** | - | - | - |
| stock-64K-22dc1178-r1-a1 | 6,179 | 6,179 | 1,790 | **FLAG** | **FLAG** | **FLAG** | paging |
| stock-64K-22dc1178-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| **windows flagged (of 51)** | | | | **11** | **6** | **6** | |

R0 reproduces the paging flag the runner recorded on 41 of 51 windows (check of this script against the recorded data).

## Which requests the activity belongs to: `stock-64K-22dc1178-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.3 | 7.2 | 1 | 143 | 0 | 0 | 0 | 21 | 889.1 | 888.6 |
| 1 | A 48K | 6.9 | 59.7 | 5 | 1,831 | 0 | 0 | 0 | 21 | 824.1 | 824.3 |
| 2 | B 48K | 66.5 | 9.8 | 0 | 400 | 0 | 0 | 0 | 21 | 69.0 | 68.7 |
| 3 | A 16K | 76.4 | 19.3 | 0 | 279 | 124 | 0 | 0 | 369 | 860.8 | 852.7 |
| 4 | B 16K | 95.7 | 8.9 | 7 | 967 | 1,716 | 0 | 0 | 2,151 | 77.2 | 78.0 |
| 5 | A 32K | 104.6 | 39.7 | 377 | 76,306 | 4,338 | 0 | 0 | 6,195 | 839.3 | 842.0 |
| 6 | B 32K | 144.3 | 9.3 | 1,400 | 9,199 | -5 | 0 | 0 | - | 73.1 | 73.3 |

## Speed next to paging (anecdotal)

Windows of one configuration, split by the R0 flag. Different server instances and times; 10 windows in all.

| config | cells | flagged / not | PP_fresh 16K flagged vs not | TG 16K flagged vs not |
|---|---|---|---|---|
| `1276046f` | P6-64K-b4096 | 1 / 1 | 2461.5 vs 2463.6 (-0.1%) | 83.2 vs 89.3 (-6.9%) |
| `22dc1178` | stock-64K | 2 / 1 | 864.4 vs 852.7 (+1.4%) | 77.5 vs 78.0 (-0.6%) |
| `2b09cb5c` | P4-64K-b4096 | 1 / 1 | 2630.4 vs 2728.3 (-3.6%) | 66.1 vs 70.4 (-6.1%) |
| `3f2ad999` | P4-64K-b2048 | 1 / 1 | 2025.8 vs 2075.3 (-2.4%) | 69.0 vs 69.3 (-0.5%) |
| `5c4ca840` | P5-64K-b2048 | 1 / 1 | 1921.3 vs 1969.7 (-2.5%) | 78.4 vs 84.2 (-6.9%) |
| `8815d72e` | P8-64K-b4096 | 1 / 1 | 2680.1 vs 2681.1 (-0.0%) | 72.5 vs 73.4 (-1.1%) |
| `8956b017` | P7-64K-b2048 | 1 / 1 | 1515.8 vs 1588.1 (-4.6%) | 75.8 vs 79.5 (-4.6%) |
| `9f88f731` | P2-64K-b4096 | 1 / 1 | 2962.0 vs 2982.0 (-0.7%) | 77.6 vs 76.7 (+1.1%) |
| `ccfc870c` | P8-64K-b2048 | 1 / 1 | 2009.2 vs 2008.9 (+0.0%) | 75.1 vs 75.3 (-0.2%) |
| `cf46edc6` | P1-64K-b4096 | 1 / 1 | 2844.6 vs 2846.8 (-0.1%) | 74.9 vs 74.5 (+0.5%) |

## What the data cannot show

- Ten windows from one session on one machine: no causal claim is possible, and every speed comparison below is anecdotal.
- This run has `VmSwap` and `VmRSS` but not `RssAnon`, `RssFile` or `RssShmem`, so it cannot show what sits in the swapped pages (anonymous heap, shared memory, or something else).
- Telemetry starts at the first warm-up request: the model load and the prefetch are not sampled. The 'server start' rows hold the first sample plus the snapshot's system counters.
- `pswpin` is system-wide (other processes swap too) and `pswpout` is not in this run's CSVs; the per-process view is `VmSwap` and the major faults of llama-server only.
- Sampling is 2 Hz: a swap burst shorter than half a second between two samples is seen only through the next sample's value.
- Windows of different server instances differ in everything the OS decided at that moment (page cache, what was swapped before), so a within-cell comparison also compares instances.

