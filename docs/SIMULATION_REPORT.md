# AIReSim Simulation Report

**Configuration:** `config.yaml` (paper Table 1 defaults)
**Date:** 2026-09-21
**Mode:** Adaptive replication — 95% CI, ±5% relative accuracy
**Data:** `examples/simulation_report_figures/results.csv` (30 rows, one per replication,
seeds 42–71), produced by `examples/simulation_report_stats.py` at commit `0cab8fb`,
re-run at commit `da28d04` with added bad-server/repair/pool columns (same seeds,
headline numbers unchanged; run log: `examples/simulation_report_figures/run.log`).
Repairs follow the paper's model: `prob_auto_to_manual` is the probability that auto
repair escalates, independent of the silent auto-repair failure `auto_repair_fail_prob`.
§5a's job-length sweep uses `examples/job_length_figures/replications.csv` (50 rows: 5 job
lengths × 10 replications, seeds 42–51), produced by `examples/job_length_sweep.py` at
commit `2255b8c` (run log: `examples/job_length_figures/run.log`).

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
| 95% CI half-width | ±12.87 hrs |
| Mean training time | 9,872.90 hrs |

The achieved accuracy of ±0.13% is about 38× tighter than the ±5% target, confirming
that 30 replications are more than sufficient for this parameter configuration.

---

## 2. Training Time

The **ideal training time** (zero failures, no overhead) at the configured job
length of 256 days is **6,144 hrs**. Failures and their downstream costs inflate
this to nearly 10,000 hrs.

| Statistic | Value (hrs) |
|-----------|------------|
| Ideal (no failures) | 6,144.00 |
| Mean total training time | 9,872.90 |
| Std deviation | 34.47 |
| Min (best run) | 9,810.92 |
| Max (worst run) | 9,955.07 |
| Run-to-run range | 144.15 |
| **Slowdown factor** | **1.61×** |
| **Total overhead** | **3,728.90 hrs (37.8%)** |
| **Effective Training Ratio (ETR)** | **62.2%** |

The cluster consistently finishes the job in **9,810–9,955 hrs** (409–415 days),
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
| Mean ETR | **0.6223 (62.2%)** |
| Std deviation | 0.0022 |
| Min (worst run) | 0.6172 (61.7%) |
| Max (best run) | 0.6262 (62.6%) |
| Run-to-run range | 0.0090 |

The ETR is **very stable** across replications (CV = 0.35%), reflecting that
each run experiences roughly the same total number of failures and therefore
the same aggregate recovery burden. Compute time is fixed at 6,144 hrs in every
replication, so ETR is purely a decreasing function of training time: the ~0.9
percentage-point spread between the best and worst run corresponds to the 144 hrs
training-time range above.

An ETR of 62.2% means **37.8% of cluster time is wasted on non-productive
work** — almost entirely checkpoint reloading after failures.

---

## 4. Time Breakdown

Every minute of wall-clock time falls into one of four categories:

| Component | Mean (hrs) | Fraction of total | Contributes to ETR? |
|-----------|-----------|-------------------|---------------------|
| Compute (job progress) | 6,144.00 | 62.2% | Yes (numerator) |
| Recovery (checkpoint reload) | 3,722.81 | 37.7% | No |
| Host selection & job restart | 2.06 | 0.02% | No |
| Waiting for spare pool | 4.02 | 0.04% | No |
| **Total training time** | **9,872.90** | 100% | (denominator) |

**Recovery time dominates the overhead at 37.7% of total wall-clock time.**
With 11,168 failures per run and a 20-minute checkpoint reload per failure,
recovery accumulates to 3,723 hrs — more than 155 additional days on top of
the ideal 256-day run.

Host-selection and spare-pool wait times are negligible (0.06% combined),
confirming that the cluster's warm-standby and spare-pool configuration
effectively mask most of the scheduling latency.

---

## 5. Failure Analysis

### 5.1 Total failures

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Total failures | 11,168.4 | 103.4 | 10,980 | 11,415 |
| Random failures | 10,483.8 | 104.2 | 10,298 | 10,747 |
| Systematic failures | 684.7 | 19.3 | 656 | 735 |

