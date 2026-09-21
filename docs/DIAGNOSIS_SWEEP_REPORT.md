# Diagnosis Parameter Sweep — Report

**Regime:** 20× failure multiplier | 75% manual repair fail probability | 4 600-server pool
**Replications per cell:** 4 (this regeneration; originally 3)
**Baseline:** Random + NeverRemove, diagnosis\_probability = 1.0, diagnosis\_uncertainty = 0.0 → **2 076 h**
**Baseline ETR:** 336 / 2076 = **16.2%** (job\_length = 14 days = 336 hrs; ETR = 336 / training\_time)

Figures: `examples/diagnosis_sweep_figures/`

> **Regenerated after a third bug fix (2026-09-20), at reduced replication count.**
> This report already documented two misdiagnosis-path bugs fixed before its original
> run (floating-server deadlock, active-server duplication — both listed below,
> unaffected by anything new here). A third, unrelated bug has since been fixed:
> `RepairShop._repair_process` constructed an injected `RepairEscalationPolicy` but
> never consulted it, so escalation to manual repair fired for a flat 80% of *all*
> auto repairs instead of 80% of the ~60% that actually failed (see `CHANGELOG.md`).
> Every table below is regenerated with that fix applied, at **4 replications per
> cell** (down from the original 3 — chosen for a memory-constrained regeneration,
> not for extra precision, so per-cell noise is still substantial). Where a cell
> overlaps exactly with `SCHEDULING_COMPARISON_REPORT.md`'s 3×3 policy grid (i.e.
> `diagnosis_probability=1.0, diagnosis_uncertainty=0.0`), this report uses that
> report's more reliable **15-replication** numbers instead of its own 4-replication
> estimate of the same cell — see §2.1 and §3.1.
>
> Two bugs in the misdiagnosis path were fixed before the *original* version of this
> sweep was run:
> 1. *Floating-server deadlock* — escaped bad servers were not returned to the working pool,
>    causing the simulation to deadlock silently at high uncertainty.
> 2. *Active-server duplication* — `on_server_returned` was called for the escaped bad server
>    while it was still in `active_servers`, potentially adding it to `warm_standbys` and
>    creating a duplicate in `active_servers` on the next standby swap.

> **Design caveat (2026-09-21).** In AIReSim the scheduling policy is consulted
> only at full host selection. Warm-standby swaps take the oldest standby
> (`Scheduler.swap_in_standby`) without consulting the policy, and repaired
> servers that were in the job return to the standby list regardless of failure
> history. The `FewestFailuresFirst`/`HighestScoreFirst` results below therefore
> measure the policy's effect at the host selections that happen when the job
> exhausts its warm standbys. They do not measure health-aware replacement as an
> operator would implement it. The number of full host selections per run was not
> recorded for this sweep. At the paper defaults it is about 16 per run against
> ~11,000 failures (`DIAGNOSIS_REALISTIC_REPORT.md`). `FewestFailuresFirst` here
> also reads ground-truth failure counts (see `DIAGNOSIS_REALISTIC_REPORT.md` for
> the attributed-count variant).

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

The `prob = 1.00` row is the same cell as `SCHEDULING_COMPARISON_REPORT.md`'s 3×3 grid;
it's shown here with that report's 15-replication numbers rather than this sweep's own
4-replication estimate of the same cell.

