# Policy Synthesis and Deployment Recommendations

**Scope:** Synthesizes the AIReSim reports: the paper-default configuration
(`SIMULATION_REPORT.md`, `DIAGNOSIS_REALISTIC_REPORT.md`) and a stress-tested "payoff
regime" (elevated failure rate, bad-server multiplier up to 30×, poor repair quality, 488
servers of working-pool headroom) swept over failure severity, repair quality, bad-server
fraction, scheduling and diagnosis quality (`RETIREMENT_POLICY_REPORT.md`,
`SCHEDULING_COMPARISON_REPORT.md`, `2D-HEAT_MAP_REPORT.md`,
`THRESHOLD_SENSITIVITY_REPORT.md`, `DIAGNOSIS_SWEEP_REPORT.md` including its §6
crossover sweep). Repairs follow the DSN'26 model: escalation is independent of silent
auto-repair failure. Retirement and scheduling were compared only in the payoff regime; at
the paper defaults only scheduling, diagnosis and the job-length sweep
(`SIMULATION_REPORT.md` §5a) were studied.

> **Updated 2026-11-20.** All reports were regenerated after the paper-conformance fixes
> (CHANGELOG). The main change is that scripts which don't set `diagnosis_probability`
> now use the Table I default of 0.8 instead of 1.0; the code fixes themselves changed no
> result measurably. With 20% of failures undiagnosed, retirement policies see less, and
> failure-aware scheduling — especially combined with retirement — gains ground
> (findings 3, 4, 7 and the new finding 12).

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
(ETR) is 61.9%. Fixed per-failure checkpoint reload (`recovery_time`) is 38.1% of wall-clock
time, warm standbys absorb 99.7% of failures in place, and the spare pool is rarely used
(about 1 preemption per run; 12 at diagnosis 1.0, when every failure sent a server to
repair).

**3. `ScoredRemoval` is the strongest retirement policy in the payoff regime and beats
`ThresholdRemoval` wherever the difference is measurable.** `SC_fast` (retire after 2
diagnosed failures) saves 259 h (10.4%) at 20× / 75% repair-fail, leads
`ThresholdRemoval` by 62 h at 10× up to 256 h at 30×, and by 41–316 h across repair
fail probabilities 0.4–0.9. Its best result is −475 h (17.5%). At mild settings (5×, or 72%
fix rate) neither policy has a measurable effect. Missed diagnoses cost it: at diagnosis
1.0 it saved 317 h at the headline setting.

**4. `FewestFailuresFirst` scheduling is free and works by benching known-bad servers,
not by acting often, and it trades curing them for avoiding them.**
`Scheduler.do_host_selection` re-picks the *entire* job from the available pool each time
it runs, so one full selection can exclude every server the policy currently regards as
bad — one that has already failed at least once — up to headroom
(`working_pool_size − job_size − warm_standbys`); between full selections, standby swaps
are FIFO and policy-blind. In the payoff regime, headroom (488) exceeds the entire initial
bad population (~368, 8%): time-averaged faulty servers in the active job are 138.1 under
`FewestFailuresFirst` vs 189.6 under `Random`, a 27% reduction (19% in the 2-D heat-map
sweep). Counted across the *whole* working pool, faulty servers are actually higher under
`FewestFailuresFirst` (262.9 vs 222.2; 124.8 idle vs 32.6) — a benched bad server never
fails, so it never enters repair and never gets cured — and it still wins. It saves 302 h
(12.2%) alone, more than `ScoredRemoval` alone, is faster than the baseline in all 25 cells
of a 5×5 severity grid, and has the lowest mean in 24 of them (16 significantly ahead of
`SC_fast`). At the paper defaults headroom is only 48 servers against ~624 initially bad
(7.7% coverage) and it shows **no measurable benefit** (a benefit above ~26 h, 0.3%, is
excluded; `DIAGNOSIS_REALISTIC_REPORT.md`). That is a headroom and saturation limit
(findings 5–6), not a consultation-frequency limit: full selection happens ~38 times per
run at defaults against ~11,000 failures, about as rarely as the payoff regime's ~6.

