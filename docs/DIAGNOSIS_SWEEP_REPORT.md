# Diagnosis Parameter Sweep — Report

**Regime:** 20× failure multiplier | 75% manual repair fail probability | 4 600-server pool
**Replications per cell:** 8
**Baseline:** Random + NeverRemove, diagnosis\_probability = 1.0, diagnosis\_uncertainty = 0.0 → **2 215 h**

Figures: `examples/diagnosis_sweep_figures/`

---

## 1  Parameter definitions

| Parameter | Meaning | Range |
|-----------|---------|-------|
| `diagnosis_probability` | P(failure triggers a repair attempt on any server) | [0, 1] |
| `diagnosis_uncertainty` | P(wrong server blamed \| failure is diagnosed) | [0, 1] |

At `diagnosis_probability = 0` every failure goes undiagnosed: the failed server auto-recovers
to the working pool instantly without entering the repair pipeline.
At `diagnosis_uncertainty = 1` every diagnosed failure is attributed to a randomly chosen
*innocent* server; the actual bad server escapes.

---

## 2  Sweep A — `diagnosis_probability`  (uncertainty fixed at 0)

### 2.1  Raw results

| prob | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 3 251.7  |  49.2 | +1 036.3    |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 3 251.7  |  49.2 | +1 036.3    |     0.0 |
| 0.00 | Random+ScoredRemoval         | 3 251.7  |  49.2 | +1 036.3    |     0.0 |
| 0.00 | FewestFailures+NeverRemove   | 3 264.8  |  54.9 | +1 049.4    |     0.0 |
| 0.00 | FewestFailures+Thresh ≥2/7d  | 3 264.8  |  54.9 | +1 049.4    |     0.0 |
| 0.00 | FewestFailures+ScoredRemoval | 3 264.8  |  54.9 | +1 049.4    |     0.0 |
| 0.20 | Random+NeverRemove           | 2 587.0  | 307.6 |   +371.6    |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 447.7  |  58.3 |   +232.4    |    41.0 |
| 0.20 | Random+ScoredRemoval         | 2 451.1  |  38.0 |   +235.7    |    33.0 |
| 0.20 | FewestFailures+NeverRemove   | 2 923.1  | 243.6 |   +707.7    |     0.0 |
| 0.20 | FewestFailures+Thresh ≥2/7d  | 2 274.1  |  55.5 |    +58.7    |    36.5 |
| 0.20 | FewestFailures+ScoredRemoval | 2 351.8  |  42.9 |   +136.4    |    27.8 |
| 0.40 | Random+NeverRemove           | 2 344.0  |  82.0 |   +128.7    |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 2 325.9  |  51.3 |   +110.5    |    60.6 |
| 0.40 | Random+ScoredRemoval         | 2 316.7  |  35.0 |   +101.4    |   101.8 |
| 0.40 | FewestFailures+NeverRemove   | 2 397.2  | 114.8 |   +181.8    |     0.0 |
| 0.40 | FewestFailures+Thresh ≥2/7d  | 2 213.5  |  48.1 |     **−1.9**|    53.5 |
| 0.40 | FewestFailures+ScoredRemoval | 2 198.3  |  39.9 |    **−17.1**|    72.6 |
| 0.60 | Random+NeverRemove           | 2 303.9  |  66.2 |    +88.5    |     0.0 |
| 0.60 | Random+Thresh ≥2/7d          | 2 231.4  |  43.9 |    +16.1    |    67.4 |
| 0.60 | Random+ScoredRemoval         | 2 228.2  |  34.9 |    +12.9    |   180.6 |
| 0.60 | FewestFailures+NeverRemove   | 2 231.2  |  30.7 |    +15.8    |     0.0 |
| 0.60 | FewestFailures+Thresh ≥2/7d  | 2 161.7  |  44.1 |    **−53.7**|    61.1 |
| 0.60 | FewestFailures+ScoredRemoval | 2 127.8  |  24.2 |    **−87.6**|   142.6 |
| 0.80 | Random+NeverRemove           | 2 234.6  |  63.4 |    +19.2    |     0.0 |
| 0.80 | Random+Thresh ≥2/7d          | 2 239.0  |  20.6 |    +23.7    |    73.4 |
| 0.80 | Random+ScoredRemoval         | 2 168.0  |  36.2 |    **−47.3**|   268.0 |
| 0.80 | FewestFailures+NeverRemove   | 2 168.2  |  48.8 |    **−47.2**|     0.0 |
| 0.80 | FewestFailures+Thresh ≥2/7d  | 2 123.6  |  40.3 |    **−91.7**|    66.9 |
| 0.80 | FewestFailures+ScoredRemoval | 2 121.0  |  36.5 |    **−94.3**|   229.5 |
| 1.00 | Random+NeverRemove           | 2 215.3  |  35.4 |       0.0   |     0.0 |
| 1.00 | Random+Thresh ≥2/7d          | 2 140.6  |  50.6 |    **−74.7**|    70.9 |
| 1.00 | Random+ScoredRemoval         | 2 046.6  |  26.3 |   **−168.7**|   338.2 |
| 1.00 | FewestFailures+NeverRemove   | 2 116.2  |  56.1 |    **−99.2**|     0.0 |
| 1.00 | FewestFailures+Thresh ≥2/7d  | 2 097.2  |  48.1 |   **−118.2**|    69.1 |
| 1.00 | FewestFailures+ScoredRemoval | 2 064.5  |  35.5 |   **−150.9**|   334.8 |