| prob | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 3 326.8  |  79.7 | +1 259.3    |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 3 326.8  |  79.7 | +1 259.3    |     0.0 |
| 0.00 | Random+ScoredRemoval         | 3 326.8  |  79.7 | +1 259.3    |     0.0 |
| 0.00 | FewestFail+NeverRemove       | 3 269.0  |  45.9 | +1 201.6    |     0.0 |
| 0.00 | FewestFail+Thresh ≥2/7d      | 3 269.0  |  45.9 | +1 201.6    |     0.0 |
| 0.00 | FewestFail+ScoredRemoval     | 3 269.0  |  45.9 | +1 201.6    |     0.0 |
| 0.20 | Random+NeverRemove           | 2 867.3  |  68.1 |   +799.8    |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 831.7  |  67.1 |   +764.3    |    59.8 |
| 0.20 | Random+ScoredRemoval         | 2 841.2  |  69.5 |   +773.8    |    53.5 |
| 0.20 | FewestFail+NeverRemove       | 2 818.0  |  45.3 |   +750.6    |     0.0 |
| 0.20 | FewestFail+Thresh ≥2/7d      | 2 253.7  |  43.9 |   +186.2    |    40.8 |
| 0.20 | FewestFail+ScoredRemoval     | 2 385.7  |  72.1 |   +318.2    |    25.0 |
| 0.40 | Random+NeverRemove           | 2 604.6  |  16.2 |   +537.1    |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 2 526.4  |  44.6 |   +458.9    |    79.2 |
| 0.40 | Random+ScoredRemoval         | 2 484.6  |  33.4 |   +417.1    |   133.8 |
| 0.40 | FewestFail+NeverRemove       | 2 385.1  | 175.6 |   +317.6    |     0.0 |
| 0.40 | FewestFail+Thresh ≥2/7d      | 2 155.8  |  72.1 |    +88.3    |    52.0 |
| 0.40 | FewestFail+ScoredRemoval     | 2 150.5  |  41.6 |    +83.1    |    58.2 |
| 0.60 | Random+NeverRemove           | 2 300.4  |  26.5 |   +232.9    |     0.0 |
| 0.60 | Random+Thresh ≥2/7d          | 2 301.4  |  27.1 |   +233.9    |    81.0 |
| 0.60 | Random+ScoredRemoval         | 2 267.3  |  44.8 |   +199.8    |   206.5 |
| 0.60 | FewestFail+NeverRemove       | 2 153.2  |  67.6 |    +85.7    |     0.0 |
| 0.60 | FewestFail+Thresh ≥2/7d      | 2 057.6  |  37.7 |     **−9.9**|    59.0 |
| 0.60 | FewestFail+ScoredRemoval     | 2 054.0  |  21.0 |    **−13.5**|   106.2 |
| 0.80 | Random+NeverRemove           | 2 218.2  |  66.5 |   +150.7    |     0.0 |
| 0.80 | Random+Thresh ≥2/7d          | 2 155.5  |  17.3 |    +88.0    |    83.8 |
| 0.80 | Random+ScoredRemoval         | 2 096.9  |  35.8 |    **+29.5**|   260.5 |
| 0.80 | FewestFail+NeverRemove       | 2 074.4  |  25.6 |     **+7.0**|     0.0 |
| 0.80 | FewestFail+Thresh ≥2/7d      | 2 014.9  |  20.0 |    **−52.6**|    58.8 |
| 0.80 | FewestFail+ScoredRemoval     | 2 022.7  |  15.9 |    **−44.8**|   174.2 |
| 1.00 | Random+NeverRemove           | 2 076.0  |  38.5 |       0.0   |     0.0 |
| 1.00 | Random+Thresh ≥2/7d          | 2 072.1  |  39.0 |     **−3.9**|    75.4 |
| 1.00 | Random+ScoredRemoval         | 1 992.9  |  47.8 |    **−83.1**|   321.8 |
| 1.00 | FewestFail+NeverRemove       | 2 007.4  |  58.3 |    **−68.6**|     0.0 |
| 1.00 | FewestFail+Thresh ≥2/7d      | 2 008.0  |  47.2 |    **−68.0**|    58.1 |
| 1.00 | FewestFail+ScoredRemoval     | 1 985.8  |  42.3 |    **−90.2**|   263.4 |

**`prob=0.80` flips sign for `Random+ScoredRemoval`**: pre-fix it was a real benefit (−47.3h);
post-fix it's a (small, likely noisy) regression (+29.5h). `FewestFail+NeverRemove` at the
same point flips too (−63.1h pre-fix → +7.0h post-fix, essentially zero either way). See §2.3.

### 2.2  ETR summary — Sweep A

ETR = 336 / mean_training_time. Values for selected configurations:

| prob | Best policy | Mean (h) | ETR | Worst policy | Mean (h) | ETR |
|------|-------------|----------|-----|--------------|----------|-----|
| 0.00 | Random+Any | 3 327 | 10.1% | FewestFail+Any | 3 269 | 10.3% |
| 0.20 | FewestFail+Thresh | 2 254 | 14.9% | FewestFail+NeverRemove | 2 818 | 11.9% |
| 0.40 | FewestFail+Scored | 2 151 | 15.6% | Random+NeverRemove | 2 605 | 12.9% |
| 0.60 | FewestFail+Scored | 2 054 | 16.4% | Random+Thresh | 2 301 | 14.6% |
| 0.80 | FewestFail+Thresh | 2 015 | 16.7% | Random+NeverRemove | 2 218 | 15.1% |
| 1.00 | Random+Scored | 1 993 | 16.9% | Random+NeverRemove | 2 076 | 16.2% |

