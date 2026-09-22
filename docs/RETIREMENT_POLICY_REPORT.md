# Retirement Policy Comparison Report
## ScoredRemoval vs ThresholdRemoval in Large-Scale AI Cluster Simulation

**Data:** `examples/scored_vs_threshold_figures/results.csv` (86 rows, 15 replications
per cell), produced by `examples/scored_vs_threshold.py` at commit `0cab8fb` (run log:
`examples/scored_vs_threshold_figures/run.log`). Repairs follow the paper's model:
`prob_auto_to_manual` is the probability that auto repair escalates, independent of the
silent auto-repair failure `auto_repair_fail_prob`. Date: 2026-09-21.

---

## 1. Executive Summary

This report compares two server retirement policies implemented in AIReSim —
`ThresholdRemoval` and `ScoredRemoval` — in the parameter regime where active
retirement is known to improve training time.

**Key findings:**

- `ScoredRemoval` outperforms `ThresholdRemoval` at every tested condition, with a lead
  that grows with severity: from ~30h at a 5× failure multiplier (z = 2.4) to **287h
  (11%) at 30×**, and from ~42h at a 20% manual repair fail probability to **377h (14%)
  at 90%**. At the regime's headline setting (20×, 75%) `SC_fast` saves **317h (13.2%)**
  against `ThresholdRemoval(≥2/7d)`'s 76h (3.2%). The best measured improvement over
  `NeverRemove` is **503h (19.3%)** at 90% repair fail probability.
- The win is not due to the uptime-credit mechanism. In any large-cluster job
  (≥ ~1000 servers), aggregate failures arrive far faster than any practical
  `time_period`, so credits are never earned. The policy degenerates to a
  **total lifetime failure count threshold** — a better discriminator than
  ThresholdRemoval's rolling window.
- `ThresholdRemoval`'s window is consistent with this result: `ThresholdRemoval(≥2/7d)`
  retires 106 servers where `ScoredRemoval` retires 390. A server that escapes a 7-day
  failure window (e.g., because it spent the week in the repair shop) is re-admitted to
  the pool still broken, while `ScoredRemoval`'s cumulative score remembers every past
  failure.
- The conservative `ThresholdRemoval(≥3/7d)` retires only 4–9 servers per run and has no
  measurable effect anywhere (−6.5h at the headline setting, z = 0.4); `≥1/7d` retires
  every server on its first failure and depletes the cluster in 100% of runs.
- The `success_increment` / `time_period` parameters are structurally inert at
  the 4096-server scale tested here. Meaningful uptime crediting would require
  either a cluster smaller than ~200 servers or a `time_period` set to match the
  typical inter-failure chunk duration (~5–10 minutes at this scale).

---

## 2. Simulation Regime

All experiments use the **retirement-payoff regime** identified in earlier
analysis (`examples/retirement_payoff.py`). Three conditions must hold
simultaneously for retirement to reduce training time:

| Parameter | Value | Notes |
|---|---|---|
| `working_pool_size` | 4600 | 488 headroom above job minimum (4112) |
| `spare_pool_size` | 200 | |
| `job_size` | 4096 | |
| `warm_standbys` | 16 | |
| `job_length` | 14 days (compute) | |
| `random_failure_rate` | 2× default | ~0.02 failures/day/good server |
| `systematic_failure_rate_multiplier` | 20× (baseline) | Bad server TTF ≈ 2.4 days |
| `systematic_failure_fraction` | 8% | 384 bad servers out of 4800 total |
| `recovery_time` | 60 min | Expensive checkpointing overhead |
| `auto_repair_fail_prob` | 0.60 | |
| `manual_repair_fail_prob` | 0.75 (baseline) | Effective fix rate ≈ 28% |
| `prob_auto_to_manual` | 0.80 | |
| Replications | 15 per data point | |

