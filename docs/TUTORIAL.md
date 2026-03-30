# AIReSim Tutorial

This tutorial walks through common use cases, from a single simulation run to
custom scheduling policies, server retirement, and diagnosis quality modelling.
Every code snippet is runnable from the repository root.

---

## 1. Running a Basic Single Simulation

The lowest-level entry point is `Simulator`.  Construct it with a `Params` object,
call `.run()`, and inspect the returned `StatsCollector`.

```python
from airesim.params import Params
from airesim.simulator import Simulator

params = Params(
    job_size=64,
    warm_standbys=8,
    working_pool_size=80,
    spare_pool_size=16,
    job_length=60 * 24 * 60,   # 60 days in minutes
    seed=42,
)

sim = Simulator(params, seed=42)
stats = sim.run()

print(f"Training time : {stats.training_time_hours:.1f} hrs")
print(f"Total failures: {stats.total_failures}")
print(f"Auto repairs  : {stats.auto_repairs}")
print(f"Manual repairs: {stats.manual_repairs}")
print(f"Servers retired: {stats.servers_retired}")
print(f"Job stalls    : {stats.job_stall_count}")
```

`stats.summary_dict()` returns every metric as a flat dict, useful for logging:

```python
import json
print(json.dumps(stats.summary_dict(), indent=2))
```

### Key `Params` fields

| Field | Default | Meaning |
|---|---|---|
| `job_size` | 4096 | Primary servers required to run the job |
| `warm_standbys` | 16 | Hot-spare servers kept ready for instant swap |
| `working_pool_size` | 4160 | Total servers in the working pool |
| `spare_pool_size` | 200 | Cold spares (preemption required to use) |
| `random_failure_rate` | ~6.9e-7 / min | Per-server random failure rate |
| `recovery_time` | 20 min | Time to reload checkpoint after a failure |
| `diagnosis_probability` | 1.0 | P(failure triggers a repair attempt on any server) |
| `diagnosis_uncertainty` | 0.0 | P(wrong server blamed \| failure diagnosed) |
| `seed` | 0 | RNG seed for reproducibility |

---

## 2. Running a One-Way Parameter Sweep

`OneWaySweep` runs multiple independent replications across a list of values for a
single parameter and returns an `AggregateStats` per value.

```python
from airesim.params import Params
from airesim.sweep import OneWaySweep

base = Params(
    job_size=64,
    warm_standbys=8,
    working_pool_size=80,
    spare_pool_size=16,
    job_length=60 * 24 * 60,
    seed=42,
)

sweep = OneWaySweep(
    param_name="recovery_time",
    values=[5, 10, 20, 40],
    base_params=base,
    num_replications=10,   # increase for tighter confidence intervals
)

result = sweep.run(verbose=True)
result.summary()
```

The printed table shows `mean ± stdev` training time and failure count per value.
To write results to CSV:

```python
from pathlib import Path
Path("recovery_sweep.csv").write_text(result.to_csv())
```

### From the command line

The same sweep runs without any Python script:

```bash
python -m airesim.run \
    --sweep recovery_time \
    --values 5,10,20,40 \
    --replications 10 \
    --output recovery_sweep.csv
```

Pass `--params config.json` to override base parameters from a JSON file:

```json
{
  "job_size": 64,
  "warm_standbys": 8,
  "working_pool_size": 80,
  "spare_pool_size": 16,
  "job_length": 86400,
  "seed": 42
}
```

```bash
python -m airesim.run \
    --params config.json \
    --sweep recovery_time \
    --values 5,10,20,40 \
    --output recovery_sweep.csv
```

---

## 3. Scheduling Policies

The scheduling policy decides which servers are assigned to the job at each host
selection.  All built-in policies live in `airesim.scheduling_policies`; they are
also re-exported from `airesim.policies` for backward compatibility.

### Built-in policies

```python
from airesim.scheduling_policies import (
    DefaultHostSelection,   # uniform random (default)
    FewestFailuresFirst,    # prefer servers with fewest cumulative failures
    HighestScoreFirst,      # prefer servers with highest ScoredRemoval score
)
from airesim.simulator import Simulator
from airesim.params import Params

params = Params(
    job_size=64, warm_standbys=8,
    working_pool_size=80, spare_pool_size=16,
    job_length=60 * 24 * 60,
    systematic_failure_fraction=0.1,
    systematic_failure_rate_multiplier=10.0,
    seed=42,
)

# FewestFailuresFirst: deprioritises servers that have failed often
sim = Simulator(params, seed=42, host_selection_policy=FewestFailuresFirst())
stats = sim.run()
print(f"FewestFailuresFirst: {stats.training_time_hours:.1f} hrs")
```

`FewestFailuresFirst` uses `server.total_failure_count` — the server's actual
hardware failure count — regardless of how failures were diagnosed.  This makes it
robust even under high `diagnosis_uncertainty`.

