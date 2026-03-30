# Diagnosis Parameter Sweep — Report

**Regime:** 20× failure multiplier | 75% manual repair fail probability | 4 600-server pool
**Replications per cell:** 3
**Baseline:** Random + NeverRemove, diagnosis\_probability = 1.0, diagnosis\_uncertainty = 0.0 → **2 190 h**

Figures: `examples/diagnosis_sweep_figures/`

> **Note:** Results in §3 (Sweep B) reflect the post-bugfix simulation.  Two bugs in the
> misdiagnosis path were fixed before this sweep was run:
> 1. *Floating-server deadlock* — escaped bad servers were not returned to the working pool,
>    causing the simulation to deadlock silently at high uncertainty.
> 2. *Active-server duplication* — `on_server_returned` was called for the escaped bad server
>    while it was still in `active_servers`, potentially adding it to `warm_standbys` and
>    creating a duplicate in `active_servers` on the next standby swap.

---

## 1  Parameter definitions

| Parameter | Meaning | Range |
|-----------|---------|-------|
| `diagnosis_probability` | P(failure triggers a repair attempt on any server) | [0, 1] |
| `diagnosis_uncertainty` | P(wrong server blamed \| failure is diagnosed) | [0, 1] |

At `diagnosis_probability = 0` every failure goes undiagnosed: the failed server auto-recovers
to the working pool instantly without entering the repair pipeline.
At `diagnosis_uncertainty = 1` every diagnosed failure is attributed to a randomly chosen
*innocent* server; the actual bad server escapes back into `active_servers`.

---

## 2  Sweep A — `diagnosis_probability`  (uncertainty fixed at 0)

*The bug fix does not affect this sweep: uncertainty = 0 means no misdiagnosis ever fires.*

### 2.1  Raw results

| prob | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 3 250.7  |  63.8 | +1 060.3    |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 3 250.7  |  63.8 | +1 060.3    |     0.0 |
| 0.00 | Random+ScoredRemoval         | 3 250.7  |  63.8 | +1 060.3    |     0.0 |
| 0.00 | FewestFail+NeverRemove       | 3 264.7  |  55.2 | +1 074.3    |     0.0 |
| 0.00 | FewestFail+Thresh ≥2/7d      | 3 264.7  |  55.2 | +1 074.3    |     0.0 |
| 0.00 | FewestFail+ScoredRemoval     | 3 264.7  |  55.2 | +1 074.3    |     0.0 |
| 0.20 | Random+NeverRemove           | 2 584.8  | 292.2 |   +394.4    |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 465.9  |   9.1 |   +275.5    |    39.3 |
| 0.20 | Random+ScoredRemoval         | 2 440.2  |  46.3 |   +249.8    |    39.0 |
| 0.20 | FewestFail+NeverRemove       | 2 782.4  | 393.0 |   +592.0    |     0.0 |
| 0.20 | FewestFail+Thresh ≥2/7d      | 2 287.9  |  17.6 |    +97.5    |    35.3 |
| 0.20 | FewestFail+ScoredRemoval     | 2 335.8  |  46.5 |   +145.5    |    29.3 |
| 0.40 | Random+NeverRemove           | 2 352.1  |  94.6 |   +161.8    |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 2 347.0  |  65.6 |   +156.6    |    59.7 |
| 0.40 | Random+ScoredRemoval         | 2 336.2  |  22.4 |   +145.8    |   107.7 |
| 0.40 | FewestFail+NeverRemove       | 2 386.5  |  73.0 |   +196.1    |     0.0 |
| 0.40 | FewestFail+Thresh ≥2/7d      | 2 215.0  |  46.5 |     **−1.9**|    53.5 |
| 0.40 | FewestFail+ScoredRemoval     | 2 198.3  |  39.9 |    **−17.1**|    72.6 |
| 0.60 | Random+NeverRemove           | 2 284.2  |  78.0 |    +93.8    |     0.0 |
| 0.60 | Random+Thresh ≥2/7d          | 2 248.7  |  44.2 |    +58.4    |    61.0 |
| 0.60 | Random+ScoredRemoval         | 2 231.7  |  54.0 |    +41.3    |   177.0 |
| 0.60 | FewestFail+NeverRemove       | 2 210.9  |  45.2 |    +20.5    |     0.0 |
| 0.60 | FewestFail+Thresh ≥2/7d      | 2 125.8  |  33.6 |    **−53.7**|    61.1 |
| 0.60 | FewestFail+ScoredRemoval     | 2 106.6  |  20.0 |    **−83.7**|   142.6 |
| 0.80 | Random+NeverRemove           | 2 220.7  |  70.3 |    +30.3    |     0.0 |
| 0.80 | Random+Thresh ≥2/7d          | 2 232.5  |  27.1 |    +42.1    |    72.7 |
| 0.80 | Random+ScoredRemoval         | 2 133.3  |  27.6 |    **−47.3**|   260.7 |
| 0.80 | FewestFail+NeverRemove       | 2 127.3  |  11.8 |    **−63.1**|     0.0 |
| 0.80 | FewestFail+Thresh ≥2/7d      | 2 137.1  |  38.7 |    **−53.2**|    65.3 |
| 0.80 | FewestFail+ScoredRemoval     | 2 104.9  |  33.0 |    **−85.5**|   222.7 |
| 1.00 | Random+NeverRemove           | 2 190.4  |  16.7 |       0.0   |     0.0 |
| 1.00 | Random+Thresh ≥2/7d          | 2 143.2  |  75.7 |    **−47.2**|    69.0 |
| 1.00 | Random+ScoredRemoval         | 2 030.9  |   2.8 |   **−159.5**|   332.7 |
| 1.00 | FewestFail+NeverRemove       | 2 129.3  |  34.1 |    **−61.1**|     0.0 |
| 1.00 | FewestFail+Thresh ≥2/7d      | 2 073.2  |  68.6 |   **−117.1**|    76.0 |
| 1.00 | FewestFail+ScoredRemoval     | 2 100.9  |  27.7 |    **−89.4**|   357.0 |