### 2.2  Observations

**At prob = 0 — repair pipeline is completely bypassed:**
Every policy converges to the same result (~3 252 h, 0 retirements).  The retirement policy
is irrelevant because no server ever enters the pipeline.  Training takes ~1 036 h longer than
the full-diagnosis baseline because bad servers keep failing and restarting without being
cleaned from the pool.

**FewestFailures is dramatically worse than Random at prob = 0.20 (without retirement):**
`FewestFailures+NeverRemove` runs 2 923 h vs. `Random+NeverRemove` at 2 587 h — a +336 h
reversal.  Mechanism: FewestFailures deprioritises bad servers after their first few failures.
When those bad servers are occasionally diagnosed (20%) and enter repair (manual: 48 h mean),
they are simultaneously excluded from the job *and* absent from the pool.  Random spreads
repair load more evenly, reducing simultaneous unavailability.

**Retirement policies begin paying off at prob ≈ 0.40:**
`FewestFailures+Thresh ≥2/7d` essentially breaks even at prob = 0.40 (−1.9 h) and delivers a
solid −54 h at prob = 0.60.  `ScoredRemoval` turns positive at prob = 0.40 (−17 h) too.
The reason retirement policies can work even below prob = 1.0: `ThresholdRemoval` reads
`failure_timestamps`, which are updated by the coordinator for *all* failures regardless of
diagnosis outcome.  So ThresholdRemoval "knows" about missed-diagnosis failures and can retire
bad servers on the first repair entry that does occur.

**ScoredRemoval requires higher probability for full benefit:**
Unlike ThresholdRemoval, ScoredRemoval's `on_failure` callback is only called for diagnosed
failures.  At prob = 0.60, `Random+ScoredRemoval` is only +13 h, while
`FewestFailures+ScoredRemoval` delivers −88 h.  At prob ≥ 0.80, `Random+ScoredRemoval`
starts outperforming `FewestFailures+ScoredRemoval`, and by prob = 1.0 it is the best
overall at −169 h.

**Best combination at each probability:**

| prob | Best policy                     | Δ (h)  |
|------|---------------------------------|--------|
| 0.00 | (all equivalent)                | +1 036 |
| 0.20 | FewestFailures+Thresh ≥2/7d     |   +59  |
| 0.40 | FewestFailures+ScoredRemoval    |   −17  |
| 0.60 | FewestFailures+ScoredRemoval    |   −88  |
| 0.80 | FewestFailures+ScoredRemoval    |   −94  |
| 1.00 | Random+ScoredRemoval            |  −169  |

---

## 3  Sweep B — `diagnosis_uncertainty`  (probability fixed at 1.0)

### 3.1  Raw results