`HighestScoreFirst` requires a `ScoredRemoval` instance (see §4) and sorts by
descending score:

```python
from airesim.policies import ScoredRemoval
from airesim.scheduling_policies import HighestScoreFirst

scorer = ScoredRemoval(
    initial_score=100.0,
    failure_penalty=60.0,
    success_increment=10.0,
    time_period=24 * 60,       # 1 day
    retirement_threshold=0.0,  # retire when score ≤ 0
)
sim = Simulator(params, seed=42,
                host_selection_policy=HighestScoreFirst(scorer),
                removal_policy=scorer)
stats = sim.run()
```

> **Note:** At large cluster scale with short job chunks (mean chunk ≪ `time_period`),
> `HighestScoreFirst` and `FewestFailuresFirst` produce identical server orderings
> because no uptime credits are ever awarded and score reduces to a linear function
> of failure count.

### Writing a custom scheduling policy

Subclass `HostSelectionPolicy` and implement `select`:

```python
import random
from airesim.scheduling_policies import HostSelectionPolicy

class HealthiestFirst(HostSelectionPolicy):
    """Pick servers with the fewest failures in the last 7 days."""

    WINDOW = 7 * 24 * 60  # 7 days in minutes

    def select(self, available_servers, job_size: int, warm_standbys: int,
               rng: random.Random):
        needed = job_size + warm_standbys
        ranked = sorted(
            available_servers,
            key=lambda s: (s.failures_in_window(self.WINDOW), rng.random()),
        )
        return ranked[:needed]

sim = Simulator(params, seed=42, host_selection_policy=HealthiestFirst())
stats = sim.run()
print(f"HealthiestFirst: {stats.training_time_hours:.1f} hrs")
```

### Using a custom policy in a sweep

```python
from airesim.sweep import OneWaySweep

sweep = OneWaySweep(
    param_name="recovery_time",
    values=[5, 20, 40],
    base_params=params,
    num_replications=10,
    host_selection_policy=HealthiestFirst(),
)
result = sweep.run()
result.summary()
```

---

## 4. Server Retirement Policies

Retirement policies decide whether a server that has just completed repair should
be returned to the pool or permanently retired.  All are in `airesim.policies`.

### `ThresholdRemoval` — retire based on failure rate

Retire a server if it has had ≥ `max_failures` failures in the most recent
`window_minutes` of simulated time:

```python
from airesim.policies import ThresholdRemoval
from airesim.simulator import Simulator

removal = ThresholdRemoval(
    max_failures=2,
    window_minutes=7 * 24 * 60,   # 7-day rolling window
)

sim = Simulator(params, seed=42, removal_policy=removal)
stats = sim.run()
print(f"Servers retired: {stats.servers_retired}")
print(f"Training time  : {stats.training_time_hours:.1f} hrs")
```

`ThresholdRemoval` reads `server.failures_in_window()`, which counts actual hardware
failures regardless of whether they were diagnosed.  This gives it partial
effectiveness even at lower `diagnosis_probability` values.

### `ScoredRemoval` — retire based on a running score

Each server starts at `initial_score`.  Every failure deducts `failure_penalty`;
every successful run of at least `time_period` minutes adds `success_increment`.
A server is retired when its score falls to or below `retirement_threshold`:

```python
from airesim.policies import ScoredRemoval

removal = ScoredRemoval(
    initial_score=100.0,
    failure_penalty=60.0,
    success_increment=10.0,
    time_period=24 * 60,       # earn credit per full day of uptime
    retirement_threshold=0.0,  # retire when score hits 0
)

sim = Simulator(params, seed=42, removal_policy=removal)
stats = sim.run()
print(f"Servers retired: {stats.servers_retired}")

# Inspect final scores
for server_id, score in removal.scores_snapshot().items():
    if score < 40:
        print(f"  Server {server_id}: score={score:.1f}")
```

`ScoredRemoval` requires diagnosed failures to work: `on_failure` is only called for
the server that was *blamed* (which may be an innocent server under misdiagnosis).
At high `diagnosis_uncertainty` (≥ 0.6) it can become counter-productive — see §5.

### `CompositeRemovalPolicy` — combine scheduling scores with a separate retirement policy

To use `HighestScoreFirst` scheduling while retiring servers by threshold (rather
than by score), wire a shared `ScoredRemoval` scorer through a composite:

```python
from airesim.policies import ScoredRemoval, CompositeRemovalPolicy, ThresholdRemoval
from airesim.scheduling_policies import HighestScoreFirst

scorer = ScoredRemoval(
    initial_score=100.0,
    failure_penalty=60.0,
    success_increment=10.0,
    time_period=24 * 60,
    retirement_threshold=float('-inf'),  # never retires — scores only
)
retirement = ThresholdRemoval(max_failures=2, window_minutes=7 * 24 * 60)

policy = CompositeRemovalPolicy(primary=retirement, secondary=scorer)

sim = Simulator(
    params, seed=42,
    host_selection_policy=HighestScoreFirst(scorer),
    removal_policy=policy,
)
stats = sim.run()
```

