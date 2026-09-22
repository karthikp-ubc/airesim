# ThresholdRemoval Sensitivity Analysis
## Where Active Server Retirement Has a Net Benefit

**Data:** `examples/threshold_sensitivity_figures/sensitivity_summary.csv` (132 rows: 44 cells ×
3 policies, 8 replications each), produced by `examples/threshold_sensitivity.py` at commit
`0cab8fb` (run log: `examples/threshold_sensitivity_figures/run.log`). Repairs follow the
paper's model: `prob_auto_to_manual` is the probability that auto repair escalates,
independent of the silent auto-repair failure `auto_repair_fail_prob`. Date: 2026-09-21.

---

## 1. Executive Summary

This report sweeps seven simulation parameters one-at-a-time from the **payoff regime** baseline
(20× failure multiplier, 75% manual repair fail probability, 4600-server pool) to identify
the conditions under which `ThresholdRemoval` saves training time relative to `NeverRemove`.

Two policies are compared throughout:

| Policy | Config | Effective rule |
|---|---|---|
| **Thresh ≥2/7d** | `max_failures=2, window=7 days` | Retire after 2 failures in any 7-day window |
| **Thresh ≥3/7d** | `max_failures=3, window=7 days` | Retire after 3 failures in any 7-day window |

Bold deltas in the tables below differ from `NeverRemove` by more than two standard errors
(8 replications per cell; standard errors of a difference are ≈14–25h).

**Key findings:**

- **Thresh ≥2/7d** saves time in most of the tested space: 35 of its 44 cells are more than
  two standard errors faster than `NeverRemove`, and none is significantly slower. Savings
  range from **12h (5-minute recovery) to 175h** (30× multiplier, or 20% bad servers),
  and are **89h (3.7%)** at the baseline. The nine cells without a significant benefit are
  all at the mild end of a severity axis (multiplier ≤15×, manual repair fail ≤0.2, 1% bad
  servers, no auto-repair failures).
- **Thresh ≥3/7d** is far more conservative (retires 0–10 servers in most cells) and shows
  no reliable effect: 1 of its 44 cells is significant (−33h at auto-repair fail 0.2).
- The **failure-rate multiplier**, the **bad-server fraction** and the **manual repair fail
  probability** are the strongest gatekeepers of the retirement benefit: the saving grows
  steadily with each. **Recovery time** scales the saving up to about 40 minutes and it is
  roughly flat beyond.
- **Pool headroom and spare-pool size do not gate the benefit** in this sweep: `Thresh ≥2/7d`
  saves 55–135h at every headroom from +18 to +688 servers and every spare-pool size from
  50 to 500, with no depletion.

---

## 2. Simulation Baseline

All sweeps vary one parameter at a time from the following payoff-regime baseline:

| Parameter | Baseline value |
|---|---|
| `working_pool_size` | 4600 |
| `spare_pool_size` | 200 |
| `job_size` | 4096 |
| `warm_standbys` | 16 |
| `job_length` | 14 days |
| `random_failure_rate` | 2× default |
| `systematic_failure_rate_multiplier` | **20×** |
| `systematic_failure_fraction` | **8%** |
| `recovery_time` | **60 min** |
| `auto_repair_fail_prob` | **0.60** |
| `manual_repair_fail_prob` | **0.75** |
| `prob_auto_to_manual` | 0.80 |
| Replications | 8 per data point |

The baseline NeverRemove time is **2394.6h ± 38.7h**.
Thresh ≥2/7d saves **88.8h** (−3.7%); Thresh ≥3/7d saves **9.5h** (−0.4%, not significant) at baseline.

**Effective Training Ratio (ETR)** = `336 hrs (job_length) / total_training_time`.
Baseline ETR (NeverRemove): **336 / 2394.6 = 14.0%**.
With Thresh ≥2/7d: 336 / 2305.8 = **14.6%** (+0.5 pp).
ETR values for all other configurations can be derived from the tables below as
`ETR = 336 / (NeverRemove_time + Δ)`.

---

## 3. Overview

![Seven-panel overview of all sweeps](../examples/threshold_sensitivity_figures/overview.png)

Each panel shows training time (top) and servers retired (bottom) vs one swept parameter.

---

## 4. Parameter Sweeps

### 4.1 Failure-Rate Multiplier

![Sweep: failure rate multiplier](../examples/threshold_sensitivity_figures/sweep_systematic_failure_rate_multiplier.png)

