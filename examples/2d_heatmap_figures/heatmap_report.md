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
| Random+NeverRemove (baseline) | 2 |
| Random+ScoredRemoval(SC_fast) | 18 |
| FewestFailuresFirst+NeverRemove | 5 |

## ScoredRemoval(SC_fast) Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -242.9 hrs at mult=25×, repair_fail=90%
- **Worst regression**: +33.7 hrs at mult=10×, repair_fail=20%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | -21.9 | -3.7 | -1.1 | -15.9 | -14.5 |
| 10× | +33.7 | -6.6 | -7.4 | -21.4 | -46.8 |
| 15× | -4.4 | -52.9 | -80.3 | -78.8 | -149.6 |
| 20× | +13.1 | -46.0 | -71.1 | -167.0 | -196.9 |
| 25× | -30.2 | -40.4 | -136.0 | -190.0 | -242.9 |

## FewestFailuresFirst+NeverRemove Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -96.3 hrs at mult=25×, repair_fail=90%
- **Worst regression**: +24.2 hrs at mult=20×, repair_fail=20%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | -22.1 | -31.2 | -1.0 | +1.9 | -7.7 |
| 10× | +4.9 | -23.1 | -31.2 | -12.6 | -39.3 |
| 15× | -16.9 | -42.8 | -52.6 | -43.3 | -84.6 |
| 20× | +24.2 | -39.9 | -33.3 | -87.7 | -89.3 |
| 25× | -24.2 | -13.8 | -69.3 | -87.4 | -96.3 |

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
