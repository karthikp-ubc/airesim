# Two-Way Policy Sweep: Heat Map Results

**Data:** `examples/2d_heatmap_figures/replications.csv` (750 runs: 3 policies × 25 cells,
10 replications each, seeds 42–51) and `results.csv`, produced by
`examples/2d_heatmap_sweep.py` at commit `be13c89` (run log:
`examples/2d_heatmap_figures/run.log`). Date: 2026-11-20.

> **What changed on 2026-11-20.** The sweep was rerun after the paper-conformance fixes
> (CHANGELOG, "Paper conformance"). The script does not set `diagnosis_probability`, so
> it now runs at the Table I default of **0.8** (20% of failures go undiagnosed and the
> server rejoins unrepaired); the previous version of this report used 1.0. That default
> change accounts for all of the differences below: this sweep never borrows a spare or
> stalls (488 idle servers of headroom; 0 preemptions in all 750 runs, before and after),
> so the code fixes don't touch it, and rerunning the old configurations on the new code
> reproduces the old training times exactly. The headline change: at diagnosis 1.0 the
> two challengers split the grid 12–13; at 0.8 **FewestFailuresFirst wins 24 of 25
> cells**. §"Diagnosis matters" explains why, and why part of that win comes from
> information the policy would not have in practice.

> **Design note.** `Scheduler.do_host_selection` re-picks the *entire* job
> (`job_size + warm_standbys`) from the available pool each time it runs, so one full
> selection can bench every server the policy currently regards as bad, up to headroom
> (`working_pool_size - job_size - warm_standbys` = 488 servers, fixed across this
> sweep's cells, against an initial bad population of ~368, 8% of the 4,600-server
> pool). Between full selections, `Scheduler.swap_in_standby` replaces a failed
> active server with the oldest warm standby, FIFO, without consulting the policy.
>
> `FewestFailuresFirst` can only bench a bad server that has already failed at least
> once — one that hasn't yet failed looks identical to a good server — so headroom
> above the bad population lets it bench every *known*-bad server, not the whole
> population outright. Averaged over all 25 cells, time-averaged faulty servers in the
> active job are **157.8** under `FewestFailuresFirst+NeverRemove` vs **195.8** under
> `Random+NeverRemove`, a **19%** reduction — not near-total exclusion.
>
> `faulty_in_pool_timeavg` counts bad servers across the whole working pool — active
> job included, per `MonitoredSimulator._monitor` in `examples/sweep_common.py`. It is
> *higher* under `FewestFailuresFirst` (250.0) than `Random` (227.0); subtracting the
> active-job count leaves the idle (benched) count: **92.2** under
> `FewestFailuresFirst` vs **31.3** under `Random`. `FewestFailuresFirst` keeps *more*
> bad servers in the cluster overall — a benched bad server never fails, so it never
> enters repair and never gets cured. It trades curing bad servers for avoiding them,
> and still wins here. See `SCHEDULING_COMPARISON_REPORT.md`'s design note for the full
> mechanism and the contrast with paper-semantics defaults, where headroom is only 48
> servers against ~624 initially bad and the policy shows no measurable benefit.
>
> **`FewestFailuresFirst` reads ground-truth failure counts** (`total_failure_count`),
> which include the failures diagnosis missed. `ScoredRemoval` is only told about
> diagnosed failures (`simulator.py`, `removal_policy.on_failure` in the attributed
> branch), and every removal policy is consulted only when a server finishes repair,
> i.e. after a diagnosed failure. At diagnosis 0.8 this comparison therefore gives the scheduler information
> the retirement policy doesn't have. §"Diagnosis matters" compares against
> `FewestAttributedFailuresFirst`, which sees only diagnosed failures.

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
| `diagnosis_probability` | 0.80 | Table I default; 20% of failures undiagnosed |

10 replications per cell × 3 policies × 25 cells = **750 simulations total**. A typical
cell mean has a standard error of about 13 h (stdevs 25–84 h). Cells marked † below have
a difference from the baseline of less than two standard errors (unpaired).

## Overview: Host Selection Activity

Mean full host-selection events per run, from `replications.csv` (10 replications/cell):

**Random + NeverRemove**

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|---|---|---|---|---|---|
| **5×** | 4.9 | 5.4 | 5.4 | 5.7 | 5.7 |
| **10×** | 4.9 | 5.7 | 5.8 | 6.5 | 6.1 |
| **15×** | 6.0 | 5.8 | 5.8 | 6.4 | 6.3 |
| **20×** | 6.0 | 5.5 | 6.2 | 6.9 | 6.9 |
| **25×** | 5.5 | 6.0 | 6.2 | 7.3 | 7.1 |

**Random + ScoredRemoval (SC_fast)**

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|---|---|---|---|---|---|
| **5×** | 12.1 | 13.0 | 14.6 | 14.1 | 15.1 |
| **10×** | 14.6 | 16.8 | 18.3 | 19.6 | 20.7 |
| **15×** | 15.9 | 19.0 | 21.5 | 22.8 | 24.4 |
| **20×** | 16.9 | 20.0 | 22.9 | 25.0 | 27.0 |
| **25×** | 17.3 | 20.7 | 23.2 | 25.5 | 28.1 |

