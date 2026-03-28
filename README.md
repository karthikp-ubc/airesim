# AIReSim — AI Cluster Reliability Simulator

A discrete-event simulator for modeling reliability, failure recovery, scheduling,
and repair processes in large-scale AI training clusters.

Built on [SimPy](https://simpy.readthedocs.io/), AIReSim lets you explore how
different knobs — spare capacity, repair pipelines, warm standbys, failure rates —
affect end-to-end training time and cluster utilization.

## Quick Start

```bash
pip install simpy
python -m airesim.run examples/paper_table1_sweep.py
```

## Running the Tests

```bash
python3 tests/test_airesim.py      # core tests (20 cases)
python3 tests/test_edge_cases.py   # edge-case / bug-regression tests (5 cases)
```

## Architecture

```
airesim/
├── params.py          # Parameter dataclass with defaults
├── server.py          # Server entity: failure process, state machine
├── coordinator.py     # Coordinates job execution across servers, handles failures
├── scheduler.py       # Host selection, warm-standby management
├── repairs.py         # Automated + manual repair pipeline
├── pool.py            # Working pool / spare pool management
├── policies.py        # Pluggable policy interfaces (host selection, repair escalation, removal)
├── simulator.py       # Top-level DES orchestrator — wires everything together
├── stats.py           # Statistics collection and reporting
├── sweep.py           # One-way and two-way parameter sweep drivers
├── run.py             # CLI entry point
└── __init__.py
```

### Key design decisions

| Decision | Rationale |
|---|---|
| **Pluggable policies** | Host-selection, repair-escalation, and server-removal strategies are injected via callables / strategy objects, so researchers can swap in their own. |
| **Dataclass params** | All simulation parameters live in a single frozen dataclass — easy to serialize, diff, sweep. |
| **SimPy processes** | Each server runs its own failure process; the coordinator, repair shop, and pool manager are separate processes that communicate via SimPy events and stores. |
| **Deterministic seeding** | Every run accepts an RNG seed for full reproducibility. |

## Parameters

See `airesim/params.py` for the full list. Key inputs:

- Failure rates (random & systematic)
- Fraction of "bad" (systematic-failure-prone) servers
- Recovery time, host-selection time, preemption wait time
- Warm standby count, working pool size, spare pool size
- Repair times and failure probabilities (automated & manual)
- Diagnosis uncertainty

## Outputs

Per simulation run:

- Total training time (wall-clock simulated time)
- Failure counts (total, random, systematic)
- Preemption count
- Repair counts (automated, manual, successful, failed)
- Average job run duration between failures

## Running Parameter Sweeps

```python
from airesim.sweep import OneWaySweep, TwoWaySweep
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

## Extending AIReSim

To add a custom host-selection policy:

```python
from airesim.policies import HostSelectionPolicy

class MyPolicy(HostSelectionPolicy):
    def select(self, available_servers, job_size, warm_standbys, rng):
        # your logic here
        return selected_servers

sim = Simulator(params=Params(), host_selection_policy=MyPolicy())
```

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
