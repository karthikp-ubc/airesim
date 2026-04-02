# AIReSim Simulation Report

**Configuration:** `config.yaml` (paper Table 1 defaults)
**Date:** 2026-04-02
**Mode:** Adaptive replication — 95% CI, ±5% relative accuracy

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
| **Achieved relative accuracy** | **±0.13% of mean** |
| 95% CI half-width | ±12.55 hrs |
| Mean training time | 9,865.97 hrs |

The achieved accuracy of ±0.13% is 40× tighter than the ±5% target, confirming
that 30 replications are more than sufficient for this parameter configuration.

---

## 2. Training Time

The **ideal training time** (zero failures, no overhead) at the configured job
length of 256 days is **6,144 hrs**. Failures and their downstream costs inflate
this to nearly 10,000 hrs.

| Statistic | Value (hrs) |
|-----------|------------|
| Ideal (no failures) | 6,144.00 |
| Mean total training time | 9,865.97 |
| Std deviation | 33.60 |
| Min (best run) | 9,802.43 |
| Max (worst run) | 9,949.38 |
| Run-to-run range | 146.95 |
| **Slowdown factor** | **1.61×** |
| **Total overhead** | **3,721.97 hrs (37.7%)** |
| **Effective Training Ratio (ETR)** | **62.3%** |

The cluster consistently finishes the job in **9,800–9,950 hrs** (409–415 days),
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
| Mean ETR | **0.6228 (62.3%)** |
| Std deviation | 0.0021 |
| Min (worst run) | 0.6175 (61.8%) |
| Max (best run) | 0.6268 (62.7%) |
| Run-to-run range | 0.0093 |

The ETR is **very stable** across replications (CV = 0.34%), reflecting that
each run experiences roughly the same total number of failures and therefore
the same aggregate recovery burden.  The ~0.9 percentage-point spread between
the best and worst run corresponds to only ~89 hrs difference in training time.

An ETR of 62.3% means **37.7% of cluster time is wasted on non-productive
work** — almost entirely checkpoint reloading after failures.

---

## 4. Time Breakdown

Every minute of wall-clock time falls into one of four categories:

| Component | Mean (hrs) | Fraction of total | Contributes to ETR? |
|-----------|-----------|-------------------|---------------------|
| Compute (job progress) | 6,144.00 | 62.3% | Yes (numerator) |
| Recovery (checkpoint reload) | 3,715.20 | 37.6% | No |
| Host selection & job restart | 2.15 | 0.02% | No |
| Waiting for spare pool | 4.62 | 0.05% | No |
| **Total training time** | **9,865.97** | 100% | (denominator) |

**Recovery time dominates the overhead at 37.6% of total wall-clock time.**
With 11,146 failures per run and a 20-minute checkpoint reload per failure,
recovery accumulates to 3,715 hrs — more than 154 additional days on top of
the ideal 256-day run.

Host-selection and spare-pool wait times are negligible (< 0.1% combined),
confirming that the cluster's warm-standby and spare-pool configuration
effectively mask most of the scheduling latency.

---

## 5. Failure Analysis

### 4.1 Total failures

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Total failures | 11,145.6 | 100.3 | 10,954 | 11,397 |
| Random failures | 10,457.0 | 96.1 | 10,288 | 10,721 |
| Systematic failures | 688.6 | 15.4 | 649 | 719 |

**Random failures account for 93.8% of all failures**; systematic failures
(from the 15% "bad" servers) account for the remaining 6.2%.  Despite bad
servers failing at 5× the baseline rate, their contribution is limited because
they represent only 15% of the pool.

### 4.2 Inter-failure intervals

| Metric | Value |
|--------|-------|
| Mean run duration between failures | 33.07 min |
| Std dev | 0.30 min |
| Min observed | 32.34 min |
| Max observed | 33.65 min |

A system-level failure (any server) occurs approximately **every 33 minutes**
on average — roughly twice per hour throughout the 9,866-hour run.

---

## 6. Repair Pipeline

All 11,146 failures per run enter the two-stage repair pipeline.

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Auto-repair attempts | 11,145.6 | 100.3 | 10,954 | 11,397 |
| Escalated to manual repair | 8,922.9 | 91.4 | 8,750 | 9,110 |
| Successful repairs | 8,469.4 | 74.8 | 8,370 | 8,717 |
| Failed repairs | 2,676.2 | 54.9 | 2,566 | 2,798 |
| Servers retired | 0 | — | 0 | 0 |

### Key repair ratios

| Ratio | Value | Interpretation |
|-------|-------|----------------|
| Escalation rate | 80.1% | Nearly all auto repairs escalate to manual — as expected from `prob_auto_to_manual = 0.80` |
| Overall repair failure rate | 24.0% | 1 in 4 repairs leaves the server faulty; it re-enters the pool and fails again |
| No servers retired | 0% | Default `NeverRemove` policy; all repaired servers are reintegrated |

