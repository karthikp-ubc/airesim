# Scheduling × Retirement Policy Comparison
## Does Smarter Scheduling Help — or Hurt?

**Data:** `examples/scheduling_comparison_figures/results.csv` (9 cells × 15 replications),
produced by `examples/scheduling_comparison.py` at commit `0cab8fb`; per-replication rows
(seed, full params, host_selection_count, systematic/random failures, faulty servers in
pool) re-logged at commit `da28d04` into
`examples/scheduling_comparison_figures/replications.csv`, same seeds, results unchanged
(run log: `examples/scheduling_comparison_figures/run.log`). Repairs follow the paper's
model: `prob_auto_to_manual` is the probability that auto repair escalates, independent
of the silent auto-repair failure `auto_repair_fail_prob`. Date: 2026-09-21.

---

> **Design caveat (2026-09-21).** In AIReSim the scheduling policy is consulted
> only at full host selection. Warm-standby swaps take the oldest standby
> (`Scheduler.swap_in_standby`) without consulting the policy, and repaired
> servers that were in the job return to the standby list regardless of failure
> history. The `FewestFailuresFirst`/`HighestScoreFirst` results below therefore
> measure the policy's effect at the host selections that happen when the job
> exhausts its warm standbys. They do not measure health-aware replacement as an
> operator would implement it. This sweep now records host_selection_count per
> replication (§below): 6.7–7.3 per run for `NeverRemove` policies and 24.9–27.7 for
> `ScoredRemoval` in this (elevated-failure, 14-day) regime — still small next to the
> ~1,450–2,800 failures per run here. At **paper-semantics defaults** (not this
> sweep's regime) full host selection happens about 41 times per run against
> ~11,000 failures (`SIMULATION_REPORT.md`; a similar sweep with realistic diagnosis
> gets 37.7, `DIAGNOSIS_REALISTIC_REPORT.md`). `FewestFailuresFirst` here also reads
> ground-truth failure counts (see `DIAGNOSIS_REALISTIC_REPORT.md` for the
> attributed-count variant).

## 1. Executive Summary

This report tests all 3×3 = 9 combinations of scheduling policy and retirement policy
in the payoff regime (20× failure multiplier, 75% manual repair fail probability,
4600-server pool).

**Key findings:**

- **`FewestFailuresFirst` and `HighestScoreFirst` are effectively identical** in this
  regime. They produce byte-for-byte matching training times across all retirement
  policies. The reason is structural: with credits inert at 4096-server scale,
  `ScoredRemoval` scores reduce to a monotone transformation of total failure count,
  so both policies impose the same ordering.

- **Smart scheduling alone (no retirement) saves 272h (11.4%)** by avoiding bad
  servers in the active job. It is the largest single lever short of `ScoredRemoval`,
  and requires no retirements and no disruption to the pool.

- **The `ScoredRemoval` combinations are statistically tied for best.**
  `FewestFailures/HighestScore + ScoredRemoval` reaches −328.9h against
  `Random + ScoredRemoval` at −317.0h. The 11.9h gap is about one standard error
  (≈11h), so neither should be called the single best combination. The smart-scheduling
  version retires 336 servers rather than 390.

- **Retirement adds less once smart scheduling is in place, but is still worth
  something.** Adding `ScoredRemoval` to smart scheduling saves a further 56.6h;
  adding `ThresholdRemoval(≥2/7d)` saves a further 32.1h (about two standard errors).

- **The two levers are substitutable, not additive.** Smart scheduling and aggressive
  retirement each attack the bad-server problem by a different mechanism, and together
  they achieve 56% of the sum of their separate effects for `ScoredRemoval`
  (−329h against −589h) and 87% for `ThresholdRemoval`.

---

## 2. Simulation Regime

| Parameter | Value |
|---|---|
| `working_pool_size` | 4600 (488 above minimum 4112) |
| `spare_pool_size` | 200 |
| `job_size` | 4096 |
| `warm_standbys` | 16 |
| `job_length` | 14 days |
| `systematic_failure_rate_multiplier` | **20×** (bad TTF ≈ 2.4 days) |
| `systematic_failure_fraction` | 8% (≈ 368 bad servers) |
| `recovery_time` | 60 min |
| `prob_auto_to_manual` | 0.80 |
| `auto_repair_fail_prob` | 0.60 |
| `manual_repair_fail_prob` | 0.75 (effective fix rate ≈ 28%) |
| Replications | 15 per cell |

**Baseline (Random + NeverRemove): 2394.8 ± 48.9 hrs**
**Baseline ETR: 336 / 2394.8 = 14.0%** (job_length = 14 days = 336 hrs)

---

## 3. Full Results Table

ETR = 336 / mean_training_time. Higher ETR = more productive compute per wall-clock hour.

| Scheduling | Retirement | Mean (hrs) | ETR | Std | Δ vs baseline | Retired |
|---|---|---|---|---|---|---|
| Random | NeverRemove | 2394.8 | 14.0% | ±48.9 | 0.0h | 0 |
| Random | Thresh ≥2/7d | 2319.1 | 14.5% | ±53.6 | −75.6h | 106 |
| Random | ScoredRemoval | 2077.7 | 16.2% | ±30.2 | −317.0h | 390 |
| FewestFailures | NeverRemove | 2122.5 | 15.8% | ±45.2 | −272.3h | 0 |
| FewestFailures | Thresh ≥2/7d | 2090.4 | 16.1% | ±40.4 | −304.4h | 68 |
| **FewestFailures** | **ScoredRemoval** | **2065.9** | **16.3%** | **±30.4** | **−328.9h** | **336** |
| HighestScore | NeverRemove | 2122.5 | 15.8% | ±45.2 | −272.3h | 0 |
| HighestScore | Thresh ≥2/7d | 2090.4 | 16.1% | ±40.4 | −304.4h | 68 |
| HighestScore | ScoredRemoval | 2065.9 | 16.3% | ±30.4 | −328.9h | 336 |

Per-cell standard errors are ≈8–14h (stdev ÷ √15). No cell was depleted.

---

## 3a. Host Selection Activity

Mean full host-selection events per run, from `replications.csv` (15 replications/cell):

| Scheduling | Retirement | Mean host selections |
|---|---|---|
| Random | NeverRemove | 7.3 |
| Random | Thresh ≥2/7d | 13.1 |
| Random | ScoredRemoval | 27.7 |
| FewestFailures | NeverRemove | 6.7 |
| FewestFailures | Thresh ≥2/7d | 11.1 |
| FewestFailures | ScoredRemoval | 24.9 |
| HighestScore | NeverRemove | 6.7 |
| HighestScore | Thresh ≥2/7d | 11.1 |
| HighestScore | ScoredRemoval | 24.9 |

Retirement drives most of the host-selection activity here (7 → 28 as retirement gets
more aggressive), not the scheduling policy — `FewestFailuresFirst`/`HighestScoreFirst`
act at slightly *fewer* host selections than `Random` because they route jobs away from
recently-failed servers, which are also the ones most likely to fail again and trigger
the next selection. In every column, host selections (7–28) remain far below the
~1,450–2,800 failures per run this regime produces (§5.1-equivalent counts in the raw
data), so §6–9's findings for `FewestFailuresFirst`/`HighestScoreFirst` describe the
policy's effect at a small fraction of all replacement events, per the design caveat above.

---

## 4. Visualisations

### 4.1 Heatmap

![3×3 heatmap of Δ training time and servers retired](../examples/scheduling_comparison_figures/heatmap.png)

### 4.2 Grouped by Retirement Policy

![Bar chart grouped by retirement policy](../examples/scheduling_comparison_figures/bars_by_retirement.png)

### 4.3 Grouped by Scheduling Policy

![Bar chart grouped by scheduling policy](../examples/scheduling_comparison_figures/bars_by_scheduling.png)

---

## 5. ETR Summary

ETR ranges from **14.0%** (Random + NeverRemove, baseline) to **16.3%**
(`FewestFailures + ScoredRemoval`) — a spread of **+2.2 percentage points** across the
nine combinations.

| Strategy | ETR | Interpretation |
|---|---|---|
| Random + NeverRemove (baseline) | 14.0% | 86.0% of time lost to failure overhead |
| Smart scheduling alone (+NeverRemove) | 15.8% | +1.8 pp from avoiding bad servers |
| Random + ThresholdRemoval | 14.5% | +0.5 pp from retirement alone |
| Random + ScoredRemoval | 16.2% | +2.1 pp from retirement alone |
| Smart scheduling + ThresholdRemoval | 16.1% | +2.0 pp |
| **Smart scheduling + ScoredRemoval** | **16.3%** | **+2.2 pp — tied with Random + ScoredRemoval** |

Combining smart scheduling with `ScoredRemoval` (16.3%) is not distinguishable from
`ScoredRemoval` alone (16.2%). Smart scheduling alone (15.8%) recovers most of the same
gain with no retirements.

---

## 6. Finding 1 — FewestFailuresFirst ≡ HighestScoreFirst in This Regime

The two non-random scheduling policies produce identical results (to the last decimal
place) across all three retirement policies.

**Reason:** `HighestScoreFirst` ranks servers by descending `ScoredRemoval` score.
`ScoredRemoval` score = `initial_score − failure_penalty × total_failures + credits`.
From the retirement policy analysis, uptime credits are **inert** at 4096-server scale
(mean run chunk ≈ 7 minutes; `time_period = 1 day`). Without credits:

```
score = initial_score − failure_penalty × total_failures
      = 100 − 60 × total_failures
```

This is a strictly decreasing linear function of `total_failures`. Ranking by
descending score is therefore identical to ranking by ascending failure count — exactly
what `FewestFailuresFirst` does. The two policies impose the same ordering on every
host-selection call, so simulation outcomes are identical.

**Consequence:** At 4096-server scale, `HighestScoreFirst` adds no information beyond
`FewestFailuresFirst`. Meaningful score-based differentiation from `FewestFailuresFirst`
would require either:
- Activating credits (set `time_period` to a few minutes), so that uptime history
  provides information beyond raw failure count, or
- A cluster small enough that individual servers have long uninterrupted run chunks.

---

## 7. Finding 2 — Smart Scheduling Without Retirement Saves 272h

Both `FewestFailuresFirst` and `HighestScoreFirst` with `NeverRemove` save **272.3h**
(11.4%) compared to `Random + NeverRemove` (2122.5h vs 2394.8h).

**Mechanism:** With ~368 bad servers in the pool (each failing every 2.4 days), random
selection assigns bad servers to the active job in proportion to their pool fraction
(~8%). Non-random selection pushes them to the back of the selection list. If there are
enough good servers to fill the 4112-server job without touching the bad ones, bad
servers sit idle and fail less often. Each avoided failure saves 60 minutes of
checkpoint recovery overhead. By the design caveat above, this operates only at the
host selections that occur when the job exhausts its warm standbys.

This is the **scheduling defence**: avoid using bad servers rather than removing them.
At 8% bad fraction and 4600-server pool, there are enough good servers (4232 good) to
comfortably staff the job (4112 needed), so the bad servers are effectively benched.

---

## 8. Finding 3 — The `ScoredRemoval` Combinations Are Tied for Best

`Random + ScoredRemoval` reaches **2077.7h** (−317.0h vs baseline).
`FewestFailures/HighestScore + ScoredRemoval` reaches **2065.9h** (−328.9h). The 11.9h
difference is about one standard error (≈11h), so the two are statistically
indistinguishable. Neither should be called the single best combination.
`FewestFailures + ThresholdRemoval` (−304.4h) is also within about one standard error
of both.

| Combination | Δ vs baseline | Retired |
|---|---|---|
| FewestFailures + ScoredRemoval | −328.9h | 336 |
| HighestScore + ScoredRemoval | −328.9h | 336 |
| Random + ScoredRemoval | −317.0h | 390 |
| FewestFailures + ThresholdRemoval | −304.4h | 68 |
| HighestScore + ThresholdRemoval | −304.4h | 68 |
| FewestFailures + NeverRemove | −272.3h | 0 |
| HighestScore + NeverRemove | −272.3h | 0 |
| Random + ThresholdRemoval | −75.6h | 106 |

Smart scheduling does change *how many* servers `ScoredRemoval` has to retire: 336
instead of 390 for the same training time.

---

## 9. Finding 4 — Smart Scheduling and Retirement Overlap

Adding smart scheduling to `ScoredRemoval` changes training time by −11.9h (within
noise); adding smart scheduling to `ThresholdRemoval` saves 228.8h. In the other
direction, adding `ScoredRemoval` to smart scheduling saves 56.6h and adding
`ThresholdRemoval` saves 32.1h.

| Combination pair | Δ (h) |
|---|---|
| Adding smart scheduling to `ScoredRemoval` | −11.8 (≈ noise) |
| Adding smart scheduling to `ThresholdRemoval` | −228.8 |
| Adding `ScoredRemoval` to smart scheduling | −56.6 |
| Adding `ThresholdRemoval` to smart scheduling | −32.1 |

**Why the levers overlap:** `ScoredRemoval(SC_fast)` retires a server after 2 cumulative
failures. Retirement works by removing bad servers, and smart scheduling works by
keeping bad servers out of the active job. Both act on the same population, so once
one has dealt with most of them the other has less left to do. Smart scheduling can also
delay retirement: a bad server that is rarely assigned to the job accumulates failures
slowly, so it takes longer to reach the 2-failure threshold. The data show no net
penalty from that delay — combined and retirement-only results are tied — but they do
show the overlap.

---

## 10. The Decomposition of Savings

| Strategy | Δ vs Random+NeverRemove |
|---|---|
| Smart scheduling alone (FewestFailures/HighestScore + NeverRemove) | −272h |
| Retirement alone: ThresholdRemoval (Random) | −76h |
| Retirement alone: ScoredRemoval (Random) | −317h |
| Smart scheduling + ThresholdRemoval | −304h |
| Smart scheduling + ScoredRemoval | −329h |
| **Expected additive, Threshold (272 + 76 = 348h)** | 304h achieved (87%) |
| **Expected additive, Scored (272 + 317 = 589h)** | 329h achieved (56%) |

Smart scheduling and `ScoredRemoval` together save 329h — far below the 272 + 317 = 589h
one might naively expect, because the two levers remove much of the same damage.
`ThresholdRemoval` retires so few servers on its own (−76h) that its combination with
smart scheduling is close to additive (87%).

---

## 11. Practical Guidance

| Goal | Recommended combination | Rationale |
|---|---|---|
| Maximum training speed | `FewestFailures + ScoredRemoval(SC_fast)` or `Random + ScoredRemoval(SC_fast)` | Statistically tied (−329h / −317h); the smart-scheduling version retires 54 fewer servers |
| Avoid retirements entirely | `FewestFailures + NeverRemove` | Saves 272h purely via scheduling; zero pool disruption |
| Moderate retirement with scheduling boost | `FewestFailures + ThresholdRemoval(2/7d)` | Balanced: 304h savings, 68 retirements |
| Safety-first with headroom concern | `FewestFailures + NeverRemove` | No retirements, still saves 272h |

**When to use `HighestScoreFirst`:** At production scale (≥1000 servers), only when
`time_period` is set to minutes (matching actual run-chunk length) so that uptime history
genuinely differentiates servers from their failure count. With `time_period ≥ 1 hour`,
`HighestScoreFirst` is indistinguishable from `FewestFailuresFirst`.

---

*Generated by `examples/scheduling_comparison.py` — AIReSim v0.1.0, regenerated 2026-09-21.*
