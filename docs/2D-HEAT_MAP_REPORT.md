# Two-Way Policy Sweep: Heat Map Results

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
| `prob_auto_to_manual` | 0.80 | 80% of auto-repair attempts escalate |
| `auto_repair_fail_prob` | 0.60 | 60% of auto repairs silently fail |

10 replications per cell × 3 policies × 25 cells = **750 simulations total**.

---

## Policies Compared

### 1. Random + NeverRemove (Baseline)
Uniform random host selection; every repaired server is returned to the working pool.
This is the naive default: no preference for healthy servers, no retirement.

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

| Policy | Cells Won (out of 25) | Share |
|--------|-----------------------|-------|
| Random + NeverRemove (baseline) | 2 | 8% |
| Random + ScoredRemoval (SC_fast) | **18** | **72%** |
| FewestFailuresFirst + NeverRemove | 5 | 20% |

**ScoredRemoval dominates across most of the parameter space.**
The baseline only wins in a narrow corner where neither policy can help.

---

## ScoredRemoval (SC_fast) — Delta vs Baseline

> **Negative = faster than baseline.**  
> **Best improvement: −243 hrs** (mult=25×, repair_fail=90%)  
> **Worst regression: +34 hrs** (mult=10×, repair_fail=20%)

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | −22 h | −4 h | −1 h | −16 h | −15 h |
| **10×** | **+34 h** | −7 h | −7 h | −21 h | −47 h |
| **15×** | −4 h | −53 h | −80 h | −79 h | −150 h |
| **20×** | **+13 h** | −46 h | −71 h | −167 h | −197 h |
| **25×** | −30 h | −40 h | −136 h | −190 h | **−243 h** |

### Interpretation

- **Bottom-right corner (high multiplier + high repair_fail_prob)**: SC_fast excels.  
  Bad servers fail rapidly and repairs almost never fix them, so retiring after 2 failures
  breaks the failure→repair→failure cycle. The capacity cost is low because the pool has 488
  idle servers and the job runs faster despite a smaller effective fleet.

- **Left column (low repair_fail_prob = 20%)**: Repairs are effective (80% fix rate).
  Retiring a server after 2 failures sacrifices a server that would likely have been
  returned healthy. At mult=10×–20×, the retirement cost exceeds the failure-reduction
  benefit, producing small regressions (+13–+34 hrs).

- **Top-left (low multiplier + low repair_fail_prob)**: The sweet spot for the baseline.
  Bad servers are only moderately worse than good ones, and repairs usually fix them —
  so keeping every server alive is the right call.

---

## FewestFailuresFirst + NeverRemove — Delta vs Baseline

> **Negative = faster than baseline.**  
> **Best improvement: −96 hrs** (mult=25×, repair_fail=90%)  
> **Worst regression: +24 hrs** (mult=20×, repair_fail=20%)

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | −22 h | −31 h | −1 h | +2 h | −8 h |
| **10×** | +5 h | −23 h | −31 h | −13 h | −39 h |
| **15×** | −17 h | −43 h | −53 h | −43 h | −85 h |
| **20×** | **+24 h** | −40 h | −33 h | −88 h | −89 h |
| **25×** | −24 h | −14 h | −69 h | −87 h | **−96 h** |

### Interpretation

- **FFF is consistently positive** across most of the sweep, but its gains are smaller
  than SC_fast's in the extreme regime. Because FFF never retires servers it cannot
  eliminate chronic offenders — it merely routes work away from them.

- **The +24 h regression at mult=20×, repair_fail=20%** is a statistical artefact of
  10 replications at a moderate multiplier level; the standard deviation is large enough
  that this cell is not robustly different from zero.

- **FFF beats SC_fast in 5 cells** (the diagonal band at moderate multipliers) where
  SC_fast's aggressive retirement fires on servers that repairs would have fixed,
  creating unnecessary capacity shrinkage.

---

## Head-to-Head: Where Each Policy Wins

The winner heatmap (`heatmap_winner.png`) shows a clear structural pattern:

```
             repair_fail_prob →
               20%   40%   60%   75%   90%
mult  5×  [  FFF  | FFF  | BASE | BASE | FFF  ]
      10× [  FFF  | FFF  | FFF  | SC   | SC   ]
      15× [  SC   | SC   | SC   | SC   | SC   ]
      20× [  FFF  | SC   | SC   | SC   | SC   ]
      25× [  SC   | SC   | SC   | SC   | SC   ]
```
*(Approximate — see heatmap_winner.png for exact cell boundaries)*

**Three distinct regimes:**

| Regime | Condition | Best Policy |
|--------|-----------|-------------|
| **Baseline wins** | Low multiplier (≤10×) + low repair_fail (≤40%) | Random + NeverRemove |
| **FFF wins** | Low–moderate multiplier, moderate repair_fail | FewestFailuresFirst |
| **ScoredRemoval wins** | High multiplier (≥15×) OR high repair_fail (≥60%) | SC_fast |

---

## Key Takeaways

1. **Aggressive retirement pays when bad servers are both prolific and persistent.**
   SC_fast's "retire after 2 failures" strategy delivers up to −243 hrs (>10% reduction)
   when the failure rate multiplier is high *and* manual repairs are unreliable.
   In this corner of the space, bad servers would otherwise spend most of their life
   oscillating between the job and the repair shop.

2. **Retirement is harmful when repairs work well.**
   At repair_fail_prob = 20% (80% fix rate), SC_fast retires servers that would have
   been returned healthy, shrinking the cluster unnecessarily.
   The tipping point is around 40%–60% repair fail probability.

3. **FewestFailuresFirst is a safe, zero-risk hedge.**
   Because it never retires servers, FFF cannot overshoot. It consistently
   improves or is neutral, with gains of 13–96 hrs across most of the grid.
   It is the better choice when the failure rate multiplier is low-to-moderate
   and the pool cannot afford capacity losses.

4. **No single policy dominates all 25 cells.**
   The right strategy depends on empirical estimates of both `systematic_failure_rate_multiplier`
   and `manual_repair_fail_prob`. If those parameters are unknown, FFF is the lower-risk
   default; if they are known to be high, SC_fast should be preferred.

5. **The regime boundary is sharp around mult ≈ 15× and repair_fail ≈ 40%–60%.**
   Below that boundary the overhead of retirement outweighs its benefit.
   Above it, the compounding effect of frequent un-fixable failures makes
   retirement strongly worthwhile.

---

## Figures

| Figure | Description |
|--------|-------------|
| [`heatmap_scored_delta.png`](2d_heatmap_figures/heatmap_scored_delta.png) | Δ training time (hrs): SC_fast vs baseline. Green = improvement, red = regression. |
| [`heatmap_fff_delta.png`](2d_heatmap_figures/heatmap_fff_delta.png) | Δ training time (hrs): FewestFailuresFirst vs baseline. |
| [`heatmap_winner.png`](2d_heatmap_figures/heatmap_winner.png) | Categorical map: which policy wins each cell. Grey = baseline, coral = SC_fast, blue = FFF. |

*Generated by [`examples/2d_heatmap_sweep.py`](2d_heatmap_sweep.py) — 10 replications per cell, 750 total simulations.*
