# AIReSim Simulation Report

**Configuration:** `config.yaml` (paper Table 1 defaults, including `diagnosis_probability: 0.8`)
**Date:** 2026-11-20
**Mode:** Adaptive replication — 95% CI, ±5% relative accuracy
**Data:** `examples/simulation_report_figures/results.csv` (30 rows, one per replication,
seeds 42–71), produced by `examples/simulation_report_stats.py` at commit `be13c89` (run
log: `examples/simulation_report_figures/run.log`). Repairs follow the paper's model:
`prob_auto_to_manual` is the probability that auto repair escalates, independent of the
silent auto-repair failure `auto_repair_fail_prob`. §5a's job-length sweep uses
`examples/job_length_figures/replications.csv` (50 rows: 5 job lengths × 10 replications,
seeds 42–51), produced by `examples/job_length_sweep.py` at commit `be13c89` (run log:
`examples/job_length_figures/run.log`).

> **What changed on 2026-11-20.** Rerun after the paper-conformance fixes (CHANGELOG).
> `config.yaml` now sets `diagnosis_probability: 0.8` (Table I; it was effectively 1.0),
> so 20% of failures go undiagnosed and the failed server rejoins the pool unrepaired.
> Mean training time rose from 9,872.9 to 9,925.7 hrs (+52.8 hrs, +0.53%; paired by seed
> +52.0 ± 14.7 hrs from the diagnosis change and +0.8 ± 4.6 hrs from the code fixes,
> which changed only 3 of the 30 runs at all). The other visible changes all follow from
> missed diagnoses: only ~80% of failures now enter the repair pipeline (§6), bad servers
> are cured more slowly, so systematic failures rise from 685 to 863 per run and plateau
> later (§5a), and spare-pool preemptions fall from 12 to ~1 per run because fewer servers
> are away in repair at once (§7).

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
| **Achieved relative accuracy** | **±0.16% of mean** |
| 95% CI half-width | ±15.41 hrs |
| Mean training time | 9,925.70 hrs |

The achieved accuracy of ±0.16% is about 32× tighter than the ±5% target, confirming
that 30 replications are more than sufficient for this parameter configuration.

---

## 2. Training Time

The **ideal training time** (zero failures, no overhead) at the configured job
length of 256 days is **6,144 hrs**. Failures and their downstream costs inflate
this to nearly 10,000 hrs.

| Statistic | Value (hrs) |
|-----------|------------|
| Ideal (no failures) | 6,144.00 |
| Mean total training time | 9,925.70 |
| Std deviation | 41.26 |
| Min (best run) | 9,833.98 |
| Max (worst run) | 10,019.42 |
| Run-to-run range | 185.44 |
| **Slowdown factor** | **1.62×** |
| **Total overhead** | **3,781.70 hrs (38.1%)** |
| **Effective Training Ratio (ETR)** | **61.9%** |

The cluster consistently finishes the job in **9,834–10,019 hrs** (410–417 days),
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
| Mean ETR | **0.6190 (61.9%)** |
| Std deviation | 0.0026 |
| Min (worst run) | 0.6132 (61.3%) |
| Max (best run) | 0.6248 (62.5%) |
| Run-to-run range | 0.0116 |

The ETR is **very stable** across replications (CV = 0.42%), reflecting that
each run experiences roughly the same total number of failures and therefore
the same aggregate recovery burden. Compute time is fixed at 6,144 hrs in every
replication, so ETR is purely a decreasing function of training time: the ~1.2
percentage-point spread between the best and worst run corresponds to the 185 hrs
training-time range above.

An ETR of 61.9% means **38.1% of cluster time is wasted on non-productive
work** — almost entirely checkpoint reloading after failures.

---

## 4. Time Breakdown

Every minute of wall-clock time falls into one of four categories:

| Component | Mean (hrs) | Fraction of total | Contributes to ETR? |
|-----------|-----------|-------------------|---------------------|
| Compute (job progress) | 6,144.00 | 61.9% | Yes (numerator) |
| Recovery (checkpoint reload) | 3,779.48 | 38.1% | No |
| Host selection & job restart | 1.82 | 0.02% | No |
| Waiting for spare pool | 0.41 | 0.004% | No |
| **Total training time** | **9,925.70** | 100% | (denominator) |

**Recovery time dominates the overhead at 38.1% of total wall-clock time.**
With 11,338 failures per run and a 20-minute checkpoint reload per failure,
recovery accumulates to 3,779 hrs — more than 157 additional days on top of
the ideal 256-day run.

Host-selection and spare-pool wait times are negligible (0.02% combined),
confirming that the cluster's warm-standby and spare-pool configuration
effectively mask most of the scheduling latency.

---

## 5. Failure Analysis

