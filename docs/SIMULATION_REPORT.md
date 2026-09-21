# AIReSim Simulation Report

**Configuration:** `config.yaml` (paper Table 1 defaults)
**Date:** 2026-09-20 (regenerated)
**Mode:** Adaptive replication — 95% CI, ±5% relative accuracy

> **Regenerated after a bug fix.** The original 2026-04-02 run predates a fix to
> `RepairShop._repair_process`: the injected `RepairEscalationPolicy` was constructed
> but never consulted, so escalation to manual repair fired for a fixed
> `prob_auto_to_manual` (80%) fraction of **all** auto repairs, including ones that
> had already succeeded. The fix only escalates auto repairs that actually failed.
> See `CHANGELOG.md` ("injected `RepairEscalationPolicy` was never consulted") for
> the full write-up. Every number below reflects the corrected behavior; nothing
> else in `config.yaml` changed.

---

## 1. Convergence Summary

The adaptive runner converged at the **minimum 30 replications**, indicating that
the configuration produces low variance relative to the mean — a hallmark of a
well-calibrated, stable cluster model.

| Metric | Value |
|--------|-------|
| Replications run | 30 |
| Convergence status | **CONVERGED** |
| Cluster depletion events | 0 / 30 |
| Confidence level | 95% |
| Target relative accuracy | ±5.0% of mean |
| **Achieved relative accuracy** | **±0.12% of mean** |
| 95% CI half-width | ±11.96 hrs |
| Mean training time | 9,832.32 hrs |

The achieved accuracy of ±0.12% is over 40× tighter than the ±5% target, confirming
that 30 replications are more than sufficient for this parameter configuration.

---

## 2. Training Time

The **ideal training time** (zero failures, no overhead) at the configured job
length of 256 days is **6,144 hrs**. Failures and their downstream costs inflate
this to nearly 9,832 hrs — about 34 hrs *faster* than the pre-fix figure (9,865.97
hrs), purely because the repair pipeline no longer wastes manual-repair time on
auto repairs that already succeeded.

| Statistic | Value (hrs) |
|-----------|------------|
| Ideal (no failures) | 6,144.00 |
| Mean total training time | 9,832.32 |
| Std deviation | 32.02 |
| Min (best run) | 9,768.20 |
| Max (worst run) | 9,907.33 |
| Run-to-run range | 139.13 |
| **Slowdown factor** | **1.60×** |
| **Total overhead** | **3,688.32 hrs (37.5%)** |
| **Effective Training Ratio (ETR)** | **62.5%** |

The cluster consistently finishes the job in **9,770–9,910 hrs** (407–413 days),
a tight band that reflects the low variance across replications.

---

## 3. Effective Training Ratio (ETR)

The **Effective Training Ratio** measures the fraction of total wall-clock time
that the cluster spends doing useful computation:

```
ETR = total_compute_time / total_training_time
```

An ETR of 1.0 means every minute of clock time advances the job; lower values
indicate time lost to failures and their downstream costs.

| Statistic | Value |
|-----------|-------|
| Mean ETR | **0.6249 (62.5%)** |
| Std deviation | 0.0020 |
| Min (worst run) | 0.6201 (62.0%) |
| Max (best run) | 0.6290 (62.9%) |
| Run-to-run range | 0.0088 |

The ETR is **very stable** across replications (CV = 0.33%), reflecting that
each run experiences roughly the same total number of failures and therefore
the same aggregate recovery burden.  The ~0.9 percentage-point spread between
the best and worst run corresponds to the same ~139 hrs training-time range
above — compute time is fixed at 6,144 hrs in every replication, so ETR here
is purely a decreasing function of training time.

An ETR of 62.5% means **37.5% of cluster time is wasted on non-productive
work** — almost entirely checkpoint reloading after failures.

---

## 4. Time Breakdown

Every minute of wall-clock time falls into one of four categories:

| Component | Mean (hrs) | Fraction of total | Contributes to ETR? |
|-----------|-----------|-------------------|---------------------|
| Compute (job progress) | 6,144.00 | 62.5% | Yes (numerator) |
| Recovery (checkpoint reload) | 3,687.33 | 37.5% | No |
| Host selection & job restart | 0.99 | 0.01% | No |
| Waiting for spare pool | 0.00 | 0.00% | No |
| **Total training time** | **9,832.32** | 100% | (denominator) |

**Recovery time still dominates the overhead, at 37.5% of total wall-clock time.**
With 11,062 failures per run (down slightly from the pre-fix 11,145.6 — see
§5) and a 20-minute checkpoint reload per failure, recovery accumulates to
3,687 hrs — still over 153 additional days on top of the ideal 256-day run.
Recovery time is a fixed per-failure cost, so it barely moved: this fix
changes *how* a failure is repaired, not *how many* checkpoint reloads the
job pays for.