`CompositeRemovalPolicy` fans out `on_failure`, `on_success`, and `reset` to both
policies, but delegates `should_remove` to the primary (`retirement`) only.

---

## 5. Modelling Diagnosis Quality

Two parameters control how accurately failures are attributed:

| Parameter | Meaning | Effect at extreme values |
|-----------|---------|--------------------------|
| `diagnosis_probability` | P(failure triggers any repair attempt) | At 0: failed server auto-recovers; repair pipeline never entered |
| `diagnosis_uncertainty` | P(wrong server blamed \| diagnosed) | At 1: innocent server always sent to repair; bad server always escapes |

### Missed diagnoses (`diagnosis_probability < 1`)

When a failure goes undiagnosed, the failed server is immediately returned to the
working pool (auto-recovery) and the job pays only `recovery_time` to reload its
checkpoint.  No server enters the repair pipeline.

```python
params_low_diag = Params(
    job_size=64, warm_standbys=8,
    working_pool_size=80, spare_pool_size=16,
    job_length=60 * 24 * 60,
    systematic_failure_fraction=0.1,
    systematic_failure_rate_multiplier=10.0,
    diagnosis_probability=0.5,   # only half of failures trigger repair
    diagnosis_uncertainty=0.0,
    seed=42,
)

sim = Simulator(params_low_diag, seed=42)
stats = sim.run()
print(f"Training time (prob=0.5): {stats.training_time_hours:.1f} hrs")
print(f"Auto repairs: {stats.auto_repairs}")  # ~half of full-diagnosis count
```

**Guidance:**
- Below `diagnosis_probability ≈ 0.40`, retirement policies give no net benefit.
- `ThresholdRemoval` has partial immunity: it reads `failure_timestamps` (actual
  hardware failures) regardless of diagnosis outcome, so it can retire bad servers on
  the first repair entry that does occur.
- `ScoredRemoval` is fully blind to missed failures; it requires `probability ≥ 0.60`
  to start paying off.

### Misattribution (`diagnosis_uncertainty > 0`)

When a failure is misattributed, an innocent server is sent to repair and the actual
bad server is returned to the pool and continues running.

```python
params_uncertain = Params(
    job_size=64, warm_standbys=8,
    working_pool_size=80, spare_pool_size=16,
    job_length=60 * 24 * 60,
    systematic_failure_fraction=0.1,
    systematic_failure_rate_multiplier=10.0,
    diagnosis_probability=1.0,
    diagnosis_uncertainty=0.2,   # 20% of repairs sent to wrong server
    seed=42,
)

sim = Simulator(params_uncertain, seed=42)
stats = sim.run()
print(f"Training time (unc=0.2): {stats.training_time_hours:.1f} hrs")
```

**Guidance by uncertainty level:**

| `diagnosis_uncertainty` | Recommended policy | Notes |
|------------------------|--------------------|-------|
| 0.00 | `Random + ScoredRemoval` | Optimal: ~−160 h vs. no-retirement baseline |
| ≤ 0.20 | `FewestFail + ScoredRemoval` | ~−105 h, low variance |
| 0.20–0.60 | `FewestFail + ScoredRemoval` or `FewestFail + ThresholdRemoval` | ScoredRemoval near-breakeven at 0.60 |
| ≥ 0.60 | `FewestFailuresFirst + NeverRemove` | No retirement policy gives net benefit; scheduling alone helps |
| = 1.00 | **Avoid ScoredRemoval** | Retires innocent servers, keeps bad ones — actively harmful |

> **Why `FewestFailuresFirst` helps at high uncertainty:** It sorts by
> `server.total_failure_count`, which counts *actual* hardware failures regardless of
> misattribution.  Bad servers accumulate real failure counts quickly, so
> `FewestFailuresFirst` deprioritises them even when their failures are attributed to
> innocent servers.

---

## 6. Interpreting the Sensitivity Summary

A sensitivity analysis runs one-way sweeps over many parameters and ranks them by
the *range* of the mean metric (max mean − min mean across swept values).  A large
range means the simulator outcome is highly sensitive to that parameter.

### Running the analysis