| Multiplier | NeverRemove (hrs) | ETR (NR) | Thresh ≥2/7d Δ | Retired | Thresh ≥3/7d Δ | Retired |
|---|---|---|---|---|---|---|
| 1× | 1572.8 ± 40.1 | 21.4% | +7.9h | 20 | +0.0h | 0 |
| 2× | 1633.0 ± 39.5 | 20.6% | +28.0h | 20 | −3.2h | 0 |
| 5× | 1848.3 ± 47.1 | 18.2% | +16.1h | 34 | +14.3h | 0 |
| 10× | 2095.6 ± 40.1 | 16.0% | −41.4h | 59 | −12.6h | 2 |
| 15× | 2267.6 ± 65.9 | 14.8% | −49.7h | 83 | −7.3h | 3 |
| 20× | 2394.6 ± 38.7 | 14.0% | **−88.8h** | 106 | −9.5h | 4 |
| 25× | 2470.6 ± 54.7 | 13.6% | **−127.6h** | 115 | −4.8h | 6 |
| 30× | 2535.5 ± 58.1 | 13.3% | **−174.9h** | 128 | −26.6h | 10 |

**Thresh ≥2/7d crossover: 20×** — significant from 20× upward, with a saving that grows
with severity (89h → 128h → 175h at 20× → 25× → 30×). At 10× and 15× it saves 41–50h, which is
suggestive (z ≈ −1.6 to −1.9) but not significant at this replication count; at 5× and
below there is no benefit (+8h to +28h, all within noise).

**Thresh ≥3/7d** never benefits reliably — it retires at most 10 servers at any
multiplier and the signal is swamped by noise.

**ETR range across multipliers:** NeverRemove ETR drops from 21.4% at 1× (low failures →
training close to ideal) to 13.3% at 30× (heavy recovery overhead).
Thresh ≥2/7d improves ETR by 0.5–1.0 pp at 20–30×.

---

### 4.2 Manual Repair Fail Probability

![Sweep: manual repair fail probability](../examples/threshold_sensitivity_figures/sweep_manual_repair_fail_prob.png)

| Manual fail prob | Effective fix rate | NeverRemove (hrs) | ETR (NR) | Thresh ≥2/7d Δ | Retired | Thresh ≥3/7d Δ | Retired |
|---|---|---|---|---|---|---|---|
| 0.00 | 88% | 1874.5 ± 46.8 | 17.9% | −9.2h | 29 | +0.0h | 0 |
| 0.20 | 72% | 1934.4 ± 36.1 | 17.4% | +7.1h | 41 | +11.8h | 1 |
| 0.40 | 56% | 2067.4 ± 44.2 | 16.3% | **−42.7h** | 59 | −6.5h | 2 |
| 0.60 | 40% | 2221.0 ± 51.1 | 15.1% | **−54.0h** | 77 | +11.6h | 3 |
| 0.75 | 28% | 2394.6 ± 38.7 | 14.0% | **−88.8h** | 106 | −9.5h | 4 |
| 0.90 | 16% | 2606.0 ± 37.8 | 12.9% | **−101.9h** | 128 | −4.9h | 7 |

**Thresh ≥2/7d crossover: 0.40** (56% fix rate). At or below 0.2 (≥72% fix rate) too many
servers are genuinely repaired for retirement to help (+7h, no better than noise). From 0.4
upward broken servers keep returning to the pool and active retirement eliminates
recidivists; the saving grows with the fail probability (43h → 102h).

**Thresh ≥3/7d** shows no significant effect at any probability (−7h to +12h).

**ETR range:** NeverRemove ETR falls from 17.9% (fail prob 0.0) to 12.9% (0.9).

---

### 4.3 Pool Headroom (Working Pool Size)

![Sweep: working pool size](../examples/threshold_sensitivity_figures/sweep_working_pool_size.png)

Pool headroom = `working_pool_size − (job_size + warm_standbys)` = `working_pool_size − 4112`.