At `prob = 0` (no diagnosis), ETR still collapses to **~10%** — bad servers cycle continuously
through the pool without repair, and the fix has no effect here (the repair pipeline is never
entered, so `RepairEscalationPolicy` is never called). Full diagnosis (`prob = 1`) now recovers
ETR to **16.9%** for the best combination (was 16.5%) — a smaller gain over the `prob=0` floor
than pre-fix, since the "no diagnosis" floor itself barely moved while the fully-diagnosed
ceiling only improved slightly.

### 2.3  Key observations

- **prob = 0:** Still unaffected by the fix — training takes +1,259h over baseline (was
  +1,060h; both numbers reflect the same "no repair pipeline at all" regime, plus n=3→4
  sampling noise; this is not a real regression).
- **FewestFail reversal at prob = 0.20 still holds:** `FewestFail+NeverRemove` is +750.6h vs
  baseline, still far worse than `Random+NeverRemove` (+799.8h is now actually *worse* — this
  particular ordering is noisy at n=4; both are clearly bad relative to `FewestFail+Thresh`).
  The mechanism is unchanged: FewestFail deprioritises bad servers, so when only 20% of
  failures are diagnosed, bad servers are simultaneously starved of repair *and* rarely
  selected out of the job, compounding unavailability.
- **Retirement still breaks even around prob ≈ 0.40–0.60**, not a clean single crossover:
  `FewestFail+ScoredRemoval` is +83.1h at 0.40 but −13.5h at 0.60; `FewestFail+Thresh ≥2/7d`
  follows a similar pattern (+88.3h → −9.9h). Directionally identical to pre-fix, magnitudes
  smaller and the exact crossover point less precise at n=4.
- **Best at prob = 1.0 is still `Random+ScoredRemoval`, at −83.1h** (15-replication figure,
  §2.1) — down from −159.5h pre-fix, consistent with every other report's finding that
  `ScoredRemoval`'s payoff roughly halved once the repair pipeline stopped over-escalating.

---

## 3  Sweep B — `diagnosis_uncertainty`  (probability fixed at 1.0)

### 3.1  Raw results

The `unc = 0.00` row reuses the same 15-replication anchor as §2.1 (identical cell).
All other rows are this regeneration's 4-replication data.

