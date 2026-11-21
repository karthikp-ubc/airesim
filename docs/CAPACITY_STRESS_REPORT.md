# Capacity Stress Report: When the Job Waits for Servers

**Data:** console output in `examples/stress_figures/run.log`,
`examples/retirement_figures/run.log` and `examples/scored_figures/run.log` (these
scripts write figures, not CSVs), produced by `examples/stress_scenario.py`,
`examples/retirement_sweep.py` and `examples/scored_sweep.py` at commit `277f43c`.
Stall counts and stall time (§2) were measured separately with the same parameters and
seeds; they reproduce the scripts' training times exactly. "Before" columns are the same
scripts run on the pre-fix code (`63c1900`). Date: 2026-11-21.

---

## 1. Summary

The other reports in this repo use clusters with enough spare capacity that the job never
waits for a server; there, training time is exactly job length plus failure,
host-selection and preemption costs (`FINDINGS.md` §1). These three scripts use a **tight
working pool** — 4,128 servers for a 4,096-server job with 16 warm standbys, i.e. 16
servers of headroom — and, in the stress scenario, a small spare pool. In that setting:

- **Waiting for servers can dominate training time.** With 10 spares at a 5× failure
  rate, the job stalls about 1,000 times and spends **42% of its training time** waiting
  for repaired servers. With 100 spares it never stalls.
- **Spare-pool size becomes one of the two largest levers**, after recovery time: at 5×,
  training time falls from 1,519 h with 10 spares to 882 h with 100.
- **Faster recovery shifts the bottleneck to capacity.** At 5×, cutting recovery time from
  20 to 5 minutes should save ~504 h of checkpoint reloading but saves only 115 h: failures
  now arrive faster than repairs return servers, and the job is stalled 49% of the time.
- **Retirement hurts with little headroom.** `ThresholdRemoval(≥2/7d)` costs 41–106 h
  against never retiring, and no `ScoredRemoval` setting beats never retiring; aggressive
  settings drain the cluster.
- **The stall fix matters here** (CHANGELOG, "Paper conformance"). The pre-fix code kept a
  stalled job waiting until `job_size + warm_standbys` servers were free although
  `job_size` suffice; the corrected code is up to 19% faster in these configurations.

---

## 2. Stress scenario (`stress_scenario.py`)

**Setup:** working pool 4,128 (16 headroom), spare pool 50 (swept), 7-day job, 5× systematic
multiplier on 15% bad servers, recovery 20 min, host selection 3 min, preemption wait
20 min, auto/manual repair 2 h / 2 days, Table I repair probabilities, diagnosis 0.8. Two
regimes: random failure rate 2× and 5× the Table I default. 6 replications per point;
± is one standard deviation.

### 2.1 Spare-pool size

| Regime | Spares | Training time (h) | Stalls/run | Stall wait | Preemptions/run |
|---|---|---|---|---|---|
| 2× | 10 | 653.7 ± 31.8 | 282 | 171 h (26%) | 10 |
| 2× | 25 | 544.1 ± 12.6 | 124 | 56 h (10%) | 25 |
| 2× | 50 | 480.6 ± 11.0 | 0 | 0 | 42 |
| 2× | 100 | 483.5 ± 10.8 | 0 | 0 | 42 |
| 5× | 10 | 1,518.8 ± 49.3 | 992 | 642 h (42%) | 10 |
| 5× | 25 | 1,155.3 ± 49.7 | 604 | 279 h (24%) | 25 |
| 5× | 50 | 883.0 ± 10.4 | 80 | 23 h (3%) | 51 |
| 5× | 100 | 881.7 ± 16.9 | 0 | 0 | 68 |

