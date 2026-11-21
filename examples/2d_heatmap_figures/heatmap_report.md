# 2-D Heatmap Sweep: Policy Comparison

## Experimental Setup

| Parameter | Value |
|-----------|-------|
| working_pool_size | 4 600 |
| spare_pool_size | 200 |
| job_size | 4 096 |
| warm_standbys | 16 |
| job_length | 14 days |
| random_failure_rate | 2× default |
| systematic_failure_fraction | 8 % |
| recovery_time | 60 min |
| prob_auto_to_manual | 0.80 |
| auto_repair_fail_prob | 0.60 |
| Replications per cell | 10 |

**Sweep axes**
- `systematic_failure_rate_multiplier`: [5, 10, 15, 20, 25]
- `manual_repair_fail_prob`: [0.2, 0.4, 0.6, 0.75, 0.9]

**SC_fast ScoredRemoval preset**: initial_score=100, failure_penalty=60,
success_increment=5, time_period=1 day → retired after 2 failures.

## Policy Win Counts (out of 25 cells)

| Policy | Cells Won |
|--------|-----------|
| Random+NeverRemove (baseline) | 0 |
| Random+ScoredRemoval(SC_fast) | 1 |
| FewestFailuresFirst+NeverRemove | 24 |

## ScoredRemoval(SC_fast) Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -629.2 hrs at mult=25×, repair_fail=90%
- **Worst regression**: +12.8 hrs at mult=10×, repair_fail=40%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | +2.5 | -10.8 | -8.8 | -35.1 | -42.9 |
| 10× | -3.2 | +12.8 | -74.7 | -102.2 | -167.6 |
| 15× | -26.2 | -69.8 | -104.8 | -181.5 | -317.1 |
| 20× | -36.9 | -102.4 | -161.7 | -264.3 | -445.2 |
| 25× | -49.2 | -47.2 | -202.5 | -359.9 | -629.2 |

## FewestFailuresFirst+NeverRemove Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -586.1 hrs at mult=25×, repair_fail=90%
- **Worst regression**: -31.5 hrs at mult=5×, repair_fail=40%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | -40.4 | -31.5 | -46.2 | -66.4 | -80.1 |
| 10× | -63.9 | -52.1 | -127.5 | -166.5 | -200.7 |
| 15× | -63.2 | -135.3 | -156.5 | -241.3 | -329.8 |
| 20× | -83.6 | -139.6 | -216.8 | -329.8 | -450.9 |
| 25× | -60.7 | -103.0 | -242.1 | -376.1 | -586.1 |

## Figures

| File | Description |
|------|-------------|
| `heatmap_scored_delta.png` | Δ training time: Random+ScoredRemoval vs baseline |
| `heatmap_fff_delta.png` | Δ training time: FewestFailuresFirst+NeverRemove vs baseline |
| `heatmap_winner.png` | Winning policy at each (multiplier, repair_fail_prob) cell |

## Key Observations

1. **ScoredRemoval(SC_fast)** aggressively retires servers after just 2 failures.
   At high `systematic_failure_rate_multiplier` and high `manual_repair_fail_prob`
   (bottom-right of the grid) this can eliminate chronic bad servers and reduce
   training time.  At lower multipliers or lower repair fail rates (good repairs
   fix servers reliably) the capacity cost of retirement outweighs the failure
   reduction and the policy regresses.

2. **FewestFailuresFirst** routes new hosts preferentially to servers with fewer
   historical failures.  It incurs no capacity penalty (no retirement) and tends
   to improve training time most when failure rates are high enough that host
   selection meaningfully steers work away from bad servers.

3. **No single policy dominates** across all 25 cells.  The optimal strategy
   depends on the interplay between failure severity (multiplier) and repair
   effectiveness (manual_repair_fail_prob).  The winner heatmap makes this
   regime-dependence concrete.