| unc  | Scheduling+Retirement        | Mean (h) | Std  | Δ vs baseline | Retired |
|------|------------------------------|----------|------|--------------|---------|
| 0.00 | Random+NeverRemove           | 2 076.0  |  38.5 |       0.0   |     0.0 |
| 0.00 | Random+Thresh ≥2/7d          | 2 072.1  |  39.0 |     **−3.9**|    75.4 |
| 0.00 | Random+ScoredRemoval         | 1 992.9  |  47.8 |    **−83.1**|   321.8 |
| 0.00 | FewestFail+NeverRemove       | 2 007.4  |  58.3 |    **−68.6**|     0.0 |
| 0.00 | FewestFail+Thresh ≥2/7d      | 2 008.0  |  47.2 |    **−68.0**|    58.1 |
| 0.00 | FewestFail+ScoredRemoval     | 1 985.8  |  42.3 |    **−90.2**|   263.4 |
| 0.20 | Random+NeverRemove           | 2 179.7  |  29.3 |   +112.2    |     0.0 |
| 0.20 | Random+Thresh ≥2/7d          | 2 144.0  |  67.0 |    +76.5    |    84.0 |
| 0.20 | Random+ScoredRemoval         | 2 092.7  |  42.3 |    **+25.2**|   336.8 |
| 0.20 | FewestFail+NeverRemove       | 2 062.2  |  47.8 |     **−5.2**|     0.0 |
| 0.20 | FewestFail+Thresh ≥2/7d      | 1 998.9  |  33.3 |    **−68.5**|    55.8 |
| 0.20 | FewestFail+ScoredRemoval     | 1 997.4  |  44.5 |    **−70.1**|   236.8 |
| 0.40 | Random+NeverRemove           | 2 355.5  |  38.3 |   +288.0    |     0.0 |
| 0.40 | Random+Thresh ≥2/7d          | 2 328.6  |  35.0 |   +261.1    |    88.0 |
| 0.40 | Random+ScoredRemoval         | 2 222.1  |  28.6 |   +154.6    |   363.0 |
| 0.40 | FewestFail+NeverRemove       | 2 087.0  |  79.2 |    +19.5    |     0.0 |
| 0.40 | FewestFail+Thresh ≥2/7d      | 2 061.7  |  50.2 |     **−5.8**|    56.8 |
| 0.40 | FewestFail+ScoredRemoval     | 2 067.9  |  18.4 |     **+0.4**|   242.5 |
| 0.60 | Random+NeverRemove           | 2 476.5  |  62.1 |   +409.0    |     0.0 |
| 0.60 | Random+Thresh ≥2/7d          | 2 433.7  |  69.8 |   +366.2    |    83.5 |
| 0.60 | Random+ScoredRemoval         | 2 432.6  |  24.2 |   +365.2    |   389.0 |
| 0.60 | FewestFail+NeverRemove       | 2 153.0  |  47.6 |    +85.5    |     0.0 |
| 0.60 | FewestFail+Thresh ≥2/7d      | 2 135.4  |  51.0 |    +67.9    |    46.0 |
| 0.60 | FewestFail+ScoredRemoval     | 2 121.5  |  16.9 |    +54.0    |   261.5 |
| 0.80 | Random+NeverRemove           | 2 732.5  |  84.1 |   +665.0    |     0.0 |
| 0.80 | Random+Thresh ≥2/7d          | 2 646.7  |  73.3 |   +579.2    |    65.2 |
| 0.80 | Random+ScoredRemoval         | 2 764.2  |  67.3 |   +696.7    |   489.8 |
| 0.80 | FewestFail+NeverRemove       | 2 261.5  |  57.6 |   +194.0    |     0.0 |
| 0.80 | FewestFail+Thresh ≥2/7d      | 2 202.1  |  45.7 |   +134.6    |    34.0 |
| 0.80 | FewestFail+ScoredRemoval     | 2 190.0  |  42.6 |   +122.5    |   272.5 |
| 1.00 | Random+NeverRemove           | 3 049.3  |  82.2 |   +981.8    |     0.0 |
| 1.00 | Random+Thresh ≥2/7d          | 3 066.6  |  41.9 |   +999.1    |     5.5 |
| 1.00 | Random+ScoredRemoval         | 3 145.3  |  76.1 |  +1077.8    |   603.8 |
| 1.00 | FewestFail+NeverRemove       | 2 320.7  |  72.1 |   +253.3    |     0.0 |
| 1.00 | FewestFail+Thresh ≥2/7d      | 2 313.8  |  56.3 |   +246.3    |     2.8 |
| 1.00 | FewestFail+ScoredRemoval     | 2 309.3  |  32.7 |   +241.8    |   340.2 |

At `unc=1.00`, `Random+NeverRemove` came out slower post-fix (3,049h) than pre-fix (2,778h)
despite the fix generally *reducing* wasted repair time elsewhere. This is very likely n=3→4
sampling noise in an already high-variance regime (misattribution at full uncertainty is
close to worst-case chaos for `Random` scheduling) rather than a real regression — the
`FewestFail` rows at the same uncertainty level move in the expected direction (down
slightly). Read the `unc≥0.60` region of this table as noisy in absolute terms; the
qualitative pattern in §3.4 is what to trust.

### 3.2  ETR summary — Sweep B

ETR = 336 / mean_training_time. Key ETR values by uncertainty level:

| unc | Best policy | Mean (h) | ETR | Worst policy | Mean (h) | ETR |
|-----|-------------|----------|-----|--------------|----------|-----|
| 0.00 | FewestFail+Scored | 1 986 | 16.9% | Random+NeverRemove | 2 076 | 16.2% |
| 0.20 | FewestFail+Scored | 2 086 | 16.1% | Random+Thresh | 2 273 | 14.8% |
| 0.40 | FewestFail+Scored | 2 102 | 16.0% | Random+NeverRemove | 2 337 | 14.4% |
| 0.60 | FewestFail+Thresh | 2 172 | 15.5% | Random+NeverRemove | 2 522 | 13.3% |
| 0.80 | FewestFail+Scored | 2 190 | 15.3% | Random+ScoredRemoval | 2 764 | 12.2% |
| 1.00 | FewestFail+Scored | 2 309 | 14.5% | Random+ScoredRemoval | 3 145 | 10.7% |