Stall wait is training time minus the accounting identity
(`job_length + failures × recovery_time + host selections × host_selection_time +
preemptions × preemption_wait_time`). With 10 or 25 spares every spare is borrowed and
never returned; once the spare pool is exhausted, each server lost to repair stalls the
job until a repair finishes. From 50 spares (2×) or 100 (5×) up, the job never waits and
the identity holds exactly. Preemption waiting itself costs 14–23 h (about 3%) per run in
the unconstrained cells.

### 2.2 Recovery time

| Regime | Recovery | Training time (h) | Recovery time spent (h) | Stall wait |
|---|---|---|---|---|
| 2× | 5 min | 354.6 ± 14.6 | 78 | 83 h (23%) |
| 2× | 20 min | 480.6 ± 11.0 | 298 | 0 |
| 2× | 40 min | 766.9 ± 26.4 | 590 | 0 |
| 2× | 80 min | 1,383.3 ± 25.2 | 1,215 | 0 |
| 5× | 5 min | 767.5 ± 19.5 | 168 | 376 h (49%) |
| 5× | 20 min | 883.0 ± 10.4 | 673 | 23 h (3%) |
| 5× | 40 min | 1,534.8 ± 22.0 | 1,356 | 0 |
| 5× | 80 min | 2,882.6 ± 46.0 | 2,710 | 0 |

Recovery time is still the largest lever, but its payoff is capped by capacity at the
short end. Faster recovery compresses the same ~2,000 failures into less wall-clock time,
while repairs still take 2 hours to 2 days, so more servers are in repair at once and the
pool runs dry. At 5×, going from 20 to 5 minutes saves 115 h instead of the ~504 h of
reload time it removes.

### 2.3 Escalation probability and warm standbys

| Regime | `prob_auto_to_manual` 0.40 / 0.60 / 0.80 / 0.95 (h) | `warm_standbys` 4 / 8 / 16 / 32 (h) |
|---|---|---|
| 2× | 484.4 / 477.6 / 480.6 / 492.8 | 498.0 / 492.2 / 480.6 / 491.0 |
| 5× | 864.6 / 869.8 / 883.0 / 966.4 | 905.7 / 898.5 / 883.0 / 875.1 |

Escalating nearly every repair to the 2-day manual stage (0.95) costs 83 h at 5×: it keeps
more servers away in repair, which matters only because capacity is tight. Warm-standby
count has a small effect (≤ 31 h).

### 2.4 Sensitivity ranking

| Rank | 2× (range of training time) | 5× (range) |
|---|---|---|
| 1 | `recovery_time` (1,029 h) | `recovery_time` (2,115 h) |
| 2 | `spare_pool_size` (173 h) | `spare_pool_size` (637 h) |
| 3 | `warm_standbys` (17 h) | `prob_auto_to_manual` (102 h) |
| 4 | `prob_auto_to_manual` (15 h) | `warm_standbys` (31 h) |

### 2.5 Before and after the fixes

Old code vs new code, both at diagnosis 1.0 (isolates the code fixes), and the official run
at the 0.8 default:

| Regime | Spares | Pre-fix (h) | Fixed, diagnosis 1.0 (h) | Fixed, diagnosis 0.8 (h) |
|---|---|---|---|---|
| 2× | 10 | 991.2 | 819.4 | 653.7 |
| 2× | 25 | 712.0 | 622.4 | 544.1 |
| 2× | 50 | 509.4 | 488.0 | 480.6 |
| 2× | 100 | 486.9 | 487.7 | 483.5 |
| 5× | 10 | 2,252.6 | 1,833.6 | 1,518.8 |
| 5× | 25 | 1,605.6 | 1,375.5 | 1,155.3 |
| 5× | 50 | 1,102.4 | 955.5 | 883.0 |
| 5× | 100 | 861.6 | 858.1 | 881.7 |