**Why this regime matters:** with a 28% effective fix rate, 72% of repaired
bad servers return to the pool still broken and resume failing every 2.4 days.
Each failure incurs 60 minutes of recovery overhead. Retiring the worst
offenders eliminates this recurring cost.

---

## 3. Policy Descriptions

### ThresholdRemoval

Retires a server if it accumulates **≥ N failures within any rolling time
window** (here: 7 days). Tested thresholds: 5, 3, 2, and 1 failure(s) per
7-day window.

```python
ThresholdRemoval(max_failures=2, window_minutes=7 * 24 * 60)
```

The window creates a **forgiveness mechanism**: failures older than 7 days are
forgotten. A server that fails twice, then successfully survives a full repair
without re-failing, is treated as clean.

### ScoredRemoval

Assigns each server an `initial_score`. On every failure the score decreases by
`failure_penalty`; after each uninterrupted run of length ≥ `time_period` the
score increases by `success_increment`. A server is retired when its score falls
to or below `retirement_threshold`.

Four configurations were tested, calibrated against the bad/good server TTF
ratio in this regime (2.4 days vs 50 days):

| Config | `initial_score` | `failure_penalty` | `success_increment` | `time_period` | Effective failures to retire |
|---|---|---|---|---|---|
| SC_fast | 100 | 60 | 10 | 1 day | 2 |
| SC_moderate | 100 | 50 | 15 | 1 day | 2 |
| SC_long_period | 100 | 50 | 10 | 4 days | 2 |
| SC_calibrated | 100 | 40 | 10 | 3 days | 3 |

> **Note on credit activation.** With 4096 active servers and a 20× failure
> multiplier, the aggregate failure arrival rate is ~0.15/minute, producing run
> chunks of ~7 minutes on average. Since `floor(7 min / time_period) = 0` for
> any `time_period` ≥ a few minutes, uptime credits are never earned in
> practice. The policy degenerates to a pure cumulative failure count:
> `ceil(initial_score / failure_penalty)` failures → retire. SC_fast,
> SC_moderate, and SC_long_period all compute to the same value (2 failures),
> producing identical results.

---

## 4. Head-to-Head Comparison (20× multiplier, 75% repair fail prob)

![Head-to-head policy comparison](../examples/scored_vs_threshold_figures/head_to_head.png)

**Effective Training Ratio (ETR)** = `job_length / total_training_time` = `336 hrs / training_time`.
ETR measures the fraction of wall-clock time spent on useful computation; overhead (recovery,
host selection, spare-pool waits) reduces it below 1.0.

| Policy | Mean Training Time (hrs) | ETR | Δ vs NeverRemove | Servers Retired | Depleted |
|---|---|---|---|---|---|
| NeverRemove | 2394.8 ± 48.9 | 14.0% | — | 0 | — |
| Thresh ≥5/7d | 2394.8 ± 48.9 | 14.0% | +0.0h | 0 | — |
| Thresh ≥3/7d | 2388.2 ± 47.4 | 14.1% | −6.5h | 4 | — |
| **Thresh ≥2/7d** | 2319.1 ± 53.6 | 14.5% | −75.6h | 106 | — |
| Thresh ≥1/7d | 1006.2 ± 79.5 | N/A† | −1388.5h | 699 | 100% depleted |
| **SC_fast / SC_moderate / SC_long_period** | 2077.7 ± 30.2 | 16.2% | −317.0h | 390 | — |
| SC_calibrated | 2232.3 ± 55.6 | 15.1% | −162.4h | 188 | — |

† ETR is not meaningful for depleted runs: the job did not complete, so compute time ≠ job_length.