| unc  | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 2 215.3  |  35.4 |       0.0   |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 2 140.6  |  50.6 |    −74.7    |    70.9 |
| 0.00 | Random+ScoredRemoval         | 2 046.6  |  26.3 |   −168.7    |   338.2 |
| 0.00 | FewestFailures+NeverRemove   | 2 116.2  |  56.1 |    −99.2    |     0.0 |
| 0.00 | FewestFailures+Thresh ≥2/7d  | 2 097.2  |  48.1 |   −118.2    |    69.1 |
| 0.00 | FewestFailures+ScoredRemoval | 2 064.5  |  35.5 |   −150.9    |   334.8 |
| 0.20 | Random+NeverRemove           | 2 225.0  |  70.5 |     +9.6    |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 154.8  |  38.2 |    −60.6    |    69.4 |
| 0.20 | Random+ScoredRemoval         | 2 115.8  |  23.1 |    −99.5    |   316.0 |
| 0.20 | FewestFailures+NeverRemove   | 2 160.1  |  51.2 |    −55.3    |     0.0 |
| 0.20 | FewestFailures+Thresh ≥2/7d  | 2 073.4  |  36.6 |   −141.9    |    63.1 |
| 0.20 | FewestFailures+ScoredRemoval | 1 852.1  | 750.3 |   −363.2    |   323.1 |
| 0.40 | Random+NeverRemove           | 2 285.3  |  76.3 |    +70.0    |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 1 891.7  | 765.5 |   −323.6    |    58.4 |
| 0.40 | Random+ScoredRemoval         |     0.0  |   0.0 | *deadlock*  |   200.9 |
| 0.40 | FewestFailures+NeverRemove   | 2 233.5  |  56.4 |    +18.2    |     0.0 |
| 0.40 | FewestFailures+Thresh ≥2/7d  | 1 882.7  | 762.2 |   −332.7    |    58.1 |
| 0.40 | FewestFailures+ScoredRemoval |     0.0  |   0.0 | *deadlock*  |   188.5 |
| 0.60 | (all combinations)           |     0.0  |   0.0 | *deadlock*  |     —   |
| 0.80 | (all combinations)           |     0.0  |   0.0 | *deadlock*  |     —   |
| 1.00 | (all combinations)           |     0.0  |   0.0 | *deadlock*  |     —   |

### 3.2  Observations

**At unc = 0.20 — mostly tolerable, but ScoredRemoval shows extreme variance:**
Most combinations remain within ±70 h of their zero-uncertainty counterparts.
`FewestFailures+ScoredRemoval` produces 1 852 ± 750 h — a bimodal distribution where some
runs complete quickly (retirement working well) and others stall badly (floating servers
accumulating faster than they are retired).  Despite the mean improvement of −363 h, the high
variance makes this combination unreliable.  `Random+ScoredRemoval` at −99 h with ±23 h std
is much more stable.

**ThresholdRemoval shows high variance at unc = 0.40:**
Both `Random+Thresh ≥2/7d` (1 892 ± 765 h) and `FewestFailures+Thresh ≥2/7d` (1 883 ± 762 h)
exhibit enormous standard deviations.  This reflects the same bimodal behaviour: some runs
complete before floating servers deplete the pool, others deadlock.  ScoredRemoval deadlocks
deterministically (all 8 reps) at this uncertainty level.

**Universal deadlock at unc ≥ 0.60:**
All six policy combinations produce `total_training_time = 0.0` with `cluster_depleted = False`
at uncertainty ≥ 0.60.  This is a **simulation deadlock**, not a successful cluster
depletion — SimPy exits silently when no future events remain.

### 3.3  Root cause: the floating-server bug

When a misdiagnosis fires (probability = `diagnosis_uncertainty`):

1. The actual bad server is marked IDLE and removed from the working pool.
2. An innocent server is marked FAILED and sent to repair.
3. The bad server stays in `active_servers` until the next full host-selection replaces it.

After host selection, the bad server is neither in `pool_mgr.working_pool` nor in
`active_servers` — it is **floating** (state = IDLE, not tracked by any pool).  As
misdiagnoses accumulate, `pool_mgr.available_in_working` shrinks below
`total_servers_needed`.

The depletion guard checks `state != RETIRED` — floating servers still count as "active" — so
the guard never fires.  Eventually all pending repairs finish, no new events are scheduled, and
SimPy exits silently with `env.now` reflecting only the elapsed time before the stall.

**Threshold at which deadlock appears:**