| Pool size | Headroom | NeverRemove (hrs) | ETR (NR) | Thresh ≥2/7d Δ | Retired | Thresh ≥3/7d Δ | Retired |
|---|---|---|---|---|---|---|---|
| 4130 | +18 | 2345.4 ± 49.0 | 14.3% | **−60.3h** | 96 | +4.9h | 5 |
| 4200 | +88 | 2379.0 ± 46.1 | 14.1% | **−86.0h** | 101 | +4.8h | 4 |
| 4300 | +188 | 2355.0 ± 34.4 | 14.3% | **−97.0h** | 97 | −8.7h | 4 |
| 4400 | +288 | 2392.8 ± 58.0 | 14.0% | **−135.4h** | 100 | +3.5h | 5 |
| 4500 | +388 | 2341.5 ± 27.9 | 14.3% | **−64.3h** | 103 | +14.4h | 3 |
| 4600 | +488 | 2394.6 ± 38.7 | 14.0% | **−88.8h** | 106 | −9.5h | 4 |
| 4800 | +688 | 2396.2 ± 36.5 | 14.0% | **−54.7h** | 105 | +23.9h | 5 |

**Thresh ≥2/7d benefits at every tested headroom, down to +18 servers.** Savings range from
55h to 135h with no monotone trend in headroom, and no run was depleted. The retirements
(~100 servers per run) are absorbed by the 200-server spare pool, which is why headroom does
not gate the benefit here; a cluster with neither headroom nor spares would deplete (see
`RETIREMENT_POLICY_REPORT.md` for the aggressive `≥1/7d` setting, which does).

`NeverRemove` training time is also nearly flat across headroom (2341–2396h), so tightening
the pool to +18 servers costs almost nothing in this regime.

**Thresh ≥3/7d** shows no effect at any headroom.

---

### 4.4 Bad-Server Fraction

![Sweep: systematic failure fraction](../examples/threshold_sensitivity_figures/sweep_systematic_failure_fraction.png)

| Bad fraction | Bad servers (of 4800) | NeverRemove (hrs) | ETR (NR) | Thresh ≥2/7d Δ | Retired | Thresh ≥3/7d Δ | Retired |
|---|---|---|---|---|---|---|---|
| 1% | 48 | 1595.4 ± 24.0 | 21.1% | −20.1h | 30 | −10.4h | 0 |
| 3% | 144 | 1837.3 ± 59.9 | 18.3% | **−55.0h** | 58 | −41.4h | 2 |
| 5% | 240 | 2065.0 ± 42.1 | 16.3% | **−65.7h** | 75 | −3.8h | 3 |
| 8% | 384 | 2394.6 ± 38.7 | 14.0% | **−88.8h** | 106 | −9.5h | 4 |
| 12% | 576 | 2860.6 ± 32.1 | 11.7% | **−116.0h** | 129 | −27.7h | 4 |
| 20% | 960 | 3800.4 ± 49.7 | 8.8% | **−174.9h** | 172 | −0.0h | 5 |

**Thresh ≥2/7d crossover: 3%** (144 bad servers) — significant from 3% upward, with the
saving growing steadily to 175h at 20%. At 1% bad servers (48) the saving (20h) is
suggestive but not significant.

**Thresh ≥3/7d** is not significant at any fraction (−41h at 3% is the largest, z = −1.7).

The absolute training time impact grows sharply with bad-server fraction because each bad
server contributes ~0.42 failures/day (TTF ≈ 2.4 days) × 60 min recovery overhead =
~25 min/day of wasted compute.

**ETR:** NeverRemove ETR degrades from 21.1% (1% bad fraction, few failures) to 8.8% (20%
bad fraction, severe failure load). Thresh ≥2/7d recovers 0.4–0.5 pp of ETR at 5–20% bad.

---

### 4.5 Recovery Time

![Sweep: recovery time](../examples/threshold_sensitivity_figures/sweep_recovery_time.png)

| Recovery time | NeverRemove (hrs) | ETR (NR) | Thresh ≥2/7d Δ | Retired | Thresh ≥3/7d Δ | Retired |
|---|---|---|---|---|---|---|
| 5 min | 500.0 ± 3.1 | 67.2% | **−12.5h** | 228 | −2.3h | 46 |
| 10 min | 670.7 ± 8.7 | 50.1% | **−31.6h** | 207 | −2.6h | 37 |
| 20 min | 1012.9 ± 13.8 | 33.2% | **−49.6h** | 172 | −1.9h | 20 |
| 40 min | 1701.9 ± 35.7 | 19.7% | **−93.8h** | 133 | −4.3h | 6 |
| 60 min | 2394.6 ± 38.7 | 14.0% | **−88.8h** | 106 | −9.5h | 4 |
| 90 min | 3442.2 ± 72.0 | 9.8% | **−104.3h** | 74 | +11.8h | 2 |

