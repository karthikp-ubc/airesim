# Findings at a Glance

*For readers arriving from the DSN'26 paper ("AIReSim: A Discrete Event Simulator for
Large-scale AI Cluster Reliability Modeling," arXiv:2603.07041). Every number below is
generated from a committed CSV by the report or script named next to it — see
`docs/POLICY_SYNTHESIS_REPORT.md` for the full synthesis this summarizes.*

---

## 1. The accounting identity

In every AIReSim run, wall-clock training time decomposes exactly:

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

## 2. At Table I defaults

`config.yaml` implements the paper's Table I parameters, and repairs follow the DSN'26
escalation model — auto repair escalates to manual with probability `prob_auto_to_manual`
(0.80), independent of the silent auto-repair failure `auto_repair_fail_prob` (0.40).

With `bad_server_regeneration` off (the default), a bad server can only be cured, never
created, so the systematic-failure count is capped by the initial bad population
(~622 of 4,160 servers, 15%) and **saturates early**: 49.4% of the systematic failures a
256-day run will ever see happen in the first 15 compute-days
(`SIMULATION_REPORT.md` §5a, `examples/job_length_figures/replications.csv`). That caps
what *any* node-management policy (retirement, health-aware scheduling) could possibly be
worth here: eliminating every systematic failure saves at most
`684.7 × 20 min ≈ 228 h ≈ 2.3%` of the 9,873 h mean training time.

Measured effects at these defaults stay well inside that ceiling
(`DIAGNOSIS_REALISTIC_REPORT.md`, `examples/diagnosis_realistic_figures/results.csv`,
1,200 runs):

- **Scheduling/retirement policy effect: not significant.** `FewestFailuresFirst`
  vs. `Random` and every `FewestAttributedFailuresFirst` contrast have 95% CIs including
  zero; a benefit larger than 18 h (0.2%) is excluded.
- **Diagnosis-quality effect: significant but small**, within the pre-registered
  uncertainty range (≤0.2): 0.37%–0.74% depending on the failure-rate multiplier (3×,
  5×, 10×). Only at `diagnosis_uncertainty = 0.5` — outside that range — does the effect
  reach ~2.3%.

## 3. The persistence regime

Every other report in this repo (`RETIREMENT_POLICY_REPORT.md`,
`SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`,
`THRESHOLD_SENSITIVITY_REPORT.md`, `DIAGNOSIS_SWEEP_REPORT.md`) uses a 14-day "payoff
regime": elevated failure severity (multiplier up to 30×, swept from 5×), poor repair
quality (manual repair fail probability up to 0.90, swept from 0.20), and a shorter job
than Table I. The job is short enough, and repair poor enough (28% per-attempt success at
the regime's headline setting, vs. 76% at Table I defaults), that bad servers **persist**
through it — 26.2% of the initial bad population is still bad at job end, vs. fully cured
by the end of a Table I run. When bad servers persist:

- `FewestFailuresFirst` and `ScoredRemoval` are worth **10–20%** of training time (11.4%
  and 13.2% at the regime's headline setting, up to 19.3% at 90% repair-fail;
  `SCHEDULING_COMPARISON_REPORT.md`, `RETIREMENT_POLICY_REPORT.md`).
- **Lifetime-count retirement (`ScoredRemoval`) beats windowed-threshold retirement
  (`ThresholdRemoval`) everywhere tested** — by 30–377 h depending on severity and repair
  quality (`RETIREMENT_POLICY_REPORT.md`).
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
  attributed failures; it has been tested at Table I defaults (§2) but not in the
  persistence regime (§3).

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
`7102330`); under the paper's semantics it saves 272.3 h (11.4%) — a ~4.0× change in
absolute hours. The regression and its revert are documented in `CHANGELOG.md`
("Revert: default escalation policy restored to the DSN'26 paper's model," 2026-09-21);
anything generated between `8896140` and that revert used the wrong semantics and has
since been regenerated. The lesson for anyone extending this repo: a policy's inferred
intent from its code is not a substitute for checking the paper, and a silent semantics
change can move a headline result by multiples without any test catching it if nothing
asserts on the actual numbers.

---

*Generated 2026-09-22 from the committed reports and CSVs listed above.*