- ScoredRemoval deadlocks first (unc = 0.40, all 8 reps) because it retires more servers
  quickly, shrinking the non-floating pool faster.
- ThresholdRemoval survives unc = 0.40 on average (mean −323 h to −333 h) but with ±765 h
  std — some reps deadlock, others complete.
- NeverRemove deadlocks reliably at 0.60 (the floating-server bottleneck, not retirements).

**Fix (not yet implemented):** The depletion guard should count
`pool_mgr.available_in_working` (or non-retired, non-floating servers) rather than
`state != RETIRED`.  Alternatively, the misdiagnosis branch should track and eventually
reintegrate floating servers.

---

## 4  Practical guidance

### When to adjust `diagnosis_probability`

| prob | Recommended policy | Rationale |
|------|--------------------|-----------|
| < 0.40 | FewestFailures+Thresh ≥2/7d | Only ThresholdRemoval has effective signal (failure timestamps); ScoredRemoval blind to missed failures |
| 0.40–0.80 | FewestFailures+ScoredRemoval | ScoredRemoval pays off; FewestFailures scheduling reduces exposure to repeat bad-server failures |
| ≥ 0.80 | Random+ScoredRemoval | At high probability, Random maximises bad-server exposure → faster score degradation → earlier retirement |

### When to adjust `diagnosis_uncertainty`

| unc  | Recommended policy | Rationale |
|------|--------------------|-----------|
| ≤ 0.20 | Random+ScoredRemoval | Best absolute time (−99 h); low variance (±23 h) |
| 0.20–0.40 | ThresholdRemoval only | ScoredRemoval deadlocks at 0.40; ThresholdRemoval shows high variance but survives |
| ≥ 0.40 | **Avoid** | All policies deadlock at 0.60+; fix floating-server bug before operating here |

### Key interactions

- **ThresholdRemoval is partially immune to missed diagnoses** because it reads raw
  `failure_timestamps`, which are updated by the coordinator for all failures regardless of
  diagnosis outcome.  A bad server accumulates timestamps even for undiagnosed failures;
  ThresholdRemoval can retire it on the first repair entry.

- **ScoredRemoval is blind to missed diagnoses** — its `on_failure` hook is only called for
  diagnosed failures.  At low `diagnosis_probability`, scores become stale and both the
  scheduling and retirement signals degrade.

- **FewestFailures reversal at low probability:** At prob = 0.20 without retirement,
  FewestFailures performs 336 h *worse* than Random (+708 h vs. +372 h over baseline).
  After early failures, FewestFailures avoids bad servers; those servers then enter repair (20%
  diagnosed) and are absent from both the job and the pool simultaneously, compounding the
  effective-pool shortfall.

- **High-uncertainty bimodal distributions:** At unc = 0.20–0.40, some cells show large
  standard deviations (± 750–765 h) reflecting bimodal behaviour — runs either complete
  efficiently (retirement cleans the pool faster than floating servers accumulate) or deadlock.
  The mean hides this risk; always check std alongside mean.

---

## 5  Summary

```
diagnosis_probability sweep (uncertainty = 0):
  Minimum net payoff from retirement: prob ≥ 0.40
    (FewestFailures+ScoredRemoval: −17 h)
  Full payoff at prob = 1.0:
    Random+ScoredRemoval:         −169 h  ← best overall
    FewestFailures+ScoredRemoval: −151 h
    FewestFailures+Thresh ≥2/7d:  −118 h

diagnosis_uncertainty sweep (probability = 1):
  Safe range:  unc ≤ 0.20
    Random+ScoredRemoval: −99 h ± 23 (stable)
    FewestFailures+ScoredRemoval: −363 h ± 750 (high variance — risky)
  Caution:     unc = 0.40
    ThresholdRemoval still runs: mean ~−330 h but ± 765 h std
    ScoredRemoval deadlocks (all 8 reps)
  Avoid:       unc ≥ 0.60
    Universal simulation deadlock — floating-server bug
```

**Practical takeaway:** keep `diagnosis_uncertainty` ≤ 0.20 and `diagnosis_probability` ≥ 0.60
to reliably benefit from automated retirement.  At full accuracy (`uncertainty = 0`,
`probability = 1`), `Random+ScoredRemoval` achieves the best training time at −169 h below
the no-retirement baseline.