**Random failures account for 93.9% of all failures**; systematic failures
(from the 15% "bad" servers) account for the remaining 6.1%. Despite bad
servers failing at 5× the baseline rate, their contribution is limited because
they represent only 15% of the pool.

### 5.2 Inter-failure intervals

| Metric | Value |
|--------|-------|
| Mean run duration between failures | 33.01 min |
| Std dev | 0.31 min |
| Min observed | 32.29 min |
| Max observed | 33.57 min |

A system-level failure (any server) occurs approximately **every 33 minutes**
on average — roughly twice per hour throughout the 9,873-hour run.

---

## 5a. Job-Length Sensitivity: Systematic Failures Saturate

With `bad_server_regeneration` off (the default), a server only ever moves from bad to
good, on a successful repair; nothing ever makes a good server bad again. The pool starts
with a fixed number of bad servers (≈622 of 4 600, ≈13.5%, `systematic_failure_fraction`
× pool size minus retirements) and that population can only shrink. Systematic failures
should therefore **saturate** as the bad population is cured — new systematic failures
become rarer over the run even though the random-failure rate stays constant. The 256-day
run above (§5.1) sits at that plateau: 684.7 systematic failures is the ceiling, not a
steady-state rate.

`examples/job_length_sweep.py` runs `config.yaml` (Random + NeverRemove) at five job
lengths, 10 replications each, to trace the curve directly:

| Job length (compute-days) | Wall-clock time (h) | Systematic failures | Random failures | Faulty servers left in pool | % of plateau reached |
|---|---|---|---|---|---|
| 15 | 677.2 ± 4.7 | 337.3 ± 6.7 | 600.3 ± 12.5 | 317.5 ± 10.3 | 49.4% |
| 30 | 1,296.9 ± 5.7 | 501.0 ± 6.8 | 1,215.3 ± 15.5 | 164.1 ± 9.0 | 73.4% |
| 60 | 2,468.0 ± 11.8 | 633.5 ± 11.1 | 2,435.4 ± 33.4 | 46.0 ± 4.7 | 92.8% |
| 120 | 4,748.5 ± 12.4 | 679.8 ± 12.0 | 4,909.5 ± 37.3 | 3.2 ± 1.1 | 99.5% |
| 256 | 9,876.8 ± 28.1 | 682.9 ± 11.6 | 10,496.2 ± 84.4 | 0.0 ± 0.0 | 100.0% |

(± is the 95% CI half-width over 10 replications, t = 2.262. "% of plateau reached" is
each row's systematic-failure count divided by the 256-day row's.) The 256-day systematic
count (682.9 ± 11.6) matches the independent 30-replication, 256-day run in §5.1
(684.7 ± 3.5 SE) within noise — both sit at the same ceiling.

**Almost half of all systematic failures a run will ever see happen in the first 15
compute-days (≈28 wall-clock days) of a 256-day job.** The bad-server population starts
at ~622 and is down to 46 by 60 compute-days, 3 by 120, and fully cured by 256. Random
failures, by contrast, grow roughly linearly with job length throughout (600 → 10,496,
close to proportional to wall-clock time), because the random-failure rate never changes
and the pool that generates them never shrinks. **Random failures dominate the failure
count at every job length in this table, and increasingly so as systematic failures
saturate** — random failures are 64% of the total at 15 days and 94% by 256 days.

**This puts a hard upper bound on what any node-management policy can win at these
parameters.** A policy cannot make a random failure not happen — by construction it is
independent of any server's history. The best any retirement, scheduling-around-bad-servers,
or diagnosis policy can do is prevent systematic failures entirely, which is worth at most

```
systematic_failures × recovery_time = 684.7 × 20 min ≈ 228.2 h ≈ 2.3% of the 9,873 h mean training time
```

Empirically, the policies actually tested at these defaults come nowhere near that
ceiling — `POLICY_SYNTHESIS_REPORT.md` finding 3 found no measurable benefit from
`FewestFailuresFirst` at the paper defaults (95% CI excludes any benefit above ~18 h,
0.2%), consistent with a ≤2.3% ceiling that a policy acting on only ~41 of ~11,168
failures per run (§7) is unlikely to approach. This bound does not apply to levers that
act on every failure regardless of cause, such as `recovery_time` or the repair-fail
probabilities (§10).

---

