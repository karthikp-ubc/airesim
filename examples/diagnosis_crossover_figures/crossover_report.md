# Diagnosis crossover: retirement vs failure-aware scheduling

Commit `9e642d0bb3`, 30 paired replications (seeds 42–71) per cell. Δ = policy − reference, paired by seed; negative = policy faster. ± is the 95% CI.

## Multiplier 15×, manual repair fail 75%

| diagnosis | Random+NeverRemove | Random+ScoredRemoval(SC_fast) | Random+Thresh>=2/7d | FewestFailuresFirst+NeverRemove | FewestFailuresFirst+ScoredRemoval(SC_fast) | FAFF+ScoredRemoval(SC_fast) | retired (Random+Scored) |
|---|---|---|---|---|---|---|---|
| 0.5 | +170 ± 25 | +59 ± 25 | +113 ± 27 | -117 ± 31 | -209 ± 26 | -102 ± 28 | 192 |
| 0.6 | +217 ± 20 | +67 ± 24 | +158 ± 24 | -82 ± 30 | -150 ± 23 | -55 ± 22 | 230 |
| 0.7 | +206 ± 23 | +44 ± 21 | +157 ± 22 | -46 ± 28 | -127 ± 24 | -32 ± 27 | 274 |
| 0.8 | +225 ± 24 | +33 ± 20 | +162 ± 20 | -43 ± 23 | -80 ± 18 | -37 ± 20 | 310 |
| 0.85 | +210 ± 24 | +9 ± 21 | +143 ± 22 | -42 ± 22 | -84 ± 22 | -26 ± 18 | 326 |
| 0.9 | +208 ± 22 | +5 ± 17 | +148 ± 19 | -16 ± 16 | -67 ± 20 | -48 ± 20 | 342 |
| 0.95 | +190 ± 23 | -25 ± 27 | +125 ± 26 | -15 ± 21 | -66 ± 25 | -46 ± 21 | 359 |
| 1 | +203 ± 28 | -40 ± 23 | +153 ± 22 | +0 ± 0 | -39 ± 24 | -39 ± 24 | 372 |

Reference: FAFF+NeverRemove (FewestAttributedFailuresFirst, which sees only diagnosed failures, like the removal policies).

## Multiplier 20×, manual repair fail 75%

| diagnosis | Random+NeverRemove | Random+ScoredRemoval(SC_fast) | Random+Thresh>=2/7d | FewestFailuresFirst+NeverRemove | FewestFailuresFirst+ScoredRemoval(SC_fast) | FAFF+ScoredRemoval(SC_fast) | retired (Random+Scored) |
|---|---|---|---|---|---|---|---|
| 0.5 | +258 ± 37 | +56 ± 31 | +179 ± 31 | -126 ± 39 | -260 ± 28 | -110 ± 31 | 231 |
| 0.6 | +309 ± 31 | +57 ± 27 | +208 ± 30 | -87 ± 25 | -197 ± 25 | -53 ± 25 | 269 |
| 0.7 | +301 ± 28 | +22 ± 24 | +209 ± 29 | -60 ± 24 | -154 ± 26 | -50 ± 23 | 307 |
| 0.8 | +275 ± 30 | +9 ± 22 | +204 ± 28 | -45 ± 27 | -114 ± 21 | -37 ± 20 | 337 |
| 0.85 | +268 ± 26 | -34 ± 16 | +171 ± 19 | -48 ± 23 | -116 ± 19 | -64 ± 23 | 348 |
| 0.9 | +257 ± 26 | -56 ± 24 | +148 ± 24 | -31 ± 30 | -106 ± 22 | -87 ± 19 | 363 |
| 0.95 | +276 ± 25 | -59 ± 18 | +179 ± 21 | -10 ± 21 | -92 ± 18 | -64 ± 19 | 379 |
| 1 | +264 ± 23 | -60 ± 20 | +177 ± 20 | +0 ± 0 | -71 ± 17 | -71 ± 17 | 391 |

Reference: FAFF+NeverRemove (FewestAttributedFailuresFirst, which sees only diagnosed failures, like the removal policies).

## Multiplier 25×, manual repair fail 90%

