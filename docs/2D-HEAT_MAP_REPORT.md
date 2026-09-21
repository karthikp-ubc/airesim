# Two-Way Policy Sweep: Heat Map Results

> **Regenerated after a bug fix (2026-09-20).** The original run predates a fix
> to `RepairShop._repair_process`: the injected `RepairEscalationPolicy` was
> constructed but never consulted, so escalation to manual repair fired for a
> flat 80% of *all* auto repairs instead of 80% of the ~60% that actually
> failed (see `CHANGELOG.md`). Every table and figure below is regenerated
> with the fix. The qualitative shape of the result — three regimes, no
> policy dominating everywhere — is unchanged, but the boundaries between
> regimes shifted and the magnitudes shrank across the board (best-case
> ScoredRemoval improvement fell from −243h to −179h). Win counts also
> shifted: FewestFailuresFirst now wins the most cells (12/25, was 5/25),
> overtaking ScoredRemoval (8/25, was 18/25) — see §"Overall Win Counts."

## Overview

This report summarises a two-dimensional parameter sweep comparing three scheduling/retirement
policy combinations across 25 cells (5 × 5) with 10 independent replications per cell.
The two swept axes capture the two most influential drivers of bad-server harm:

| Axis | Values |
|------|--------|
| `systematic_failure_rate_multiplier` | 5×, 10×, 15×, 20×, 25× |
| `manual_repair_fail_prob` | 20%, 40%, 60%, 75%, 90% |

All other parameters are held at the **payoff regime baseline**:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `working_pool_size` | 4 600 | 488 idle servers above the 4 112 minimum — enough headroom to absorb retirements |
| `spare_pool_size` | 200 | standard preemptible buffer |
| `job_size` | 4 096 | large-scale training job |
| `warm_standbys` | 16 | hot spares allocated to the job |
| `job_length` | 14 days | compute time with no failures |
| `random_failure_rate` | 2× default | elevated ambient failure rate |
| `systematic_failure_fraction` | 8% | ≈ 368 bad servers out of 4 600 |
| `recovery_time` | 60 min | expensive checkpoint reload per failure |
| `prob_auto_to_manual` | 0.80 | 80% of auto-repair attempts escalate |
| `auto_repair_fail_prob` | 0.60 | 60% of auto repairs silently fail |

10 replications per cell × 3 policies × 25 cells = **750 simulations total**.

---

## Policies Compared

### 1. Random + NeverRemove (Baseline)
Uniform random host selection; every repaired server is returned to the working pool.
This is the naive default: no preference for healthy servers, no retirement.

### 2. Random + ScoredRemoval — SC_fast (Challenger A)
Uniform random host selection, but uses a score-based retirement policy tuned for fast culling:

| SC_fast parameter | Value |
|-------------------|-------|
| `initial_score` | 100 |
| `failure_penalty` | 60 |
| `success_increment` | 5 per day of clean uptime |
| `retirement_threshold` | 0 |

A server is retired after **just 2 failures** (score path: 100 → 40 → −20 ≤ 0).
Recovery is slow (5 pts/day) so a retired bad server is rarely reinstated.

### 3. FewestFailuresFirst + NeverRemove (Challenger B)
Prefers hosts with fewer historical failures when selecting replacements.
No retirement — every repaired server returns to the pool.
This is a zero-capacity-cost policy: it routes work away from bad servers
without permanently shrinking the cluster.

---

## Overall Win Counts

| Policy | Cells Won (out of 25) | Share |
|--------|-----------------------|-------|
| Random + NeverRemove (baseline) | 5 | 20% |
| Random + ScoredRemoval (SC_fast) | 8 | 32% |
| **FewestFailuresFirst + NeverRemove** | **12** | **48%** |

**The headline result reverses.** Pre-fix, `ScoredRemoval` dominated (18/25
cells, 72%) and the baseline barely won anywhere (2/25). Post-fix,
`FewestFailuresFirst` wins the most cells (12/25) and the baseline wins a
meaningfully larger share (5/25, 20%) — because with the repair pipeline
behaving correctly, `NeverRemove` is no longer artificially crippled, and a
zero-capacity-cost scheduling defense competes much better against
`ScoredRemoval`'s retirement cost. `ScoredRemoval` still wins the cells where
severity is highest (§"Head-to-Head" below), just fewer of them.

---

## ScoredRemoval (SC_fast) — Delta vs Baseline

