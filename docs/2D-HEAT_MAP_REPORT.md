# Two-Way Policy Sweep: Heat Map Results

**Data:** `examples/2d_heatmap_figures/results.csv` (75 rows: 3 policies × 25 cells, 10
replications each), produced by `examples/2d_heatmap_sweep.py` at commit `0cab8fb`
(run log: `examples/2d_heatmap_figures/run.log`). Repairs follow the paper's model:
`prob_auto_to_manual` is the probability that auto repair escalates, independent of the
silent auto-repair failure `auto_repair_fail_prob`. Date: 2026-09-21.

> **Design caveat (2026-09-21).** In AIReSim the scheduling policy is consulted
> only at full host selection. Warm-standby swaps take the oldest standby
> (`Scheduler.swap_in_standby`) without consulting the policy, and repaired
> servers that were in the job return to the standby list regardless of failure
> history. The `FewestFailuresFirst`/`HighestScoreFirst` results below therefore
> measure the policy's effect at the host selections that happen when the job
> exhausts its warm standbys. They do not measure health-aware replacement as an
> operator would implement it. The number of full host selections per run was not
> recorded for this sweep. At the paper defaults it is about 16 per run against
> ~11,000 failures (`DIAGNOSIS_REALISTIC_REPORT.md`). `FewestFailuresFirst` here
> also reads ground-truth failure counts (see `DIAGNOSIS_REALISTIC_REPORT.md` for
> the attributed-count variant).

## Overview

This report summarises a two-dimensional parameter sweep comparing three scheduling/retirement
policy combinations across 25 cells (5 × 5) with 10 independent replications per cell.
The two swept axes capture the two most influential drivers of bad-server harm:

| Axis | Values |
|------|--------|
| `systematic_failure_rate_multiplier` | 5×, 10×, 15×, 20×, 25× |
| `manual_repair_fail_prob` | 20%, 40%, 60%, 75%, 90% |

All other parameters are held at the **payoff regime baseline**:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `working_pool_size` | 4 600 | 488 idle servers above the 4 112 minimum — enough headroom to absorb retirements |
| `spare_pool_size` | 200 | standard preemptible buffer |
| `job_size` | 4 096 | large-scale training job |
| `warm_standbys` | 16 | hot spares allocated to the job |
| `job_length` | 14 days | compute time with no failures |
| `random_failure_rate` | 2× default | elevated ambient failure rate |
| `systematic_failure_fraction` | 8% | ≈ 368 bad servers out of 4 600 |
| `recovery_time` | 60 min | expensive checkpoint reload per failure |
| `prob_auto_to_manual` | 0.80 | 80% of auto-repair attempts escalate to manual repair |
| `auto_repair_fail_prob` | 0.60 | 60% of repairs left to auto repair silently fail |

10 replications per cell × 3 policies × 25 cells = **750 simulations total**. A typical
cell mean has a standard error of about 12 h (stdevs 26–62 h). Cells marked † below have
a difference from the baseline of less than two standard errors.

---

## Policies Compared

### 1. Random + NeverRemove (Baseline)
Uniform random host selection; every repaired server is returned to the working pool.
This is the naive default: no preference for healthy servers, no retirement.

Baseline mean training time (h):

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | 1760 h | 1784 h | 1833 h | 1849 h | 1883 h |
| **10×** | 1886 h | 1938 h | 2007 h | 2098 h | 2198 h |
| **15×** | 1921 h | 2028 h | 2138 h | 2276 h | 2400 h |
| **20×** | 1937 h | 2060 h | 2220 h | 2389 h | 2605 h |
| **25×** | 1956 h | 2082 h | 2278 h | 2481 h | 2807 h |

### 2. Random + ScoredRemoval — SC_fast (Challenger A)
Uniform random host selection, but uses a score-based retirement policy tuned for fast culling:

| SC_fast parameter | Value |
|-------------------|-------|
| `initial_score` | 100 |
| `failure_penalty` | 60 |
| `success_increment` | 5 per day of clean uptime |
| `retirement_threshold` | 0 |

A server is retired after **just 2 failures** (score path: 100 → 40 → −20 ≤ 0).
Recovery is slow (5 pts/day) so a retired bad server is rarely reinstated.

### 3. FewestFailuresFirst + NeverRemove (Challenger B)
Prefers hosts with fewer historical failures when selecting replacements.
No retirement — every repaired server returns to the pool.
This is a zero-capacity-cost policy: it routes work away from bad servers
without permanently shrinking the cluster.

---

## Overall Win Counts

| Policy | Cells with lowest mean (out of 25) | Share |
|--------|-----------------------|-------|
| Random + NeverRemove (baseline) | 0 | 0% |
| Random + ScoredRemoval (SC_fast) | 12 | 48% |
| FewestFailuresFirst + NeverRemove | 13 | 52% |

**The baseline wins no cell**, and the two challengers split the grid almost evenly.
The win counts overstate the difference between the challengers: only 7 of the 25
`SC_fast` vs FFF differences exceed two standard errors (see the head-to-head grid).

---

## ScoredRemoval (SC_fast) — Delta vs Baseline

> **Negative = faster than baseline.**
> **Best improvement: −671 h (−23.9%)** (mult=25×, repair_fail=90%)
> **Worst regression: +17 h** (mult=5×, repair_fail=40%, within noise)

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | -14 h † | +17 h † | -22 h † | -31 h † | -25 h † |
| **10×** | -15 h † | -16 h † | -65 h | -107 h | -186 h |
| **15×** | -10 h † | -73 h | -117 h | -246 h | -306 h |
| **20×** | -34 h | -73 h | -188 h | -309 h | -489 h |
| **25×** | -17 h † | -82 h | -211 h | -379 h | -671 h |