### 5.1 Total failures

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Total failures | 11,338.4 | 123.7 | 11,065 | 11,621 |
| Random failures | 10,475.9 | 120.3 | 10,227 | 10,771 |
| Systematic failures | 862.6 | 22.7 | 812 | 916 |

**Random failures account for 92.4% of all failures**; systematic failures
(from the 15% "bad" servers) account for the remaining 7.6%. Despite bad
servers failing at 5× the baseline rate, their contribution is limited because
they represent only 15% of the pool and most are cured early (§5a). Missed
diagnoses raise the systematic count by 26% (685 at diagnosis 1.0): an undiagnosed
bad server goes back into the pool unrepaired and fails again.

### 5.2 Inter-failure intervals

| Metric | Value |
|--------|-------|
| Mean run duration between failures | 32.51 min |
| Std dev | 0.35 min |
| Min observed | 31.72 min |
| Max observed | 33.32 min |

A system-level failure (any server) occurs approximately **every 32.5 minutes**
on average — roughly twice per hour throughout the 9,926-hour run.

---

## 5a. Job-Length Sensitivity: Systematic Failures Saturate

With `bad_server_regeneration` off (the default), a server only ever moves from bad to
good, on a successful repair; nothing ever makes a good server bad again. The pool starts
with a fixed number of bad servers (≈623 of 4,160, ≈15%, `systematic_failure_fraction`
× pool size minus retirements) and that population can only shrink. Systematic failures
should therefore **saturate** as the bad population is cured — new systematic failures
become rarer over the run even though the random-failure rate stays constant. The 256-day
run above (§5.1) sits at that plateau: 862.6 systematic failures is the ceiling, not a
steady-state rate.

`examples/job_length_sweep.py` runs `config.yaml` (Random + NeverRemove) at five job
lengths, 10 replications each, to trace the curve directly:

| Job length (compute-days) | Wall-clock time (h) | Systematic failures | Random failures | Faulty servers left in pool | % of plateau reached |
|---|---|---|---|---|---|
| 15 | 684.5 ± 7.9 | 363.2 ± 9.3 | 609.4 ± 19.8 | 366.3 ± 9.2 | 41.6% |
| 30 | 1,313.3 ± 10.2 | 571.1 ± 9.3 | 1,207.5 ± 29.8 | 215.3 ± 6.4 | 65.4% |
| 60 | 2,513.1 ± 12.3 | 770.2 ± 10.5 | 2,447.4 ± 37.7 | 72.1 ± 6.3 | 88.3% |
| 120 | 4,800.1 ± 9.0 | 860.2 ± 17.2 | 4,897.2 ± 19.1 | 9.2 ± 2.2 | 98.6% |
| 256 | 9,917.9 ± 14.9 | 872.6 ± 15.5 | 10,443.8 ± 41.6 | 0.1 ± 0.2 | 100.0% |

(± is the 95% CI half-width over 10 replications, t = 2.262. "% of plateau reached" is
each row's systematic-failure count divided by the 256-day row's.) The 256-day systematic
count (872.6 ± 15.5) matches the independent 30-replication, 256-day run in §5.1
(862.6 ± 4.1 SE) within noise — both sit at the same ceiling.

**About 40% of all systematic failures a run will ever see happen in the first 15
compute-days (≈29 wall-clock days) of a 256-day job.** The bad-server population starts
at ~623 and is down to 72 by 60 compute-days, 9 by 120, and essentially fully cured by
256. Saturation is slower than at diagnosis 1.0 (49% of the plateau by 15 days, 46 bad
servers left at 60 days) because a bad server whose failure goes undiagnosed is not
repaired that time. Random failures, by contrast, grow roughly linearly with job length
throughout (609 → 10,444, close to proportional to wall-clock time), because the
random-failure rate never changes and the pool that generates them never shrinks.
**Random failures dominate the failure count at every job length in this table, and
increasingly so as systematic failures saturate** — random failures are 63% of the total
at 15 days and 92% by 256 days.

**This puts a hard upper bound on what any node-management policy can win at these
parameters.** A policy cannot make a random failure not happen — by construction it is
independent of any server's history. The best any retirement, scheduling-around-bad-servers,
or diagnosis policy can do is prevent systematic failures entirely, which is worth at most

```
systematic_failures × recovery_time = 862.6 × 20 min ≈ 287.5 h ≈ 2.9% of the 9,926 h mean training time
```

(2.3% at diagnosis 1.0). Empirically, the policies actually tested at these defaults come
nowhere near that ceiling — `DIAGNOSIS_REALISTIC_REPORT.md` found no measurable benefit
from `FewestFailuresFirst` at the paper defaults (95% CI excludes any benefit above
~26 h, 0.3%), consistent with a ≤2.9% ceiling that a policy acting on only ~36 of ~11,338
failures per run (§7) is unlikely to approach. This bound does not apply to levers that
act on every failure regardless of cause, such as `recovery_time` (§10).

