# Diagnosis Parameter Sweep — Report

**Regime:** 20× failure multiplier | 75% manual repair fail probability | 4 600-server pool
**Replications per cell:** 8
**Baseline:** Random + NeverRemove, diagnosis\_probability = 1.0, diagnosis\_uncertainty = 0.0 → **2 395 h** (± 39)
**Baseline ETR:** 336 / 2395 = **14.0%** (job\_length = 14 days = 336 hrs; ETR = 336 / training\_time)

**Data:** `examples/diagnosis_sweep_figures/diagnosis_sweep.csv` (73 rows), produced by
`examples/diagnosis_sweep.py` at commit `0cab8fb` (run log:
`examples/diagnosis_sweep_figures/run.log`). Repairs follow the paper's model:
`prob_auto_to_manual` is the probability that auto repair escalates, independent of the
silent auto-repair failure `auto_repair_fail_prob`. Date: 2026-09-21.

Figures: `examples/diagnosis_sweep_figures/`

> **Note:** Sweep B depends on two fixes to the misdiagnosis path in `simulator.py`:
> 1. *Floating-server deadlock* — escaped bad servers were not returned to the working pool,
>    causing the simulation to deadlock silently at high uncertainty.
> 2. *Active-server duplication* — `on_server_returned` was called for the escaped bad server
>    while it was still in `active_servers`, potentially adding it to `warm_standbys` and
>    creating a duplicate in `active_servers` on the next standby swap.