```python
from airesim.params import Params
from airesim.sweep import OneWaySweep
from airesim.plotting import sensitivity_summary, print_sensitivity_table

base = Params(
    job_size=64,
    warm_standbys=8,
    working_pool_size=80,
    spare_pool_size=16,
    job_length=60 * 24 * 60,
    seed=42,
)

PARAMS_TO_SWEEP = [
    ("recovery_time",        [5, 20, 40]),
    ("preemption_wait_time", [5, 20, 40]),
    ("warm_standbys",        [2, 8, 16]),
    ("auto_repair_time",     [60, 120, 240]),
    ("manual_repair_time",   [720, 2880, 5760]),
    ("diagnosis_probability",[0.4, 0.7, 1.0]),
    ("diagnosis_uncertainty",[0.0, 0.2, 0.4]),
]

one_way_results = {}
for param_name, values in PARAMS_TO_SWEEP:
    sweep = OneWaySweep(
        param_name=param_name,
        values=values,
        base_params=base,
        num_replications=10,
    )
    one_way_results[param_name] = sweep.run(verbose=False)

rows = sensitivity_summary(one_way_results, metric="training_time_hrs")
print_sensitivity_table(rows)
```

### Reading the output

```
Parameter                           Min        Max      Range   Impact
------------------------------------------------------------------------------
manual_repair_time                  820.3     1640.5     820.2     high
diagnosis_probability               900.1     1250.8     350.7     high
recovery_time                       900.1     1050.8     150.7   medium
diagnosis_uncertainty               960.0     1080.0     120.0   medium
auto_repair_time                    940.2      980.3      40.1      low
preemption_wait_time                960.0      970.0      10.0      low
warm_standbys                       960.5      961.0       0.5     none
```

- **Range** — the headline number.  Larger means more leverage over training time.
- **Min / Max** — the mean training time at the lowest and highest swept value.
  Check which end of the parameter range produces the worse outcome.
- **Impact classification**
  - `high`   — range > 20 % of the max mean
  - `medium` — range 5–20 % of the max mean
  - `low`    — range < 5 % of the max mean
  - `none`   — effectively zero range

### Generating a tornado chart

```python
import statistics
from airesim.simulator import Simulator
from airesim.plotting import plot_tornado_chart

baseline_runs = [
    Simulator(base, seed=base.seed + i).run().training_time_hours
    for i in range(10)
]
baseline = statistics.mean(baseline_runs)

plot_tornado_chart(
    rows,
    baseline=baseline,
    title="Sensitivity Tornado",
    save_path="tornado.png",
)
```

The chart draws a horizontal bar for each parameter spanning from its minimum to
maximum mean training time.  The dashed vertical line marks the baseline (all
parameters at their mid values).  Parameters are sorted so the highest-impact one
appears at the top.

---

## 7. Policy Comparison Recipe

A common pattern is running the same base scenario across all combinations of
scheduling and retirement policies to find the best pairing.

```python
from itertools import product
from airesim.params import Params
from airesim.simulator import Simulator
from airesim.scheduling_policies import DefaultHostSelection, FewestFailuresFirst
from airesim.policies import NeverRemove, ThresholdRemoval, ScoredRemoval
import statistics

params = Params(
    job_size=64, warm_standbys=8,
    working_pool_size=80, spare_pool_size=16,
    job_length=60 * 24 * 60,
    systematic_failure_fraction=0.08,
    systematic_failure_rate_multiplier=20.0,
    auto_repair_fail_prob=0.60,
    manual_repair_fail_prob=0.75,
    seed=42,
)

N_REPS = 5

def run_policy(sched_factory, retire_factory, params, n_reps):
    times = []
    for rep in range(n_reps):
        sim = Simulator(params,
                        host_selection_policy=sched_factory(),
                        removal_policy=retire_factory(),
                        seed=params.seed + rep)
        times.append(sim.run().training_time_hours)
    return statistics.mean(times), statistics.stdev(times)

combos = [
    ("Random",       "NeverRemove",  DefaultHostSelection, NeverRemove),
    ("Random",       "Threshold",    DefaultHostSelection,
     lambda: ThresholdRemoval(max_failures=2, window_minutes=7*24*60)),
    ("Random",       "Scored",       DefaultHostSelection,
     lambda: ScoredRemoval(100.0, 60.0, 10.0, 24*60, 0.0)),
    ("FewestFail",   "NeverRemove",  FewestFailuresFirst,  NeverRemove),
    ("FewestFail",   "Threshold",    FewestFailuresFirst,
     lambda: ThresholdRemoval(max_failures=2, window_minutes=7*24*60)),
    ("FewestFail",   "Scored",       FewestFailuresFirst,
     lambda: ScoredRemoval(100.0, 60.0, 10.0, 24*60, 0.0)),
]

print(f"{'Scheduling':<14} {'Retirement':<12}  {'Mean (h)':>9}  {'Std':>6}")
print("-" * 48)
for sched_label, retire_label, sched_f, retire_f in combos:
    mean, std = run_policy(sched_f, retire_f, params, N_REPS)
    print(f"{sched_label:<14} {retire_label:<12}  {mean:>8.1f}h  {std:>5.1f}")
```