**Thresh ≥2/7d benefits at every tested recovery time**, even 5 minutes (−12.5h,
z = −8.1), where NeverRemove takes only 500h. The absolute saving grows with recovery time
up to about 40 minutes (94h) and is roughly flat beyond (89h at 60 min, 104h at 90 min), so
as a share of training time it peaks at ~5.5% (40 min) and falls to 3.0% at 90 min.

**Recovery time is the strongest continuous amplifier at the short end**, but at very
short recovery times the trade is poor: at 5 minutes the policy retires 228 servers to save
12.5h (2.5%).

**Thresh ≥3/7d** is not significant anywhere, even where it retires many servers
(46 at 5 min).

**ETR:** NeverRemove ETR rises sharply as recovery time shrinks — from 9.8% at 90 min to
67.2% at 5 min.

---

### 4.6 Auto Repair Fail Probability

![Sweep: auto repair fail probability](../examples/threshold_sensitivity_figures/sweep_auto_repair_fail_prob.png)

`auto_repair_fail_prob` is the probability that the auto-repair stage silently fails. Only
the 20% of servers that are *not* escalated (`prob_auto_to_manual = 0.8`) are repaired by the
auto stage alone, so this parameter has a smaller effect on the baseline than the manual
repair fail probability does.

| Auto fail prob | NeverRemove (hrs) | ETR (NR) | Thresh ≥2/7d Δ | Retired | Thresh ≥3/7d Δ | Retired |
|---|---|---|---|---|---|---|
| 0.00 | 2229.1 ± 67.1 | 15.1% | −47.1h | 76 | −29.8h | 2 |
| 0.20 | 2281.0 ± 22.6 | 14.7% | **−82.0h** | 84 | **−32.5h** | 3 |
| 0.40 | 2370.8 ± 58.6 | 14.2% | **−112.7h** | 95 | −9.5h | 3 |
| 0.60 | 2394.6 ± 38.7 | 14.0% | **−88.8h** | 106 | −9.5h | 4 |
| 0.80 | 2439.4 ± 44.9 | 13.8% | **−66.1h** | 109 | +42.5h | 4 |

**Thresh ≥2/7d crossover: 0.2.** From 0.2 upward the saving is significant (66–113h), with a
maximum at 0.4. At 0.0 (auto repair never fails silently) the saving (47h) is suggestive but
not significant. Even a 20% auto-fail rate leaves enough silently broken servers for
retirement to help.

**Thresh ≥3/7d** is significant only at 0.2 (−33h, z = −2.1) and is otherwise noise; at 0.8
its point estimate is a 43h *cost* (z = +1.7).

---

### 4.7 Spare Pool Size

![Sweep: spare pool size](../examples/threshold_sensitivity_figures/sweep_spare_pool_size.png)

| Spare pool | NeverRemove (hrs) | ETR (NR) | Thresh ≥2/7d Δ | Retired | Thresh ≥3/7d Δ | Retired |
|---|---|---|---|---|---|---|
| 50 | 2401.1 ± 42.2 | 14.0% | **−68.0h** | 98 | −31.2h | 4 |
| 100 | 2417.5 ± 54.8 | 13.9% | **−121.8h** | 107 | −29.4h | 5 |
| 150 | 2358.5 ± 59.8 | 14.2% | **−52.7h** | 104 | +5.8h | 4 |
| 200 | 2394.6 ± 38.7 | 14.0% | **−88.8h** | 106 | −9.5h | 4 |
| 300 | 2384.5 ± 75.3 | 14.1% | **−90.0h** | 105 | +15.1h | 4 |
| 500 | 2380.0 ± 17.7 | 14.1% | **−61.1h** | 103 | +6.0h | 4 |

**Thresh ≥2/7d benefits at every spare-pool size from 50 to 500** (53–122h). The spare pool
does not gate retirement — retired servers come from the working pool and spares cover the
working-pool gaps — and it barely moves the `NeverRemove` baseline (2359–2418h). The
variation in savings across sizes (−53h to −122h) is within what 8-replication noise allows
and shows no trend.

**Thresh ≥3/7d** shows no reliable effect at any spare-pool size.

---

## 5. Crossover Summary

The table below shows the first parameter value at which each policy produces a **net
time reduction more than two standard errors from `NeverRemove`** (with no pool depletion):