### 2.2  Key observations

- **prob = 0:** All policies converge — repair pipeline never entered, 0 retirements.
  Training takes +1 060 h over baseline (bad servers keep failing, never cleaned).
- **FewestFail reversal at prob = 0.20:** `FewestFail+NeverRemove` is +592 h vs baseline,
  far worse than `Random+NeverRemove` (+394 h).  Mechanism: FewestFail deprioritises bad
  servers; when they do enter repair (20% diagnosed), they are simultaneously out of the job
  and out of the pool, compounding unavailability.
- **Retirement breaks even at prob ≈ 0.40:** `FewestFail+ScoredRemoval` −17 h and
  `FewestFail+Thresh ≥2/7d` −2 h at prob = 0.40.
- **Best at prob = 1.0:** `Random+ScoredRemoval` −160 h.

---

## 3  Sweep B — `diagnosis_uncertainty`  (probability fixed at 1.0)

### 3.1  Raw results  *(post-bugfix)*

| unc  | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 2 190.4  |  16.7 |       0.0   |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 2 143.2  |  75.7 |    −47.2    |    69.0 |
| 0.00 | Random+ScoredRemoval         | 2 030.9  |   2.8 |   −159.5    |   332.7 |
| 0.00 | FewestFail+NeverRemove       | 2 129.3  |  34.1 |    −61.1    |     0.0 |
| 0.00 | FewestFail+Thresh ≥2/7d      | 2 073.2  |  68.6 |   −117.2    |    76.0 |
| 0.00 | FewestFail+ScoredRemoval     | 2 100.9  |  27.7 |    −89.5    |   357.0 |
| 0.20 | Random+NeverRemove           | 2 267.4  |  81.9 |    +77.0    |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 273.0  |  24.8 |    +82.6    |    77.3 |
| 0.20 | Random+ScoredRemoval         | 2 164.6  |  14.3 |    **−25.8**|   355.7 |
| 0.20 | FewestFail+NeverRemove       | 2 138.7  |  61.0 |    **−51.7**|     0.0 |
| 0.20 | FewestFail+Thresh ≥2/7d      | 2 107.9  |  68.0 |    **−82.5**|    65.3 |
| 0.20 | FewestFail+ScoredRemoval     | 2 085.8  |  37.9 |    **−104.6**|  295.3 |
| 0.40 | Random+NeverRemove           | 2 337.0  |  49.9 |   +146.6    |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 2 330.7  |  28.0 |   +140.2    |    74.0 |
| 0.40 | Random+ScoredRemoval         | 2 234.9  |  48.4 |    +44.5    |   343.3 |
| 0.40 | FewestFail+NeverRemove       | 2 220.7  |  59.0 |    +30.3    |     0.0 |
| 0.40 | FewestFail+Thresh ≥2/7d      | 2 143.8  |  43.5 |    **−46.6**|    58.3 |
| 0.40 | FewestFail+ScoredRemoval     | 2 101.7  |  20.5 |    **−88.7**|   268.3 |
| 0.60 | Random+NeverRemove           | 2 522.4  |  87.0 |   +332.0    |     0.0 |
| 0.60 | Random+Thresh ≥2/7d          | 2 443.2  |  71.3 |   +252.8    |    61.3 |
| 0.60 | Random+ScoredRemoval         | 2 402.0  |  18.8 |   +211.6    |   363.3 |
| 0.60 | FewestFail+NeverRemove       | 2 209.0  |  39.3 |    +18.6    |     0.0 |
| 0.60 | FewestFail+Thresh ≥2/7d      | 2 172.2  |  34.1 |    **−18.2**|    44.7 |
| 0.60 | FewestFail+ScoredRemoval     | 2 188.5  |  23.2 |     **−1.9**|   283.3 |
| 0.80 | Random+NeverRemove           | 2 601.7  |  20.6 |   +411.3    |     0.0 |
| 0.80 | Random+Thresh ≥2/7d          | 2 579.6  |  51.2 |   +389.2    |    39.3 |
| 0.80 | Random+ScoredRemoval         | 2 652.2  |  36.5 |   +461.8    |   399.0 |
| 0.80 | FewestFail+NeverRemove       | 2 338.7  |  77.5 |   +148.3    |     0.0 |
| 0.80 | FewestFail+Thresh ≥2/7d      | 2 207.5  |  12.1 |    +17.1    |    31.3 |
| 0.80 | FewestFail+ScoredRemoval     | 2 253.2  |  27.5 |    +62.8    |   293.0 |
| 1.00 | Random+NeverRemove           | 2 777.7  |  71.6 |   +587.3    |     0.0 |
| 1.00 | Random+Thresh ≥2/7d          | 2 756.4  |  90.1 |   +566.0    |     2.7 |
| 1.00 | Random+ScoredRemoval         | 2 926.0  | 127.2 |   +735.6    |   499.3 |
| 1.00 | FewestFail+NeverRemove       | 2 326.4  |   7.0 |   +136.0    |     0.0 |
| 1.00 | FewestFail+Thresh ≥2/7d      | 2 347.1  |  26.7 |   +156.7    |     3.0 |
| 1.00 | FewestFail+ScoredRemoval     | 2 352.3  |  35.8 |   +161.9    |   345.0 |