Host-selection time is negligible (0.01%), and **spare-pool wait time dropped
to exactly zero across all 30 replications** (was 0.05%, ~4.6 hrs, pre-fix).
See §7 for why.

---

## 5. Failure Analysis

### 4.1 Total failures

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Total failures | 11,062.0 | 96.1 | 10,869 | 11,287 |
| Random failures | 10,455.2 | 93.5 | 10,249 | 10,667 |
| Systematic failures | 606.8 | 14.1 | 579 | 636 |

**Random failures account for 94.5% of all failures**; systematic failures
(from the 15% "bad" servers) account for the remaining 5.5% — down from 6.2%
pre-fix. Bad servers still fail at 5× the baseline rate, but the corrected
repair pipeline actually *cures* more of them: the overall repair success rate
rose from 76.0% to 85.7% (§6), so fewer servers remain persistently bad across
the run, and the systematic-failure share shrinks along with the population
generating it.

### 4.2 Inter-failure intervals

| Metric | Value |
|--------|-------|
| Mean run duration between failures | 33.32 min |
| Std dev | 0.29 min |
| Min observed | 32.66 min |
| Max observed | 33.92 min |

A system-level failure (any server) occurs approximately **every 33 minutes**
on average — roughly twice per hour throughout the 9,832-hour run.

---

## 6. Repair Pipeline

All 11,062 failures per run enter the two-stage repair pipeline.

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Auto-repair attempts | 11,062.0 | 96.1 | 10,869 | 11,287 |
| Escalated to manual repair | 3,538.6 | 46.5 | 3,410 | 3,637 |
| Successful repairs | 9,475.6 | 96.6 | 9,231 | 9,658 |
| Failed repairs | 1,586.4 | 40.4 | 1,488 | 1,643 |
| Servers retired | 0 | — | 0 | 0 |

### Key repair ratios

| Ratio | Value | Interpretation |
|-------|-------|----------------|
| Escalation rate | 32.0% | Only auto repairs that actually failed can escalate now — see below |
| Overall repair failure rate | 14.3% | Down from 24.0% pre-fix — 1 in 7 repairs leaves the server faulty, not 1 in 4 |
| No servers retired | 0% | Default `NeverRemove` policy; all repaired servers are reintegrated |

Both ratios moved because of the escalation-policy fix, and both are now
derivable directly from `config.yaml`'s repair parameters instead of
matching them by coincidence:

- **Escalation rate = `auto_repair_fail_prob` × `prob_auto_to_manual`
  = 0.40 × 0.80 = 32.0%**, matching the measured rate exactly. Pre-fix, the
  escalation coin flip ignored the auto-repair outcome entirely, so the rate
  was simply `prob_auto_to_manual` = 80.1% — more than double, because ~60% of
  the servers it sent to manual repair didn't need to be there.
- **Overall repair failure rate = `auto_repair_fail_prob` × [`prob_auto_to_manual`
  × `manual_repair_fail_prob` + (1 − `prob_auto_to_manual`) × 1]
  = 0.40 × [0.80×0.20 + 0.20×1] = 14.4%**, matching the measured 14.3% within
  rounding. Pre-fix this was 24.0%, because a server whose auto repair had
  already succeeded could still be randomly escalated and then fail the
  *unrelated* manual-repair coin flip — a server the pipeline had already
  fixed could be "un-fixed" by a repair stage it never needed.

These "silent-fail" repairs — now 14.3% of all repairs instead of 24.0% —
still return servers to the pool that will fail again soon, but there are
fewer of them, which is the direct cause of the ~0.75% drop in total failures
noted in §5.

---

## 7. Scheduling and Pool Activity

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Host-selection events | 19.8 | 2.5 | 15 | 25 |
| Spare-pool preemptions | 0.0 | 0.0 | 0 | 0 |
| Job stalls | 0 | — | 0 | 0 |

- **Host-selection events (19.8)** are far fewer than total failures (11,062)
  and less than half the pre-fix count (42.9) — warm standbys now absorb
  99.82% of failures with an immediate in-place swap (up from 99.6%
  pre-fix), because fewer manual repairs means the working pool spends less
  time thin enough to force a full host-selection round-trip.
- **Spare-pool preemptions dropped from ~14 per run to exactly zero across
  all 30 replications.** Manual repair (`manual_repair_time = 2,880 min`,
  2 days) takes 24× longer than auto repair (120 min), so cutting the
  escalation rate from 80.1% to 32.0% (§6) removes a large amount of
  cumulative time servers spend absent from the working pool. Pre-fix, that
  extra time-in-repair occasionally thinned the pool below the 48-server
  headroom above `total_servers_needed`, forcing a preemption from the
  200-server spare pool; post-fix, the headroom is never exhausted at this
  configuration, so the spare pool goes unused.
- **Zero job stalls** — the cluster never ran out of both working and spare
  servers simultaneously.  The configuration has adequate combined capacity.

