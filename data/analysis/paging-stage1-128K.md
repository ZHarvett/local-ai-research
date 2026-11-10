# Paging analysis of `stage1-128K`

**Functional-test data (WP9 mini-sweep), not results.** This is an investigation; `flags.paging` is unchanged.

## Per-window table

VmSwap and RSS in MiB. `nature`: state = swap already there at the window's first sample, activity = it grew. Speeds are tokens/s: PP_fresh at the 16K pair (Request A) and TG of the 16K Request B (and the mean TG of all B requests).

| cell | segment | inst | VmSwap start | end | max | change | nature | major faults | pswpin | MemAvail min | RSS start→end | PP_fresh 16K | TG 16K | TG B mean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P1-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 491 | 25,849 | 21,024→21,024 | - | - | - |
| P1-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 420 | 25,278 | 21,245→21,664 | 2,118.5 | 79.1 | - |
| P1-128K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 72,564 | 22,314 | 21,813→24,623 | - | - | 58.2 |
| P1-128K-b2048 | window r1 | 0 | 0 | 3,603 | 3,615 | 3,603 | activity | 4,861 | 159,917 | 20,140 | 25,062→20,847 | - | - | 58.1 |
| P1-128K-b2048 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 10 | 25,746 | 21,025→21,025 | - | - | - |
| P1-128K-b2048 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 221 | 25,142 | 21,246→21,665 | 2,126.0 | 79.3 | - |
| P1-128K-b2048 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 1,414 | 23,103 | 21,814→23,880 | - | - | 58.4 |
| P1-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 497 | 25,246 | 21,671→21,671 | - | - | - |
| P1-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 166 | 24,649 | 21,919→22,343 | 2,724.4 | 75.1 | - |
| P1-128K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 81,084 | 21,279 | 22,493→25,131 | - | - | 55.6 |
| P1-128K-b4096 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 20 | 20,753 | 18,292 | 25,570→21,514 | - | - | 56.1 |
| P2-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 578 | 25,753 | 21,026→21,026 | - | - | - |
| P2-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 2 | 237 | 25,157 | 21,247→21,668 | 2,248.3 | 80.9 | - |
| P2-128K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 6,355 | 22,766 | 21,817→24,298 | - | - | 59.3 |
| P2-128K-b2048 | window r1 | 0 | 3 | 3,338 | 3,354 | 3,335 | state+activity | 3,813 | 38,967 | 19,470 | 25,003→20,564 | - | - | 59.3 |
| P2-128K-b2048 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 3 | 25,577 | 21,026→21,026 | - | - | - |
| P2-128K-b2048 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 456 | 25,034 | 21,247→21,666 | 2,255.1 | 81.3 | - |
| P2-128K-b2048 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 12,719 | 22,191 | 21,815→24,644 | - | - | 59.2 |
| P2-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 218 | 25,190 | 21,621→21,621 | - | - | - |
| P2-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 4 | 135 | 24,574 | 21,846→22,293 | 2,795.0 | 78.6 | - |
| P2-128K-b4096 | window r0 | 0 | 0 | 331 | 331 | 331 | activity | 97 | 16,706 | 22,391 | 22,440→24,059 | - | - | 57.7 |
| P2-128K-b4096 | window r1 | 0 | 331 | 5,069 | 5,071 | 4,739 | state+activity | 9,341 | 47,005 | 19,381 | 25,168→21,287 | - | - | 57.6 |
| P2-128K-b4096 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 15 | 25,119 | 21,670→21,670 | - | - | - |
| P2-128K-b4096 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 3 | 1,121 | 24,495 | 21,914→22,343 | 2,833.7 | 77.8 | - |
| P2-128K-b4096 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 27,097 | 21,921 | 22,492→24,869 | - | - | 57.3 |
| P3-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 0 | 25,856 | 21,027→21,027 | - | - | - |
| P3-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 20 | 25,273 | 21,248→21,674 | 2,028.5 | 57.9 | - |
| P3-128K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,111 | 22,035 | 21,823→24,647 | - | - | 45.9 |
| P3-128K-b2048 | window r1 | 0 | 0 | 5,369 | 5,400 | 5,369 | activity | 8,071 | 212,341 | 19,449 | 25,086→19,831 | - | - | 47.3 |
| P3-128K-b2048 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 22 | 25,576 | 21,027→21,027 | - | - | - |
| P3-128K-b2048 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 631 | 24,966 | 21,248→21,673 | 2,026.2 | 57.9 | - |
| P3-128K-b2048 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 5,113 | 21,912 | 21,822→24,633 | - | - | 47.3 |
| P3-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 785 | 25,010 | 21,672→21,672 | - | - | - |
| P3-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 408 | 24,360 | 21,920→22,352 | 2,647.7 | 53.4 | - |
| P3-128K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 17,880 | 22,444 | 22,501→24,649 | - | - | 43.8 |
| P3-128K-b4096 | window r1 | 0 | 0 | 4,023 | 4,061 | 4,023 | activity | 24,142 | 106,718 | 19,503 | 24,881→19,368 | - | - | 44.0 |
| P3-128K-b4096 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 4 | 24,589 | 21,674→21,674 | - | - | - |
| P3-128K-b4096 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 35 | 24,010 | 21,922→22,354 | 2,647.8 | 53.5 | - |
| P3-128K-b4096 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 1,743 | 22,189 | 22,503→24,649 | - | - | 44.5 |
| P4-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 836 | 26,029 | 21,026→21,026 | - | - | - |
| P4-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 225 | 25,436 | 21,247→21,673 | 1,953.4 | 71.4 | - |
| P4-128K-b2048 | window r0 | 0 | 0 | 8 | 8 | 8 | activity | 2 | 28,212 | 22,523 | 21,823→24,567 | - | - | 53.0 |
| P4-128K-b2048 | window r1 | 0 | 8 | 4,180 | 4,181 | 4,172 | state+activity | 2,966 | 60,048 | 19,760 | 25,006→20,918 | - | - | 53.4 |
| P4-128K-b2048 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 12 | 25,212 | 21,031→21,031 | - | - | - |
| P4-128K-b2048 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 17 | 24,771 | 21,252→21,678 | 1,954.7 | 71.5 | - |
| P4-128K-b2048 | window r1 | 1 | 0 | 20 | 20 | 20 | activity | 0 | 1,949 | 22,133 | 21,827→24,301 | - | - | 53.8 |
| P4-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 659 | 25,129 | 21,672→21,672 | - | - | - |
| P4-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 1,577 | 24,582 | 21,920→22,353 | 2,569.8 | 65.4 | - |
| P4-128K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 49,763 | 22,351 | 22,502→24,649 | - | - | 50.4 |
| P4-128K-b4096 | window r1 | 0 | 13 | 3,008 | 3,011 | 2,994 | state+activity | 19,386 | 16,884 | 19,124 | 25,757→20,739 | - | - | 49.8 |
| P4-128K-b4096 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 2 | 25,190 | 21,673→21,673 | - | - | - |
| P4-128K-b4096 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 32,552 | 24,445 | 21,921→22,354 | 2,571.9 | 65.7 | - |
| P4-128K-b4096 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 2,371 | 21,707 | 22,504→24,974 | - | - | 50.5 |
| P5-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 694 | 25,928 | 21,029→21,029 | - | - | - |
| P5-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 1 | 715 | 25,315 | 21,249→21,678 | 1,783.1 | 76.6 | - |
| P5-128K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 21,707 | 22,783 | 21,828→24,312 | - | - | 59.0 |
| P5-128K-b2048 | window r1 | 0 | 0 | 3,757 | 3,785 | 3,757 | activity | 79,505 | 82,338 | 19,617 | 24,954→22,066 | - | - | 56.1 |
| P5-128K-b2048 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 3 | 25,784 | 21,031→21,031 | - | - | - |
| P5-128K-b2048 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 298 | 25,188 | 21,251→21,680 | 1,781.6 | 76.5 | - |
| P5-128K-b2048 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 10,163 | 22,128 | 21,829→24,662 | - | - | 59.1 |
| P5-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 152 | 25,223 | 21,675→21,675 | - | - | - |
| P5-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 62,417 | 24,380 | 21,922→22,356 | 2,420.6 | 76.0 | - |
| P5-128K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 19,892 | 22,125 | 22,503→24,871 | - | - | 54.0 |
| P5-128K-b4096 | window r1 | 0 | 0 | 3,147 | 3,150 | 3,147 | activity | 8,083 | 62,454 | 18,604 | 24,916→20,100 | - | - | 54.8 |
| P5-128K-b4096 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 2 | 25,008 | 21,673→21,673 | - | - | - |
| P5-128K-b4096 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 102 | 24,320 | 21,921→22,358 | 2,404.1 | 75.5 | - |
| P5-128K-b4096 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 3,146 | 21,231 | 22,507→25,214 | - | - | 54.6 |
| P6-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 893 | 25,805 | 21,027→21,027 | - | - | - |
| P6-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 486 | 25,358 | 21,246→21,688 | 1,465.4 | 84.0 | - |
| P6-128K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 1 | 31,208 | 22,493 | 21,838→24,655 | - | - | 66.1 |
| P6-128K-b2048 | window r1 | 0 | 0 | 4,562 | 4,565 | 4,562 | activity | 1,077 | 23,877 | 20,053 | 25,084→20,761 | - | - | 62.4 |
| P6-128K-b2048 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 1 | 25,301 | 21,027→21,027 | - | - | - |
| P6-128K-b2048 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 228 | 24,671 | 21,246→21,689 | 1,467.3 | 84.2 | - |
| P6-128K-b2048 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 2,854 | 22,683 | 21,838→23,897 | - | - | 62.2 |
| P6-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 54 | 25,005 | 21,673→21,673 | - | - | - |
| P6-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 73 | 24,315 | 21,919→22,363 | 2,131.4 | 77.8 | - |
| P6-128K-b4096 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 0 | 5,030 | 22,127 | 22,512→24,481 | - | - | 60.8 |
| P6-128K-b4096 | window r1 | 0 | 0 | 4,554 | 4,563 | 4,554 | activity | 37,190 | 70,389 | 19,782 | 24,645→20,607 | - | - | 58.9 |
| P6-128K-b4096 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 7 | 25,116 | 21,672→21,672 | - | - | - |
| P6-128K-b4096 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 426 | 24,449 | 21,918→22,362 | 2,106.4 | 77.2 | - |
| P6-128K-b4096 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 44,122 | 22,046 | 22,511→24,660 | - | - | 60.8 |
| P7-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 42 | 25,825 | 21,031→21,031 | - | - | - |
| P7-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 135 | 25,198 | 21,250→21,693 | 1,388.3 | 76.6 | - |
| P7-128K-b2048 | window r0 | 0 | 0 | 71 | 71 | 71 | activity | 0 | 2,667 | 22,483 | 21,842→24,255 | - | - | 59.5 |
| P7-128K-b2048 | window r1 | 0 | 204 | 4,952 | 4,976 | 4,747 | state+activity | 44,061 | 83,452 | 19,789 | 24,897→20,753 | - | - | 53.9 |
| P7-128K-b2048 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 4 | 25,608 | 21,027→21,027 | - | - | - |
| P7-128K-b2048 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 214 | 25,004 | 21,246→21,689 | 1,364.7 | 75.8 | - |
| P7-128K-b2048 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 46,471 | 22,083 | 21,838→24,231 | - | - | 55.8 |
| P7-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 1,048 | 25,259 | 21,673→21,673 | - | - | - |
| P7-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 703 | 24,589 | 21,919→22,363 | 2,016.4 | 68.4 | - |
| P7-128K-b4096 | window r0 | 0 | 0 | 16 | 16 | 16 | activity | 0 | 17,264 | 22,502 | 22,512→24,550 | - | - | 53.0 |
| P7-128K-b4096 | window r1 | 0 | 20 | 5,386 | 5,388 | 5,366 | state+activity | 81,062 | 105,154 | 19,273 | 25,603→20,640 | - | - | 50.2 |
| P7-128K-b4096 | server start | 1 | 0 | 0 | 0 | 0 | none | - | 3 | 24,847 | 21,672→21,672 | - | - | - |
| P7-128K-b4096 | warm-up | 1 | 0 | 0 | 0 | 0 | none | 0 | 82 | 24,182 | 21,918→22,362 | 2,014.4 | 68.6 | - |
| P7-128K-b4096 | window r1 | 1 | 0 | 0 | 0 | 0 | none | 0 | 3,770 | 21,519 | 22,511→24,999 | - | - | 53.2 |
| P8-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 604 | 25,609 | 10,295→10,295 | - | - | - |
| P8-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,065 | 25,099 | 10,505→10,933 | 1,913.9 | 76.9 | - |
| P8-128K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 7 | 9,252 | 23,074 | 11,053→13,231 | - | - | 56.8 |
| P8-128K-b2048 | window r1 | 0 | 0 | 2,277 | 2,277 | 2,277 | activity | 61 | 73,201 | 19,485 | 14,353→14,405 | - | - | 56.7 |
| P8-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 675 | 25,571 | 11,893→11,893 | - | - | - |
| P8-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 3 | 600 | 24,961 | 12,157→12,587 | 2,543.2 | 74.4 | - |
| P8-128K-b4096 | window r0 | 0 | 0 | 333 | 333 | 333 | activity | 105 | 30,213 | 22,550 | 12,631→14,395 | - | - | 55.3 |
| P8-128K-b4096 | window r1 | 0 | 345 | 345 | 345 | 0 | state | 24 | 47,485 | 19,017 | 15,501→17,987 | - | - | 55.3 |
| P9-128K-b2048 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 121 | 26,043 | 9,323→9,323 | - | - | - |
| P9-128K-b2048 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 762 | 25,428 | 9,533→9,960 | 2,049.9 | 80.7 | - |
| P9-128K-b2048 | window r0 | 0 | 0 | 0 | 0 | 0 | none | 74 | 9,203 | 22,361 | 10,109→12,934 | - | - | 58.9 |
| P9-128K-b2048 | window r1 | 0 | 0 | 0 | 0 | 0 | none | 0 | 6,747 | 19,282 | 13,366→16,202 | - | - | 58.8 |
| P9-128K-b4096 | server start | 0 | 0 | 0 | 0 | 0 | none | - | 274 | 25,451 | 10,713→10,713 | - | - | - |
| P9-128K-b4096 | warm-up | 0 | 0 | 0 | 0 | 0 | none | 5 | 208 | 24,817 | 10,964→11,578 | 2,586.7 | 77.5 | - |
| P9-128K-b4096 | window r0 | 0 | 0 | 173 | 173 | 173 | activity | 23 | 18,028 | 22,338 | 11,728→13,685 | - | - | 57.3 |
| P9-128K-b4096 | window r1 | 0 | 173 | 825 | 825 | 652 | state+activity | 42 | 26,930 | 19,639 | 14,801→16,042 | - | - | 56.8 |
| canary-end | server start | 0 | 0 | 0 | 0 | 0 | none | - | 14,395 | 26,196 | 20,502→20,502 | - | - | - |
| canary-end | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 177 | 25,857 | 20,686→21,100 | 983.7 | 84.9 | - |
| canary-end | window r103 | 0 | 0 | 0 | 0 | 0 | none | 0 | 38,682 | 24,919 | 21,100→21,719 | 965.4 | 78.7 | 78.7 |
| canary-end | window r104 | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,837 | 24,285 | 21,719→22,458 | 958.9 | 78.7 | 78.7 |
| canary-end | window r105 | 0 | 0 | 0 | 0 | 0 | none | 0 | 8,713 | 23,589 | 22,458→23,191 | 961.7 | 78.1 | 78.1 |
| canary-rerun-end | server start | 0 | 0 | 0 | 0 | 0 | none | - | 16,030 | 26,236 | 20,505→20,505 | - | - | - |
| canary-rerun-end | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 3,795 | 25,535 | 20,689→21,107 | 982.5 | 84.5 | - |
| canary-rerun-end | window r113 | 0 | 0 | 0 | 0 | 0 | none | 0 | 982 | 25,071 | 21,107→21,728 | 965.1 | 78.1 | 78.1 |
| canary-rerun-end | window r114 | 0 | 0 | 0 | 0 | 0 | none | 0 | 8,508 | 24,304 | 21,728→22,468 | 955.6 | 78.1 | 78.1 |
| canary-rerun-end | window r115 | 0 | 0 | 191 | 191 | 191 | activity | 5 | 1,192 | 23,549 | 22,468→22,932 | 960.2 | 77.9 | 77.9 |
| canary-rerun-start | server start | 0 | 0 | 0 | 0 | 0 | none | - | 316 | 25,539 | 20,505→20,505 | - | - | - |
| canary-rerun-start | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 174 | 25,092 | 20,689→21,107 | 983.0 | 84.4 | - |
| canary-rerun-start | window r110 | 0 | 0 | 0 | 0 | 0 | none | 0 | 614 | 24,472 | 21,107→21,723 | 961.9 | 79.0 | 79.0 |
| canary-rerun-start | window r111 | 0 | 0 | 0 | 0 | 0 | none | 0 | 784 | 23,975 | 21,723→22,462 | 955.1 | 78.9 | 78.9 |
| canary-rerun-start | window r112 | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,427 | 22,982 | 22,462→23,193 | 959.1 | 78.5 | 78.5 |
| canary-start | server start | 0 | 0 | 0 | 0 | 0 | none | - | 375 | 25,937 | 20,501→20,501 | - | - | - |
| canary-start | warm-up | 0 | 0 | 0 | 0 | 0 | none | 0 | 178 | 25,576 | 20,688→21,107 | 984.3 | 84.7 | - |
| canary-start | window r100 | 0 | 0 | 0 | 0 | 0 | none | 0 | 1,797 | 24,700 | 21,107→21,724 | 962.7 | 78.7 | 78.7 |
| canary-start | window r101 | 0 | 0 | 0 | 0 | 0 | none | 0 | 2,600 | 24,332 | 21,724→22,466 | 956.1 | 78.4 | 78.4 |
| canary-start | window r102 | 0 | 0 | 0 | 0 | 0 | none | 0 | 184 | 23,671 | 22,466→23,199 | 961.1 | 78.5 | 78.5 |
| stock-128K | server start | 0 | 0 | 0 | 0 | 0 | none | - | 102 | 26,372 | 20,549→20,549 | - | - | - |
| stock-128K | warm-up | 0 | 0 | 0 | 0 | 0 | none | 5 | 1,186 | 25,868 | 20,736→21,236 | 760.6 | 76.5 | - |
| stock-128K | window r0 | 0 | 0 | 823 | 823 | 823 | activity | 25 | 60,546 | 21,861 | 21,236→24,403 | - | - | 62.4 |
| stock-128K | window r1 | 0 | 1,018 | 552 | 3,315 | -467 | state+activity | 5,861 | 91,597 | 18,218 | 24,919→19,226 | - | - | 62.8 |
| stock-128K | server start | 1 | 0 | 0 | 0 | 0 | none | - | 2 | 26,393 | 20,553→20,553 | - | - | - |
| stock-128K | warm-up | 1 | 0 | 0 | 0 | 0 | none | 2 | 150 | 25,726 | 20,740→21,250 | 766.8 | 76.6 | - |
| stock-128K | window r1 | 1 | 0 | 2,366 | 2,366 | 2,366 | activity | 327 | 154,805 | 20,938 | 21,476→22,836 | - | - | 62.1 |