**Best ThresholdRemoval:** Thresh ≥2/7d — saves 76h (3.2%), retires 106 servers.
**Best ScoredRemoval:** SC_fast/SC_moderate/SC_long_period — saves **317h (13.2%)**, retires 390 servers.
**Head-to-head winner: ScoredRemoval by 241h** (10.4% faster than ThresholdRemoval's best; z = 15).

**Why ScoredRemoval retires so many more servers (390 vs 106):**
`ThresholdRemoval(2/7d)` forgives failures older than 7 days. A bad server that
completes a long manual repair (2 days) and then happens not to fail for
another 5 days has its window reset — it's no longer a retirement candidate
despite being structurally unchanged. With a 72% non-fix rate, most servers
return from repair still broken and eventually re-accumulate failures, but each
window-reset gives them another reprieve.

`ScoredRemoval` accumulates failure count across the server's entire lifetime.
There is no forgiveness window. A bad server that has failed twice will
eventually be retired regardless of how long it goes between failures. This
catches the ~284 additional servers (390 − 106) that ThresholdRemoval lets
re-enter the pool after window resets.

**Why SC_calibrated is more conservative:** With penalty=40 and initial=100,
a server must fail **3 times** before retiring. Good servers (TTF ≈ 50 days)
rarely accumulate 3 failures in a 14-day simulation, so collateral damage is
lower. Training time (2232h, 188 retired) is better than NeverRemove but 155h worse
than the 2-failure configs.

---

The ETR difference between `NeverRemove` (14.0%) and the best `ScoredRemoval` config (16.2%)
is **+2.1 percentage points** — meaning ScoredRemoval reclaims 2.1% of wall-clock time
that NeverRemove wastes on avoidable repeat failures from bad servers.

---

## 5. Benefit vs Failure Rate Multiplier

![Training time benefit vs failure rate multiplier](../examples/scored_vs_threshold_figures/vs_multiplier.png)

| Multiplier | Bad TTF | NeverRemove (hrs) | ETR (NeverRemove) | Best Threshold Δ | Best Scored Δ | ETR (Best Scored) | Winner (lead) |
|---|---|---|---|---|---|---|---|
| 5× | 8.3 days | 1854.8 | 18.1% | −5.7h (≥2/7d) | **−36.2h** | 18.5% | Scored by 30.5h (z=2.4) |
| 10× | 4.5 days | 2093.1 | 16.1% | −22.0h (≥2/7d) | **−104.2h** | 16.9% | Scored by 82.2h (z=5.4) |
| 15× | 3.1 days | 2276.7 | 14.8% | −44.7h (≥2/7d) | **−251.0h** | 16.6% | Scored by 206.2h (z=15.3) |
| 20× | 2.4 days | 2394.8 | 14.0% | −75.6h (≥2/7d) | **−317.0h** | 16.2% | Scored by 241.4h (z=15.2) |
| 25× | 1.9 days | 2466.0 | 13.6% | −118.3h (≥2/7d) | **−366.7h** | 16.0% | Scored by 248.3h (z=19.8) |
| 30× | 1.6 days | 2551.8 | 13.2% | −181.8h (≥2/7d) | **−468.9h** | 16.1% | Scored by 287.2h (z=18.9) |

`z` is the lead divided by its standard error (unpaired, 15 replications per policy).
The 20× row is the same cell as §4.

ScoredRemoval leads at every multiplier tested. The lead is smallest at 5× (30h,
z = 2.4), where bad servers (TTF ≈ 8 days) fail about once per 7-day window and there
is little recurring damage to remove, and grows steadily with severity to 287h at 30×.
`ThresholdRemoval(≥2/7d)` also improves with severity (−6h at 5× to −182h at 30×) but
never closes the gap: as bad servers fail faster, more of them reach the 2-failure
threshold within a window, yet a substantial number still escape between windows.

**No crossover.** Unlike a regime where the two policies trade places, ScoredRemoval is
ahead everywhere in this sweep; the only question is by how much.

---

## 6. Benefit vs Manual Repair Fail Probability

![Training time benefit vs repair fail probability](../examples/scored_vs_threshold_figures/vs_repair_fail_prob.png)

| Repair fail prob | Effective fix rate | NeverRemove (hrs) | ETR (NeverRemove) | Best Threshold Δ | Best Scored Δ | ETR (Best Scored) | Winner (lead) |
|---|---|---|---|---|---|---|---|
| 0.2 | 72% | 1953.9 | 17.2% | −2.4h (≥2/7d) | **−43.9h** | 17.6% | Scored by 41.5h (z=4.3) |
| 0.4 | 56% | 2060.2 | 16.3% | −23.7h (≥2/7d) | **−71.9h** | 16.9% | Scored by 48.3h (z=3.6) |
| 0.6 | 40% | 2231.2 | 15.1% | −68.6h (≥2/7d) | **−200.5h** | 16.5% | Scored by 131.9h (z=11.5) |
| 0.75 | 28% | 2394.8 | 14.0% | −75.6h (≥2/7d) | **−317.0h** | 16.2% | Scored by 241.4h (z=15.2) |
| 0.9 | 16% | 2612.3 | 12.9% | −126.5h (≥2/7d) | **−503.3h** | 15.9% | Scored by 376.9h (z=21.6) |

Both policies benefit more as repair quality degrades. The ScoredRemoval lead grows
monotonically with fail probability, from 42h at 20% (72% effective fix rate) to 377h
at 90% (16% fix rate).

**Interpretation:** At high fix rates (72%), many bad servers are genuinely healed
after repair, so there is less for retirement to remove: ScoredRemoval still saves
44h (2.2%, z = 3.7) while ThresholdRemoval's effect is indistinguishable from zero
(−2.4h, z = 0.2). Even "fixed" servers carry residual random failure rate, and
ScoredRemoval retires 255 servers here against ThresholdRemoval's 40, so some of its
retirements are of servers that would have been fine — but the cost is small because
the pool has 488 servers of headroom. At low fix rates (16%), almost no server is
genuinely healed and ScoredRemoval's aggressive total-count approach is clearly correct.

---

## 7. Structural Finding: The Credits Mechanism

### Why uptime credits are inert at scale

The `success_increment` / `time_period` parameters are designed to reward
servers for sustained fault-free operation. In practice, with a job running on
4096 servers, the **aggregate** failure arrival rate determines chunk length —
not any individual server's rate.

At the baseline regime (20× multiplier):

```
Aggregate rate ≈ (326 bad servers × 21 × rate) + (3770 good × 2 × rate)
               ≈ 0.147 failures/minute
→ Mean chunk duration ≈ 6.8 minutes
```

For any `time_period` longer than ~7 minutes, `floor(chunk / time_period) = 0`
and no credits are ever awarded. The three SC configs with `time_period` of 1
day, 4 days, and 3 days are all equally inert and produce byte-for-byte
identical results.

### Effective policy equivalence

Without credits, `ScoredRemoval` reduces to:

```
retire_after_N_failures  where  N = ceil(initial_score / failure_penalty)
```

This is a **lifetime failure count threshold** — equivalent to ThresholdRemoval
with an **infinite window** (no forgetting). The table below maps each config
to its equivalent N:

| ScoredRemoval config | `initial_score / failure_penalty` | Effective N |
|---|---|---|
| SC_fast | 100 / 60 = 1.67 | 2 |
| SC_moderate | 100 / 50 = 2.00 | 2 |
| SC_long_period | 100 / 50 = 2.00 | 2 |
| SC_calibrated | 100 / 40 = 2.50 | 3 |

### When would credits activate?

Credits become active when the typical run chunk duration exceeds `time_period`.
For a job of size N using exponential failures at aggregate rate λ:

```
mean_chunk = 1 / λ
credits activate when: time_period < 1 / λ
```

For `time_period = 1 day (1440 min)`:

```
1/λ > 1440  →  λ < 0.00069 failures/min
→ N × per_server_rate < 0.00069
→ N < 0.00069 / (2 × DEFAULT_RATE) ≈ 50 servers
```

Credits are only meaningful for clusters smaller than ~50 servers with a 1-day
`time_period`, or ~1200 servers with a 1-hour `time_period`. For production
AI training at the 4096-server scale, the uptime credit mechanism requires
`time_period` to be set to the order of minutes (matching the actual chunk
duration) to have any discriminating effect.

---

## 8. Summary of Conditions Where ScoredRemoval Outperforms ThresholdRemoval

| Condition | Threshold wins | Scored wins | Reason |
|---|---|---|---|
| Repair fix rate ≥ 72% (fail prob 0.2) | — | By 42h (z = 4.3); small absolute benefit (44h vs NeverRemove) | Little recurring damage to remove; Threshold has no measurable effect |
| Repair fix rate ≤ 56% (fail prob ≥ 0.4) | — | Decisively (48–377h) | Non-fixing repairs make window-forgetting counterproductive |
| Failure multiplier ≥ 10× | — | Decisively (82–287h) | Fast-failing bad servers need no window to accumulate — window only delays retirement |
| Failure multiplier 5× | — | By 30h (z = 2.4) | Modest but positive; bad servers fail about once per window |
| Pool headroom < ~100 servers | Either can deplete | Either can deplete | Aggressive strategies risk depletion (`Thresh ≥1/7d` depletes 100% of runs even with 488 headroom) |

**Practical guidance:**

- Use `ScoredRemoval` (2 failures = `penalty = initial_score / 2`) in regimes
  with **high failure multipliers (≥10×) or high repair fail probabilities
  (≥40%)**. It will consistently outperform ThresholdRemoval, by 48–377h in this regime.
- Prefer `SC_calibrated` (3 failures) when pool headroom is moderate — it
  retires half as many servers (188 vs 390, safer) and still beats ThresholdRemoval's
  best by 87h at the headline setting.
- `ThresholdRemoval(≥2/7d)` is a milder alternative that retires far fewer servers but
  captures only about a quarter of `ScoredRemoval`'s benefit at the headline setting;
  `≥3/7d` has no measurable effect and `≥1/7d` is unusable.
- The `success_increment` and `time_period` parameters provide no benefit at
  the 4096-server scale tested. To activate them, set `time_period` to match
  the actual mean chunk duration (~5–10 minutes in this regime) with a small
  `success_increment` relative to `failure_penalty`.

---

## 9. Bugs Found and Fixed During This Analysis

Two bugs were uncovered while running these experiments:

### Bug 1: ScoredRemoval state leaked across replications

**Symptom:** When the same `ScoredRemoval` instance was reused across multiple
`Simulator.run()` calls (as is common in replication loops), server scores from
replication N were carried into replication N+1 via `_scores[server_id]`. Since
server IDs are reused across runs, servers in later replications started below
`initial_score` and were retired on their first failure regardless of actual
behavior.

**Fix:** `Simulator.run()` now calls `removal_policy.reset()` at the start of
each run. `ScoredRemoval.reset()` clears `_scores`. A no-op default is
provided in the `ServerRemovalPolicy` base class so all existing policies are
unaffected.

### Bug 2: Simulation stalled when all repairs resulted in retirement

**Symptom:** When a retirement policy was so aggressive that every repaired
server was retired (e.g., `ScoredRemoval` with `initial_score=25,
failure_penalty=30`), the repair shop's `_signal_repaired()` was never called
(it was only called when a server was *returned* to the pool). The main loop
waited indefinitely on `server_repaired_event`. When SimPy exhausted all
remaining events (all repair timeouts completed, retiring servers), `env.run()`
returned silently with `total_training_time = 0` and `cluster_depleted = False`
— a silent incorrect result.

**Fix:** `RepairShop._repair_process()` now calls `_signal_repaired()` on both
the retirement and return branches. The main loop wakes up after each retirement
and re-checks the depletion guard, which then correctly sets
`cluster_depleted = True` and records the actual simulation time.

---

*Generated by `examples/scored_vs_threshold.py` — AIReSim v0.1.0, regenerated 2026-09-21*