| Parameter | Thresh ≥2/7d | Thresh ≥3/7d |
|---|---|---|
| Failure-rate multiplier | **20×** (10–15× suggestive) | Never |
| Manual repair fail prob | **0.40** | Never |
| Pool headroom above minimum | **+18 servers** (lowest tested) | Never |
| Bad-server fraction | **3%** (1% suggestive) | Never |
| Recovery time | **5 min** (lowest tested) | Never |
| Auto repair fail prob | **0.20** (0.0 suggestive) | 0.20 (isolated; not at neighbouring values) |
| Spare pool size | **50** (lowest tested) | Never |

---

## 6. When Does ThresholdRemoval Pay Off?

Three conditions determine the benefit; the first two are gatekeepers and the third is an
amplifier:

### Condition 1 — Failures are both frequent and persistent

Retirement only helps when bad servers reliably accumulate two or more failures within the
7-day window. In this sweep that requires either:
- **Failure rate multiplier ≥ 20×** (bad server TTF ≤ 2.4 days; benefit suggestive from
  10×), **or**
- **Bad-server fraction ≥ 3%** (144 servers).

At 5× multiplier (TTF ≈ 8 days) bad servers fail about once per window on average, so
they rarely hit the threshold twice — the window resets too often.

### Condition 2 — Repair is ineffective

Retirement saves time only when retired servers are servers that *would keep failing* if
re-admitted. This requires:
- **Manual repair fail prob ≥ 0.40** (effective fix rate ≤ 56%), or
- **Auto repair fail prob ≥ 0.2**.

When repair is highly effective (manual fail prob ≤ 0.2), most returning servers are genuinely
fixed; retirement retires servers that would have been fine and gains nothing.

### Condition 3 — Failures are expensive (amplifier)

Each failure triggers a `recovery_time` checkpoint reload, so the saving scales with it up
to about 40 minutes (12h at 5 min, 32h at 10 min, 50h at 20 min, 94h at 40 min). Recovery
time is not a gatekeeper — the benefit is significant even at 5 minutes — but at short
recovery times it comes at the price of many retirements (228 servers for 12h at 5 min).

---

## 7. When ThresholdRemoval Does Not Help

### Thresh ≥3/7d — structurally too conservative

With `max_failures=3`, a server must fail three times within 7 days to be retired. The data
show 0–10 servers retired per run at most settings, so the policy misses the vast majority
of recidivists in the 14-day payoff regime with 384 bad servers cycling through the pool.
It shows no reliable effect anywhere in this sweep, and its point estimates flip sign from
cell to cell.

### Thresh ≥2/7d at the mild end of each severity axis

At multipliers ≤5×, manual repair fail probability ≤0.2, and (marginally) 1% bad servers or
0% auto-repair failures, the point estimates are near zero or slightly positive (+7h to
+28h) and none is significant. Retirement removes servers that repairs would have fixed
without reducing recurring failures enough to matter, so there is nothing to gain and a
small chance of a cost.

---

## 8. Practical Guidance

| Scenario | Recommendation |
|---|---|
| Failure multiplier ≥ 20× AND manual repair fail prob ≥ 0.4 | Use `Thresh ≥2/7d` — saves roughly 45–175h (2–7%) |
| Failure multiplier 10–15× OR bad-server fraction ≈ 3% | Modest, suggestive benefit (41–55h); worth it if retirements are cheap, but not significant at 8 replications |
| Failure multiplier ≤ 5× AND manual repair fail prob ≤ 0.2 | Neither policy helps; NeverRemove is sufficient |
| Bad-server fraction ≥ 12% | Use `Thresh ≥2/7d` — saves 116–175h regardless of other parameters |
| Pool headroom or spare pool size | Not a reason to avoid retirement in this sweep: benefit at +18 headroom and at 50 spares, no depletion |
| Recovery time ≲ 10 min per failure | Retirement saves little (12–32h) for 200+ retirements; probably not worth the complexity |
| `Thresh ≥3/7d` over `Thresh ≥2/7d` | Only for a depletion-safety margin; it has no measurable training-time benefit |

**When to use `Thresh ≥3/7d` instead of `Thresh ≥2/7d`:**
`Thresh ≥3/7d` retires 10–50× fewer servers and is therefore much safer against pool
depletion, but it captures essentially none of the benefit. Prefer it only when depletion
risk dominates, e.g. a cluster with little headroom and a small spare pool.

---

*Generated by `examples/threshold_sensitivity.py` — AIReSim v0.1.0, regenerated 2026-09-21.*