**FewestFailuresFirst + NeverRemove**

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|---|---|---|---|---|---|
| **5×** | 5.6 | 4.9 | 5.3 | 5.2 | 5.3 |
| **10×** | 5.2 | 5.6 | 5.0 | 5.3 | 5.4 |
| **15×** | 5.7 | 6.0 | 5.3 | 5.9 | 5.2 |
| **20×** | 5.5 | 5.1 | 6.0 | 5.8 | 5.5 |
| **25×** | 5.5 | 5.6 | 5.8 | 6.1 | 6.6 |

`ScoredRemoval` raises host selections 2–4× over the baseline because every retirement
forces a replacement; retirements grow with both severity and repair-fail probability,
which is why its host-selection grid tracks the same corner. `FewestFailuresFirst` (no
retirement) tracks the `Random` baseline closely — the scheduling policy itself barely
changes how often full host selection is needed.

---

## Policies Compared

### 1. Random + NeverRemove (Baseline)
Uniform random host selection; every repaired server is returned to the working pool.
This is the naive default: no preference for healthy servers, no retirement.

Baseline mean training time (h):

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | 1801 h | 1818 h | 1840 h | 1862 h | 1887 h |
| **10×** | 1946 h | 1986 h | 2082 h | 2156 h | 2242 h |
| **15×** | 2011 h | 2128 h | 2221 h | 2334 h | 2500 h |
| **20×** | 2059 h | 2190 h | 2323 h | 2494 h | 2695 h |
| **25×** | 2079 h | 2180 h | 2378 h | 2603 h | 2921 h |

These are 0.2–6.3% above the diagnosis-1.0 values: undiagnosed bad servers rejoin the
pool without repair and fail again.

### 2. Random + ScoredRemoval — SC_fast (Challenger A)
Uniform random host selection, but uses a score-based retirement policy tuned for fast culling:

| SC_fast parameter | Value |
|-------------------|-------|
| `initial_score` | 100 |
| `failure_penalty` | 60 |
| `success_increment` | 5 per day of clean uptime |
| `retirement_threshold` | 0 |

A server is retired after **just 2 diagnosed failures** (score path: 100 → 40 → −20 ≤ 0).
Recovery is slow (5 pts/day) so a retired bad server is rarely reinstated.

### 3. FewestFailuresFirst + NeverRemove (Challenger B)
Prefers hosts with fewer historical failures (ground truth, including undiagnosed
failures) when selecting hosts. No retirement — every repaired server returns to the
pool. This is a zero-capacity-cost policy: it routes work away from bad servers without
permanently shrinking the cluster.

---

## Overall Win Counts

| Policy | Cells with lowest mean (of 25) | At diagnosis 1.0 (previous report) |
|--------|------|------|
| Random + NeverRemove (baseline) | 0 | 0 |
| Random + ScoredRemoval (SC_fast) | 1 | 12 |
| FewestFailuresFirst + NeverRemove | 24 | 13 |

**The baseline wins no cell.** FFF is significantly faster than `SC_fast` (difference
over two standard errors) in 16 cells; `SC_fast` is significantly faster in none (at
diagnosis 1.0: 4 cells, with FFF significantly faster in 3).

---

## ScoredRemoval (SC_fast) — Delta vs Baseline

> **Negative = faster than baseline.**
> **Best improvement: −629 h (−21.5%)** (mult=25×, repair_fail=90%)
> **Worst regression: +13 h** (mult=10×, repair_fail=40%, within noise)

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | +2 h † | -11 h † | -9 h † | -35 h † | -43 h |
| **10×** | -3 h † | +13 h † | -75 h | -102 h | -168 h |
| **15×** | -26 h † | -70 h | -105 h | -181 h | -317 h |
| **20×** | -37 h | -102 h | -162 h | -264 h | -445 h |
| **25×** | -49 h | -47 h | -202 h | -360 h | -629 h |

### Interpretation

- **Bottom-right corner (high multiplier + high repair_fail_prob)**: SC_fast still
  helps a lot against the baseline — bad servers fail rapidly and repairs rarely fix
  them, so retiring after 2 failures breaks the failure→repair→failure cycle. The gain
  grows along both axes, to 300–630 h at repair_fail=90% for multipliers ≥15×. It is
  faster than the baseline in 23 of 25 cells, significantly so in 18.

- **Top-left (low multiplier + low repair_fail_prob)**: the gain is small and inside
  the noise; the two positive deltas (+2 h, +13 h) are not distinguishable from zero.

- **Retirement sees less.** Only diagnosed failures move a server's score, so with 20%
  of failures undiagnosed SC_fast retires fewer servers (250 per run averaged over the
  grid, against 313 at diagnosis 1.0) and leaves more bad servers in the job
  (time-averaged 173.7 faulty servers in the active job, against 153.6).

