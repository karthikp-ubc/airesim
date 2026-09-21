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
| Random+ScoredRemoval(SC_fast) | 12 |
| FewestFailuresFirst+NeverRemove | 13 |

## ScoredRemoval(SC_fast) Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -671.0 hrs at mult=25×, repair_fail=90%
- **Worst regression**: +16.9 hrs at mult=5×, repair_fail=40%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | -14.3 | +16.9 | -22.2 | -30.8 | -25.1 |
| 10× | -15.2 | -15.9 | -64.8 | -106.7 | -185.8 |
| 15× | -9.7 | -72.6 | -116.9 | -246.3 | -305.6 |
| 20× | -34.3 | -73.3 | -187.6 | -308.9 | -488.6 |
| 25× | -17.3 | -81.6 | -211.1 | -378.5 | -671.0 |

## FewestFailuresFirst+NeverRemove Delta vs Baseline

Negative values indicate the policy finished training faster than baseline.

- **Best improvement**: -536.0 hrs at mult=25×, repair_fail=90%
- **Worst regression**: -9.3 hrs at mult=20×, repair_fail=20%

### Delta Table (hrs, negative = faster)

| mult↓ / fail_prob→ | 20% | 40% | 60% | 75% | 90% |
|--------|--------|--------|--------|--------|--------|
| 5× | -9.4 | -34.5 | -58.4 | -41.4 | -63.8 |
| 10× | -31.6 | -63.0 | -93.7 | -133.4 | -198.6 |
| 15× | -33.1 | -79.6 | -120.2 | -223.7 | -278.6 |
| 20× | -9.3 | -72.9 | -163.5 | -266.4 | -395.6 |
| 25× | -35.3 | -71.3 | -184.0 | -289.9 | -536.0 |

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
