# Policy Synthesis and Deployment Recommendations

**Scope:** Synthesizes findings across six AIReSim reports — the paper-default
configuration (`SIMULATION_REPORT.md`) and a stress-tested "payoff regime"
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

**2. `FewestFailuresFirst` scheduling is the strongest general-purpose
lever.** It costs nothing — no capacity loss, no depletion risk, no tuning —
and is diagnosis-agnostic: it orders servers by raw failure count, which
stays accurate even when failures are misattributed to the wrong server.
Across a 5×5 severity grid (failure multiplier × repair fail probability) it
wins outright in the most cells (12/25) and beats `ScoredRemoval`
head-to-head in 14/25.

**3. Active retirement (`ScoredRemoval`) only pays off in genuinely severe
regimes.** It needs several conditions at once — failure-rate multiplier
≳15×, repair fail probability ≳60%, or an already-substantial bad-server
fraction (≳5–8%) — before it clearly beats doing nothing. Outside those
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

**6. Bad-server fraction is the most reliable trigger for retirement.**
Unlike the repair-quality axes, its effect doesn't depend on how well the
repair pipeline behaves — any tested fraction of persistently-bad servers
(1%–20%) produces a real, scaling benefit from retiring them, making this
the one condition under which retirement can be recommended with confidence
on its own.

**7. Diagnosis quality is the most consequential and dangerous variable in
the system.** Missed diagnosis (`diagnosis_probability` < 1) simply reduces
retirement's benefit, with breakeven around 0.4–0.6. Misattribution
(`diagnosis_uncertainty` > 0) is worse: past roughly 0.2–0.4,
`ScoredRemoval` actively sabotages the cluster — it penalizes scapegoated
innocent servers while the real offenders keep clean scores and are
preferentially retained. `ThresholdRemoval` degrades the same way, for the
same reason. `FewestFailuresFirst` is immune to this failure mode because it
counts actual hardware failures rather than attributed blame.

**8. Uptime-credit scoring provides no benefit at production scale.**
Aggregate failure arrival across thousands of servers is too fast
(~7-minute average run chunks) for any practical `time_period` to ever award
a credit, so `ScoredRemoval` degenerates to a pure lifetime-failure-count
threshold regardless of its credit parameters.

---

## Recommendations

| Situation | Deploy | Why |
|---|---|---|
| Default or unknown regime, diagnosis reliable | `FewestFailuresFirst` + `NeverRemove` | Zero-cost, zero-risk baseline that captures most of the available benefit |
| Failure multiplier ≳15× or repair-fail probability ≳60%, diagnosis reliable | `FewestFailuresFirst` + `ScoredRemoval` (2-failure threshold) | Best measured combination once severity justifies retirement's capacity cost |
| Bad-server fraction known to be ≳5% | `ScoredRemoval`, regardless of other parameters | The one condition where retirement reliably pays off on its own |
| `diagnosis_uncertainty` ≳0.2–0.4, or `diagnosis_probability` < 0.4 | `FewestFailuresFirst` + `NeverRemove`; avoid `ScoredRemoval` | Retirement relies on accurate blame attribution; under misdiagnosis it punishes the wrong servers |
| Diagnosis quality unverified | `FewestFailuresFirst` alone | The only lever in this study that is provably safe regardless of diagnosis quality |
| Working-pool headroom is tight (≲100 servers above minimum) | `NeverRemove` or `ThresholdRemoval` only — never `ScoredRemoval` | Aggressive retirement risks depleting the pool below the job's minimum |
| Considering `ThresholdRemoval` | Use `≥2/7d`, not `≥3/7d` | The conservative config retires too few servers to matter in any tested condition |

**Bottom line:** deploy `FewestFailuresFirst` scheduling everywhere — it is
strictly beneficial and free. Layer `ScoredRemoval` on top only when at
least one of (high failure severity, poor repair quality, a known
substantial bad-server population) holds **and** diagnosis is trustworthy;
otherwise the added retirement risk outweighs its benefit.

---

*Synthesized from `SIMULATION_REPORT.md`, `RETIREMENT_POLICY_REPORT.md`,
`SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`,
`THRESHOLD_SENSITIVITY_REPORT.md`, and `DIAGNOSIS_SWEEP_REPORT.md`. 2026-09-20.*
