# AIReSim — AI Cluster Reliability Simulator

A discrete-event simulator for modeling reliability, failure recovery, scheduling,
and repair processes in large-scale AI training clusters.

Built on [SimPy](https://simpy.readthedocs.io/), AIReSim lets you explore how
different knobs — spare capacity, repair pipelines, warm standbys, failure rates,
scheduling policies, and diagnosis quality — affect end-to-end training time and
cluster utilization.

## Quick Start

```bash
pip install simpy matplotlib numpy
python -m airesim.run examples/paper_table1_sweep.py
```

## Running the Tests

```bash
pip install pytest
pytest tests/
```

79 tests across 5 test modules, all passing.

| Test file | What it covers |
|-----------|---------------|
| `tests/test_airesim.py` | Core params, server state machine, coordinator, pool, scheduler, full simulation, sweeps, failure distributions |
| `tests/test_edge_cases.py` | Race-condition fixes: warm-standby callback, misdiagnosis double-submit, missed-signal event |
| `tests/test_scored_removal.py` | `ScoredRemoval` score arithmetic, retirement thresholds, snapshot, integration |
| `tests/test_scheduling_policies.py` | `HighestScoreFirst` ordering, untracked servers, reset, integration with `ScoredRemoval` |
| `tests/test_diagnosis_probability.py` | `diagnosis_probability` and `diagnosis_uncertainty` parameter validation and simulation behaviour; floating-server and duplication bug regressions |

## File Structure

```
airesim/
├── params.py               # Params dataclass — every simulation knob
├── server.py               # Server entity: state machine, failure history
├── coordinator.py          # Failure engine: samples next failure, drives job clock
├── scheduler.py            # Host selection and warm-standby management
├── repairs.py              # Automated + manual repair pipeline (SimPy processes)
├── pool.py                 # Working pool / spare pool bookkeeping
├── scheduling_policies.py  # HostSelectionPolicy ABC + DefaultHostSelection,
│                           #   FewestFailuresFirst, HighestScoreFirst
├── policies.py             # RepairEscalationPolicy + ServerRemovalPolicy ABCs;
│                           #   NeverRemove, ThresholdRemoval, ScoredRemoval,
│                           #   CompositeRemovalPolicy; re-exports scheduling_policies
├── simulator.py            # Top-level DES orchestrator — wires everything together
├── stats.py                # StatsCollector (per-run) and AggregateStats (multi-rep)
├── sweep.py                # OneWaySweep / TwoWaySweep parameter sweep drivers
├── plotting.py             # Matplotlib chart helpers (optional dependency)
├── run.py                  # CLI entry point  (python -m airesim.run)
└── __init__.py

tests/
├── test_airesim.py                 # Core simulation tests (23 cases)
├── test_edge_cases.py              # Race-condition / bug-regression tests (5 cases)
├── test_scored_removal.py          # ScoredRemoval unit + integration tests (22 cases)
├── test_scheduling_policies.py     # HighestScoreFirst tests (9 cases)
└── test_diagnosis_probability.py   # Diagnosis parameter tests (20 cases)

examples/
├── paper_table1_sweep.py       # Reproduce Table 1 from the paper
├── retirement_payoff.py        # Regime analysis for retirement policies
├── retirement_sweep.py         # ThresholdRemoval / ScoredRemoval sensitivity
├── scored_vs_threshold.py      # Head-to-head comparison
├── threshold_sensitivity.py    # Seven-parameter crossover analysis
├── scoring_sweep.py            # ScoredRemoval hyperparameter grid
├── scheduling_comparison.py    # 3×3 scheduling × retirement policy experiment
├── diagnosis_sweep.py          # Diagnosis probability/uncertainty parameter sweep
├── stress_scenario.py          # High-load stress test
└── generate_paper_figures.py   # All paper figures in one run

docs/
├── ARCHITECTURE.md             # This file's companion: module-by-module reference
├── TUTORIAL.md                 # Step-by-step guide for new users
├── RETIREMENT_POLICY_REPORT.md # Retirement policy payoff analysis
├── THRESHOLD_SENSITIVITY_REPORT.md  # ThresholdRemoval crossover analysis
├── SCHEDULING_COMPARISON_REPORT.md  # Scheduling × retirement 3×3 experiment
└── DIAGNOSIS_SWEEP_REPORT.md   # Diagnosis quality parameter sweep report
```

## Parameters

See `airesim/params.py` for the full list. Key inputs:

**Cluster topology**
- `working_pool_size`, `spare_pool_size` — pool sizes
- `job_size`, `warm_standbys` — job footprint and standby reserve

**Failure model**
- `random_failure_rate` — baseline failures per minute per server
- `systematic_failure_fraction`, `systematic_failure_rate_multiplier` — fraction of "bad" servers and their rate multiplier
- Weibull / lognormal failure distributions via `failure_distribution`, `weibull_shape`, `lognormal_sigma`

**Repair pipeline**
- `recovery_time` — checkpoint reload time after any failure
- `auto_repair_time`, `manual_repair_time` — mean repair durations
- `prob_auto_to_manual`, `auto_repair_fail_prob`, `manual_repair_fail_prob` — pipeline probabilities

**Diagnosis quality** *(both in [0, 1])*
- `diagnosis_probability` — P(failure triggers a repair attempt on any server). At 0, every failure goes undiagnosed: the failed server auto-recovers without entering the repair pipeline.
- `diagnosis_uncertainty` — P(wrong server blamed | failure diagnosed). At 1, every repair is sent to a randomly chosen innocent server while the actual bad server escapes.

**Timing**
- `host_selection_time`, `preemption_wait_time` — overhead costs
- `job_length`, `num_replications`, `seed`

## Pluggable Policies

All three policy types are injected into `Simulator` at construction time:

### Host-selection policies  (`scheduling_policies.py`)

| Class | Behaviour |
|-------|-----------|
| `DefaultHostSelection` | Uniform random (default) |
| `FewestFailuresFirst` | Prefer servers with the fewest cumulative failures |
| `HighestScoreFirst` | Prefer servers with the highest `ScoredRemoval` score |

### Server-removal (retirement) policies  (`policies.py`)

| Class | Behaviour |
|-------|-----------|
| `NeverRemove` | Always reintegrate after repair (default) |
| `ThresholdRemoval(max_failures, window_minutes)` | Retire if failures in rolling window ≥ threshold |
| `ScoredRemoval(initial_score, failure_penalty, ...)` | Retire when score drops below threshold; score = initial − penalties + credits |
| `CompositeRemovalPolicy(primary, secondary)` | Fan-out hooks to two policies; delegates `should_remove` to primary |

### Repair-escalation policies  (`policies.py`)

| Class | Behaviour |
|-------|-----------|
| `DefaultRepairEscalation(prob_escalate)` | Fixed probability of escalating to manual repair (default) |

### Custom policy example

```python
from airesim.scheduling_policies import HostSelectionPolicy
from airesim.policies import ScoredRemoval, CompositeRemovalPolicy
from airesim.simulator import Simulator
from airesim.params import Params

# Pair HighestScoreFirst scheduling with ThresholdRemoval retirement
from airesim.scheduling_policies import HighestScoreFirst
from airesim.policies import ThresholdRemoval

scorer = ScoredRemoval(
    initial_score=100.0, failure_penalty=60.0,
    retirement_threshold=float('-inf'),   # scores-only, never retires
)
policy = CompositeRemovalPolicy(
    primary=ThresholdRemoval(max_failures=2, window_minutes=7*24*60),
    secondary=scorer,
)
sim = Simulator(
    params=Params(),
    host_selection_policy=HighestScoreFirst(scorer),
    removal_policy=policy,
)
result = sim.run()
```

## Running Parameter Sweeps

```python
from airesim.sweep import OneWaySweep
from airesim.params import Params

sweep = OneWaySweep(
    param_name="recovery_time",
    values=[10, 20, 30],
    base_params=Params(),
    num_replications=30,
)
results = sweep.run()
results.summary()
```

## Outputs

Per simulation run (`StatsCollector`):

- `total_training_time` — wall-clock simulated time to job completion (minutes)
- `total_compute_time`, `total_recovery_time`, `total_host_selection_time`
- `auto_repairs`, `manual_repairs`, `successful_repairs`, `failed_repairs`
- `servers_retired`, `cluster_depleted`
- `job_stall_count`, `host_selection_count`
- `preemption_count`

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a module-by-module reference
including design decisions and data-flow diagrams.

Key design decisions at a glance:

| Decision | Rationale |
|---|---|
| **Pluggable policies** | Host-selection, repair-escalation, and server-removal are injected strategy objects — swap in custom logic without touching the core |
| **`scheduling_policies.py` split** | Keeps scheduling and retirement concerns in separate files; `policies.py` re-exports for backward compatibility |
| **Aggregated failure sampling** | Exponential TTFs use the min-of-exponentials shortcut (two RNG calls instead of N SimPy processes) — critical for 4 000+ server simulations |
| **Dataclass params** | All parameters in one `Params` dataclass; `with_overrides()` creates isolated copies for sweep replications |
| **Deterministic seeding** | Every run uses an explicit seed; `seed + rep` gives independent, reproducible replications |
| **Missed-signal-safe event** | The stall-wait event is owned by the main loop (checked before yield, replaced after wake) to avoid a race where repairs fire while the loop is running |
| **Floating-server fix** | Escaped bad servers (misdiagnosis) are explicitly returned to `working_pool`; `on_server_returned` is not called (server is still in `active_servers`) to prevent duplication |

## License

MIT

## Citation

If you use AIReSim in your research, please cite:

```bibtex
@article{airesim2026,
  title={AIReSim: A Discrete Event Simulator for Large-scale AI Cluster Reliability Modeling},
  author={Pattabiraman, Karthik and Patel, Mihir and Lin, Fred},
  journal={arXiv preprint arXiv:2603.07041},
  year={2026}
}
```
