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
| Random+NeverRemove (baseline) | 5 |
| Random+ScoredRemoval(SC_fast) | 8 |
| FewestFailuresFirst+NeverRemove | 12 |

## ScoredRemoval(SC_fast) Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -179.1 hrs at mult=20×, repair_fail=90%
- **Worst regression**: +19.1 hrs at mult=20×, repair_fail=20%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | -22.0 | -7.2 | +15.4 | -3.4 | +6.1 |
| 10× | +6.7 | +13.2 | -14.7 | -28.1 | -48.8 |
| 15× | +18.2 | -23.9 | -42.5 | -64.8 | -90.3 |
| 20× | +19.1 | -25.0 | -53.3 | -86.8 | -179.1 |
| 25× | -7.3 | -21.7 | -95.7 | -123.2 | -177.6 |

## FewestFailuresFirst+NeverRemove Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -124.4 hrs at mult=20×, repair_fail=90%
- **Worst regression**: +27.2 hrs at mult=10×, repair_fail=20%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | -5.7 | -17.0 | +17.5 | -11.1 | +8.2 |
| 10× | +27.2 | -17.7 | -73.3 | -26.2 | -69.6 |
| 15× | +0.3 | -43.0 | -44.9 | -87.4 | -97.9 |
| 20× | +0.7 | -19.4 | -63.4 | -70.0 | -124.4 |
| 25× | -15.8 | -41.5 | -78.7 | -63.0 | -108.0 |

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