---

## 8. Statistical Quality

| Metric | Value |
|--------|-------|
| Replications | 30 |
| Mean training time | 9,832.32 hrs |
| Standard deviation | 32.02 hrs |
| Coefficient of variation | 0.33% |
| 95% CI | [9,820.37, 9,844.28] hrs |
| CI half-width | ±11.96 hrs |
| Relative half-width | **±0.12%** |

The coefficient of variation (CV) of 0.33% is exceptionally low, explaining
why 30 replications are sufficient to produce a CI over 40× tighter than the
±5% target.  The low CV reflects the **law of large numbers operating within
each replication**: with ~11,000 independent failure events per run, the
within-run randomness averages out, leaving very little run-to-run variance.

---

## 9. Key Findings

1. **ETR of 62.5% — over a third of cluster time is still non-productive.**
   The Effective Training Ratio sits at 0.6249 across all 30 replications,
   with very low variance (CV = 0.33%). This is essentially unchanged from
   the pre-fix 62.3%: recovery time, not the repair pipeline, is what mostly
   determines ETR at this configuration. Improving ETR is still the primary
   lever for reducing total training time; every 1 percentage-point gain
   saves ~100 hrs of wall-clock time at this cluster scale.

2. **Failure recovery is still the dominant overhead.** At 37.5% of total
   time, checkpoint-reload latency (`recovery_time = 20 min`) accounts for
   virtually all slowdown — the escalation-policy fix changes *which* repair
   stage a server visits, not how many times the job pays the fixed
   `recovery_time` cost per failure. Halving `recovery_time` would still
   reduce total training time by roughly ~1,844 hrs (~19%).

3. **The repair pipeline is measurably less leaky than previously measured.**
   The net repair failure rate is 14.3%, not the pre-fix 24.0% — that 24.0%
   figure was itself an artifact of the bug (successfully auto-repaired
   servers could still be randomly escalated and then fail an unrelated
   manual-repair check). The pipeline was never as leaky as the original
   report suggested; `auto_repair_fail_prob` and `manual_repair_fail_prob`
   remain the levers for reducing it further.

4. **Warm standbys work even better than previously measured.** With only
   19.8 host-selection events across 11,062 failures, the 16-server
   warm-standby reserve absorbs 99.82% of failures with zero scheduling
   overhead (up from a measured 99.6% pre-fix).

5. **The spare pool is now completely unused at this configuration.** Zero
   preemptions across all 30 replications, down from ~14 per run pre-fix
   (§7) — a direct, mechanical consequence of the fix, not a new insight
   about the cluster. The 200-server spare pool remains valuable as a safety
   margin for regimes with more or longer failures; it just isn't exercised
   here.

6. **The cluster never depletes.** Zero stalls and zero depletion events across
   all 30 replications confirm the configuration has sufficient resilience for
   the modelled failure rates and repair durations.

7. **Systematic failures are an even smaller contributor than previously
   measured.** Bad servers (15% of the pool, failing 5× faster) generate
   5.5% of total failures, down from 6.2% pre-fix — because the corrected
   pipeline cures more bad servers on the first attempt (repair success rate
   85.7% vs. 76.0% pre-fix; §6), leaving fewer persistently-bad servers in
   the pool over the run. Increasing `systematic_failure_fraction` or
   `systematic_failure_rate_multiplier` would still shift this balance.

8. **Total training time is ~34 hrs (0.34%) faster than the pre-fix figure,
   purely from removing a modeling bug.** This number should not be read as
   an infrastructure improvement, and pre- and post-fix sweeps should not be
   compared directly — any report generated before this fix used a repair
   pipeline that escalated far more often than `config.yaml` actually
   specifies.

---

## 10. Recommendations

| Action | Expected effect on ETR |
|--------|----------------------|
| Reduce `recovery_time` from 20 → 10 min | ETR: ~62.5% → ~76.9% (+14 pp); saves ~1,844 hrs |
| Reduce `auto_repair_fail_prob` from 0.40 → 0.20 | Fewer repeat failures *and* fewer escalations (escalation rate scales with this parameter now) → lower recovery burden → ETR increase |
| Reduce `prob_auto_to_manual` from 0.80 → 0.40 | Now only affects the ~40% of repairs where auto genuinely failed: fewer of those get the slower, more thorough manual stage — a real speed/thoroughness trade-off, not a blanket reduction in unnecessary manual repairs |
| Increase `warm_standbys` from 16 → 32 | Maintain near-zero host-selection overhead under higher failure rates |
| Enable `bad_server_regeneration` | Models hardware aging; expected to gradually reduce ETR over time |

All of these can be evaluated with a one-way sweep
(`python -m airesim.run --sweep recovery_time --values 5,10,15,20`) or by
adjusting `config.yaml` and re-running `--adaptive`.