Rows named *warm-up* show the warm-up requests' speeds (8K prompts, 128 tokens) instead. On *server start* rows the swap columns are the first telemetry sample, and `pswpin` is the system-wide change from the environment snapshot to that sample.

## Three candidate rules

- **R0**: v1.3 as is: majflt > 1,000 or VmSwap > 0 at any sample.
- **R1**: majflt > 1,000 or VmSwap growth > 64 MiB in the window.
- **R2**: majflt > 1,000 or absolute VmSwap change > 64 MiB in the window.

| window | growth | abs. change | faults | R0 | R1 | R2 | recorded flag |
|---|---|---|---|---|---|---|---|
| P1-128K-b2048-719d8935-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P1-128K-b2048-719d8935-r1-a1 | 3,615 | 3,615 | 4,861 | **FLAG** | **FLAG** | **FLAG** | paging |
| P1-128K-b2048-719d8935-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P1-128K-b4096-94df7974-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P1-128K-b4096-94df7974-r1-a1 | 0 | 0 | 20 | - | - | - | - |
| P2-128K-b2048-30d55af4-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P2-128K-b2048-30d55af4-r1-a1 | 3,351 | 3,351 | 3,813 | **FLAG** | **FLAG** | **FLAG** | paging |
| P2-128K-b2048-30d55af4-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P2-128K-b4096-f989bd0a-r0-a1 | 331 | 331 | 97 | **FLAG** | **FLAG** | **FLAG** | - |
| P2-128K-b4096-f989bd0a-r1-a1 | 4,740 | 4,740 | 9,341 | **FLAG** | **FLAG** | **FLAG** | paging |
| P2-128K-b4096-f989bd0a-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P3-128K-b2048-ec9defe0-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P3-128K-b2048-ec9defe0-r1-a1 | 5,400 | 5,400 | 8,071 | **FLAG** | **FLAG** | **FLAG** | paging |
| P3-128K-b2048-ec9defe0-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P3-128K-b4096-95a0b1dd-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P3-128K-b4096-95a0b1dd-r1-a1 | 4,061 | 4,061 | 24,142 | **FLAG** | **FLAG** | **FLAG** | paging |
| P3-128K-b4096-95a0b1dd-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P4-128K-b2048-058d1758-r0-a1 | 8 | 8 | 2 | **FLAG** | - | - | - |
| P4-128K-b2048-058d1758-r1-a1 | 4,173 | 4,173 | 2,966 | **FLAG** | **FLAG** | **FLAG** | paging |
| P4-128K-b2048-058d1758-r1-a2 | 20 | 20 | 0 | **FLAG** | - | - | - |
| P4-128K-b4096-93b48048-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P4-128K-b4096-93b48048-r1-a1 | 2,997 | 2,997 | 19,386 | **FLAG** | **FLAG** | **FLAG** | paging |
| P4-128K-b4096-93b48048-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P5-128K-b2048-45dd3f62-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P5-128K-b2048-45dd3f62-r1-a1 | 3,785 | 3,785 | 79,505 | **FLAG** | **FLAG** | **FLAG** | paging |
| P5-128K-b2048-45dd3f62-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P5-128K-b4096-f68f2a79-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P5-128K-b4096-f68f2a79-r1-a1 | 3,150 | 3,150 | 8,083 | **FLAG** | **FLAG** | **FLAG** | paging |
| P5-128K-b4096-f68f2a79-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P6-128K-b2048-9bc32784-r0-a1 | 0 | 0 | 1 | - | - | - | - |
| P6-128K-b2048-9bc32784-r1-a1 | 4,565 | 4,565 | 1,077 | **FLAG** | **FLAG** | **FLAG** | paging |
| P6-128K-b2048-9bc32784-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P6-128K-b4096-b801464e-r0-a1 | 0 | 0 | 0 | - | - | - | - |
| P6-128K-b4096-b801464e-r1-a1 | 4,563 | 4,563 | 37,190 | **FLAG** | **FLAG** | **FLAG** | paging |
| P6-128K-b4096-b801464e-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P7-128K-b2048-b1c77f83-r0-a1 | 71 | 71 | 0 | **FLAG** | **FLAG** | **FLAG** | - |
| P7-128K-b2048-b1c77f83-r1-a1 | 4,772 | 4,772 | 44,061 | **FLAG** | **FLAG** | **FLAG** | paging |
| P7-128K-b2048-b1c77f83-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P7-128K-b4096-af2a855d-r0-a1 | 16 | 16 | 0 | **FLAG** | - | - | - |
| P7-128K-b4096-af2a855d-r1-a1 | 5,368 | 5,368 | 81,062 | **FLAG** | **FLAG** | **FLAG** | paging |
| P7-128K-b4096-af2a855d-r1-a2 | 0 | 0 | 0 | - | - | - | - |
| P8-128K-b2048-704dd2e5-r0-a1 | 0 | 0 | 7 | - | - | - | - |
| P8-128K-b2048-704dd2e5-r1-a1 | 2,277 | 2,277 | 61 | **FLAG** | **FLAG** | **FLAG** | - |
| P8-128K-b4096-1d653124-r0-a1 | 333 | 333 | 105 | **FLAG** | **FLAG** | **FLAG** | - |
| P8-128K-b4096-1d653124-r1-a1 | 0 | 0 | 24 | **FLAG** | - | - | - |
| P9-128K-b2048-b27da9b0-r0-a1 | 0 | 0 | 74 | - | - | - | - |
| P9-128K-b2048-b27da9b0-r1-a1 | 0 | 0 | 0 | - | - | - | - |
| P9-128K-b4096-0ae6029e-r0-a1 | 173 | 173 | 23 | **FLAG** | **FLAG** | **FLAG** | - |
| P9-128K-b4096-0ae6029e-r1-a1 | 652 | 652 | 42 | **FLAG** | **FLAG** | **FLAG** | - |
| canary-end-debea778-r103-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-end-debea778-r104-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-end-debea778-r105-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-end-debea778-r113-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-end-debea778-r114-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-end-debea778-r115-a1 | 191 | 191 | 5 | **FLAG** | **FLAG** | **FLAG** | - |
| canary-rerun-start-debea778-r110-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-start-debea778-r111-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-rerun-start-debea778-r112-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-start-debea778-r100-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-start-debea778-r101-a1 | 0 | 0 | 0 | - | - | - | - |
| canary-start-debea778-r102-a1 | 0 | 0 | 0 | - | - | - | - |
| stock-128K-139ecd8b-r0-a1 | 823 | 823 | 25 | **FLAG** | **FLAG** | **FLAG** | - |
| stock-128K-139ecd8b-r1-a1 | 2,297 | 2,297 | 5,861 | **FLAG** | **FLAG** | **FLAG** | paging |
| stock-128K-139ecd8b-r1-a2 | 2,366 | 2,366 | 327 | **FLAG** | **FLAG** | **FLAG** | - |
| **windows flagged (of 64)** | | | | **27** | **23** | **23** | |