| diagnosis | Random+NeverRemove | Random+ScoredRemoval(SC_fast) | Random+Thresh>=2/7d | FewestFailuresFirst+NeverRemove | FewestFailuresFirst+ScoredRemoval(SC_fast) | FAFF+ScoredRemoval(SC_fast) | retired (Random+Scored) |
|---|---|---|---|---|---|---|---|
| 0.5 | +569 ± 44 | +78 ± 36 | +335 ± 42 | -138 ± 42 | -362 ± 37 | -138 ± 41 | 291 |
| 0.6 | +585 ± 41 | -4 ± 45 | +316 ± 45 | -73 ± 55 | -316 ± 42 | -102 ± 42 | 330 |
| 0.7 | +556 ± 42 | -62 ± 39 | +295 ± 47 | -104 ± 50 | -282 ± 40 | -128 ± 41 | 359 |
| 0.8 | +553 ± 32 | -104 ± 22 | +293 ± 24 | -48 ± 30 | -227 ± 22 | -123 ± 27 | 383 |
| 0.85 | +533 ± 24 | -89 ± 30 | +303 ± 25 | -23 ± 32 | -210 ± 24 | -120 ± 21 | 401 |
| 0.9 | +563 ± 31 | -114 ± 24 | +287 ± 28 | -27 ± 28 | -181 ± 21 | -120 ± 22 | 411 |
| 0.95 | +548 ± 30 | -119 ± 19 | +283 ± 26 | -9 ± 27 | -156 ± 18 | -128 ± 20 | 426 |
| 1 | +532 ± 25 | -133 ± 20 | +279 ± 24 | +0 ± 0 | -148 ± 17 | -148 ± 17 | 441 |

Reference: FAFF+NeverRemove (FewestAttributedFailuresFirst, which sees only diagnosed failures, like the removal policies).

## Crossovers

`crossover` is where the mean contrast changes sign scanning down from 1.0 (linear interpolation); `clearly better from` is the lowest diagnosis value from which every point up to 1.0 has its CI below zero; `clearly worse up to` is the highest value up to which every point has its CI above zero.

| regime | policy | vs | crossover | clearly better from | clearly worse up to |
|---|---|---|---|---|---|
| 15×, 75% | Random+ScoredRemoval(SC_fast) | FAFF+NeverRemove | 0.91 | 1.00 | 0.80 |
| 15×, 75% | Random+Thresh>=2/7d | FAFF+NeverRemove | — | — | 1.00 |
| 15×, 75% | FAFF+ScoredRemoval(SC_fast) | FAFF+NeverRemove | — | 0.50 | — |
| 15×, 75% | Random+ScoredRemoval(SC_fast) | FewestFailuresFirst+NeverRemove | 0.93 | 1.00 | 0.90 |
| 15×, 75% | FewestFailuresFirst+ScoredRemoval(SC_fast) | FewestFailuresFirst+NeverRemove | — | 0.50 | — |
| 15×, 75% | FewestFailuresFirst+NeverRemove | FAFF+NeverRemove | — | — | — |
| 15×, 75% | Random+ScoredRemoval(SC_fast) | Random+NeverRemove | — | 0.50 | — |
| 15×, 75% | FAFF+NeverRemove | Random+NeverRemove | — | 0.50 | — |
| 20×, 75% | Random+ScoredRemoval(SC_fast) | FAFF+NeverRemove | 0.81 | 0.85 | 0.60 |
| 20×, 75% | Random+Thresh>=2/7d | FAFF+NeverRemove | — | — | 1.00 |
| 20×, 75% | FAFF+ScoredRemoval(SC_fast) | FAFF+NeverRemove | — | 0.50 | — |
| 20×, 75% | Random+ScoredRemoval(SC_fast) | FewestFailuresFirst+NeverRemove | 0.87 | 0.90 | 0.80 |
| 20×, 75% | FewestFailuresFirst+ScoredRemoval(SC_fast) | FewestFailuresFirst+NeverRemove | — | 0.50 | — |
| 20×, 75% | FewestFailuresFirst+NeverRemove | FAFF+NeverRemove | — | — | — |
| 20×, 75% | Random+ScoredRemoval(SC_fast) | Random+NeverRemove | — | 0.50 | — |
| 20×, 75% | FAFF+NeverRemove | Random+NeverRemove | — | 0.50 | — |
| 25×, 90% | Random+ScoredRemoval(SC_fast) | FAFF+NeverRemove | 0.59 | 0.70 | 0.50 |
| 25×, 90% | Random+Thresh>=2/7d | FAFF+NeverRemove | — | — | 1.00 |
| 25×, 90% | FAFF+ScoredRemoval(SC_fast) | FAFF+NeverRemove | — | 0.50 | — |
| 25×, 90% | Random+ScoredRemoval(SC_fast) | FewestFailuresFirst+NeverRemove | 0.74 | 0.80 | 0.70 |
| 25×, 90% | FewestFailuresFirst+ScoredRemoval(SC_fast) | FewestFailuresFirst+NeverRemove | — | 0.50 | — |
| 25×, 90% | FewestFailuresFirst+NeverRemove | FAFF+NeverRemove | — | — | — |
| 25×, 90% | Random+ScoredRemoval(SC_fast) | Random+NeverRemove | — | 0.50 | — |
| 25×, 90% | FAFF+NeverRemove | Random+NeverRemove | — | 0.50 | — |