The fix is worth up to 419 h (19%), all of it from the stall threshold: rerunning with
`return_borrowed_spares=False` gives the same times, because a tight pool never has
borrowed spares to return. Where the job never stalls (100 spares) old and new code agree.
The diagnosis default then lowers times further in the stalled cells — an undiagnosed
failure sends the server straight back to the pool instead of into a multi-day repair, so
fewer servers are away at once — at the cost of more failures (the 100-spare 5× cell is
24 h slower). The pre-fix code's spare-pool range at 5× (862–2,253 h) overstated the lever
by about 40%; it remains the second-largest.

---

## 3. Retirement with little headroom (`retirement_sweep.py`)

**Setup:** working pool 4,128 (16 headroom), spare pool 200, 14-day job, 5× random failure
rate, 10 replications; `auto_repair_fail_prob` × `ThresholdRemoval` threshold.

| Threshold | auto fail 0.2 | 0.4 | 0.6 | 0.8 |
|---|---|---|---|---|
| Never | 1,562 h / 0 | 1,582 h / 0 | 1,580 h / 0 | 1,613 h / 0 |
| 5 / 7d | 1,562 h / 0 | 1,582 h / 0 | 1,580 h / 0 | 1,613 h / 0 |
| 3 / 7d | 1,570 h / 5 | 1,578 h / 6 | 1,599 h / 7 | 1,605 h / 8 |
| 2 / 7d | 1,603 h / 150 | 1,644 h / 163 | 1,686 h / 174 | 1,688 h / 170 |

(mean training time / servers retired). With 16 servers of headroom every retirement
eventually costs a spare, and `≥2/7d` retires 150–174 servers — most of the 200-server
spare pool — making training 41–106 h slower than never retiring. `≥3/7d` and `≥5/7d`
retire almost nothing and change nothing. Contrast the 4,600-server payoff regime, where
the same `≥2/7d` saves time (`THRESHOLD_SENSITIVITY_REPORT.md`). Pre-fix results at
diagnosis 1.0 lead to the same conclusions; the code-fix differences are within noise.

---

## 4. `ScoredRemoval` parameters at Table I-like settings (`scored_sweep.py`)

**Setup:** working pool 4,160 (48 headroom), spare pool 200, 7-day job, Table I failure
and repair parameters, 10 replications; one `ScoredRemoval` parameter swept at a time
around `initial_score=100, failure_penalty=30, success_increment=10, time_period=1 day,
retirement_threshold=0`. `NeverRemove` baseline: 327.6 ± 4.8 h.

- **Most settings retire nothing.** A server needs `initial_score / failure_penalty`
  diagnosed failures to be retired; in a 7-day job at Table I failure rates few servers
  get there.
- **Retiring ~13 servers costs 3.6 h** (`failure_penalty = 50`, `initial_score = 50` or
  `retirement_threshold = 50`).
- **Aggressive settings drain the cluster** (`failure_penalty = 100`, `initial_score = 25`
  or `retirement_threshold = 75`): every run retires 265 servers — the whole working pool
  plus spares minus the job size — and ends depleted after 509 h. With the corrected
  depletion check the run continues until fewer than `job_size` servers remain (it used
  to stop at `job_size + warm_standbys`, after 252 retirements).
- **Uptime credits are inert:** `success_increment` and `time_period` have no effect at any
  value (see `RETIREMENT_POLICY_REPORT.md` §7).
- **No setting beats `NeverRemove`.**

---

## 5. Takeaways

1. **Capacity, not just recovery, can dominate.** In a cluster with little headroom and a
   small spare pool, time waiting for repaired servers reaches 40–50% of training time.
   Spare-pool size is then the second-largest lever, and the accounting identity used
   elsewhere in this repo no longer describes training time.
2. **Levers interact through capacity.** Faster recovery, more escalation to slow manual
   repair, and aggressive retirement all change how many servers are away at once; in a
   tight pool that can cancel most of their nominal effect or turn it negative.
3. **Don't retire servers you can't replace.** With 16 servers of headroom, retirement
   policies that pay off in a 488-server-headroom cluster cost time.

---

*Generated from the run logs listed above, 2026-11-21.*