R0 reproduces the paging flag the runner recorded on 51 of 64 windows (check of this script against the recorded data).

## Which requests the activity belongs to: `P1-128K-b2048-719d8935-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.2 | 6.0 | 0 | 130 | 0 | 0 | 0 | 0 | 1,777.1 | 2,121.7 |
| 1 | A 64K | 5.8 | 36.7 | 96 | 1,222 | 164 | 0 | 0 | 164 | 1,788.0 | 1,786.1 |
| 2 | B 64K | 42.5 | 9.6 | 14 | 419 | 703 | 0 | 0 | 866 | 57.0 | 57.4 |
| 3 | A 32K | 52.0 | 17.6 | 181 | 46,777 | 2,748 | 0 | 0 | 3,611 | 1,966.7 | 1,962.9 |
| 4 | B 32K | 69.7 | 8.0 | 902 | 6,672 | -4 | 0 | 0 | 3,606 | 67.6 | 67.6 |
| 5 | A 96K | 77.7 | 61.0 | 2,512 | 103,380 | -6 | 0 | 0 | 3,604 | 1,620.5 | 1,621.8 |
| 6 | B 96K | 138.7 | 11.1 | 1,156 | 1,317 | -1 | 0 | 0 | - | 49.6 | 49.8 |

## Which requests the activity belongs to: `P2-128K-b2048-30d55af4-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.4 | 5.7 | 0 | 50 | 0 | 0 | 0 | 3 | 2,244.2 | 2,248.2 |
| 1 | A 96K | 5.3 | 58.2 | 0 | 1,428 | 0 | 0 | 0 | 3 | 1,690.5 | 1,696.7 |
| 2 | B 96K | 63.5 | 10.8 | 0 | 535 | 0 | 0 | 42 | 45 | 50.6 | 50.5 |
| 3 | A 64K | 74.3 | 37.3 | 1,348 | 31,824 | 3,303 | 0 | 0 | 3,342 | 1,872.8 | 1,869.8 |
| 4 | B 64K | 111.6 | 9.3 | 2,269 | 2,183 | -9 | 0 | 0 | 3,339 | 58.3 | 58.4 |
| 5 | A 32K | 120.9 | 15.9 | 2 | 1,596 | 0 | 0 | 0 | 3,339 | 2,078.4 | 2,070.7 |
| 6 | B 32K | 136.8 | 7.7 | 194 | 1,235 | -1 | 0 | 0 | - | 69.0 | 68.8 |