The **24% repair failure rate** is the combined effect of
`auto_repair_fail_prob = 0.40` and `manual_repair_fail_prob = 0.20`: a server
that proceeds through both stages has a net failure probability of
1 − (1 − 0.40) × (1 − 0.20) = 52% when auto repair succeeds on the first
attempt, but 80% of servers escalate to manual, making the blended rate ~24%.
These "silent-fail" repairs return servers to the pool that will fail again
soon, amplifying the total failure count above what the raw failure rates alone
would predict.

---

## 7. Scheduling and Pool Activity

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Host-selection events | 42.9 | 3.4 | 37 | 48 |
| Spare-pool preemptions | 13.9 | 4.5 | 8 | 25 |
| Job stalls | 0 | — | 0 | 0 |

- **Host-selection events (43)** are far fewer than total failures (11,146)
  because warm standbys absorb ~99.6% of failures with an immediate in-place
  swap — no host-selection round-trip needed.
- **Spare-pool preemptions (~14)** occur when the working pool is temporarily
  exhausted and the scheduler must pull from the 200-server spare pool.  The
  small number relative to failures confirms the spare pool is rarely needed.
- **Zero job stalls** — the cluster never ran out of both working and spare
  servers simultaneously.  The configuration has adequate combined capacity.

---

## 8. Statistical Quality

| Metric | Value |
|--------|-------|
| Replications | 30 |
| Mean training time | 9,865.97 hrs |
| Standard deviation | 33.60 hrs |
| Coefficient of variation | 0.34% |
| 95% CI | [9,853.42, 9,878.52] hrs |
| CI half-width | ±12.55 hrs |
| Relative half-width | **±0.13%** |

The coefficient of variation (CV) of 0.34% is exceptionally low, explaining
why 30 replications are sufficient to produce a CI 40× tighter than the
±5% target.  The low CV reflects the **law of large numbers operating within
each replication**: with ~11,000 independent failure events per run, the
within-run randomness averages out, leaving very little run-to-run variance.

---

## 9. Key Findings

1. **ETR of 62.3% — over a third of cluster time is non-productive.** The
   Effective Training Ratio sits at 0.6228 across all 30 replications, with
   very low variance (CV = 0.34%).  Improving ETR is the primary lever for
   reducing total training time; every 1 percentage-point gain in ETR saves
   ~100 hrs of wall-clock time at this cluster scale.

2. **Failure recovery is the dominant overhead.** At 37.6% of total time,
   checkpoint-reload latency (`recovery_time = 20 min`) accounts for virtually
   all slowdown.  Halving recovery time would reduce total training time by
   ~1,858 hrs (~19%).

3. **The repair pipeline is leaky.** A 24% net repair failure rate means the
   cluster is continuously re-encountering servers that were declared healthy
   but are not.  Reducing `auto_repair_fail_prob` or `manual_repair_fail_prob`
   would reduce repeat failures and therefore total recovery time.

4. **Warm standbys work as designed.** With only 43 host-selection events
   across 11,146 failures, the 16-server warm-standby reserve absorbs
   ~99.6% of failures with zero scheduling overhead.

5. **The spare pool is barely used.** ~14 preemptions per run from a pool of
   200 servers means the spare pool provides a large safety margin that is
   rarely exercised under these parameters.

6. **The cluster never depletes.** Zero stalls and zero depletion events across
   all 30 replications confirm the configuration has sufficient resilience for
   the modelled failure rates and repair durations.

7. **Systematic failures are a minor contributor.** Despite failing 5× faster,
   bad servers (15% of the pool) generate only 6.2% of total failures because
   of their relatively small population share.  Increasing
   `systematic_failure_fraction` or `systematic_failure_rate_multiplier` would
   shift this balance.

---

## 10. Recommendations

| Action | Expected effect on ETR |
|--------|----------------------|
| Reduce `recovery_time` from 20 → 10 min | ETR: ~62.3% → ~76.5% (+14 pp); saves ~1,858 hrs |
| Reduce `auto_repair_fail_prob` from 0.40 → 0.20 | Fewer repeat failures → lower recovery burden → ETR increase |
| Reduce `prob_auto_to_manual` from 0.80 → 0.40 | Faster average repair cycle → fewer servers in repair simultaneously |
| Increase `warm_standbys` from 16 → 32 | Maintain near-zero host-selection overhead under higher failure rates |
| Enable `bad_server_regeneration` | Models hardware aging; expected to gradually reduce ETR over time |

All of these can be evaluated with a one-way sweep
(`python -m airesim.run --sweep recovery_time --values 5,10,15,20`) or by
adjusting `config.yaml` and re-running `--adaptive`.
