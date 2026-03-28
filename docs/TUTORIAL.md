# AIReSim Tutorial

This tutorial walks through four common use cases, from a single simulation run to
interpreting a full sensitivity analysis.  Every code snippet is runnable from the
repository root.

---

## 1. Running a Basic Single Simulation

The lowest-level entry point is `Simulator`.  Construct it with a `Params` object,
call `.run()`, and inspect the returned `StatsCollector`.

```python
from airesim.params import Params
from airesim.simulator import Simulator

# Use defaults — a 4 096-node job with sensible failure / repair rates.
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
| `recovery_time` | 20 min | Time to swap in a standby after a failure |
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

## 3. Creating a Custom Host Selection Policy

`HostSelectionPolicy` is an abstract base class.  Subclass it and pass an instance
to `Simulator` (or to a sweep) to replace the default random selection.

### Example: prefer servers that haven't failed recently

```python
import random
from airesim.policies import HostSelectionPolicy
from airesim.params import Params
from airesim.simulator import Simulator


class HealthiestFirst(HostSelectionPolicy):
    """Pick servers with the fewest failures in the last 7 days."""

    WINDOW = 7 * 24 * 60  # 7 days in minutes

    def select(
        self,
        available_servers,
        job_size: int,
        warm_standbys: int,
        rng: random.Random,
    ):
        needed = job_size + warm_standbys
        # Sort by recent failures ascending, break ties with a random tiebreak.
        ranked = sorted(
            available_servers,
            key=lambda s: (s.failures_in_window(self.WINDOW), rng.random()),
        )
        return ranked[:needed]


params = Params(
    job_size=64,
    warm_standbys=8,
    working_pool_size=80,
    spare_pool_size=16,
    job_length=60 * 24 * 60,
    seed=42,
)

sim = Simulator(params, seed=42, host_selection_policy=HealthiestFirst())
stats = sim.run()
print(f"Training time with HealthiestFirst: {stats.training_time_hours:.1f} hrs")
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

### Other pluggable policies

| Base class | Purpose | Defaults |
|---|---|---|
| `HostSelectionPolicy` | Choose which servers run the job | `DefaultHostSelection` (random) |
| `RepairEscalationPolicy` | Decide when auto → manual repair | `DefaultRepairEscalation` (80 % escalation) |
| `ServerRemovalPolicy` | Retire chronically failing servers | `NeverRemove` |

---

## 4. Interpreting the Sensitivity Summary

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
recovery_time                       900.1     1050.8     150.7   medium
auto_repair_time                    940.2      980.3      40.1      low
preemption_wait_time                960.0      970.0      10.0      low
warm_standbys                       960.5      961.0       0.5     none
```

- **Range** — the headline number.  Larger means more leverage over training time.
- **Min / Max** — the mean training time at the lowest and highest swept value.
  Check whether a high Max comes from the low end or high end of the parameter
  range; that tells you the direction of the effect.
- **Impact classification**
  - `high`   — range > 20 % of the max mean
  - `medium` — range 5–20 % of the max mean
  - `low`    — range < 5 % of the max mean
  - `none`   — effectively zero range

### Generating a tornado chart

```python
from airesim.simulator import Simulator
import statistics
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