## Which requests the activity belongs to: `P2-128K-b4096-f989bd0a-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.4 | 6.1 | 0 | 160 | 70 | 0 | 0 | 431 | 1,995.4 | 2,076.9 |
| 1 | A 96K | 5.7 | 52.0 | 5 | 21,399 | 843 | 0 | 0 | 1,411 | 1,892.3 | 1,893.9 |
| 2 | B 96K | 57.7 | 10.5 | 37 | 2,313 | 222 | 0 | 0 | 1,859 | 49.5 | 49.3 |
| 3 | A 32K | 68.1 | 14.8 | 8,059 | 8,060 | 1,966 | 0 | 0 | 3,433 | 2,482.7 | 2,575.7 |
| 4 | B 32K | 82.9 | 7.5 | 359 | 316 | 0 | 0 | 0 | 3,433 | 66.6 | 66.3 |
| 5 | A 64K | 90.5 | 29.9 | 363 | 9,565 | 1,638 | 0 | 0 | 5,070 | 2,200.8 | 2,215.4 |
| 6 | B 64K | 120.3 | 9.0 | 518 | 5,192 | -1 | 0 | 0 | - | 56.6 | 56.4 |

## Which requests the activity belongs to: `P3-128K-b2048-ec9defe0-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.4 | 7.8 | 0 | 23 | 0 | 0 | 0 | 0 | 1,674.4 | 1,985.9 |
| 1 | A 64K | 7.4 | 38.1 | 0 | 24,264 | 0 | 0 | 0 | 0 | 1,721.1 | 1,714.5 |
| 2 | B 64K | 45.5 | 11.2 | 0 | 454 | 0 | 0 | 0 | 0 | 46.6 | 46.1 |
| 3 | A 96K | 56.8 | 63.5 | 531 | 80,202 | 5,399 | 0 | 0 | 5,380 | 1,573.1 | 1,569.3 |
| 4 | B 96K | 120.2 | 12.8 | 7,114 | 103,328 | -28 | 0 | 0 | 5,371 | 41.4 | 41.0 |
| 5 | A 32K | 133.0 | 17.6 | 414 | 3,554 | -2 | 0 | 0 | 5,369 | 1,890.4 | 1,894.4 |
| 6 | B 32K | 150.6 | 9.6 | 12 | 516 | 0 | 0 | 0 | - | 53.9 | 52.6 |