**5. Any node-management policy at the paper defaults is capped at ≈2.9% of training
time.** With `bad_server_regeneration` off, a repair only ever cures a bad server, so the
systematic-failure count is capped by the initial bad population and plateaus at
862.6 ± 22.7 over a 256-day run (`SIMULATION_REPORT.md` §5a; 684.7 at diagnosis 1.0,
because undiagnosed bad servers aren't repaired). A policy that targeted bad servers
perfectly could eliminate at most those failures: 862.6 × 20 min ≈ 288 h ≈ **2.9%** of the
9,926 h mean training time. Every result measured at the paper defaults sits inside this
ceiling, which is why effects there are small or null while the same mechanisms are large
in the payoff regime.

**6. The payoff regime matters because bad servers persist through the job, not only
because severity is high.** Its 14-day job is short relative to how slowly repairs work
there: the blended per-attempt repair success rate is `1 − (0.8×0.75 + 0.2×0.60) = 28%`
(vs. 76% at the paper defaults), and with 20% of failures undiagnosed 31.8% of the initial
~367 bad servers are still bad at job end under `Random + NeverRemove`
(`examples/scheduling_comparison_figures/replications.csv`; 24.4% at diagnosis 1.0) —
compare the paper defaults' 256-day job, long enough to cure essentially the whole bad
population. A short job with ineffective repair gives retirement and health-aware
scheduling a bad population that stays large all run.

**7. Scheduling and retirement overlap, but the combination is clearly best.**
`FewestFailures + ScoredRemoval` (−380 h) beats `Random + ScoredRemoval` (−259 h) by
122 ± 21 h (paired); with diagnosed-only information (`HighestScoreFirst`, whose scores
see only diagnosed failures), the combination still wins by 65 ± 23 h. Together the
levers achieve 68% of the sum of their separate effects, and smart scheduling cuts
retirements from 338 to 225–264. At diagnosis 1.0 the combination and retirement alone
were tied.

**8. `ThresholdRemoval` rarely pays.** `≥3/7d` retires about 6 servers and has no reliable
effect; `≥1/7d` retires every server on its first failure and depletes every run. `≥2/7d`
is faster in 36 of 44 sensitivity cells (19–190 h; 72 h at baseline) but at the headline
setting captures only about a quarter of `ScoredRemoval`'s benefit, and with random
scheduling it is slower than diagnosed-only scheduling alone at every diagnosis level
tested (finding 12).

**9. Bad-server fraction drives the retirement benefit, but only `ThresholdRemoval` was
swept on it.** `Thresh ≥2/7d` saves 30–72 h from 1% to 8% bad servers (significant except
at 3%) and 127–137 h at 12–20% (`THRESHOLD_SENSITIVITY_REPORT.md` §4.4). `ScoredRemoval`
has not been swept on this axis.

**10. In the payoff regime, diagnosis quality matters, and `ScoredRemoval` fails only at
the extreme.** Under misattribution (`diagnosis_uncertainty`) `ScoredRemoval` still helps
through uncertainty 0.8, then turns harmful at 1.0 (+65 to +96 h), retiring innocent
servers while real offenders keep clean scores (`DIAGNOSIS_SWEEP_REPORT.md` §3). Random
scheduling degrades 33% by uncertainty 1.0, `FewestFailuresFirst` only 9% — but
`FewestFailuresFirst` reads ground-truth failure counts; `FewestAttributedFailuresFirst`
has been tested in this regime only against missed diagnoses (finding 12), not
misattribution. At the paper defaults the misattribution damage is small and is exactly
an extra-failures cost (finding 1): uncertainty 0.2 raises training time 0.40% (95% CI
+0.16% to +0.63%), 2.0–2.2% at 0.5.

**11. Uptime-credit scoring provides no benefit at production scale.** Aggregate failure
arrival is too fast (~7-minute run chunks) for any practical `time_period` to award a
credit, so `ScoredRemoval` reduces to a lifetime count of diagnosed failures.

**12. Whether retirement or scheduling wins depends on diagnosis quality — and running
both wins at every level.** (`DIAGNOSIS_SWEEP_REPORT.md` §6; 30 paired seeds, three
payoff-regime cells, diagnosis probability 0.5–1.0, with `FewestAttributedFailuresFirst`
(FAFF) as the realistic-information scheduler.)
- `Random + ScoredRemoval` beats `FAFF + NeverRemove` only above a diagnosis probability
  of **0.91** (15×/75%), **0.81** (20×/75%) or **0.59** (25×/90%): the worse the bad
  servers, the more missed diagnoses retirement can absorb. Against ground-truth
  `FewestFailuresFirst` the crossovers are 0.93 / 0.87 / 0.74.
- **Ranking survives missed diagnoses; thresholds don't.** From diagnosis 1.0 to 0.5,
  FAFF keeps 84–107% of its value over random scheduling, while `SC_fast` keeps only
  46–74% of its value. Missing a random share of failures thins every server's count
  alike, so the ranking survives; retirement needs two observed failures and is only
  checked after a diagnosed failure.
- `FAFF + ScoredRemoval` is faster than `FAFF + NeverRemove` at every diagnosis level in
  every regime (26–148 h), faster than `Random + ScoredRemoval` at every level below 1.0
  (19–69 h at 0.8, 161–216 h at 0.5), and retires fewer servers. It is the fastest
  realistic policy in 23 of 24 cells and tied in the other.
- Ground-truth failure attribution is worth 43–103 h on top of that at diagnosis 0.8 and
  107–223 h at 0.5.

---

## Recommendations

| Situation | Deploy | Why |
|---|---|---|
| Default or unknown regime | Failure-aware scheduling (`FewestAttributedFailuresFirst`) + `NeverRemove` | Free; at defaults headroom (48 servers) is too small for any node-management policy to matter, capping the benefit at ≈2.9% of training time (findings 4–5) |
| Persistent bad servers (payoff-like regime), any diagnosis quality | Failure-aware scheduling + `ScoredRemoval` (2-failure) | Fastest or tied at every diagnosis level tested; beats either lever alone and retires fewer servers than retirement alone (findings 7, 12) |
| Retirement only (no control over host selection) | `ScoredRemoval` if diagnosis probability is high enough for the regime (≳0.6–0.9); otherwise prefer investing in scheduling | Retirement loses 26–54% of its value as diagnosis falls to 0.5 (finding 12) |
| Multiplier ≲5× and repair-fail ≲20% | `NeverRemove` | Neither retirement policy has a measurable effect (finding 3) |
| Bad-server fraction ≥ 12% | `ThresholdRemoval(≥2/7d)` or `ScoredRemoval` | `≥2/7d` saves 127–137 h there; `ScoredRemoval` untested on this axis but stronger everywhere it was tested |
| Diagnosis uncertainty may reach 1.0 | Scheduling alone; no `ScoredRemoval` | `ScoredRemoval` harmful at 1.0 (finding 10) |
| Tight working-pool headroom | `NeverRemove` or `ThresholdRemoval` | `ScoredRemoval` retires 225–390 servers, more than the 200-server spare pool; failure-aware scheduling itself needs headroom to work (finding 4); untested with tight headroom |
| Choosing a threshold | `≥2/7d`, never `≥3/7d` or `≥1/7d` | `≥3/7d` does nothing; `≥1/7d` depletes the cluster |

**Bottom line:** in the payoff regime, run failure-aware scheduling *and* `ScoredRemoval`:
the combination is the best policy at every diagnosis quality tested, while the better
single lever flips from retirement to scheduling as diagnosis gets worse, at a point that
depends on severity. Scheduling is robust to missed diagnoses because it only needs a
ranking. At the paper defaults neither headroom nor persistence holds, capping any
node-management policy's possible benefit at ≈2.9% of training time; misattribution there
costs about 0.4% at uncertainty 0.2.

---

*Synthesized from the reports listed above. 2026-11-20.*