---

## FewestFailuresFirst + NeverRemove — Delta vs Baseline

> **Negative = faster than baseline.**
> **Best improvement: −586 h (−20.1%)** (mult=25×, repair_fail=90%)
> **Smallest improvement: −32 h** (mult=5×, repair_fail=40%)

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | -40 h | -32 h | -46 h | -66 h | -80 h |
| **10×** | -64 h | -52 h | -128 h | -166 h | -201 h |
| **15×** | -63 h | -135 h | -157 h | -241 h | -330 h |
| **20×** | -84 h | -140 h | -217 h | -330 h | -451 h |
| **25×** | -61 h | -103 h | -242 h | -376 h | -586 h |

### Interpretation

- **FFF is significantly faster than the baseline in all 25 cells**, with gains that
  grow with severity in the same way as SC_fast's.

- **FFF has no capacity cost** and cannot overshoot by retiring servers that repairs
  would have fixed.

- **FFF is unaffected by missed diagnoses, by construction.** It ranks on every failure,
  diagnosed or not, so the undiagnosed failures that blind the retirement policy still
  count against a bad server here.

---

## Head-to-Head: Where Each Policy Wins

Winner at each cell by lowest mean training time; `*` marks cells where the
`SC_fast` − FFF difference exceeds two standard errors (FFF significantly faster in 16
cells, `SC_fast` in none, indistinguishable in 9):

```
             repair_fail_prob →
               20%     40%     60%     75%     90%
mult  5×  [ FFF*  | FFF   | FFF*  | FFF   | FFF*  ]
     10×  [ FFF*  | FFF*  | FFF*  | FFF*  | FFF   ]
     15×  [ FFF*  | FFF*  | FFF*  | FFF*  | FFF   ]
     20×  [ FFF*  | FFF   | FFF*  | FFF*  | FFF   ]
     25×  [ FFF   | FFF*  | FFF*  | FFF   | SC    ]
```

FFF's significant leads are 37–65 h. The one `SC_fast` cell (25×/90%) is 43 h ahead,
within noise. For comparison, at diagnosis 1.0:

```
             repair_fail_prob →
               20%     40%     60%     75%     90%
mult  5×  [ SC    | FFF*  | FFF*  | FFF   | FFF   ]
     10×  [ FFF   | FFF*  | FFF   | FFF   | FFF   ]
     15×  [ FFF   | FFF   | FFF   | SC    | SC    ]
     20×  [ SC    | SC    | SC    | SC*   | SC*   ]
     25×  [ FFF   | SC    | SC    | SC*   | SC*   ]
```

---

## Diagnosis matters: where retirement stops winning

The flip between the two grids above is caused by one parameter,
`diagnosis_probability`, and part of it is an information asymmetry (design note
above). `examples/diagnosis_crossover.py` sweeps diagnosis from 0.5 to 1.0 in three
regimes where `SC_fast` beat FFF at 1.0, and adds `FewestAttributedFailuresFirst`
(FAFF, diagnosed failures only) as the fair scheduling comparison. Results:
`DIAGNOSIS_SWEEP_REPORT.md` §"Crossover".

---

## Key Takeaways

1. **Both policies beat doing nothing almost everywhere, and the benefit scales with
   severity.** At 25×/90%: −629 h (`SC_fast`, −21.5%) and −586 h (FFF, −20.1%).

2. **At diagnosis 0.8, failure-aware scheduling beats aggressive retirement nearly
   everywhere** (24 of 25 cells, 16 significantly). At diagnosis 1.0 retirement pulled
   clearly ahead at multiplier ≥ 20× with repair_fail ≥ 75%; that advantage is gone.

3. **The comparison is not like-for-like below diagnosis 1.0.** FFF ranks on
   ground-truth failure counts; retirement only acts on diagnosed failures. See the
   crossover results for the comparison against FAFF.

4. **These results are specific to how AIReSim applies the scheduling policy**: it acts
   only at full host selection, with headroom (488) above the bad population (~368).

---

## Figures

| Figure | Description |
|--------|-------------|
| [`heatmap_scored_delta.png`](../examples/2d_heatmap_figures/heatmap_scored_delta.png) | Δ training time (hrs): SC_fast vs baseline. Green = improvement, red = regression. |
| [`heatmap_fff_delta.png`](../examples/2d_heatmap_figures/heatmap_fff_delta.png) | Δ training time (hrs): FewestFailuresFirst vs baseline. |
| [`heatmap_winner.png`](../examples/2d_heatmap_figures/heatmap_winner.png) | Categorical map: which policy wins each cell. Grey = baseline, coral = SC_fast, blue = FFF. |

*Generated by [`examples/2d_heatmap_sweep.py`](../examples/2d_heatmap_sweep.py) — 10 replications per cell, 750 total simulations, regenerated 2026-11-20 at `be13c89`.*