### Interpretation

- **Bottom-right corner (high multiplier + high repair_fail_prob)**: SC_fast excels.
  Bad servers fail rapidly and repairs rarely fix them, so retiring after 2 failures
  breaks the failure→repair→failure cycle. The improvement grows steadily along both
  axes, from roughly 10–35 h at repair_fail=20% to 300–670 h at 90% for multipliers
  ≥15×. The capacity cost is low because the pool has 488 idle servers.

- **Top-left (low multiplier + low repair_fail_prob)**: the gain is small
  (−14 to −34 h at repair_fail=20%) and mostly inside the noise, and the only
  positive delta in the grid (+17 h at 5×/40%) is not distinguishable from zero.
  Here bad servers are only moderately worse than good ones and repairs usually fix
  them, so there is little for retirement to remove.

---

## FewestFailuresFirst + NeverRemove — Delta vs Baseline

> **Negative = faster than baseline.**
> **Best improvement: −536 h (−19.1%)** (mult=25×, repair_fail=90%)
> **No cell is slower than the baseline.**

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | -9 h † | -34 h † | -58 h | -41 h | -64 h |
| **10×** | -32 h | -63 h | -94 h | -133 h | -199 h |
| **15×** | -33 h | -80 h | -120 h | -224 h | -279 h |
| **20×** | -9 h † | -73 h | -163 h | -266 h | -396 h |
| **25×** | -35 h † | -71 h | -184 h | -290 h | -536 h |

### Interpretation

- **FFF is faster than the baseline in all 25 cells** (by more than two standard errors
  in 21 of them), with gains that grow with severity in the same way as SC_fast's.
  Because FFF never retires servers it cannot eliminate chronic offenders — it merely
  routes work away from them at host selection — so its ceiling is lower than SC_fast's
  in the most severe corner.

- **FFF has no capacity cost.** It cannot overshoot by retiring servers that repairs
  would have fixed, which is why it stays at or near SC_fast's level at low and moderate
  severity.

---

## Head-to-Head: Where Each Policy Wins

Winner at each cell by lowest mean training time; `*` marks cells where the
`SC_fast` − FFF difference exceeds two standard errors (`SC_fast` significantly faster in
4 cells, FFF in 3, indistinguishable in 18):

```
             repair_fail_prob →
               20%     40%     60%     75%     90%
mult  5×  [ SC    | FFF*  | FFF*  | FFF   | FFF   ]
     10×  [ FFF   | FFF*  | FFF   | FFF   | FFF   ]
     15×  [ FFF   | FFF   | FFF   | SC    | SC    ]
     20×  [ SC    | SC    | SC    | SC*   | SC*   ]
     25×  [ FFF   | SC    | SC    | SC*   | SC*   ]
```

**Three observations:**

| Regime | Condition | Best Policy |
|--------|-----------|-------------|
| **`SC_fast` clearly ahead** | Multiplier ≥ 20× *and* repair_fail ≥ 75% (4 cells, 42–135 h ahead) | Random + ScoredRemoval |
| **FFF clearly ahead** | Three cells at multiplier 5–10× with repair_fail 40–60% (36–51 h ahead) | FewestFailuresFirst |
| **No distinguishable difference** | Everywhere else (18 of 25 cells) | Either; prefer FFF (no retirements) |

The baseline is never the best choice.

---

## Key Takeaways

1. **Both policies beat doing nothing almost everywhere, and the benefit scales with
   severity.** The improvement over the baseline grows from a few tens of hours at
   the mildest settings to 671 h (`SC_fast`, −23.9%) and 536 h (FFF, −19.1%) at 25×/90%.
   `SC_fast` is faster than the baseline in 24 of 25 cells and FFF in all 25.

2. **Aggressive retirement pays most when bad servers are both prolific and
   persistent.** `SC_fast`'s "retire after 2 failures" rule pulls clearly ahead of FFF
   only at multiplier ≥ 20× with repair_fail ≥ 75%, where bad servers would otherwise
   oscillate between the job and the repair shop.

3. **FewestFailuresFirst is a safe, zero-cost default.** It is never slower than the
   baseline, never risks depleting the pool, and matches `SC_fast` within noise in
   18 of 25 cells. It is significantly better than `SC_fast` at low-to-moderate
   multipliers with intermediate repair quality (5–10×, 40–60%).

4. **The choice between them depends on the regime.** If failure severity and repair
   quality are unknown, FFF is the lower-risk default; if they are known to be at the
   high end (≥ 20×, ≥ 75%), `SC_fast` should be preferred.

5. **These results are specific to how AIReSim applies the scheduling policy** (see
   the design caveat at the top): FFF acts only at full host selection and reads
   ground-truth failure counts.

---

## Figures

| Figure | Description |
|--------|-------------|
| [`heatmap_scored_delta.png`](../examples/2d_heatmap_figures/heatmap_scored_delta.png) | Δ training time (hrs): SC_fast vs baseline. Green = improvement, red = regression. |
| [`heatmap_fff_delta.png`](../examples/2d_heatmap_figures/heatmap_fff_delta.png) | Δ training time (hrs): FewestFailuresFirst vs baseline. |
| [`heatmap_winner.png`](../examples/2d_heatmap_figures/heatmap_winner.png) | Categorical map: which policy wins each cell. Grey = baseline, coral = SC_fast, blue = FFF. |

*Generated by [`examples/2d_heatmap_sweep.py`](../examples/2d_heatmap_sweep.py) — 10 replications per cell, 750 total simulations, regenerated 2026-09-21.*