### 3.2  Comparison with pre-fix results

| unc  | Pre-fix result                         | Post-fix result                              |
|------|----------------------------------------|----------------------------------------------|
| 0.00 | All correct (no misdiagnosis)          | Identical ✓                                  |
| 0.20 | FewestFail+Scored: 1852±750 (bimodal)  | FewestFail+Scored: 2086±38 (stable, −105 h)  |
| 0.40 | ScoredRemoval: deadlock (0.0 h)        | ScoredRemoval: 2235/2102 h (−45 to −89 h)   |
| 0.60 | All: deadlock (0.0 h)                  | All complete; FewestFail+Thresh: −18 h       |
| 0.80 | All: deadlock (0.0 h)                  | All complete; training time +150–+460 h      |
| 1.00 | All: deadlock (0.0 h)                  | All complete; +136–+736 h (ScoredRemoval worst) |

The extreme variance (±750 h) seen at unc=0.20 before the fix was a symptom of bimodal
behaviour: some runs deadlocked (0 h) while others completed normally.  With the bug fixed,
variance at unc=0.20 shrinks to ±14–68 h — the distribution is no longer bimodal.

### 3.3  Key observations

**ScoredRemoval becomes actively harmful at unc ≥ 0.80:**
At unc=0.80, `Random+ScoredRemoval` (2 652 h) is *worse* than `Random+NeverRemove` (2 602 h).
At unc=1.0, the gap widens to 2 926 h vs. 2 778 h.  Mechanism: `on_failure` is called on the
misdiagnosed *innocent* server, not the actual bad server.  Innocent servers accumulate penalty
scores and are retired; bad servers' scores remain pristine and they are preferentially kept.
The pool progressively fills with high-failure-rate servers.  This is a perverse inversion of
ScoredRemoval's intent — at high uncertainty it actively selects *against* the job.

**FewestFailures scheduling gives large benefit at high uncertainty (without retirement):**
At unc=1.0, `FewestFail+NeverRemove` (2 326 h) is 452 h *better* than
`Random+NeverRemove` (2 778 h).  Reason: FewestFailures sorts by `total_failure_count`, which
tracks the server's *actual* hardware failures regardless of misattribution.  Bad servers
accumulate real failure counts quickly; FewestFailures deprioritises them even though their
failures are attributed to innocent servers.  This is a fundamentally different mechanism from
ScoredRemoval — it does not rely on the diagnosis pipeline at all.

