# Policy Synthesis and Deployment Recommendations

**Scope:** Synthesizes seven AIReSim reports: the paper-default configuration
(`SIMULATION_REPORT.md`, `DIAGNOSIS_REALISTIC_REPORT.md`) and a stress-tested "payoff
regime" (elevated failure rate, bad-server multiplier up to 30×, poor repair quality, 488
servers of working-pool headroom) swept over failure severity, repair quality, bad-server
fraction, scheduling and diagnosis quality (`RETIREMENT_POLICY_REPORT.md`,
`SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`,
`THRESHOLD_SENSITIVITY_REPORT.md`, `DIAGNOSIS_SWEEP_REPORT.md`). Repairs follow the DSN'26
model: escalation is independent of silent auto-repair failure. Retirement and scheduling
were compared only in the payoff regime; at the paper defaults only diagnosis and the
job-length sweep (`SIMULATION_REPORT.md` §5a) were studied.

---

## Findings

**1. Training time is an accounting identity.** In every run, `training_time =
job_length + total_failures × recovery_time + host_selection_count × host_selection_time
+ preemption_count × preemption_wait_time` (largest residual across 1,200 runs: 1.2e-10 h,
`DIAGNOSIS_REALISTIC_REPORT.md` §6). No lost work is charged since the last checkpoint, so
any policy's, parameter's, or misdiagnosis's effect on training time is exactly its effect
on the failure count, plus small host-selection and preemption terms — every finding below
is a statement about failure counts through this identity.

**2. At default parameters the pipeline is already efficient.** Effective Training Ratio
(ETR) is 62.2%. Fixed per-failure checkpoint reload (`recovery_time`) is 37.7% of wall-clock
time, warm standbys absorb 99.6% of failures in place, and the spare pool is rarely used
(about 12 preemptions per run).

**3. `ScoredRemoval` is the strongest single lever in the payoff regime and beats
`ThresholdRemoval` everywhere tested.** `SC_fast` (retire after 2 failures) saves 317 h
(13.2%) at 20× / 75% repair-fail, leads `ThresholdRemoval` by 30 h at 5× up to 287 h at 30×,
and by 42–377 h across repair quality. Its best result is −503 h (19%). The gain grows with
severity: at mild settings (5×, or 72% fix rate) it is only 36–44 h (about 2%) for 240–255
retirements.

**4. `FewestFailuresFirst` scheduling is free and works by benching bad servers, not by
acting often.** `Scheduler.do_host_selection` re-picks the *entire* job from the available
pool each time it runs, so one full selection can exclude every server the policy regards
as bad, up to headroom (`working_pool_size − job_size − warm_standbys`); between full
selections, standby swaps are FIFO and policy-blind. In the payoff regime, headroom (488)
exceeds the entire initial bad population (~368, 8%), and the data confirm the exclusion
happens: time-averaged faulty servers in the active job are 129.7 under
`FewestFailuresFirst` vs 170.9 under `Random` (24% fewer), correspondingly higher in the
idle pool (242.3 vs 201.1). It saves 272 h (11.4%) alone, is faster than the baseline in
all 25 cells of a 5×5 severity grid, and is statistically tied with `SC_fast` in 18 of them;
`SC_fast` is clearly ahead only at ≥20× with ≥75% repair-fail (42–135 h). At the paper
defaults headroom is only 48 servers against an initial bad population of ~624 (15%) —
7.7% coverage, vs 133% in the payoff regime — and it shows **no measurable benefit** (CIs
exclude any benefit above about 18 h, 0.2%; active-job faulty-server counts are
statistically indistinguishable between the two policies, `DIAGNOSIS_REALISTIC_REPORT.md`).
This is a headroom and saturation limit (findings 5–6), not a consultation-frequency
limit: full selection happens ~41 times per run at defaults against ~11,000 failures,
about as rarely (relatively) as the payoff regime's ~7 against ~1,450–2,800, yet the
mechanism works in one regime and not the other.

**5. Any node-management policy at the paper defaults is capped at ≈2.3% of training
time.** With `bad_server_regeneration` off, a repair only ever cures a bad server, so the
systematic-failure count is capped by the initial bad population and plateaus at
684.7 ± 19.3 over a 256-day run (`SIMULATION_REPORT.md` §5a). A policy that targeted bad
servers perfectly — instant, free, zero false positives — could eliminate at most those
684.7 failures: 684.7 × 20 min ≈ 228 h ≈ **2.3%** of the 9,873 h mean training time. Every
retirement and scheduling result measured at the paper defaults (finding 4; misattribution
in finding 10) sits inside this ceiling, which explains why the effects there are small or
null while the same mechanisms are large in the payoff regime.

**6. The payoff regime matters because bad servers persist through the job, not only
because severity is high.** Its 14-day job is short relative to how slowly repairs work
there: the blended per-attempt repair success rate is `1 − (0.8×0.75 + 0.2×0.60) = 28%`
(vs. 76% at the paper defaults), so only 73.8% of the initial ~368 bad servers are ever
cured, leaving 26.2% still bad at job end — compare the paper defaults' 256-day job, long
enough to fully cure the bad population out by the end (§5a). A short job with ineffective
repair gives retirement and health-aware scheduling a bad population that stays large all
run; a long job with effective repair does not, independent of the failure-rate multiplier.

**7. The two levers overlap.** `FewestFailures + ScoredRemoval` (−329 h) and
`Random + ScoredRemoval` (−317 h) are statistically tied. Together they achieve 56% of the
sum of their separate effects, though smart scheduling cuts retirements from 390 to 336.

