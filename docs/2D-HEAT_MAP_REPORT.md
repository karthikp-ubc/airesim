# Two-Way Policy Sweep: Heat Map Results

**Data:** `examples/2d_heatmap_figures/results.csv` (75 rows: 3 policies × 25 cells, 10
replications each), produced by `examples/2d_heatmap_sweep.py` at commit `0cab8fb`;
per-replication rows (seed, full params, host_selection_count, systematic/random
failures, faulty servers in pool) re-logged at commit `da28d04` into
`examples/2d_heatmap_figures/replications.csv`, same seeds, results unchanged
(run log: `examples/2d_heatmap_figures/run.log`). Repairs follow the paper's model:
`prob_auto_to_manual` is the probability that auto repair escalates, independent of the
silent auto-repair failure `auto_repair_fail_prob`. Date: 2026-09-21.

> **Design note (2026-09-22, corrected).** An earlier version of this caveat argued
> that low host-selection counts (§2a) mean `FewestFailuresFirst` is "rarely
> consulted" and so its results here don't generalize. That's wrong:
> `Scheduler.do_host_selection` re-picks the *entire* job (`job_size + warm_standbys`)
> from the available pool each time it runs, so one full selection can bench every
> server the policy currently regards as bad, up to headroom
> (`working_pool_size - job_size - warm_standbys` = 488 servers, fixed across this
> sweep's cells, against an initial bad population of ~368, 8% of the 4,600-server
> pool). Between full selections, `Scheduler.swap_in_standby` replaces a failed
> active server with the oldest warm standby, FIFO, without consulting the policy.
>
> `FewestFailuresFirst` can only bench a bad server that has already failed at least
> once — one that hasn't yet failed looks identical to a good server — so headroom
> above the bad population lets it bench every *known*-bad server, not the whole
> population outright. The per-replication data show the measured effect: averaged
> over all 25 cells, time-averaged faulty servers in the active job are **150.0**
> under `FewestFailuresFirst+NeverRemove` vs **179.2** under `Random+NeverRemove`, a
> **16%** reduction — not near-total exclusion.
>
> `faulty_in_pool_timeavg` counts bad servers across the whole working pool — active
> job included, per `MonitoredSimulator._monitor` in `examples/sweep_common.py` — not
> just the idle portion. It is *higher* under `FewestFailuresFirst` (229.3) than
> `Random` (207.7); subtracting the active-job count leaves the idle (benched) count:
> **79.3** under `FewestFailuresFirst` vs **28.6** under `Random`.
> `FewestFailuresFirst` keeps *more* bad servers in the cluster overall — a benched
> bad server never fails, so it never enters repair and never gets cured. It trades
> curing bad servers for avoiding them, and still wins here
> (`examples/2d_heatmap_figures/replications.csv`, `faulty_in_active_timeavg` /
> `faulty_in_pool_timeavg`). See `SCHEDULING_COMPARISON_REPORT.md`'s design note for
> the full mechanism and the contrast with paper-semantics defaults, where headroom
> is only 48 servers against ~624 initially bad (7.7% coverage, vs 133% here) and the
> policy shows no measurable benefit — bounded by headroom and by saturation
> (`SIMULATION_REPORT.md` §5a), not by consultation frequency.
> `FewestFailuresFirst` here also reads ground-truth failure counts;
> `FewestAttributedFailuresFirst` has not been tested in this regime — see
> `DIAGNOSIS_REALISTIC_REPORT.md` for the attributed-count variant at paper defaults.

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

## Overview: Host Selection Activity

Mean full host-selection events per run, from `replications.csv` (10 replications/cell):

**Random + NeverRemove**

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|---|---|---|---|---|---|
| **5×** | 5.6 | 5.7 | 5.8 | 5.9 | 5.9 |
| **10×** | 5.9 | 5.7 | 5.8 | 6.6 | 6.1 |
| **15×** | 6.6 | 6.5 | 6.6 | 6.4 | 7.5 |
| **20×** | 5.9 | 6.4 | 7.6 | 7.4 | 7.5 |
| **25×** | 6.3 | 6.7 | 7.5 | 7.4 | 8.1 |

**Random + ScoredRemoval (SC_fast)**

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|---|---|---|---|---|---|
| **5×** | 15.4 | 16.8 | 18.0 | 18.9 | 20.8 |
| **10×** | 18.3 | 20.5 | 22.9 | 24.8 | 26.1 |
| **15×** | 20.0 | 22.0 | 25.1 | 26.2 | 29.2 |
| **20×** | 19.8 | 23.4 | 26.0 | 27.8 | 30.6 |
| **25×** | 20.8 | 24.1 | 27.2 | 29.0 | 31.3 |

**FewestFailuresFirst + NeverRemove**

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|---|---|---|---|---|---|
| **5×** | 5.8 | 6.0 | 6.3 | 5.7 | 6.0 |
| **10×** | 6.2 | 5.9 | 6.3 | 6.6 | 6.9 |
| **15×** | 6.5 | 5.6 | 6.4 | 6.4 | 6.4 |
| **20×** | 6.4 | 6.3 | 6.2 | 6.7 | 6.8 |
| **25×** | 5.9 | 6.4 | 6.3 | 6.2 | 7.4 |

`ScoredRemoval` raises host selections 2–5× over the baseline because every retirement
forces a replacement; retirements grow with both severity and repair-fail probability
(§ScoredRemoval below), which is why its host-selection grid tracks the same corner.
`FewestFailuresFirst` (no retirement) tracks the `Random` baseline closely — the
scheduling policy itself barely changes how often full host selection is needed.

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