## Which requests the activity belongs to: `P3-128K-b4096-95a0b1dd-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.0 | 8.2 | 0 | 224 | 0 | 0 | 0 | 0 | 1,833.1 | 1,848.0 |
| 1 | A 64K | 8.2 | 31.4 | 0 | 685 | 0 | 0 | 0 | 84 | 2,090.3 | 2,104.2 |
| 2 | B 64K | 39.6 | 11.2 | 0 | 904 | 328 | 0 | 0 | 656 | 44.0 | 43.6 |
| 3 | A 32K | 50.8 | 16.7 | 17,930 | 44,684 | 3,703 | 0 | 0 | 4,031 | 2,326.6 | 2,432.1 |
| 4 | B 32K | 67.4 | 9.9 | 3,852 | 18,247 | -3 | 0 | 0 | 4,027 | 48.7 | 49.8 |
| 5 | A 96K | 77.3 | 54.5 | 728 | 35,042 | -3 | 0 | 0 | 4,024 | 1,806.5 | 1,801.0 |
| 6 | B 96K | 131.9 | 12.7 | 1,632 | 6,932 | -1 | 0 | 0 | - | 39.3 | 39.0 |

## Which requests the activity belongs to: `P4-128K-b2048-058d1758-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.4 | 6.2 | 48 | 1,317 | 0 | 0 | 0 | 8 | 1,918.9 | - |
| 1 | A 96K | 5.9 | 63.3 | 0 | 1,569 | 0 | 0 | 0 | 8 | 1,553.6 | - |
| 2 | B 96K | 69.2 | 11.8 | 1 | 352 | 0 | 0 | 0 | 8 | 45.8 | - |
| 3 | A 32K | 81.0 | 18.0 | 0 | 393 | 0 | 0 | 0 | 8 | 1,843.7 | - |
| 4 | B 32K | 99.0 | 8.7 | 0 | 67 | 287 | 0 | 0 | 711 | 61.0 | - |
| 5 | A 64K | 107.7 | 39.4 | 1,175 | 54,745 | 3,885 | 0 | 0 | 4,180 | 1,688.8 | - |
| 6 | B 64K | 147.1 | 10.2 | 1,742 | 1,605 | 0 | 0 | 0 | - | 53.4 | - |