> **Negative = faster than baseline.**  
> **Best improvement: −179.1 hrs** (mult=20×, repair_fail=90%; was −243h at 25×/90%)  
> **Worst regression: +19.1 hrs** (mult=20×, repair_fail=20%; was +34h at 10×/20%)

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | −22.0 h | −7.2 h | +15.4 h | −3.4 h | +6.1 h |
| **10×** | +6.7 h | +13.2 h | −14.7 h | −28.1 h | −48.8 h |
| **15×** | +18.2 h | −23.9 h | −42.5 h | −64.8 h | −90.3 h |
| **20×** | **+19.1 h** | −25.0 h | −53.3 h | −86.8 h | **−179.1 h** |
| **25×** | −7.3 h | −21.7 h | −95.7 h | −123.2 h | −177.6 h |

(10 replications per cell, freshly measured; see `examples/2d_heatmap_figures/heatmap_report.md`
for the auto-generated version of this table.)

### Interpretation

- **Bottom-right corner (high multiplier + high repair_fail_prob)**: SC_fast still
  excels, and the mechanism is unchanged — bad servers fail rapidly, repairs mostly
  don't fix them at 90% fail probability even post-fix, and retiring after 2 failures
  breaks the failure→repair→failure cycle. The magnitude just shrank (−179h vs −243h,
  a 26% reduction) because the corrected repair pipeline makes even the *un*-retired
  baseline less broken.

- **The "effective repairs hurt retirement" story is now much stronger.** Pre-fix,
  regressions only appeared at repair_fail=20% for mult=10×–20× (+13 to +34h).
  Post-fix, the regression band widens: 5×/60%, 5×/90%, 10×/20%, 10×/40%, and
  15×/20% are all positive too, alongside a larger regression at 20×/20% (+19.1h).
  With repairs genuinely working better across the board, there are simply more
  corners of this grid where a server that fails twice would likely have come back
  healthy on a third repair — exactly the case SC_fast can't tell apart from a truly
  chronic offender.

- **Top-left (low multiplier + low repair_fail_prob)**: Still the sweet spot for the
  baseline, and more so than before — the "do nothing" region of the grid grew.

---

## FewestFailuresFirst + NeverRemove — Delta vs Baseline

> **Negative = faster than baseline.**  
> **Best improvement: −124.4 hrs** (mult=20×, repair_fail=90%; was −96h at 25×/90%)  
> **Worst regression: +27.2 hrs** (mult=10×, repair_fail=20%; was +24h at 20×/20%)

| mult↓ / repair_fail→ | 20% | 40% | 60% | 75% | 90% |
|----------------------|-----|-----|-----|-----|-----|
| **5×** | −5.7 h | −17.0 h | +17.5 h | −11.1 h | +8.2 h |
| **10×** | **+27.2 h** | −17.7 h | −73.3 h | −26.2 h | −69.6 h |
| **15×** | +0.3 h | −43.0 h | −44.9 h | −87.4 h | −97.9 h |
| **20×** | +0.7 h | −19.4 h | −63.4 h | −70.0 h | **−124.4 h** |
| **25×** | −15.8 h | −41.5 h | −78.7 h | −63.0 h | −108.0 h |

(10 replications per cell, freshly measured.)

### Interpretation

- **FFF is still consistently positive** across most of the sweep, and now with a
  larger *share* of the grid than SC_fast (§"Overall Win Counts"), because it has
  zero capacity cost — it can never lose by retiring a server that repairs would
  have fixed. That structural advantage matters more, not less, now that repairs
  are genuinely more effective.

- **Two near-zero cells (15×/20%: +0.3h, 20×/20%: +0.7h)** replace the single
  pre-fix regression at 20×/20% (+24h) — with the corrected pipeline, benching bad
  servers at low severity is now essentially a wash rather than a measurable win
  *or* loss, since there's so little bad-server damage left to route around at
  20% repair-fail probability.

- **FFF now beats SC_fast head-to-head in 14 of 25 cells**, not 5 — including
  most of the moderate-multiplier band. SC_fast only pulls ahead of FFF at the
  highest-severity cells (§"Head-to-Head" below), where its capacity cost is
  finally outweighed by eliminating servers repairs genuinely cannot fix; FFF
  is the overall winner (beating both SC_fast and the baseline) in 12 of
  those 25 cells.

---

## Head-to-Head: Where Each Policy Wins

The winner heatmap (`heatmap_winner.png`) shows a noisier, more fragmented
pattern than pre-fix — expected, since every cell's margin shrank and 10
replications per cell leaves real sampling noise at the boundaries:

```
             repair_fail_prob →
               20%    40%    60%    75%    90%
mult  5×  [  SC   |  FFF  | BASE  |  FFF  | BASE  ]
      10× [ BASE  |  FFF  |  FFF  |  SC   |  FFF  ]
      15× [ BASE  |  FFF  |  FFF  |  FFF  |  FFF  ]
      20× [ BASE  |  SC   |  FFF  |  SC   |  SC   ]
      25× [  FFF  |  FFF  |  SC   |  SC   |  SC   ]
```
(Computed directly from the two delta tables above — the winner at each cell
is whichever of {baseline, SC_fast, FFF} has the lowest training time.)

**The three-regime story from the pre-fix report is weaker but still
directionally present:**

| Regime | Condition | Best Policy |
|--------|-----------|-------------|
| **Baseline wins** | repair_fail=20% at moderate multiplier (10×–20×), or high repair_fail at low multiplier (5×/60%, 5×/90%) | Random + NeverRemove |
| **FFF wins** | Most of the middle of the grid — low-to-moderate multiplier at moderate-to-high repair_fail, plus the two lowest-severity high-multiplier cells (20×/60%, 25×/20–40%) | FewestFailuresFirst |
| **ScoredRemoval wins** | High multiplier (≥20×) *and* high repair_fail (≥60%), plus two scattered outliers (5×/20%, 10×/75%) | SC_fast |

Pre-fix, `ScoredRemoval`'s winning region was "high multiplier OR high
repair_fail" — a large union. Post-fix it's closer to "high multiplier AND
high repair_fail" — a much smaller intersection, with `FewestFailuresFirst`
now the default winner everywhere else. The boundary is also less clean than
before: at this replication count (10/cell) several cells are close calls
(e.g. 15×/20%: FFF +0.3h vs SC +18.2h — FFF wins, but SC's own worst-case
margin here is well within noise of zero too).

---

## Key Takeaways

1. **Aggressive retirement still pays when bad servers are both prolific and
   persistent, but the ceiling is lower.** SC_fast's "retire after 2 failures"
   strategy now delivers up to −179 hrs (was −243h) when the failure rate
   multiplier and manual repair fail probability are both high. The mechanism
   is unchanged; the corrected repair pipeline just leaves less damage on the
   table for retirement to recover.

2. **Retirement is harmful in more of the grid than previously measured.**
   Pre-fix, regressions were confined to repair_fail=20% at moderate
   multipliers. Post-fix, SC_fast also regresses at 5×/60%, 5×/90%, and
   10×/40% — repairs are now good enough in more of the parameter space that
   retiring a twice-failed server is more often a mistake.

3. **FewestFailuresFirst is now the stronger general-purpose default, not
   just a safe hedge.** It wins the most cells overall (12/25) and beats
   SC_fast head-to-head in 14/25 cells — up from 5/25 pre-fix. Because it
   never retires servers, it still cannot overshoot; what changed is that its
   zero-cost floor now competes with SC_fast's ceiling over much more of the
   grid, because that ceiling is lower than it used to be.

4. **No single policy dominates all 25 cells** — this holds pre- and
   post-fix, but the split moved from roughly 72/20/8 (SC/FFF/baseline) to
   32/48/20. **If choosing a single default without measuring your specific
   regime, `FewestFailuresFirst` is now the better blind choice**, reversing
   the pre-fix guidance to prefer `SC_fast` when severity is unknown.

5. **The regime boundary is fuzzier and shifted toward higher severity.**
   Pre-fix it sat around mult≈15×, repair_fail≈40–60%. Post-fix, SC_fast's
   winning region contracts to roughly mult≥20× *and* repair_fail≥60% — a
   smaller, more extreme corner of the grid than before, with several
   near-tied cells at the new boundary given the ±20–65h standard deviations
   at 10 replications per cell.

---

## Figures

| Figure | Description |
|--------|-------------|
| [`heatmap_scored_delta.png`](2d_heatmap_figures/heatmap_scored_delta.png) | Δ training time (hrs): SC_fast vs baseline. Green = improvement, red = regression. |
| [`heatmap_fff_delta.png`](2d_heatmap_figures/heatmap_fff_delta.png) | Δ training time (hrs): FewestFailuresFirst vs baseline. |
| [`heatmap_winner.png`](2d_heatmap_figures/heatmap_winner.png) | Categorical map: which policy wins each cell. Grey = baseline, coral = SC_fast, blue = FFF. |

*Generated by [`examples/2d_heatmap_sweep.py`](2d_heatmap_sweep.py) — 10 replications per cell,
750 total simulations, regenerated 2026-09-20 post-fix.*
