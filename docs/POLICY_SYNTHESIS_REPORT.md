# Policy Synthesis and Deployment Recommendations

**Scope:** Synthesizes findings across seven AIReSim reports — the paper-default
configuration (`SIMULATION_REPORT.md`, `DIAGNOSIS_REALISTIC_REPORT.md`) and a stress-tested "payoff regime"
(elevated failure rate, aggressive bad-server multiplier, tight repair
budgets) swept across failure severity, repair quality, bad-server fraction,
scheduling policy, and diagnosis quality (`RETIREMENT_POLICY_REPORT.md`,
`SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`,
`THRESHOLD_SENSITIVITY_REPORT.md`, `DIAGNOSIS_SWEEP_REPORT.md`). See those
reports for full data and methodology.

---

## Findings

**1. At default parameters, the pipeline is already efficient.** Effective
Training Ratio (ETR) is 62.5%, and the overhead is dominated almost entirely
by the fixed per-failure checkpoint-reload cost (`recovery_time`), not by
which repair or retirement policy is in use. Warm standbys absorb 99.8% of
failures in place; the spare pool and retirement policies are essentially
idle at this scale of failure.

**2. `FewestFailuresFirst` scheduling is free, but AIReSim only lets it act
at full host selection.** It costs nothing: no capacity loss, no depletion
risk, no tuning. In the current design, though, warm-standby swaps take the
oldest standby without consulting the scheduling policy, and repaired servers
rejoin the job's standbys regardless of failure history. The policy only
chooses servers when the job exhausts its standbys and triggers a full host
selection. In the stress-tested regime, where that happens often enough to
matter, it wins outright in the most cells of a 5×5 severity grid (12/25) and
beats `ScoredRemoval` head-to-head in 14/25. At the paper defaults, full host
selection ran about 16 times per job against ~11,000 failures, so 99.86% of
replacements bypassed the policy. Accordingly, it showed **no measurable
benefit** over `Random` (CIs exclude any benefit larger than about 21 h,
0.2%). This is a property of the simulator's design, so these results cannot
say whether health-aware replacement would help in a real cluster at those
parameters.

**3. Active retirement (`ScoredRemoval`) only pays off in genuinely severe
regimes.** It needs several conditions at once — failure-rate multiplier
≳15×, repair fail probability ≳60%, or possibly a substantial bad-server fraction (see finding 6) — before it
clearly beats doing nothing. Outside those
conditions it ranges from no better than `NeverRemove` to a net cost: a
retired server that repairs would likely have fixed anyway just shrinks the
working pool for no benefit.

**4. `ScoredRemoval` layered on `FewestFailuresFirst` is the best measured
combination** once retirement is warranted at all. The two levers are mildly
complementary rather than competing: smart scheduling still avoids bad
servers while retirement cleans up the ones that persist.

**5. The conservative `ThresholdRemoval` config (≥3 failures in a 7-day
window) essentially never earns its complexity.** It retires too few servers
to matter under almost every tested condition. A more aggressive
`ThresholdRemoval(≥2/7d)` performs better but is consistently dominated by
`ScoredRemoval` wherever retirement helps at all.

**6. Bad-server fraction is a promising trigger for retirement, but the
evidence is thin.** The only bad-fraction sweep
(`THRESHOLD_SENSITIVITY_REPORT.md`) tested `ThresholdRemoval(≥2/7d)`, not
`ScoredRemoval`, at 4 replications per cell. Its benefit is clear from about
12% bad servers (−47.7h at 12%, −65.6h at 20%). At 1–8% the measured gains
(16–26h) are within one standard deviation. `ScoredRemoval` has not been swept
on this axis, so no threshold for it is supported yet.

**7. In the stress-tested regime, diagnosis quality is the most
consequential and dangerous variable in the system.** (At the paper defaults
its effect is small; see the end of this finding.) Missed diagnosis (`diagnosis_probability` < 1) simply reduces
retirement's benefit, with breakeven around 0.4–0.6. Misattribution
(`diagnosis_uncertainty` > 0) is worse: past roughly 0.2–0.4,
`ScoredRemoval` actively sabotages the cluster — it penalizes scapegoated
innocent servers while the real offenders keep clean scores and are
preferentially retained. `ThresholdRemoval` degrades the same way, for the
same reason. `FewestFailuresFirst` is immune to this failure mode because it
counts actual hardware failures rather than attributed blame — ground truth an
operator may not have. Its operator-visible variant
(`FewestAttributedFailuresFirst`) has only been tested at the paper defaults,
where neither variant could act (finding 2), so it is not known whether FFF's
robustness survives without ground truth. At paper-default parameters
misattribution's damage is small: uncertainty 0.2 raises training time about
0.35% (95% CI +0.15% to +0.54%), rising to about 1.4–2.0% at 0.5. That cost is
exactly the extra failures times `recovery_time`: misattributed failures leave
faulty servers unrepaired, and they fail again.

**8. Uptime-credit scoring provides no benefit at production scale.**
Aggregate failure arrival across thousands of servers is too fast
(~7-minute average run chunks) for any practical `time_period` to ever award
a credit, so `ScoredRemoval` degenerates to a pure lifetime-failure-count
threshold regardless of its credit parameters.

---

## Recommendations

| Situation | Deploy | Why |
|---|---|---|
| Default or unknown regime, diagnosis reliable | `FewestFailuresFirst` + `NeverRemove` | Free and showed no measurable harm. Its benefit at the paper defaults is untested, because AIReSim applies the policy only at full host selection (finding 2) |
| Failure multiplier ≳15× or repair-fail probability ≳60%, diagnosis reliable | `FewestFailuresFirst` + `ScoredRemoval` (2-failure threshold) | Best measured combination once severity justifies retirement's capacity cost |
| Bad-server fraction known to be ≳12% | `ThresholdRemoval(≥2/7d)` | Clear benefit only from ~12% bad servers, at 4 replications per cell. `ScoredRemoval` is untested on this axis (finding 6) |
| `diagnosis_uncertainty` ≳0.2–0.4, or `diagnosis_probability` < 0.4 | `FewestFailuresFirst` + `NeverRemove`; avoid `ScoredRemoval` | Retirement relies on accurate blame attribution; under misdiagnosis it punishes the wrong servers |
| Diagnosis quality unverified | `FewestFailuresFirst` alone, if true failure counts are observable | The only lever here that does not depend on diagnosis; the attributed-count variant is untested anywhere the policy can act |
| Working-pool headroom is tight (≲100 servers above minimum) | `NeverRemove` or `ThresholdRemoval` only — never `ScoredRemoval` | Aggressive retirement risks depleting the pool below the job's minimum |
| Considering `ThresholdRemoval` | Use `≥2/7d`, not `≥3/7d` | The conservative config retires too few servers to matter in any tested condition |

**Bottom line:** deploy `FewestFailuresFirst` scheduling by default. It is
free and helps in the stress-tested regime. Its value at realistic parameters
is untested, because AIReSim only applies the policy at full host selection. Layer `ScoredRemoval` on top only when at
least one of (high failure severity, poor repair quality, a known
substantial bad-server population) holds **and** diagnosis is trustworthy;
otherwise the added retirement risk outweighs its benefit.

---

*Synthesized from `SIMULATION_REPORT.md`, `DIAGNOSIS_REALISTIC_REPORT.md`,
`RETIREMENT_POLICY_REPORT.md`, `SCHEDULING_COMPARISON_REPORT.md`,
`2D-HEAT_MAP_REPORT.md`, `THRESHOLD_SENSITIVITY_REPORT.md`, and
`DIAGNOSIS_SWEEP_REPORT.md`. 2026-09-21.*