## Which requests the activity belongs to: `P4-128K-b4096-93b48048-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.4 | 7.1 | 5 | 2,570 | 232 | 0 | 0 | 336 | 1,817.5 | 1,828.4 |
| 1 | A 96K | 6.8 | 55.0 | 10 | 1,737 | 369 | 0 | 0 | 730 | 1,788.3 | 1,791.0 |
| 2 | B 96K | 61.8 | 11.8 | 358 | 2,740 | 2,105 | 0 | 0 | 2,720 | 43.2 | 43.8 |
| 3 | A 32K | 73.5 | 15.3 | 12,766 | 1,354 | 291 | 0 | 0 | 3,010 | 2,249.0 | 2,379.7 |
| 4 | B 32K | 88.8 | 8.8 | 5,302 | 947 | 0 | 0 | 0 | 3,009 | 56.1 | 57.2 |
| 5 | A 64K | 97.7 | 31.6 | 458 | 7,092 | -2 | 0 | 0 | 3,008 | 2,079.8 | 2,078.2 |
| 6 | B 64K | 129.3 | 10.1 | 487 | 444 | -1 | 0 | 0 | - | 50.0 | 50.4 |

## Which requests the activity belongs to: `P5-128K-b2048-45dd3f62-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.1 | 5.5 | 0 | 143 | 0 | 0 | 0 | 0 | 1,872.5 | 1,868.6 |
| 1 | A 64K | 5.4 | 40.6 | 0 | 1,613 | 250 | 0 | 0 | 250 | 1,614.5 | 1,621.7 |
| 2 | B 64K | 46.1 | 9.7 | 42 | 256 | 128 | 0 | 0 | 571 | 57.6 | 58.5 |
| 3 | A 96K | 55.8 | 66.9 | 4,461 | 39,903 | 3,397 | 0 | 0 | 3,763 | 1,480.3 | 1,487.0 |
| 4 | B 96K | 122.6 | 12.4 | 63,361 | 8,122 | -17 | 0 | 0 | 3,758 | 44.2 | 49.8 |
| 5 | A 32K | 135.0 | 19.0 | 2,470 | 31,972 | 0 | 0 | 0 | 3,758 | 1,749.2 | 1,752.6 |
| 6 | B 32K | 154.0 | 8.3 | 9,171 | 329 | 0 | 0 | 0 | - | 66.4 | 68.9 |