---

## 6. Repair Pipeline

Of the 11,338 failures per run, **9,062 (79.9%) are diagnosed and enter the two-stage
repair pipeline**; the other 2,276 go undiagnosed and the failed server rejoins the pool
without repair (`diagnosis_probability = 0.8`).

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Auto-repair attempts | 9,062.4 | 120.0 | 8,812 | 9,313 |
| Escalated to manual repair | 7,253.4 | 104.8 | 7,005 | 7,488 |
| Successful repairs | 6,868.9 | 98.1 | 6,620 | 7,049 |
| Failed repairs | 2,193.6 | 52.1 | 2,088 | 2,319 |
| Servers retired | 0 | — | 0 | 0 |

### Key repair ratios

| Ratio | Value | Interpretation |
|-------|-------|----------------|
| Diagnosis rate | 79.9% | Matches `diagnosis_probability = 0.8`: 1 in 5 failures never reaches repair |
| Escalation rate | 80.0% | Matches `prob_auto_to_manual = 0.80`: auto repair hands 4 in 5 servers to manual repair |
| Overall repair failure rate | 24.2% | About 1 in 4 repairs leaves the server faulty; it re-enters the pool and fails again |
| No servers retired | 0% | Default `NeverRemove` policy; all repaired servers are reintegrated |

The **24% repair failure rate** follows from the two paths a repair can take.
80% of servers escalate and are repaired only by the manual stage, which silently
fails with probability `manual_repair_fail_prob = 0.20`; the other 20% are handled
by auto repair alone, which silently fails with probability
`auto_repair_fail_prob = 0.40`. The blended rate is
0.80 × 0.20 + 0.20 × 0.40 = 24%, matching the measured 24.2%.

That 24% applies uniformly to every repair, but the outcome only *matters* for servers
that were actually bad. Splitting the 9,062 repairs per run by whether the server was
faulty (`is_bad`) going in:

| Repair population | Repairs/run | Share | Silent-fail rate | Effect of a silent failure |
|---|---|---|---|---|
| Bad server (`is_bad=True`) | 823.4 | 9.1% | 24.3% (200.2 stay bad) | Server stays bad, fails systematically again — this is the leak |
| Good server (`is_bad=False`) | 8,239.0 | 90.9% | ~24% | **None** — the server was never bad, so it stays good whether the repair is recorded as a "success" or a "failure" |

90.9% of repairs are on servers that were not faulty to begin with (a random,
non-systematic failure is not evidence the server itself is bad), so a "failed" repair
there changes nothing observable. Only the 9.1% of repairs on genuinely bad servers can
amplify the failure count, and even there roughly 3 in 4 succeed and cure the server
(§5a). Missed diagnoses are a second leak of the same kind: a bad server whose failure
goes undiagnosed simply stays bad, which is why systematic failures rise to 863 per run.

---

## 7. Scheduling and Pool Activity

| Metric | Mean | Std Dev | Min | Max |
|--------|------|---------|-----|-----|
| Host-selection events | 36.3 | 2.6 | 30 | 41 |
| Spare-pool preemptions | 1.2 | 3.8 | 0 | 13 |
| Job stalls | 0 | — | 0 | 0 |

- **Host-selection events (36)** are far fewer than total failures (11,338)
  because warm standbys absorb ~99.7% of failures with an immediate in-place
  swap — no host-selection round-trip needed.
- **Spare-pool preemptions (~1)** occur when the working pool is temporarily
  exhausted and the scheduler must pull from the 200-server spare pool; most runs
  have none. At diagnosis 1.0 there were ~12 per run: every failure then sent a server
  to repair, while now 20% of failed servers rejoin the pool at once, so the working
  pool runs short less often. Borrowed spares are now returned when no longer needed
  (`return_borrowed_spares`), so each borrowing costs `preemption_wait_time` afresh;
  at this rate that is negligible (0.4 hrs per run waiting).
- **Zero job stalls** — the cluster never ran out of both working and spare
  servers simultaneously. The configuration has adequate combined capacity.

---

## 8. Statistical Quality

| Metric | Value |
|--------|-------|
| Replications | 30 |
| Mean training time | 9,925.70 hrs |
| Standard deviation | 41.26 hrs |
| Coefficient of variation | 0.42% |
| 95% CI | [9,910.29, 9,941.11] hrs |
| CI half-width | ±15.41 hrs |
| Relative half-width | **±0.16%** |

The coefficient of variation (CV) of 0.42% is exceptionally low, explaining
why 30 replications are sufficient to produce a CI about 32× tighter than the
±5% target. The low CV reflects the **law of large numbers operating within
each replication**: with ~11,000 independent failure events per run, the
within-run randomness averages out, leaving very little run-to-run variance.