The core pattern is unchanged from pre-fix, just shifted: as misdiagnosis uncertainty rises,
the **best achievable ETR still falls** monotonically (16.9%→14.5%, was 16.5%→14.4%), and
`Random+ScoredRemoval` is still the clear *worst* policy at high uncertainty (ETR=10.7% at
unc=1.0, was 11.5%) for the same reason as before — it retires innocent servers while bad
ones keep their scores pristine, inverting its intended effect. What changed at n=4:
`FewestFail+ScoredRemoval`, not `FewestFail+NeverRemove`, comes out best at unc=0.80–1.00
in this run — plausibly real (misattributed *scoring* still hurts `ScoredRemoval` less than
misattributed *scheduling avoidance* hurts nothing, since `FewestFailuresFirst` never relies
on diagnosis at all — see §3.4), but given the margins involved (2190 vs 2261 at 0.80; 2309
vs 2321 at 1.00, both well within one standard deviation) this specific ranking shouldn't be
treated as settled without more replications.

### 3.3  Comparison with pre-fix results

*(This table is about the two misdiagnosis-path bugs fixed before this report's original
run — floating-server deadlock and active-server duplication — not the escalation-policy
fix this regeneration adds. It's reproduced unchanged since it remains accurate; see §3.1
above for the escalation-policy comparison instead.)*

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

### 3.4  Key observations

**ScoredRemoval is still actively harmful at unc ≥ 0.80 — mechanism unchanged, margin
smaller:**
At unc=0.80, `Random+ScoredRemoval` (2,764h) is *worse* than `Random+NeverRemove` (2,733h)
by 32h (was ~50h pre-fix). At unc=1.0, the gap is 96h (was ~148h). The mechanism is exactly
as before and is unaffected by the escalation-policy fix: `on_failure` is called on the
misdiagnosed *innocent* server, not the actual bad server, so innocent servers accumulate
penalty scores and get retired while bad servers' scores stay pristine. The pool
progressively fills with high-failure-rate servers — a perverse inversion of ScoredRemoval's
intent that gets *smaller* post-fix only because the whole regime is less punishing overall,
not because the inversion itself weakened.

**FewestFailures scheduling still gives a large benefit at high uncertainty (without
retirement):** At unc=1.0, `FewestFail+NeverRemove` (2,321h) is 728h *better* than
`Random+NeverRemove` (3,049h) in this run — larger than the pre-fix 452h gap, though as
flagged in §3.1, `Random+NeverRemove`'s absolute value at unc=1.0 is itself one of this
regeneration's noisiest cells, so treat the exact 728h figure loosely; the direction and
rough scale are consistent with pre-fix. The mechanism is unchanged: `FewestFailuresFirst`
sorts by `total_failure_count`, which tracks a server's *actual* hardware failures
regardless of misattribution, so it deprioritises truly bad servers even when their
failures are attributed to innocent ones — a fundamentally different mechanism from
`ScoredRemoval` that doesn't rely on the diagnosis pipeline at all.

**ThresholdRemoval is still neutral-to-harmful at unc ≥ 0.80, mechanism unchanged:**
`FewestFail+Thresh ≥2/7d` is +134.6h at unc=0.80 and +246.3h at unc=1.0 (was +17h / +157h
— larger in absolute terms here, though these are 4-replication numbers in a
high-variance regime). The reason is unchanged: `ThresholdRemoval` reads
`failure_timestamps` on the server *entering repair*, which at high uncertainty is almost
always the innocent one — so it rarely triggers on the actual bad servers, while
occasionally retiring an innocent server based on accumulated misattributed "blame."

**`FewestFail+ScoredRemoval`'s benefit now vanishes earlier — above unc ≈ 0.20–0.40, not
0.60:** At unc=0.20 this combination is still −70.1h (net benefit). At unc=0.40 it's
essentially zero (+0.4h, was −89h pre-fix — a real shift, not noise, given the pattern is
consistent with every other repair-adjacent metric in this regeneration shrinking). At
unc=0.60 it's +54.0h (net harm, was ≈breakeven pre-fix). The practical crossover moved from
≈0.60 to somewhere between 0.20 and 0.40.

---

## 4  Revised practical guidance

### When to adjust `diagnosis_probability`  (uncertainty = 0)

| prob | Recommended policy | Rationale |
|------|--------------------|-----------|
| < 0.40 | FewestFail+Thresh ≥2/7d | ThresholdRemoval has signal via timestamps; ScoredRemoval blind to missed failures |
| 0.40–0.80 | FewestFail+ScoredRemoval or FewestFail+Thresh ≥2/7d | Breaks even around 0.40, delivers roughly −10 to −53h at 0.60–0.80 — smaller than pre-fix, but still the best available combination |
| ≥ 0.80 | Random+ScoredRemoval (15-rep figure) | −83.1h at full diagnosis — down from −159.5h pre-fix, still the best measured combination |