**ThresholdRemoval is neutral-to-harmful at unc ≥ 0.80:**
`FewestFail+Thresh ≥2/7d` at unc=0.80 is +17 h (barely above baseline) and at unc=1.0 is
+157 h (harmful).  The reason: ThresholdRemoval reads `failure_timestamps` on the *server
entering repair*.  At unc=1.0, the server entering repair is always the innocent one, whose
timestamps reflect only its rare genuine failures.  ThresholdRemoval rarely triggers on
innocent servers, so it provides no benefit.  Meanwhile, the occasional early retirement of
an innocent server (based on accumulated misattributed "blame") makes the pool slightly worse.

**FewestFail+ScoredRemoval: last remaining benefit vanishes above unc = 0.60:**
At unc=0.40 this combination is −89 h (strong net benefit).  At unc=0.60 it is −2 h
(breakeven).  At unc=0.80 it is +63 h (net harm).  The crossover at unc≈0.60 is the practical
limit for this combination.

---

## 4  Revised practical guidance

### When to adjust `diagnosis_probability`  (uncertainty = 0)

| prob | Recommended policy | Rationale |
|------|--------------------|-----------|
| < 0.40 | FewestFail+Thresh ≥2/7d | ThresholdRemoval has signal via timestamps; ScoredRemoval blind to missed failures |
| 0.40–0.80 | FewestFail+ScoredRemoval | Breaks even at 0.40, delivers −84 to −86 h at 0.60–0.80 |
| ≥ 0.80 | Random+ScoredRemoval | At high probability Random maximises bad-server exposure → faster retirement |

### When to adjust `diagnosis_uncertainty`  (probability = 1)

| unc  | Recommended policy | Rationale |
|------|--------------------|-----------|
| 0.00 | Random+ScoredRemoval | Optimal: −160 h, low variance |
| ≤ 0.20 | FewestFail+ScoredRemoval | −105 h, stable ±38 h; ScoredRemoval still net-positive |
| 0.20–0.60 | FewestFail+ScoredRemoval or FewestFail+Thresh ≥2/7d | ScoredRemoval −89 h at 0.40, −2 h at 0.60 |
| ≥ 0.60 | FewestFail+NeverRemove | No retirement policy helps; FewestFail scheduling alone gives large benefit via actual failure counts |
| = 1.00 | **Avoid ScoredRemoval** | +736 h — actively harmful; retires innocent servers, keeps bad ones |

### Critical interactions revealed by the fix

- **ScoredRemoval inverts at high uncertainty:** `on_failure` is called on the wrong server.
  At unc ≥ 0.80, ScoredRemoval does more harm than no retirement policy at all.

- **FewestFailures is diagnosis-agnostic:** It uses raw `total_failure_count` (actual hardware
  failures, not attributed blame), making it the most robust scheduling policy under
  misattribution.  At unc=1.0 it saves 452 h vs. Random scheduling alone.

- **ThresholdRemoval's partial immunity breaks at high uncertainty:** It can leverage
  `failure_timestamps` (actual failures, not attributed blame) only for servers that enter
  repair.  At unc=1.0, only innocent servers enter repair, so ThresholdRemoval cannot act on
  the bad servers' timestamps.

---

## 5  Summary

```
Sweep A — diagnosis_probability (uncertainty = 0):  [UNCHANGED BY BUG FIX]
  Retirement breaks even at prob ≥ 0.40
  Best at prob = 1.0: Random+ScoredRemoval  −160 h

Sweep B — diagnosis_uncertainty (probability = 1):  [SIGNIFICANTLY CHANGED BY BUG FIX]

  Pre-fix: deadlocks at unc ≥ 0.40 (ScoredRemoval) and unc ≥ 0.60 (all policies)
  Post-fix: all simulations complete; qualitatively different behaviour revealed:

  unc = 0.00:  Random+ScoredRemoval  −160 h  (optimal)
  unc = 0.20:  FewestFail+ScoredRemoval  −105 h  (stable)
  unc = 0.40:  FewestFail+ScoredRemoval  −89 h
  unc = 0.60:  FewestFail+Thresh ≥2/7d  −18 h  (ScoredRemoval near-breakeven)
  unc = 0.80:  FewestFail+Thresh ≥2/7d  +17 h  (no policy gives net benefit)
  unc = 1.00:  FewestFail+NeverRemove   +136 h  (scheduling alone; retirement harmful)

  Key crossovers:
    ScoredRemoval net-negative:    unc > 0.60
    ThresholdRemoval net-negative: unc > 0.80
    FewestFail scheduling benefit: monotonically increases with uncertainty
```

**Practical bottom line:** if `diagnosis_uncertainty` cannot be kept below 0.60, retire
ScoredRemoval from the retirement policy and rely on FewestFailures scheduling alone.
Above unc = 0.80, no retirement policy produces net benefit — the priority is accurate
diagnosis, not smarter retirement.