---

## 9. Key Findings

1. **ETR of 61.9% — over a third of cluster time is non-productive.** The
   Effective Training Ratio sits at 0.6190 across all 30 replications, with
   very low variance (CV = 0.42%). Improving ETR is the primary lever for
   reducing total training time; every 1 percentage-point gain in ETR saves
   ~158 hrs of wall-clock time at this cluster scale.

2. **Failure recovery is the dominant overhead.** At 38.1% of total time,
   checkpoint-reload latency (`recovery_time = 20 min`) accounts for virtually
   all slowdown. Halving recovery time would reduce total training time by
   ~1,890 hrs (~19%).

3. **The repair pipeline's "leak" only matters for the 9.1% of repairs on
   genuinely bad servers, and for missed diagnoses.** The measured 24% repair
   failure rate is the same silent-fail probability whether or not the server
   was actually faulty going in, but a failure only has a consequence for the
   servers that were (§6): they stay bad and fail systematically again. The
   other 90.9% of repairs (8,239/run) are on servers that were never bad.
   Reducing the repair-fail probabilities or raising `diagnosis_probability`
   therefore only reduces the systematic-failure count, not the dominant
   random-failure count, and its benefit is bounded by the same ≤2.9% ceiling as
   any other node-management lever at these defaults (§5a). Perfect diagnosis
   would recover 52 hrs (0.5%) here.

4. **Warm standbys work as designed.** With only 36 host-selection events
   across 11,338 failures, the 16-server warm-standby reserve absorbs
   ~99.7% of failures with zero scheduling overhead.

5. **The spare pool is barely used.** ~1 preemption per run from a pool of
   200 servers means the spare pool provides a large safety margin that is
   rarely exercised under these parameters.

6. **The cluster never depletes.** Zero stalls and zero depletion events across
   all 30 replications confirm the configuration has sufficient resilience for
   the modelled failure rates and repair durations.

7. **Systematic failures saturate; the 7.6% share (§5.1) is a long-run
   average, not a stable rate.** With `bad_server_regeneration` off, a
   successful repair cures a bad server and nothing turns a good server bad,
   so the systematic-failure count is capped by the initial bad population
   (~623 of 4,160 servers) and plateaus at 862.6 ± 22.7 over a 256-day run —
   **about 40% of that ceiling is reached in the first 15 compute-days** (§5a).
   Random failures have no such ceiling and grow roughly linearly with job
   length (609 at 15 days → 10,444 at 256 days), so systematic failures'
   share of the total falls from 37% at 15 days to 7.6% at 256 days as the
   bad population is cured out from under them. Any policy that targets bad
   servers exclusively — retirement, health-aware scheduling, faster or more
   reliable repair, better diagnosis — is capped at eliminating 862.6
   systematic failures × `recovery_time` ≈ **288 h ≈ 2.9% of training time** at
   these parameters (§5a); increasing `systematic_failure_fraction` or
   `systematic_failure_rate_multiplier` would raise both the ceiling and the
   plateau.

---

## 10. Recommendations

| Action | Expected effect on ETR |
|--------|----------------------|
| Reduce `recovery_time` from 20 → 10 min | ETR: ~61.9% → ~76.5% (+14.6 pp); saves ~1,890 hrs |
| Raise `diagnosis_probability` from 0.8 → 1.0 | Saves ~52 hrs (+0.3 pp); only affects the systematic-failure share, capped by the ≤2.9% ceiling (§5a) |
| Reduce `auto_repair_fail_prob` from 0.40 → 0.20 | Blended failure rate 24% → 20%, but the change only has a consequence for the 9.1% of repairs on genuinely bad servers (§6); benefit capped by the ≤2.9% systematic-failure ceiling (§5a), not the 24%→20% headline drop |
| Reduce `manual_repair_fail_prob` from 0.20 → 0.10 | Blended failure rate 24% → 16%, same caveat: only the 9.1% bad-server repair share is affected, so the realized benefit is well under the ≤2.9% ceiling (§5a) |
| Reduce `prob_auto_to_manual` from 0.80 → 0.40 | Blended failure rate rises 24% → 32%, but again only for the 9.1% bad-server share — the random-failure majority (§5a) is untouched either way |
| Increase `warm_standbys` from 16 → 32 | Maintain near-zero host-selection overhead under higher failure rates |
| Enable `bad_server_regeneration` | Models hardware aging; expected to gradually reduce ETR over time |

All of these can be evaluated with a one-way sweep
(`python -m airesim.run --sweep recovery_time --values 5,10,15,20`) or by
adjusting `config.yaml` and re-running `--adaptive`.