## Which requests the activity belongs to: `P5-128K-b4096-f68f2a79-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.0 | 5.7 | 0 | 110 | 120 | 0 | 0 | 120 | 1,750.0 | 1,743.7 |
| 1 | A 64K | 5.7 | 32.4 | 6 | 2,425 | 88 | 0 | 0 | 347 | 2,024.3 | 2,010.9 |
| 2 | B 64K | 38.1 | 9.4 | 70 | 349 | 139 | 0 | 0 | 857 | 54.7 | 54.3 |
| 3 | A 96K | 47.6 | 58.0 | 160 | 54,658 | 2,803 | 0 | 0 | 3,150 | 1,745.8 | 1,742.9 |
| 4 | B 96K | 105.6 | 10.9 | 5,120 | 3,978 | -2 | 0 | 0 | 3,147 | 47.8 | 48.8 |
| 5 | A 32K | 116.5 | 14.4 | 1,409 | 547 | 0 | 0 | 0 | 3,147 | 2,320.2 | 2,294.2 |
| 6 | B 32K | 130.9 | 8.2 | 1,318 | 387 | 0 | 0 | 0 | - | 62.0 | 59.7 |

## Which requests the activity belongs to: `P6-128K-b2048-9bc32784-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.2 | 5.3 | 0 | 278 | 0 | 0 | 0 | 0 | 1,704.6 | 1,764.8 |
| 1 | A 32K | 5.1 | 19.8 | 0 | 413 | 0 | 0 | 0 | 0 | 1,656.4 | 1,653.8 |
| 2 | B 32K | 24.9 | 7.8 | 0 | 133 | 0 | 0 | 0 | 0 | 74.1 | 73.7 |
| 3 | A 64K | 32.7 | 43.4 | 0 | 2,614 | 0 | 0 | 0 | 0 | 1,513.7 | 1,521.8 |
| 4 | B 64K | 76.1 | 9.3 | 0 | 156 | 46 | 0 | 0 | 46 | 62.1 | 64.4 |
| 5 | A 96K | 85.4 | 71.1 | 686 | 19,392 | 4,517 | 0 | 0 | 4,563 | 1,400.7 | 1,404.2 |
| 6 | B 96K | 156.5 | 11.2 | 391 | 891 | -1 | 0 | 0 | - | 51.1 | 54.4 |

## Which requests the activity belongs to: `P6-128K-b4096-b801464e-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.1 | 6.0 | 114 | 5,002 | 1,605 | 0 | 0 | 1,605 | 1,581.5 | 1,637.2 |
| 1 | A 64K | 6.0 | 33.9 | 705 | 9,472 | 124 | 0 | 0 | 1,729 | 1,935.1 | 1,925.2 |
| 2 | B 64K | 39.9 | 9.2 | 34 | 878 | 1,422 | 0 | 0 | 3,589 | 58.1 | 58.5 |
| 3 | A 32K | 49.1 | 16.4 | 13,839 | 14,065 | 1,409 | 0 | 0 | 4,560 | 2,121.3 | 2,192.6 |
| 4 | B 32K | 65.5 | 7.7 | 11,304 | 4,889 | -2 | 0 | 0 | 4,557 | 68.4 | 72.3 |
| 5 | A 96K | 73.2 | 58.6 | 1,917 | 33,759 | -2 | 0 | 0 | 4,556 | 1,679.8 | 1,672.8 |
| 6 | B 96K | 131.9 | 10.8 | 9,277 | 2,324 | -2 | 0 | 0 | - | 50.3 | 51.6 |