> **Design note (2026-09-22, corrected).** An earlier version of this caveat argued
> that `FewestFailuresFirst`'s results here don't generalize because full host
> selection is "rarely consulted." That's wrong: `Scheduler.do_host_selection`
> re-picks the *entire* job (`job_size + warm_standbys`) from the available pool
> each time it runs, so one full selection can bench every server the policy
> currently regards as bad, up to headroom
> (`working_pool_size - job_size - warm_standbys`). Between full selections,
> `Scheduler.swap_in_standby` replaces a failed active server with the oldest warm
> standby, FIFO, without consulting the policy.
>
> `FewestFailuresFirst` can only bench a bad server that has already failed at least
> once — one that hasn't yet failed looks identical to a good server. This sweep uses
> the same stress-regime parameters as `SCHEDULING_COMPARISON_REPORT.md` and
> `2D-HEAT_MAP_REPORT.md` (`working_pool_size=4,600`, `job_size=4,096`,
> `warm_standbys=16`, `systematic_failure_fraction=0.08`): headroom is 488 servers
> against an initial bad population of ~368 (8%) — headroom above the bad population
> lets a full selection bench every *known*-bad server, not the whole population
> outright. Both of those reports' per-replication data confirm the measured effect —
> a 24% (scheduling sweep) to 16% (heat map) reduction in time-averaged faulty
> servers in the active job, not near-total exclusion — and that
> `FewestFailuresFirst` keeps *more* bad servers in the cluster overall (they're
> benched, not cured) while still winning on training time (see their design notes).
> This sweep's own per-run host-selection counts and active/pool faulty-server
> breakdowns were not logged and are not reproduced here. At **paper-semantics
> defaults** (not this sweep's regime), headroom is only 48 servers against ~624
> initially bad (7.7% coverage) and systematic failures saturate early
> (`SIMULATION_REPORT.md` §5a), which is why `FewestFailuresFirst` shows no
> measurable benefit there (`DIAGNOSIS_REALISTIC_REPORT.md`) — bounded by headroom
> and saturation, not by consultation frequency. `FewestFailuresFirst` and
> `ThresholdRemoval` below read ground-truth failure counts/timestamps, not
> attributed blame (see §3.3 and §4); `FewestAttributedFailuresFirst` has not been
> tested in this (stress) regime.

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

Bold values in the tables below differ from the baseline by more than two standard errors
(standard error of a difference of two 8-replication means, from the per-cell standard
deviations).

---

## 2  Sweep A — `diagnosis_probability`  (uncertainty fixed at 0)

### 2.1  Raw results

The `prob = 1.00` row is the same cell as the `unc = 0.00` row of Sweep B.

| prob | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 3 295.9 |  69.8 | **+901.3** |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 3 295.9 |  69.8 | **+901.3** |     0.0 |
| 0.00 | Random+ScoredRemoval         | 3 295.9 |  69.8 | **+901.3** |     0.0 |
| 0.00 | FewestFail+NeverRemove       | 3 264.8 |  55.0 | **+870.2** |     0.0 |
| 0.00 | FewestFail+Thresh ≥2/7d      | 3 264.8 |  55.0 | **+870.2** |     0.0 |
| 0.00 | FewestFail+ScoredRemoval     | 3 264.8 |  55.0 | **+870.2** |     0.0 |
| 0.20 | Random+NeverRemove           | 3 025.1 |  82.7 | **+630.4** |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 926.8 |  35.5 | **+532.2** |    58.5 |
| 0.20 | Random+ScoredRemoval         | 2 976.7 |  63.3 | **+582.1** |    73.8 |
| 0.20 | FewestFail+NeverRemove       | 2 923.1 | 243.6 | **+528.4** |     0.0 |
| 0.20 | FewestFail+Thresh ≥2/7d      | 2 274.1 |  55.5 | **-120.6** |    36.5 |
| 0.20 | FewestFail+ScoredRemoval     | 2 351.8 |  43.0 | **-42.9** |    27.8 |
| 0.40 | Random+NeverRemove           | 2 764.4 |  38.1 | **+369.8** |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 2 696.1 |  59.7 | **+301.5** |    86.5 |
| 0.40 | Random+ScoredRemoval         | 2 618.5 |  37.0 | **+223.8** |   179.8 |
| 0.40 | FewestFail+NeverRemove       | 2 397.2 | 114.8 | +2.5 |     0.0 |
| 0.40 | FewestFail+Thresh ≥2/7d      | 2 213.5 |  48.1 | **-181.2** |    53.5 |
| 0.40 | FewestFail+ScoredRemoval     | 2 198.3 |  39.9 | **-196.4** |    72.6 |
| 0.60 | Random+NeverRemove           | 2 641.6 |  72.5 | **+247.0** |     0.0 |
| 0.60 | Random+Thresh ≥2/7d          | 2 554.1 |  53.7 | **+159.4** |   107.2 |
| 0.60 | Random+ScoredRemoval         | 2 391.8 |  48.7 | -2.9 |   263.1 |
| 0.60 | FewestFail+NeverRemove       | 2 231.2 |  30.7 | **-163.4** |     0.0 |
| 0.60 | FewestFail+Thresh ≥2/7d      | 2 161.7 |  44.1 | **-233.0** |    61.1 |
| 0.60 | FewestFail+ScoredRemoval     | 2 127.8 |  24.1 | **-266.9** |   142.6 |
| 0.80 | Random+NeverRemove           | 2 502.0 |  50.3 | **+107.3** |     0.0 |
| 0.80 | Random+Thresh ≥2/7d          | 2 430.2 |  58.5 | +35.5 |   100.5 |
| 0.80 | Random+ScoredRemoval         | 2 227.2 |  33.1 | **-167.4** |   336.4 |
| 0.80 | FewestFail+NeverRemove       | 2 168.2 |  48.8 | **-226.5** |     0.0 |
| 0.80 | FewestFail+Thresh ≥2/7d      | 2 123.6 |  40.3 | **-271.0** |    66.9 |
| 0.80 | FewestFail+ScoredRemoval     | 2 121.0 |  36.5 | **-273.6** |   229.5 |
| 1.00 | Random+NeverRemove           | 2 394.6 |  38.7 | +0.0 |     0.0 |
| 1.00 | Random+Thresh ≥2/7d          | 2 305.8 |  68.2 | **-88.8** |   105.6 |
| 1.00 | Random+ScoredRemoval         | 2 083.0 |  37.1 | **-311.6** |   388.2 |
| 1.00 | FewestFail+NeverRemove       | 2 116.2 |  56.1 | **-278.4** |     0.0 |
| 1.00 | FewestFail+Thresh ≥2/7d      | 2 097.2 |  48.1 | **-297.5** |    69.1 |
| 1.00 | FewestFail+ScoredRemoval     | 2 064.5 |  35.5 | **-330.2** |   334.8 |

### 2.2  ETR summary — Sweep A

ETR = 336 / mean_training_time. Values for the best and worst policy combination at each level:

| value | Best policy | Mean (h) | ETR | Worst policy | Mean (h) | ETR |
|-----|-------------|----------|-----|--------------|----------|-----|
| 0.00 | Any (no repairs) | 3 265–3 296 | 10.2–10.3% | — | — | — |
| 0.20 | FewestFail+Thresh ≥2/7d | 2 274 | 14.8% | Random+NeverRemove | 3 025 | 11.1% |
| 0.40 | FewestFail+ScoredRemoval | 2 198 | 15.3% | Random+NeverRemove | 2 764 | 12.2% |
| 0.60 | FewestFail+ScoredRemoval | 2 128 | 15.8% | Random+NeverRemove | 2 642 | 12.7% |
| 0.80 | FewestFail+ScoredRemoval | 2 121 | 15.8% | Random+NeverRemove | 2 502 | 13.4% |
| 1.00 | FewestFail+ScoredRemoval | 2 064 | 16.3% | Random+NeverRemove | 2 395 | 14.0% |

At `prob = 0` (no diagnosis), ETR collapses to **~10%** — bad servers cycle continuously through
the pool without repair, adding roughly 900 h of recovery overhead. Full diagnosis (`prob = 1`)
recovers ETR to **16.3%** for the best policy combination.

### 2.3  Key observations

- **prob = 0:** All policies converge — the repair pipeline is never entered, 0 retirements.
  Training takes about +900 h over baseline (bad servers keep failing, never cleaned). The
  two scheduling policies (3 296 h vs 3 265 h) are indistinguishable at this noise level.
- **Retirement is what rescues low diagnosis probability, and only with smart scheduling.**
  At `prob = 0.20`, `Random+NeverRemove` is +630 h, and adding retirement to random
  scheduling recovers only about 50–100 h. `FewestFail+Thresh ≥2/7d` is −121 h and
  `FewestFail+ScoredRemoval` is −43 h. `ThresholdRemoval` does better than
  `ScoredRemoval` here (2 274 h vs 2 352 h, about 3 standard errors) because it reads
  every server's failure timestamps, while `ScoredRemoval`'s score only moves on
  diagnosed failures.
- **`FewestFail+NeverRemove` is very noisy at low probability:** standard deviations of 244 h
  (`prob = 0.20`) and 115 h (`prob = 0.40`), against 40–60 h elsewhere, so its means there
  (2 923 h, 2 397 h) should not be read precisely.
- **Retirement breaks even against the baseline at different points:** `Random+ScoredRemoval`
  at `prob ≈ 0.6` (−3 h), `Random+Thresh ≥2/7d` between 0.8 (+36 h) and 1.0 (−89 h).
  With smart scheduling, both retirement policies are already net-beneficial from
  `prob = 0.2`.
- **Best at prob = 1.0:** `FewestFail+ScoredRemoval` (−330 h) and `Random+ScoredRemoval`
  (−312 h) are statistically tied (18 h apart, about one standard error). Smart scheduling
  alone (`FewestFail+NeverRemove`, −278 h) reaches 84% of the best.

---

## 3  Sweep B — `diagnosis_uncertainty`  (probability fixed at 1.0)

### 3.1  Raw results

The `unc = 0.00` row is the same cell as the `prob = 1.00` row of Sweep A.

| unc | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 2 394.6 |  38.7 | +0.0 |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 2 305.8 |  68.2 | **-88.8** |   105.6 |
| 0.00 | Random+ScoredRemoval         | 2 083.0 |  37.1 | **-311.6** |   388.2 |
| 0.00 | FewestFail+NeverRemove       | 2 116.2 |  56.1 | **-278.4** |     0.0 |
| 0.00 | FewestFail+Thresh ≥2/7d      | 2 097.2 |  48.1 | **-297.5** |    69.1 |
| 0.00 | FewestFail+ScoredRemoval     | 2 064.5 |  35.5 | **-330.2** |   334.8 |
| 0.20 | Random+NeverRemove           | 2 547.7 |  53.3 | **+153.1** |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 394.3 |  62.2 | -0.4 |   108.0 |
| 0.20 | Random+ScoredRemoval         | 2 179.1 |  24.1 | **-215.6** |   411.1 |
| 0.20 | FewestFail+NeverRemove       | 2 148.7 |  58.9 | **-245.9** |     0.0 |
| 0.20 | FewestFail+Thresh ≥2/7d      | 2 142.0 |  57.6 | **-252.6** |    68.1 |
| 0.20 | FewestFail+ScoredRemoval     | 2 088.1 |  23.2 | **-306.5** |   292.4 |
| 0.40 | Random+NeverRemove           | 2 605.3 |  56.8 | **+210.6** |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 2 501.4 |  65.1 | **+106.8** |   111.9 |
| 0.40 | Random+ScoredRemoval         | 2 386.0 |  51.1 | -8.7 |   442.5 |
| 0.40 | FewestFail+NeverRemove       | 2 238.6 |  70.2 | **-156.1** |     0.0 |
| 0.40 | FewestFail+Thresh ≥2/7d      | 2 158.0 |  34.0 | **-236.7** |    60.8 |
| 0.40 | FewestFail+ScoredRemoval     | 2 113.3 |  39.5 | **-281.3** |   275.2 |
| 0.60 | Random+NeverRemove           | 2 744.4 |  63.4 | **+349.8** |     0.0 |
| 0.60 | Random+Thresh ≥2/7d          | 2 678.1 |  64.3 | **+283.5** |    93.8 |
| 0.60 | Random+ScoredRemoval         | 2 588.5 |  46.3 | **+193.8** |   476.2 |
| 0.60 | FewestFail+NeverRemove       | 2 225.4 |  36.4 | **-169.3** |     0.0 |
| 0.60 | FewestFail+Thresh ≥2/7d      | 2 197.4 |  42.0 | **-197.3** |    48.6 |
| 0.60 | FewestFail+ScoredRemoval     | 2 195.5 |  25.8 | **-199.1** |   283.4 |
| 0.80 | Random+NeverRemove           | 2 943.9 |  76.7 | **+549.3** |     0.0 |
| 0.80 | Random+Thresh ≥2/7d          | 2 882.0 |  35.8 | **+487.3** |    60.5 |
| 0.80 | Random+ScoredRemoval         | 2 885.5 |  51.7 | **+490.8** |   536.0 |
| 0.80 | FewestFail+NeverRemove       | 2 309.4 |  59.3 | **-85.3** |     0.0 |
| 0.80 | FewestFail+Thresh ≥2/7d      | 2 208.6 |  43.7 | **-186.0** |    30.6 |
| 0.80 | FewestFail+ScoredRemoval     | 2 268.8 |  41.3 | **-125.8** |   305.1 |
| 1.00 | Random+NeverRemove           | 3 191.5 |  50.4 | **+796.8** |     0.0 |
| 1.00 | Random+Thresh ≥2/7d          | 3 158.7 |  36.4 | **+764.1** |     4.9 |
| 1.00 | Random+ScoredRemoval         | 3 287.7 | 121.2 | **+893.1** |   646.0 |
| 1.00 | FewestFail+NeverRemove       | 2 316.0 |  64.6 | **-78.7** |     0.0 |
| 1.00 | FewestFail+Thresh ≥2/7d      | 2 326.8 |  74.8 | **-67.9** |     2.1 |
| 1.00 | FewestFail+ScoredRemoval     | 2 381.5 |  44.7 | -13.2 |   359.9 |

### 3.2  ETR summary — Sweep B

ETR = 336 / mean_training_time. Key ETR values by uncertainty level:

| value | Best policy | Mean (h) | ETR | Worst policy | Mean (h) | ETR |
|-----|-------------|----------|-----|--------------|----------|-----|
| 0.00 | FewestFail+ScoredRemoval | 2 064 | 16.3% | Random+NeverRemove | 2 395 | 14.0% |
| 0.20 | FewestFail+ScoredRemoval | 2 088 | 16.1% | Random+NeverRemove | 2 548 | 13.2% |
| 0.40 | FewestFail+ScoredRemoval | 2 113 | 15.9% | Random+NeverRemove | 2 605 | 12.9% |
| 0.60 | FewestFail+ScoredRemoval | 2 196 | 15.3% | Random+NeverRemove | 2 744 | 12.2% |
| 0.80 | FewestFail+Thresh ≥2/7d | 2 209 | 15.2% | Random+NeverRemove | 2 944 | 11.4% |
| 1.00 | FewestFail+NeverRemove | 2 316 | 14.5% | Random+ScoredRemoval | 3 288 | 10.2% |

As misdiagnosis uncertainty rises, the **best achievable ETR falls** monotonically from 16.3%
(unc = 0) to 14.5% (unc = 1). At full uncertainty, `Random+ScoredRemoval` is the *worst*
policy (ETR = 10.2%) because it retires innocent servers and keeps bad ones.
`FewestFailures+NeverRemove` is the most ETR-robust strategy at high uncertainty.

### 3.3  Key observations

**Random scheduling degrades steeply with uncertainty; FewestFailures scheduling barely does.**
`Random+NeverRemove` rises from 2 395 h to 3 192 h (+33%) between `unc = 0` and `unc = 1`,
while `FewestFail+NeverRemove` rises from 2 116 h to 2 316 h (+9%). At `unc = 1.0` the
scheduling policy alone is worth 875 h (`FewestFail+NeverRemove` vs `Random+NeverRemove`).
Reason: `FewestFailuresFirst` sorts by `total_failure_count`, which tracks the server's
*actual* hardware failures regardless of misattribution. Bad servers accumulate real
failure counts quickly, so FewestFailures deprioritises them even though their failures
are attributed to innocent servers. This does not rely on the diagnosis pipeline at all
— but it does read ground-truth counts an operator may not have (see the design caveat).

**ScoredRemoval is only net-harmful at full uncertainty.**
Relative to the matching `NeverRemove` cell, `ScoredRemoval` still helps through
`unc = 0.8` (`Random`: −58 h; `FewestFail`: −41 h) and turns harmful at `unc = 1.0`
(`Random`: +96 h, `FewestFail`: +65 h, each about two standard errors). Mechanism:
`on_failure` is called on the misdiagnosed *innocent* server, not the actual bad server.
Innocent servers accumulate penalty scores and are retired (up to 646 retirements at
`unc = 1.0`); the bad servers' scores remain pristine and they are preferentially kept.
The pool progressively fills with high-failure-rate servers — a perverse inversion of
ScoredRemoval's intent.

**ThresholdRemoval degrades toward NeverRemove at high uncertainty.**
At `unc = 1.0`, `Thresh ≥2/7d` retires only 2–5 servers and its time is
indistinguishable from `NeverRemove` (3 159 h vs 3 192 h with random scheduling; 2 327 h
vs 2 316 h with FewestFailures). The reason: ThresholdRemoval reads `failure_timestamps` on
the *server entering repair*. At `unc = 1.0`, the server entering repair is always the
innocent one, whose timestamps reflect only its rare genuine failures, so the threshold is
almost never reached.

**The benefit of retirement over smart scheduling alone shrinks as uncertainty rises.**
With FewestFailures scheduling, `ScoredRemoval` saves 52 h relative to `NeverRemove` at
`unc = 0`, 61 h at 0.2 and 125 h at 0.4, then 30–41 h at 0.6–0.8 and turns into a 65 h penalty at 1.0.
At `unc ≥ 0.6` the best combinations are `FewestFail+Thresh ≥2/7d` or
`FewestFail+NeverRemove`, and by `unc = 1.0` no retirement policy helps.

---

## 4  Practical guidance

> Every recommendation below that names `FewestFailures` or `ThresholdRemoval` assumes
> the ground truth those policies actually read: `total_failure_count` and
> `failure_timestamps` are recorded on the server that truly failed at the moment it
> fails, before diagnosis runs — including failures diagnosis misses entirely. An
> operator using the attributed-count variant (`FewestAttributedFailuresFirst`) would
> not have this; it has not been tested at these (stress-regime) parameters.

### When to adjust `diagnosis_probability`  (uncertainty = 0)

| prob | Recommended policy | Rationale |
|------|--------------------|-----------|
| < 0.40 | FewestFail+Thresh ≥2/7d | ThresholdRemoval has signal via timestamps; ScoredRemoval blind to missed failures |
| 0.40–0.80 | FewestFail+ScoredRemoval (or FewestFail+Thresh ≥2/7d) | The two are within about two standard errors from 0.4 up; −196 to −274 h |
| ≥ 0.80 | FewestFail+ScoredRemoval or Random+ScoredRemoval | At full diagnosis the two are tied (−330 h / −312 h); FewestFail+NeverRemove gets −278 h with no retirements |

### When to adjust `diagnosis_uncertainty`  (probability = 1)

| unc  | Recommended policy | Rationale |
|------|--------------------|-----------|
| 0.00 | FewestFail+ScoredRemoval | −330 h |
| ≤ 0.40 | FewestFail+ScoredRemoval | −307 h (0.2), −281 h (0.4); still clearly net-positive |
| 0.60–0.80 | FewestFail+Thresh ≥2/7d | −197 h (0.6), −186 h (0.8); ScoredRemoval ties at 0.6 and falls behind at 0.8 |
| = 1.00 | FewestFail+NeverRemove | −79 h; no retirement policy helps |
| = 1.00 | **Avoid ScoredRemoval** | Random+ScoredRemoval is +893 h vs +797 h for Random+NeverRemove; retires innocent servers, keeps bad ones |

### Critical interactions

- **ScoredRemoval inverts at high uncertainty:** `on_failure` is called on the wrong server.
  At `unc = 1.0`, ScoredRemoval does more harm than no retirement policy at all.

- **FewestFailures is diagnosis-agnostic:** It uses raw `total_failure_count` (actual hardware
  failures, not attributed blame), making it the most robust scheduling policy under
  misattribution *among the policies tested here* — this assumes access to that
  ground-truth count, which an operator relying on the diagnosis pipeline would not have;
  `FewestAttributedFailuresFirst`, the attributed-count variant an operator could actually
  deploy, has not been tested at these (stress-regime) parameters. At `unc = 1.0` it saves
  875 h vs. Random scheduling alone.

- **ThresholdRemoval's partial immunity breaks at high uncertainty:** It can leverage
  `failure_timestamps` (actual failures, not attributed blame) only for servers that enter
  repair — also ground truth, recorded on the server before diagnosis runs, including
  failures diagnosis missed. At `unc = 1.0`, only innocent servers enter repair, so
  ThresholdRemoval cannot act on the bad servers' timestamps.

---

## 5  Summary

```
Sweep A — diagnosis_probability (uncertainty = 0):
  Smart scheduling + retirement is net-beneficial from prob ≈ 0.2
  Random scheduling + ScoredRemoval breaks even at prob ≈ 0.6
  Best at prob = 1.0: FewestFail+ScoredRemoval  −330 h  (tied with Random+ScoredRemoval −312 h)

Sweep B — diagnosis_uncertainty (probability = 1):

  unc = 0.00:  FewestFail+ScoredRemoval  −330 h  (optimal)
  unc = 0.20:  FewestFail+ScoredRemoval  −307 h
  unc = 0.40:  FewestFail+ScoredRemoval  −281 h
  unc = 0.60:  FewestFail+Thresh ≥2/7d  −197 h  (ScoredRemoval tied, −199 h)
  unc = 0.80:  FewestFail+Thresh ≥2/7d  −186 h
  unc = 1.00:  FewestFail+NeverRemove   −79 h   (scheduling alone; retirement gives no benefit)

  Key crossovers:
    ScoredRemoval net-negative vs NeverRemove: unc = 1.0 (unc ≤ 0.8 still net-positive)
    ThresholdRemoval: no effect at unc = 1.0 (retires only 2–5 servers)
    FewestFail scheduling benefit: increases with uncertainty (875 h at unc = 1.0)
```

**Practical bottom line:** `ScoredRemoval` helps at every uncertainty level up to 0.8 but turns
net-harmful at `diagnosis_uncertainty = 1.0`, and from about 0.6 upward
`ThresholdRemoval` matches or beats it. If `diagnosis_uncertainty` can reach 1.0, drop
`ScoredRemoval` and rely on FewestFailures scheduling alone; at that point no retirement
policy produces a net benefit and the priority is accurate diagnosis, not smarter retirement.