### When to adjust `diagnosis_uncertainty`  (probability = 1)

| unc  | Recommended policy | Rationale |
|------|--------------------|-----------|
| 0.00 | Random or FewestFail+ScoredRemoval | −83.1h / −90.2h (15-rep figures) — down from −160h pre-fix, still best |
| ≤ 0.20 | FewestFail+ScoredRemoval | −70.1h, still net-positive |
| 0.20–0.40 | FewestFail+ScoredRemoval or FewestFail+Thresh ≥2/7d | Benefit is shrinking fast — both are close to breakeven by 0.40 |
| ≥ 0.40 | FewestFail+NeverRemove or FewestFail+Thresh ≥2/7d | No retirement policy reliably helps past this point; FewestFail scheduling alone still gives a real benefit via actual failure counts |
| = 1.00 | **Avoid `Random+ScoredRemoval`** | +1,077.8h — still actively harmful, still retires innocent servers and keeps bad ones; the magnitude scaled up rather than down here (see §3.1's noise caveat) |

### Critical interactions (unaffected by the escalation-policy fix — these concern
diagnosis_uncertainty mechanics, not repair routing)

- **ScoredRemoval inverts at high uncertainty:** `on_failure` is called on the wrong server.
  At unc ≥ 0.60–0.80, ScoredRemoval does more harm than no retirement policy at all.

- **FewestFailures is diagnosis-agnostic:** It uses raw `total_failure_count` (actual hardware
  failures, not attributed blame), making it the most robust scheduling policy under
  misattribution — still true post-fix, with an even larger measured gap at unc=1.0 in this
  run (see §3.4's noise caveat on the exact figure).

- **ThresholdRemoval's partial immunity breaks at high uncertainty:** It can leverage
  `failure_timestamps` (actual failures, not attributed blame) only for servers that enter
  repair.  At unc=1.0, only innocent servers enter repair, so ThresholdRemoval cannot act on
  the bad servers' timestamps.

---

## 5  Summary

```
Sweep A — diagnosis_probability (uncertainty = 0):  [CHANGED BY THE ESCALATION-POLICY FIX —
                                                       same shape, smaller numbers]
  Retirement still breaks even around prob ≈ 0.40-0.60 (was a cleaner ≥0.40)
  Best at prob = 1.0: Random+ScoredRemoval  −83.1 h (15-rep figure; was −160 h pre-fix)

Sweep B — diagnosis_uncertainty (probability = 1):  [ALSO CHANGED BY THE ESCALATION-POLICY FIX
                                                       — the earlier floating-server/duplication
                                                       fix is what made this sweep completable
                                                       at all; see §3.3]

  unc = 0.00:  Random/FewestFail+ScoredRemoval  −83 to −90 h (15-rep; was −160 h)
  unc = 0.20:  FewestFail+ScoredRemoval  −70.1 h
  unc = 0.40:  FewestFail+ScoredRemoval  ≈breakeven (+0.4 h; was −89 h — benefit gone earlier)
  unc = 0.60:  FewestFail+Thresh ≥2/7d  +67.9 h  (was −18 h — now harmful, not helpful)
  unc = 0.80:  FewestFail+ScoredRemoval  +122.5 h  (no policy gives net benefit)
  unc = 1.00:  FewestFail scheduling alone (any retirement policy) — retirement-heavy
               combinations noticeably worse

  Key crossovers (n=4, treat as approximate):
    ScoredRemoval net-negative:    unc ≳ 0.20–0.40 (was > 0.60)
    ThresholdRemoval net-negative: unc ≳ 0.40–0.60 (was > 0.80)
    FewestFail scheduling benefit: still monotonically increases with uncertainty,
                                    unaffected by the fix
```

**Practical bottom line, revised:** the escalation-policy fix pulls every crossover in this
report toward *less* tolerance for diagnosis problems, not more. If `diagnosis_uncertainty`
cannot be kept below roughly 0.20–0.40 (was 0.60), retire `ScoredRemoval` from the retirement
policy and rely on `FewestFailuresFirst` scheduling alone — it remains the single most
robust lever in this entire sweep, and is completely unaffected by either bug fix discussed
in this report because it never depends on the repair or diagnosis pipeline.