## Which requests the activity belongs to: `P7-128K-b2048-b1c77f83-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.4 | 5.8 | 6 | 178 | 172 | 0 | 0 | 376 | 1,515.3 | 1,529.7 |
| 1 | A 32K | 5.4 | 22.1 | 26 | 12,755 | 85 | 0 | 0 | 462 | 1,485.5 | 1,454.4 |
| 2 | B 32K | 27.5 | 8.9 | 6 | 960 | 151 | 0 | 0 | 613 | 64.7 | 64.3 |
| 3 | A 96K | 36.4 | 77.1 | 5,036 | 48,974 | 4,345 | 0 | 0 | 4,958 | 1,280.0 | 1,258.1 |
| 4 | B 96K | 113.5 | 12.2 | 7,119 | 4,382 | -6 | 0 | 0 | 4,952 | 46.5 | 47.6 |
| 5 | A 64K | 125.7 | 48.5 | 8,859 | 15,467 | 0 | 0 | 0 | 4,952 | 1,363.4 | 1,348.0 |
| 6 | B 64K | 174.2 | 11.1 | 23,009 | 736 | 0 | 0 | 0 | - | 50.5 | 55.6 |

## Which requests the activity belongs to: `P7-128K-b4096-af2a855d-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.5 | 6.5 | 0 | 81 | 0 | 0 | 0 | 20 | 1,430.6 | 1,440.6 |
| 1 | A 96K | 6.0 | 62.5 | 0 | 946 | 0 | 0 | 0 | 20 | 1,573.3 | 1,573.6 |
| 2 | B 96K | 68.5 | 11.7 | 0 | 191 | 0 | 0 | 0 | 299 | 45.6 | 45.7 |
| 3 | A 32K | 80.2 | 19.4 | 14,602 | 35,305 | 5,197 | 0 | 0 | 5,217 | 1,919.4 | 2,026.2 |
| 4 | B 32K | 99.6 | 9.1 | 23,747 | 21,390 | -3 | 0 | 0 | 5,214 | 57.2 | 62.5 |
| 5 | A 64K | 108.7 | 37.2 | 8,276 | 45,082 | 174 | 0 | 0 | 5,387 | 1,764.8 | 1,775.1 |
| 6 | B 64K | 145.9 | 10.9 | 34,437 | 2,159 | -2 | 0 | 0 | - | 47.7 | 51.6 |

## Which requests the activity belongs to: `stock-128K-139ecd8b-r1-a1`

Each interval between two samples is given to the request that was running at its midpoint, otherwise to the gap after the previous request. Counter changes; VmSwap in MiB (signed).

| pos | request | start (s) | duration (s) | faults during | pswpin during | VmSwap change during | faults in gap after | VmSwap change in gap | VmSwap at end | speed (PP for A and short, TG for B) | same request, window without R0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | short 2K | -0.3 | 9.7 | 1,556 | 4,198 | 2,262 | 0 | 0 | 3,281 | 761.2 | - |
| 1 | A 64K | 9.4 | 93.5 | 559 | 75,899 | -3 | 0 | 0 | 3,278 | 701.5 | - |
| 2 | B 64K | 102.8 | 11.2 | 21 | 64 | 0 | 0 | 0 | 3,315 | 62.0 | - |
| 3 | A 96K | 114.1 | 145.4 | 2,603 | 9,389 | 31 | 0 | 0 | 3,308 | 678.5 | - |
| 4 | B 96K | 259.5 | 12.2 | 206 | 263 | -1 | 0 | 0 | 553 | 56.7 | - |
| 5 | A 32K | 271.8 | 45.6 | 688 | 1,417 | -2,755 | 0 | 0 | 552 | 729.0 | - |
| 6 | B 32K | 317.4 | 10.2 | 228 | 367 | -1 | 0 | 0 | - | 69.6 | - |

## Speed next to paging (anecdotal)

Windows of one configuration, split by the R0 flag. Different server instances and times; 10 windows in all.

| config | cells | flagged / not | PP_fresh 16K flagged vs not | TG 16K flagged vs not |
|---|---|---|---|---|
| `30d55af4` | P2-128K-b2048 | 1 / 2 | - | - |
| `45dd3f62` | P5-128K-b2048 | 1 / 2 | - | - |
| `704dd2e5` | P8-128K-b2048 | 1 / 1 | - | - |
| `719d8935` | P1-128K-b2048 | 1 / 2 | - | - |
| `93b48048` | P4-128K-b4096 | 1 / 2 | - | - |
| `95a0b1dd` | P3-128K-b4096 | 1 / 2 | - | - |
| `9bc32784` | P6-128K-b2048 | 1 / 2 | - | - |
| `af2a855d` | P7-128K-b4096 | 2 / 1 | - | - |
| `b1c77f83` | P7-128K-b2048 | 2 / 1 | - | - |
| `b801464e` | P6-128K-b4096 | 1 / 2 | - | - |
| `debea778` | canary-end, canary-rerun-end, canary-rerun-start, canary-start | 1 / 11 | 960.2 vs 960.3 (-0.0%) | 77.9 vs 78.5 (-0.8%) |
| `ec9defe0` | P3-128K-b2048 | 1 / 2 | - | - |
| `f68f2a79` | P5-128K-b4096 | 1 / 2 | - | - |
| `f989bd0a` | P2-128K-b4096 | 2 / 1 | - | - |

## What the data cannot show

- Ten windows from one session on one machine: no causal claim is possible, and every speed comparison below is anecdotal.
- This run has `VmSwap` and `VmRSS` but not `RssAnon`, `RssFile` or `RssShmem`, so it cannot show what sits in the swapped pages (anonymous heap, shared memory, or something else).
- Telemetry starts at the first warm-up request: the model load and the prefetch are not sampled. The 'server start' rows hold the first sample plus the snapshot's system counters.
- `pswpin` is system-wide (other processes swap too) and `pswpout` is not in this run's CSVs; the per-process view is `VmSwap` and the major faults of llama-server only.
- Sampling is 2 Hz: a swap burst shorter than half a second between two samples is seen only through the next sample's value.
- Windows of different server instances differ in everything the OS decided at that moment (page cache, what was swapped before), so a within-cell comparison also compares instances.

