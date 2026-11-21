# Findings at a Glance

*For readers arriving from the DSN'26 paper ("AIReSim: A Discrete Event Simulator for
Large-scale AI Cluster Reliability Modeling," arXiv:2603.07041). Every number below is
generated from a committed CSV by the report or script named next to it — see
`docs/POLICY_SYNTHESIS_REPORT.md` for the full synthesis this summarizes.*

---

## 1. The accounting identity

In every AIReSim run in which the job never stalls — every run behind the reports listed
here — wall-clock training time decomposes exactly:

```
training_time = job_length + total_failures × recovery_time
               + host_selection_count × host_selection_time
               + preemption_count × preemption_wait_time
```

No work is charged for time since the last checkpoint beyond one `recovery_time` per
failure — the model assumes checkpoints are frequent enough that a failure's cost doesn't
depend on when in the job it occurs. Verified across 1,200 runs of the diagnosis sweep:
largest residual **1.2e-10 h** (`DIAGNOSIS_REALISTIC_REPORT.md` §6,
`examples/diagnosis_realistic_figures/results.csv`). One consequence follows immediately:
**every parameter, misdiagnosis mode, or policy this repo studies acts on training time
only by changing the failure count** (plus the small host-selection and preemption
terms). There is no other channel.

The exception is capacity: when the working and spare pools can't field `job_size`
servers, the job stalls until a repair returns one, and that wait is not in the identity.
In `examples/stress_scenario.py` (16 servers of headroom, 10 spares, 5× failure rate)
stall waiting is up to 41% of training time, and spare-pool size becomes one of the two
largest levers. Waiting for servers can dominate a capacity-constrained cluster; the
Table I configuration simply has enough capacity that it never happens.

## 2. At Table I defaults

`config.yaml` implements the paper's Table I parameters (including
`diagnosis_probability = 0.8`, so 20% of failures go undiagnosed and the server rejoins the
pool unrepaired), and repairs follow the DSN'26 escalation model — auto repair escalates to manual with probability `prob_auto_to_manual`
(0.80), independent of the silent auto-repair failure `auto_repair_fail_prob` (0.40).

With `bad_server_regeneration` off (the default), a bad server can only be cured, never
created, so the systematic-failure count is capped by the initial bad population
(~623 of 4,160 servers, 15%) and **saturates early**: about 40% of the systematic failures a
256-day run will ever see happen in the first 15 compute-days
(`SIMULATION_REPORT.md` §5a, `examples/job_length_figures/replications.csv`). That caps
what *any* node-management policy (retirement, health-aware scheduling) could possibly be
worth here: eliminating every systematic failure saves at most
`862.6 × 20 min ≈ 288 h ≈ 2.9%` of the 9,926 h mean training time.

Measured effects at these defaults stay well inside that ceiling
(`DIAGNOSIS_REALISTIC_REPORT.md`, `examples/diagnosis_realistic_figures/results.csv`,
1,200 runs):

- **Scheduling/retirement policy effect: not significant.** `FewestFailuresFirst`
  vs. `Random` and every `FewestAttributedFailuresFirst` contrast have 95% CIs including
  zero; a benefit larger than 26 h (0.3%) is excluded.
- **Diagnosis-quality effect: significant but small**, within the pre-registered
  uncertainty range (≤0.2): about 0.4%–0.7% depending on the failure-rate multiplier
  (3×, 5×, 10×) and policy. Only at `diagnosis_uncertainty = 0.5` — outside that range —
  does the effect reach 1.3%–2.3%.

## 3. The persistence regime