## 6. Repair Pipeline

All 11,168 failures per run enter the two-stage repair pipeline.

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Auto-repair attempts | 11,168.4 | 103.4 | 10,980 | 11,415 |
| Escalated to manual repair | 8,930.7 | 83.4 | 8,786 | 9,104 |
| Successful repairs | 8,488.0 | 102.7 | 8,329 | 8,765 |
| Failed repairs | 2,680.4 | 51.7 | 2,571 | 2,767 |
| Servers retired | 0 | — | 0 | 0 |

### Key repair ratios

| Ratio | Value | Interpretation |
|-------|-------|----------------|
| Escalation rate | 80.0% | Matches `prob_auto_to_manual = 0.80`: auto repair hands 4 in 5 servers to manual repair |
| Overall repair failure rate | 24.0% | 1 in 4 repairs leaves the server faulty; it re-enters the pool and fails again |
| No servers retired | 0% | Default `NeverRemove` policy; all repaired servers are reintegrated |

The **24% repair failure rate** follows from the two paths a repair can take.
80% of servers escalate and are repaired only by the manual stage, which silently
fails with probability `manual_repair_fail_prob = 0.20`; the other 20% are handled
by auto repair alone, which silently fails with probability
`auto_repair_fail_prob = 0.40`. The blended rate is
0.80 × 0.20 + 0.20 × 0.40 = 24%, matching the measured 24.0%.

That 24% applies uniformly to every repair, but every failure — bad-server or not —
enters the same pipeline, and the outcome only *matters* for servers that were actually
bad. Splitting the 11,168 repairs per run by whether the server was faulty (`is_bad`)
going in:

| Repair population | Repairs/run | Share | Silent-fail rate | Effect of a silent failure |
|---|---|---|---|---|
| Bad server (`is_bad=True`) | 817.4 | 7.3% | 23.6% (192.5 stay bad) | Server stays bad, fails systematically again — this is the leak |
| Good server (`is_bad=False`) | 10,351.0 | 92.7% | ~24.0% (measured) | **None** — the server was never bad, so it stays good whether the repair is recorded as a "success" or a "failure" |

92.7% of repairs are on servers that were not faulty to begin with (a random,
non-systematic failure is not evidence the server itself is bad), so a "failed" repair
there changes nothing observable. Only the 7.3% of repairs on genuinely bad servers can
amplify the failure count, and even there roughly 3 in 4 succeed and cure the server
(§5a). The measured 24.0% blended rate is the same silent-fail probability for both
populations — it is not that bad servers fail repair more often, only that a failure
there is consequential and a failure on a good server is bookkeeping noise.

---

## 7. Scheduling and Pool Activity

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Host-selection events | 41.3 | 3.5 | 32 | 48 |
| Spare-pool preemptions | 12.1 | 3.2 | 0 | 23 |
| Job stalls | 0 | — | 0 | 0 |

- **Host-selection events (41)** are far fewer than total failures (11,168)
  because warm standbys absorb ~99.6% of failures with an immediate in-place
  swap — no host-selection round-trip needed.
- **Spare-pool preemptions (~12)** occur when the working pool is temporarily
  exhausted and the scheduler must pull from the 200-server spare pool. The
  small number relative to failures confirms the spare pool is rarely needed.
- **Zero job stalls** — the cluster never ran out of both working and spare
  servers simultaneously. The configuration has adequate combined capacity.

---

## 8. Statistical Quality

| Metric | Value |
|--------|-------|
| Replications | 30 |
| Mean training time | 9,872.90 hrs |
| Standard deviation | 34.47 hrs |
| Coefficient of variation | 0.35% |
| 95% CI | [9,860.02, 9,885.77] hrs |
| CI half-width | ±12.87 hrs |
| Relative half-width | **±0.13%** |

The coefficient of variation (CV) of 0.35% is exceptionally low, explaining
why 30 replications are sufficient to produce a CI about 38× tighter than the
±5% target. The low CV reflects the **law of large numbers operating within
each replication**: with ~11,000 independent failure events per run, the
within-run randomness averages out, leaving very little run-to-run variance.

---

## 9. Key Findings

