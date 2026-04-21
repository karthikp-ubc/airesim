# CLAUDE.md — AIReSim

This file gives Claude Code the context needed to work effectively in this repo.

---

## Project overview

AIReSim is a discrete-event simulator (DES) built on [SimPy](https://simpy.readthedocs.io/)
for modeling reliability, failure recovery, scheduling, and repair in large-scale AI training
clusters.  The core concept: a job needs `job_size` servers running simultaneously; failures
interrupt the job and trigger a repair pipeline; the simulator measures end-to-end training
time and cluster efficiency (ETR — Effective Training Ratio).

---

## Setup

```bash
pip install -e ".[dev]"    # simpy + matplotlib + pytest + ruff
```

Python 3.10+ required.

---

## Essential commands

```bash
# Lint (must pass before any commit)
ruff check airesim/ tests/
ruff check airesim/ tests/ --fix   # auto-fix safe issues

# Tests (must pass before any commit)
pytest tests/ -v

# Both at once (mirrors CI)
ruff check airesim/ tests/ && pytest tests/ -v

# Run the built-in demo
python -m airesim.run

# Run a sweep script
python -m airesim.run examples/paper_table1_sweep.py

# CLI one-way sweep
python -m airesim.run --sweep recovery_time --values 10,20,30 --replications 30

# Adaptive replication from a YAML params file
python -m airesim.run --params config.yaml --adaptive
```

---

## Repository layout

```
airesim/                    # source package
├── params.py               # Params dataclass — every simulation knob
├── server.py               # Server entity: ServerState enum + state machine
├── coordinator.py          # Failure engine: aggregated exponential / Weibull / lognormal sampling
├── scheduler.py            # Host selection and warm-standby management
├── repairs.py              # RepairShop: auto → manual two-stage pipeline (SimPy processes)
├── pool.py                 # PoolManager: working pool / spare pool bookkeeping
├── scheduling_policies.py  # HostSelectionPolicy ABC + Default, FewestFailuresFirst, HighestScoreFirst
├── policies.py             # RepairEscalationPolicy + ServerRemovalPolicy ABCs;
│                           #   NeverRemove, ThresholdRemoval, ScoredRemoval,
│                           #   CompositeRemovalPolicy; re-exports scheduling_policies
├── simulator.py            # Top-level DES orchestrator
├── stats.py                # StatsCollector (per-run), AggregateStats (multi-rep)
├── sweep.py                # OneWaySweep / TwoWaySweep parameter sweep drivers
├── adaptive.py             # AdaptiveRunner — auto-determines sufficient replications
├── plotting.py             # Matplotlib chart helpers (optional dep)
├── run.py                  # CLI entry point
└── __init__.py

tests/                      # 79 tests across 5 modules, all passing
├── test_airesim.py         # Core params, server, coordinator, pool, scheduler, sweeps (23)
├── test_edge_cases.py      # Race-condition / bug-regression tests (5)
├── test_scored_removal.py  # ScoredRemoval unit + integration (24)
├── test_scheduling_policies.py   # HighestScoreFirst ordering, reset (9)
└── test_diagnosis_probability.py # diagnosis_probability / diagnosis_uncertainty (18)

docs/
├── ARCHITECTURE.md         # Module-by-module reference + design decisions
├── TUTORIAL.md             # Step-by-step user guide
└── *.md                    # Simulation reports (ETR, retirement, scheduling, heatmap, …)

examples/                   # Standalone sweep scripts; each produces a *_figures/ directory
config.yaml                 # Ready-to-use params file (paper defaults + adaptive settings)
```

---

## Code conventions

These are enforced by `ruff` and checked in CI.  Violating them will break the lint step.

| Rule | Detail |
|------|--------|
| **Style** | PEP 8; `ruff` rules E, W, F, I |
| **Line length** | ≤ 100 characters (`ruff` E501) |
| **Import order** | `ruff` I001 — stdlib → third-party → first-party; each group alphabetical |
| **Unused imports** | Not allowed (`ruff` F401); tests exempt from unused-variable F841 |
| **Type annotations** | Required on all public functions and methods |
| **Docstrings** | Required on all public classes, methods, functions |

Do **not** add new core dependencies to `airesim/` without discussion.  Optional deps
(e.g. matplotlib) go in `[project.optional-dependencies]` in `pyproject.toml`.

---

## Architecture essentials

### Key invariants

- **No circular imports.** Dependency order: `params` → `server` → `pool` →
  `scheduling_policies` → `policies` → `repairs/scheduler/coordinator` → `simulator` →
  `stats/sweep/adaptive`.  `plotting.py` only imports via `TYPE_CHECKING`.
- **`Params` is the single source of truth.** All simulation knobs live in the `Params`
  dataclass.  Use `params.with_overrides(**kwargs)` to create isolated copies for sweeps.
- **Pluggable policies via dependency injection.** `HostSelectionPolicy`,
  `RepairEscalationPolicy`, and `ServerRemovalPolicy` are strategy objects injected into
  `Simulator.__init__`.  Subclass the relevant ABC to add custom behaviour.
- **Deterministic seeding.** Every run takes an explicit seed.  Sweep replications use
  `seed + rep` so results are reproducible without fixing global state.

### Performance-critical path

`Coordinator` uses the min-of-exponentials shortcut: instead of running one SimPy process
per server, it samples the time-to-next-failure from a single exponential (rate = sum of all
server rates) in O(1).  Changing this to per-server processes would make 4 000+ server
simulations impractical.

### Two known bug fixes (see CHANGELOG)

1. **Floating-server deadlock** (`simulator.py` misdiagnosis branch): escaped bad servers
   must be explicitly returned to `working_pool` via `pool_mgr.return_to_working()` +
   `repair_shop.notify_server_available()`.  Do **not** call `on_server_returned` here (the
   server is still in `active_servers`).
2. **Missed-signal race** (`simulator.py` stall loop): the `server_repaired_event` is owned
   by the main loop — check `.triggered` before `yield`, then replace with a fresh event
   after waking.  Never replace it inside `RepairShop._signal_repaired()`.

---

## Testing guidance

- Run `pytest tests/ -v` to see individual test names.
- Edge-case tests in `test_edge_cases.py` use subclasses of `Simulator` that override
  `_main_loop` to inspect internal state — this is intentional and fine.
- The `test_diagnosis_probability.py` module contains regression tests for both bugs above;
  these are the most sensitive tests and the first to break if the misdiagnosis branch is
  modified.
- All tests are deterministic (fixed seeds).  Flakiness = a real bug.

---

## Adding things

### New parameter
1. Add field to `Params` in `params.py` with a sensible default.
2. Add validation in `Params.validate()` if constrained.
3. Wire through to the component that uses it.
4. Add at least one test.
5. Update `ARCHITECTURE.md` / `TUTORIAL.md` if user-facing; add a CHANGELOG entry.

### New policy
Subclass the appropriate ABC:

| Goal | ABC | File |
|------|-----|------|
| Which servers run the job | `HostSelectionPolicy` | `scheduling_policies.py` |
| Auto → manual escalation | `RepairEscalationPolicy` | `policies.py` |
| Permanent server retirement | `ServerRemovalPolicy` | `policies.py` |

### New failure distribution
1. Add name to `_valid_dists` in `Params.validate()`.
2. Add sampling branch in `Coordinator._sample_ttf()`.
3. Add a test alongside `test_failure_distributions` in `test_airesim.py`.

---

## CI

GitHub Actions (`.github/workflows/test.yml`) runs on every push and PR:

1. `pip install -e ".[dev]"`
2. `ruff check airesim/ tests/`
3. `pytest tests/ -v --tb=short`

Matrix: Python 3.10, 3.11, 3.12.

---

## Key docs

| File | When to read it |
|------|----------------|
| `docs/ARCHITECTURE.md` | Understanding module internals and design decisions |
| `docs/TUTORIAL.md` | Writing sweep scripts or custom policies |
| `CHANGELOG.md` | History of bug fixes and new features |
| `CONTRIBUTING.md` | PR checklist and code conventions |