**8. `ThresholdRemoval` rarely pays.** `≥3/7d` retires 4–10 servers and has no reliable
effect; `≥1/7d` retires every server on its first failure and depletes every run. `≥2/7d`
is faster in 35 of 44 sensitivity cells (12–175 h; 89 h at baseline) but at the headline setting captures
only about a quarter of `ScoredRemoval`'s benefit.

**9. Bad-server fraction is a retirement trigger with a clear crossover, but only
`ThresholdRemoval` was swept on it.** `Thresh ≥2/7d`'s saving is significant from 3% bad
servers (144 servers, −55 h) and grows steadily through 8% (−88.8 h — the payoff regime's
own bad-server fraction) to a large, dependable −116 h to −175 h from 12% (576 servers) to
20% (960 servers); "significant" and "dependable-regardless-of-other-parameters" are
different bars on the same monotonic curve (`THRESHOLD_SENSITIVITY_REPORT.md` §4.4, §8),
not conflicting numbers. `ScoredRemoval` has not been swept on this axis.

**10. In the payoff regime, diagnosis quality matters, and `ScoredRemoval` fails only at
the extreme — but the scheduling and retirement policies tested here read ground truth an
operator would not have.** Smart scheduling plus retirement is net-beneficial from
diagnosis probability 0.2; `Random + ScoredRemoval` breaks even at about 0.6. Under
misattribution `ScoredRemoval` still helps through uncertainty 0.8, then turns harmful at
1.0 (+65 to +96 h), retiring innocent servers while real offenders keep clean scores;
`ThresholdRemoval` degrades to no effect. Random scheduling degrades 33% by uncertainty
1.0, `FewestFailuresFirst` only 9% — but `FewestFailuresFirst` reads `total_failure_count`
and `ThresholdRemoval` reads `failure_timestamps`, both recorded on the server that truly
failed, before diagnosis runs, including failures diagnosis missed. Neither policy's
robustness here is available to an operator relying on diagnosis alone; the
attributed-count variant (`FewestAttributedFailuresFirst`) has been tested only at the
paper defaults, where headroom is too small for any scheduling policy to show an effect
(finding 4) — it has **not** been tested in the payoff regime, so whether it keeps
`FewestFailuresFirst`'s robustness there is unknown. At the paper defaults the
misattribution damage is small and is exactly an extra-failures cost (finding 1):
uncertainty 0.2 raises training time 0.37% (95% CI +0.15% to +0.58%), 2.1–2.4% at 0.5.

**11. Uptime-credit scoring provides no benefit at production scale.** Aggregate failure
arrival is too fast (~7-minute run chunks) for any practical `time_period` to award a
credit, so `ScoredRemoval` reduces to a lifetime failure count.

---

## Recommendations

| Situation | Deploy | Why |
|---|---|---|
| Default or unknown regime | `FewestFailuresFirst` + `NeverRemove` | Free; headroom (48 servers, 7.7% of the initial bad population) is too small at defaults for any node-management policy to matter, capping the benefit at ≈2.3% of training time (findings 4–5) |
| Multiplier ≳20× and repair-fail ≳75% | `ScoredRemoval` (2-failure), with or without `FewestFailuresFirst` | Clearly ahead of scheduling alone (42–135 h); needs the ~390 retirements and 488-server headroom tested here |
| Multiplier 10–15× or repair-fail 40–60% | `FewestFailuresFirst` + `NeverRemove`, or `ScoredRemoval` if capacity allows | Statistically tied in most cells; `ScoredRemoval` −72 to −251 h against the baseline |
| Multiplier ≲5× and repair-fail ≲20% | `NeverRemove` | Retirement gains about 2% for 240+ retirements |
| Bad-server fraction ≥ 3% (144 servers) | `ThresholdRemoval(≥2/7d)` | Only policy tested on this axis: significant from −55h at 3%, dependable −116h to −175h from 12% up; `ScoredRemoval` untested |
| Diagnosis uncertainty may reach 1.0 | `FewestFailuresFirst` if true failure counts are observable; no `ScoredRemoval` | `ScoredRemoval` harmful at 1.0; from 0.6 up `ThresholdRemoval` matches or beats it (this row and the next assume ground truth an operator using only diagnosis may lack — finding 10) |
| Diagnosis probability below 0.4 | `FewestFailuresFirst` + `ThresholdRemoval(≥2/7d)` | It reads every failure timestamp; `ScoredRemoval` is blind to missed failures |
| Tight working-pool headroom | `NeverRemove` or `ThresholdRemoval` | `ScoredRemoval` retires ~390 servers, more than the 200-server spare pool; `FewestFailuresFirst` itself needs headroom to work (finding 4); untested with tight headroom |
| Choosing a threshold | `≥2/7d`, never `≥3/7d` or `≥1/7d` | `≥3/7d` does nothing; `≥1/7d` depletes the cluster |

**Bottom line:** in the payoff regime, `ScoredRemoval` is the best retirement policy and
`FewestFailuresFirst` a free scheduling default that works the same way — benching known-bad
servers at full host selection — whenever headroom is large relative to the bad population
and the job is long/ineffective-repair enough for that population to persist. At the paper
defaults neither headroom nor persistence holds, capping any node-management policy's
possible benefit at ≈2.3% of training time; misattribution there costs about 0.4% at
uncertainty 0.2. Both `FewestFailuresFirst` and `ThresholdRemoval`'s payoff-regime results
assume ground-truth failure data an operator relying on diagnosis would not have.

---

*Synthesized from the seven reports listed above. 2026-09-22 (corrected).*