Every other report in this repo (`RETIREMENT_POLICY_REPORT.md`,
`SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`,
`THRESHOLD_SENSITIVITY_REPORT.md`, `DIAGNOSIS_SWEEP_REPORT.md`) uses a 14-day "payoff
regime": elevated failure severity (multiplier up to 30×, swept from 5×), poor repair
quality (manual repair fail probability up to 0.90, swept from 0.20), and a shorter job
than Table I. The job is short enough, and repair poor enough (28% per-attempt success at
the regime's headline setting, vs. 76% at Table I defaults), that bad servers **persist**
through it — 31.8% of the initial bad population is still bad at job end, vs. essentially
fully cured by the end of a Table I run. When bad servers persist:

- `FewestFailuresFirst` and `ScoredRemoval` are worth **10–20%** of training time (12.2%
  and 10.4% at the regime's headline setting, up to about 20% at the most severe settings;
  `SCHEDULING_COMPARISON_REPORT.md`, `RETIREMENT_POLICY_REPORT.md`).
- **Lifetime-count retirement (`ScoredRemoval`) beats windowed-threshold retirement
  (`ThresholdRemoval`) wherever the difference is measurable** — by 41–316 h depending on
  severity and repair quality (`RETIREMENT_POLICY_REPORT.md`).
- **Which lever wins depends on diagnosis quality; running both wins everywhere.**
  Retirement alone beats realistic-information scheduling (`FewestAttributedFailuresFirst`)
  only above a diagnosis probability of 0.59–0.91, lower the more severe the bad servers
  are. Scheduling keeps 84–107% of its value as diagnosis falls from 1.0 to 0.5 (it only
  needs a ranking); retirement keeps 46–74% (it needs two observed failures). Scheduling
  plus `ScoredRemoval` is the fastest realistic policy at every diagnosis level tested
  (`DIAGNOSIS_SWEEP_REPORT.md` §6).
- **Misattribution interacts with retirement**: `ScoredRemoval` penalizes whichever
  server diagnosis blames, so at `diagnosis_uncertainty = 1.0` it retires innocent
  servers while the real offenders keep clean scores and turns net-harmful (+65 to +96 h;
  `DIAGNOSIS_SWEEP_REPORT.md`).

**Production AI training clusters are not believed to operate in this regime.** It was
constructed to find where node-management policy *can* matter; whether real clusters see
severity, repair quality, and job lengths in this range is outside this repo's scope.

## 4. Modeling assumptions

- **Escalation is independent of silent auto-repair failure**, per DSN'26: auto repair
  escalates to manual with probability `prob_auto_to_manual` regardless of whether the
  (unobservable) auto-repair outcome would have succeeded (`airesim/policies.py`,
  `DefaultRepairEscalation`).
- **Checkpoints are assumed frequent**: a failure costs exactly one `recovery_time`
  (finding 1) with no separate lost-work term for compute since the last checkpoint.
- **`bad_server_regeneration` is off by default**: a bad server can be cured but nothing
  turns a good server bad, so the bad population only shrinks over a run (§2).
- **The scheduling policy acts only at full host selection.**
  `Scheduler.do_host_selection` re-picks the entire job from the available pool and is
  the only point a `HostSelectionPolicy` is consulted; `Scheduler.swap_in_standby`, the
  warm-standby replacement between full selections, is FIFO and policy-blind.
- **`FewestFailuresFirst` and `ThresholdRemoval` see ground-truth failure history** —
  `total_failure_count` and `failure_timestamps` are recorded on the server that truly
  failed, before diagnosis runs, including failures diagnosis misses. An operator without
  that ground truth would use `FewestAttributedFailuresFirst`, which reads only diagnosed,
  attributed failures; it has been tested at Table I defaults (§2) and, against missed
  diagnoses (not misattribution), in the persistence regime (§3).
- **Removal policies decide only when a server finishes repair**, which happens only after
  a diagnosed failure; `ScoredRemoval`'s score also moves only on diagnosed failures.

## 5. Reproducibility

| Report | Config | Job length |
|---|---|---|
| `SIMULATION_REPORT.md` | `config.yaml` (Table I) | 256 days |
| `DIAGNOSIS_REALISTIC_REPORT.md` | `config.yaml`, sweeping `diagnosis_probability`/`diagnosis_uncertainty`/multiplier | 256 days |
| `RETIREMENT_POLICY_REPORT.md`, `SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`, `THRESHOLD_SENSITIVITY_REPORT.md`, `DIAGNOSIS_SWEEP_REPORT.md` | Payoff regime (`working_pool_size=4,600`, `systematic_failure_rate_multiplier` 5–30×, `manual_repair_fail_prob` 0.20–0.90, one script's `BASE` per report — see each script) | 14 days |
| `POLICY_SYNTHESIS_REPORT.md` | Synthesizes all of the above | — |

**This repo's defaults (`config.yaml`) implement the paper's Table I.** The DSN'26 paper's
Fig. 2 figures were produced with a different configuration and are **not** reproduced by
`config.yaml` — do not expect `python -m airesim.run --params config.yaml --adaptive` to
regenerate them.

## 6. Lessons

**A one-line change to escalation semantics changed `FewestFailuresFirst`'s
persistence-regime benefit by roughly 4×.** Commit `8896140` made the default escalation
policy condition on the (unobservable, per the paper) auto-repair outcome, dropping the
effective escalation rate from `prob_auto_to_manual` (80%) to
`auto_repair_fail_prob × prob_auto_to_manual` (32%). Under that semantics,
`FewestFailuresFirst + NeverRemove` saved 68.6 h (3.3%) in the payoff regime (commit
`7102330`); under the paper's semantics it saved 272.3 h (11.4%; both at diagnosis 1.0) — a ~4.0× change in
absolute hours. The regression and its revert are documented in `CHANGELOG.md`
("Revert: default escalation policy restored to the DSN'26 paper's model," 2026-09-21);
anything generated between `8896140` and that revert used the wrong semantics and has
since been regenerated. The lesson for anyone extending this repo: a policy's inferred
intent from its code is not a substitute for checking the paper, and a silent semantics
change can move a headline result by multiples without any test catching it if nothing
asserts on the actual numbers.

---

*Generated 2026-09-22; updated 2026-11-20 after the paper-conformance rerun (CHANGELOG).*
