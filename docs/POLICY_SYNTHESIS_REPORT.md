# Policy Synthesis and Deployment Recommendations

**Scope:** Synthesizes seven AIReSim reports: the paper-default configuration
(`SIMULATION_REPORT.md`, `DIAGNOSIS_REALISTIC_REPORT.md`) and a stress-tested "payoff
regime" (elevated failure rate, bad-server multiplier up to 30×, poor repair quality, 488
servers of working-pool headroom) swept over failure severity, repair quality, bad-server
fraction, scheduling and diagnosis quality (`RETIREMENT_POLICY_REPORT.md`,
`SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`,
`THRESHOLD_SENSITIVITY_REPORT.md`, `DIAGNOSIS_SWEEP_REPORT.md`). Repairs follow the DSN'26
model: escalation is independent of silent auto-repair failure. Retirement and scheduling
were compared only in the payoff regime; at the paper defaults only diagnosis was studied.

---

## Findings

**1. At default parameters the pipeline is already efficient.** Effective Training Ratio
(ETR) is 62.2%. Fixed per-failure checkpoint reload (`recovery_time`) is 37.7% of wall-clock
time, warm standbys absorb 99.6% of failures in place, and the spare pool is rarely used
(about 12 preemptions per run).

**2. `ScoredRemoval` is the strongest single lever in the payoff regime and beats
`ThresholdRemoval` everywhere tested.** `SC_fast` (retire after 2 failures) saves 317 h
(13.2%) at 20× / 75% repair-fail, leads `ThresholdRemoval` by 30 h at 5× up to 287 h at 30×,
and by 42–377 h across repair quality. Its best result is −503 h (19%). The gain grows with
severity: at mild settings (5×, or 72% fix rate) it is only 36–44 h (about 2%) for 240–255
retirements.

**3. `FewestFailuresFirst` scheduling is free and nearly as good, but AIReSim only lets it
act at full host selection.** Warm-standby swaps take the oldest standby without consulting
the policy, and repaired servers rejoin the standbys regardless of failure history. In the
payoff regime it saves 272 h (11.4%) alone, is faster than the baseline in all 25 cells of
a 5×5 severity grid, and is statistically tied with `SC_fast` in 18 of them; `SC_fast` is
clearly ahead only at ≥20× with ≥75% repair-fail (by 42–135 h). At the paper defaults, full
host selection ran about 38 times per job against ~11,500 failures, so 99.7% of replacements
bypassed the policy and it showed **no measurable benefit** (CIs exclude any benefit above
about 18 h, 0.2%). These runs cannot say whether health-aware replacement would help a real
cluster.

**4. The two levers overlap.** `FewestFailures + ScoredRemoval` (−329 h) and
`Random + ScoredRemoval` (−317 h) are statistically tied. Together they achieve 56% of the
sum of their separate effects, though smart scheduling cuts retirements from 390 to 336.

**5. `ThresholdRemoval` rarely pays.** `≥3/7d` retires 4–10 servers and has no reliable
effect; `≥1/7d` retires every server on its first failure and depletes every run. `≥2/7d`
is faster in 35 of 44 sensitivity cells (12–175 h; 89 h at baseline) but at the headline setting captures
only about a quarter of `ScoredRemoval`'s benefit.

**6. Bad-server fraction is a promising retirement trigger, but the evidence is thin.**
Only `ThresholdRemoval(≥2/7d)` was swept (8 replications): its saving is significant from 3%
bad servers (55 h) and reaches 175 h at 20%. `ScoredRemoval` has not been swept on this axis.

**7. In the payoff regime, diagnosis quality matters, and `ScoredRemoval` fails only at the
extreme.** Smart scheduling plus retirement is net-beneficial from diagnosis probability 0.2;
`Random + ScoredRemoval` breaks even at about 0.6. Under misattribution `ScoredRemoval` still
helps through uncertainty 0.8, then turns harmful at 1.0 (+65 to +96 h), retiring innocent
servers while real offenders keep clean scores; `ThresholdRemoval` degrades to no effect.
Random scheduling degrades 33% by uncertainty 1.0, `FewestFailuresFirst` 9%, but it reads
ground-truth failure counts an operator may not have, and its attributed-count variant
(`FewestAttributedFailuresFirst`) has only been tested where the policy could not act. At
the paper defaults the damage is small: uncertainty 0.2 raises training time 0.37% (95% CI
+0.15% to +0.58%), and 2.1–2.4% at 0.5. That cost is the extra failures times
`recovery_time`, plus small host-selection and preemption terms.

**8. Uptime-credit scoring provides no benefit at production scale.** Aggregate failure
arrival is too fast (~7-minute run chunks) for any practical `time_period` to award a
credit, so `ScoredRemoval` reduces to a lifetime failure count.

---

## Recommendations

| Situation | Deploy | Why |
|---|---|---|
| Default or unknown regime | `FewestFailuresFirst` + `NeverRemove` | Free; its benefit at paper-default parameters is unmeasured because the policy rarely acts (finding 3) |
| Multiplier ≳20× and repair-fail ≳75% | `ScoredRemoval` (2-failure), with or without `FewestFailuresFirst` | Clearly ahead of scheduling alone (42–135 h); needs the ~390 retirements and 488-server headroom tested here |
| Multiplier 10–15× or repair-fail 40–60% | `FewestFailuresFirst` + `NeverRemove`, or `ScoredRemoval` if capacity allows | Statistically tied in most cells; `ScoredRemoval` −72 to −251 h against the baseline |
| Multiplier ≲5× and repair-fail ≲20% | `NeverRemove` | Retirement gains about 2% for 240+ retirements |
| Bad-server fraction ≳12% | `ThresholdRemoval(≥2/7d)` | Only policy tested on this axis: −116 to −175 h; `ScoredRemoval` untested |
| Diagnosis uncertainty may reach 1.0 | `FewestFailuresFirst` if true failure counts are observable; no `ScoredRemoval` | `ScoredRemoval` harmful at 1.0; from 0.6 up `ThresholdRemoval` matches or beats it |
| Diagnosis probability below 0.4 | `FewestFailuresFirst` + `ThresholdRemoval(≥2/7d)` | It reads every failure timestamp; `ScoredRemoval` is blind to missed failures |
| Tight working-pool headroom | `NeverRemove` or `ThresholdRemoval` | `ScoredRemoval` retires ~390 servers, more than the 200-server spare pool; untested with tight headroom |
| Choosing a threshold | `≥2/7d`, never `≥3/7d` or `≥1/7d` | `≥3/7d` does nothing; `≥1/7d` depletes the cluster |

**Bottom line:** in the payoff regime, `ScoredRemoval` is the best retirement policy and
`FewestFailuresFirst` a free scheduling default of similar strength. Use retirement when
severity is high (multiplier ≳20× or repair-fail ≳75%) and diagnosis is trustworthy; at the
paper defaults, neither policy has yet been shown to matter, and misattribution costs
about 0.4% at uncertainty 0.2.

---

*Synthesized from the seven reports listed above. 2026-09-21.*