1. **ETR of 62.2% — over a third of cluster time is non-productive.** The
   Effective Training Ratio sits at 0.6223 across all 30 replications, with
   very low variance (CV = 0.35%). Improving ETR is the primary lever for
   reducing total training time; every 1 percentage-point gain in ETR saves
   ~159 hrs of wall-clock time at this cluster scale.

2. **Failure recovery is the dominant overhead.** At 37.7% of total time,
   checkpoint-reload latency (`recovery_time = 20 min`) accounts for virtually
   all slowdown. Halving recovery time would reduce total training time by
   ~1,861 hrs (~19%).

3. **The repair pipeline's "leak" only matters for the 7.3% of repairs on
   genuinely bad servers.** The measured 24% repair failure rate is the same
   silent-fail probability whether or not the server was actually faulty
   going in, but a failure only has a consequence for the servers that were
   (§6): they stay bad and fail systematically again. The other 92.7% of
   repairs (10,351/run) are on servers that were never bad, where a "failed"
   repair changes nothing observable. Reducing `auto_repair_fail_prob` or
   `manual_repair_fail_prob` therefore only reduces the systematic-failure
   count, not the dominant random-failure count, and its benefit is bounded
   by the same ≤2.3% ceiling as any other node-management lever at these
   defaults (§5a).

4. **Warm standbys work as designed.** With only 41 host-selection events
   across 11,168 failures, the 16-server warm-standby reserve absorbs
   ~99.6% of failures with zero scheduling overhead.

5. **The spare pool is barely used.** ~12 preemptions per run from a pool of
   200 servers means the spare pool provides a large safety margin that is
   rarely exercised under these parameters.

6. **The cluster never depletes.** Zero stalls and zero depletion events across
   all 30 replications confirm the configuration has sufficient resilience for
   the modelled failure rates and repair durations.

7. **Systematic failures saturate; the 6.1% share (§5.1) is a long-run
   average, not a stable rate.** With `bad_server_regeneration` off, a
   successful repair cures a bad server and nothing turns a good server bad,
   so the systematic-failure count is capped by the initial bad population
   (~622 of 4,600 servers) and plateaus at 684.7 ± 19.3 over a 256-day run —
   **49.4% of that ceiling is reached in the first 15 compute-days** (§5a).
   Random failures have no such ceiling and grow roughly linearly with job
   length (600 at 15 days → 10,496 at 256 days), so systematic failures'
   share of the total falls from 36% at 15 days to 6.1% at 256 days as the
   bad population is cured out from under them. Any policy that targets bad
   servers exclusively — retirement, health-aware scheduling, faster or more
   reliable repair — is capped at eliminating 684.7 systematic failures ×
   `recovery_time` ≈ **228 h ≈ 2.3% of training time** at these parameters
   (§5a); increasing `systematic_failure_fraction` or
   `systematic_failure_rate_multiplier` would raise both the ceiling and the
   plateau.

---

## 10. Recommendations

| Action | Expected effect on ETR |
|--------|----------------------|
| Reduce `recovery_time` from 20 → 10 min | ETR: ~62.2% → ~76.7% (+14.5 pp); saves ~1,861 hrs |
| Reduce `auto_repair_fail_prob` from 0.40 → 0.20 | Blended failure rate 24% → 20%, but the change only has a consequence for the 7.3% of repairs on genuinely bad servers (§6); benefit capped by the ≤2.3% systematic-failure ceiling (§5a), not the 24%→20% headline drop |
| Reduce `manual_repair_fail_prob` from 0.20 → 0.10 | Blended failure rate 24% → 16%, same caveat: only the 7.3% bad-server repair share is affected, so the realized benefit is well under the ≤2.3% ceiling (§5a) |
| Reduce `prob_auto_to_manual` from 0.80 → 0.40 | Blended failure rate rises 24% → 32%, but again only for the 7.3% bad-server share — the random-failure majority (§5a) is untouched either way |
| Increase `warm_standbys` from 16 → 32 | Maintain near-zero host-selection overhead under higher failure rates |
| Enable `bad_server_regeneration` | Models hardware aging; expected to gradually reduce ETR over time |

All of these can be evaluated with a one-way sweep
(`python -m airesim.run --sweep recovery_time --values 5,10,15,20`) or by
adjusting `config.yaml` and re-running `--adaptive`.
