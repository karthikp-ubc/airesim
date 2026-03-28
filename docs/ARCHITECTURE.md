# AIReSim Architecture

This document describes the code structure of AIReSim, what each class does, and
the reasoning behind the key design decisions.

---

## High-level overview

AIReSim is a **discrete-event simulation (DES)** of an AI training cluster built on
[SimPy](https://simpy.readthedocs.io/).  The simulator models a single large job
(e.g. 4 096 GPU nodes) running until completion while servers fail and are repaired
concurrently.

The primary question it answers is: *given a set of cluster parameters, what is the
expected total training time, and which parameters have the most leverage?*

```
┌─────────────────────────────────────────────────────────────┐
│                        Simulator                            │
│  (wires every component together; owns the main SimPy loop) │
│                                                             │
│  ┌──────────┐  ┌────────────┐  ┌───────────┐  ┌─────────┐  │
│  │  Params  │  │Coordinator │  │ Scheduler │  │Repair-  │  │
│  │(config)  │  │(failures)  │  │(selection)│  │  Shop   │  │
│  └──────────┘  └────────────┘  └───────────┘  └─────────┘  │
│                                                             │
│  ┌─────────────────────────┐   ┌──────────────────────────┐ │
│  │       PoolManager       │   │       StatsCollector     │ │
│  │  (working / spare pool) │   │  (per-run metrics store) │ │
│  └─────────────────────────┘   └──────────────────────────┘ │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Server  (state machine — one instance per node)     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

Sweep layer (optional):
  OneWaySweep / TwoWaySweep  →  AggregateStats  →  SweepResult
  plotting.py  →  PNG charts
  run.py       →  CLI entry point
```

---

## Module-by-module reference

### `params.py` — `Params`

**What it does:** A single `@dataclass` holding every tunable knob for one
simulation run (failure rates, repair times, pool sizes, job parameters, RNG seed,
and so on).  All times are in **minutes**; all rates are in **failures per minute**.

**Design decisions:**

- *Single source of truth.* Every other module receives the values it needs directly
  from `Params`; nothing reads global state.  This makes it trivial to create
  isolated configurations for each replication in a sweep.
- *`with_overrides(**kwargs) → Params`* uses `dataclasses.replace` to return a new
  instance with selected fields changed.  Sweeps call this once per value rather than
  mutating a shared object, keeping each simulation run independent.
- *Derived properties* (`systematic_failure_rate`, `total_servers_needed`) are
  computed on the fly so they always stay in sync with their inputs.
- *`validate()`* is called at the top of `Simulator.run()` so every run gets
  parameter checks, including when `with_overrides` produces an unusual combination.

---

### `server.py` — `Server`, `ServerState`

**What it does:** A bookkeeping entity for a single cluster node.  Tracks state
(`IDLE`, `RUNNING`, `FAILED`, `AUTO_REPAIR`, `MANUAL_REPAIR`, `RETIRED`, `SPARE`),
failure history, and whether the server is "bad" (elevated systematic failure rate).

**Design decisions:**

- *Pure state machine, no SimPy processes.* Failure timing is computed analytically
  by the `Coordinator` (see below).  Keeping `Server` process-free makes it
  lightweight and avoids the overhead of thousands of concurrent SimPy processes.
- *"Bad" vs "good" servers* model the paper's distinction between servers with a
  normal random failure rate and those with an additional systematic component.
  `is_bad` is a simple boolean; the effective rate is `random + systematic` for bad
  servers and just `random` for good ones.
- *`failure_timestamps`* is a list of wall-clock times at which the server failed,
  used by `ThresholdRemoval` to count failures within a rolling time window.

---

### `pool.py` — `PoolManager`

**What it does:** Maintains two mutable lists of `Server` objects — the **working
pool** (servers that are available or assigned to the job) and the **spare pool**
(servers running background work, available via preemption at a cost).

**Design decisions:**

- *Separate pool object.* The pool could have lived inside `Simulator`, but
  extracting it makes the movement logic testable in isolation and keeps `Simulator`
  from becoming a god class.
- *`return_to_working` is idempotent* — it checks `server not in working_pool`
  before appending.  This protects against double-return bugs that could arise from
  the misdiagnosis path.
- *Spare pool preemption* (`move_spare_to_working`) increments a
  `preemption_count` counter so the main loop can copy it into `StatsCollector` at
  the end of the run.

---

### `coordinator.py` — `Coordinator`

**What it does:** The engine of failure simulation.  Given a list of active servers
and the remaining job time, it samples the next failure event and returns `(failed_server, time_to_failure)` (or `(None, remaining_time)` if the job completes first).

**Design decisions:**

- *Aggregated-rate exponential shortcut (exponential distribution only).*
  For exponential TTFs, the minimum of N independent exponentials with rates
  λ₁…λₙ is itself exponential with rate Σλᵢ.  The failing server can then be
  chosen proportionally to its rate using a single extra uniform sample.  This
  reduces N SimPy processes and an `AnyOf` event to two RNG calls — a major
  performance win for clusters of thousands of nodes.
- *Per-server sampling for Weibull and lognormal.*
  These distributions don't have an analytic aggregate-minimum shortcut, so the
  coordinator samples a TTF for every server and takes the minimum directly (O(N)
  calls).  This is still fast because the expensive part of the original N-process
  design was SimPy process overhead, not sampling cost.
- *Mean-matching.* Weibull and lognormal parameters are derived so that the mean
  TTF equals `1 / failure_rate`, matching the exponential baseline.  This lets you
  compare distributions without changing the average failure frequency.
- *Single SimPy process per "run segment".* `run_until_failure` is itself a SimPy
  generator; the main loop yields on its result, so the simulation advances exactly
  to the next event (failure or job completion) with a single `timeout`.

---

### `repairs.py` — `RepairShop`, `RepairResult`

**What it does:** Accepts failed servers via `submit()` and runs each through a
two-stage repair pipeline — automated repair first, then optional manual escalation —
as independent SimPy processes.  When a server is returned to the pool it fires a
signal event so the main loop can wake up if it was waiting for a server.

**Design decisions:**

- *Independent SimPy processes per server.* Unlike failure simulation (which is
  aggregated), each server's repair can take a different amount of time and the
  pipeline has genuine conditional branching (escalate or not).  Separate processes
  model this naturally.
- *`on_server_returned` callback.* After returning a server to the pool, the repair
  shop calls this optional function if it was set.  The `Simulator` wires it to
  `Scheduler.return_server_to_job`, so repaired servers flow back into the warm-
  standby list mid-job without the repair shop needing to know anything about
  scheduling.  This keeps the two components decoupled.
- *`server_repaired_event` lifecycle (race-condition fix).* A naive implementation
  would `succeed()` the event and immediately replace it with a fresh event.  But if
  the main loop was running (not suspended in a `yield`) when the repair fired, the
  main loop would later grab the *replaced* event and wait forever — a missed-signal
  race.  The fix: the repair shop only `succeed()`s the event and never replaces it.
  The main loop owns the lifecycle: it checks `triggered` before yielding, and
  creates a new event after it wakes up.
- *Silent repair failures.* Both auto and manual stages have independent
  probabilities of reporting success while the underlying issue persists
  (`auto_repair_fail_prob`, `manual_repair_fail_prob`).  This models imperfect
  diagnostics in production environments.

---

### `scheduler.py` — `Scheduler`

**What it does:** Manages host selection (choosing which servers run the job) and
the warm-standby list (servers pre-assigned to swap in immediately after a failure).

**Design decisions:**

- *Separation from the main loop.* Selection logic could live in `Simulator._main_loop`
  but extracting it into `Scheduler` keeps the loop clean and makes policies easy
  to inject.
- *`swap_in_standby(failed_server)`* removes the failed server from `active_servers`
  and replaces it with the first available standby.  This is O(1) relative to
  calling `do_host_selection` again, and avoids the `host_selection_time` overhead.
- *`return_server_to_job(server)`* is the target of `repair_shop.on_server_returned`.
  It re-adds a repaired server to `warm_standbys` (up to the configured maximum),
  so the job's reserve is gradually rebuilt after failures while it is still running.

---

### `simulator.py` — `Simulator`

**What it does:** The top-level orchestrator.  Constructs and wires all components,
then drives `simpy.Environment.run()` through a single `_main_loop` process.

**Design decisions:**

- *Single main-loop process.* The core logic — host selection, failure handling,
  preemption, stall-waiting — all runs sequentially inside one SimPy generator.
  This makes the control flow easy to follow and reason about, while repair
  processes run concurrently in the background.
- *Seed threading.* The `Simulator` receives an explicit `seed` parameter (separate
  from `params.seed`) so that sweep replications can use `base_params.seed + rep`
  without modifying the shared `Params` object.
- *Stall-wait pattern.* When no servers are available from either the working or
  spare pool, the main loop yields on `repair_shop.server_repaired_event` (the
  missed-signal-safe version described above), then loops to re-check availability.
  This avoids busy-waiting (`yield env.timeout(1)`) in the common case.
- *`_bad_server_regen` optional process.* If `bad_server_regeneration` is enabled,
  a background process periodically converts some good servers to bad, modelling
  hardware aging or batch deployments of lower-quality nodes.

---

### `policies.py` — pluggable strategy interfaces

**What it does:** Defines three abstract base classes and their default implementations:

| ABC | Question answered | Default |
|---|---|---|
| `HostSelectionPolicy` | Which servers should run the job? | `DefaultHostSelection` — uniform random |
| `RepairEscalationPolicy` | Should auto repair escalate to manual? | `DefaultRepairEscalation` — fixed probability |
| `ServerRemovalPolicy` | Should a repaired server be retired? | `NeverRemove` — always reintegrate |

Also provided: `FewestFailuresFirst` (lowest-failure-count selection) and
`ThresholdRemoval` (retire if failures in window ≥ threshold).

**Design decisions:**

- *Strategy pattern.* All three policies are injected into `Simulator` at
  construction time.  This lets users experiment with custom logic (see
  `docs/TUTORIAL.md`) without touching the simulator core.
- *`rng` passed into every `select` / `should_remove` call.* Policies that need
  randomness share the simulation's RNG rather than constructing their own, ensuring
  all stochasticity flows through a single seeded source and results remain
  reproducible.

---

### `stats.py` — `StatsCollector`, `AggregateStats`

**What it does:** Two-level statistics system.

- `StatsCollector` — mutable counters for a **single run** (failures, repairs,
  training time, stalls, etc.).  Written to by the simulator components during the
  run; read by the sweep layer afterwards.
- `AggregateStats` — wraps a list of `StatsCollector` objects from multiple
  replications and computes mean / stdev / percentiles via `_summarize`.

**Design decisions:**

- *Dataclass for `StatsCollector`.* Using a dataclass with typed fields rather than
  a plain dict catches typos at import time and makes the fields self-documenting.
- *`AggregateStats` is separate from the sweep.* Sweeps produce it, but
  `AggregateStats` doesn't import `sweep.py`.  This keeps the stats layer usable
  without the sweep layer (e.g. for one-off analysis scripts).
- *`summary_table() → dict`* provides a stable interface that the plotting layer
  queries by metric name, so new metrics can be added without changing plotting code.

---

### `sweep.py` — `OneWaySweep`, `TwoWaySweep`, `SweepResult`

**What it does:** Runs a grid of `Simulator` instances across parameter values,
collects `AggregateStats` per configuration, and packages results into a
`SweepResult` that can print a summary table or export CSV.

**Design decisions:**

- *Sweeps are thin wrappers.* They loop over values, call `Simulator.run()`, and
  accumulate results.  All the interesting logic is in the simulator and stats layers.
- *Seed increment per replication* (`base_params.seed + rep`) gives each
  replication a distinct but deterministic seed, making experiments reproducible
  while keeping replications independent.
- *`SweepResult.to_csv()`* writes a flat table (one row per swept value) rather than
  raw replication data.  This is the format most useful for downstream analysis in
  spreadsheet tools.

---

### `plotting.py` — visualization utilities

**What it does:** Standalone functions that consume `SweepResult` and sensitivity
rows and produce matplotlib figures.  All functions are optional — matplotlib is
imported lazily inside each function so the rest of the simulator works without it.

**Design decisions:**

- *Not a class.* The plotting layer has no shared state; free functions are simpler
  and easier to call from scripts.
- *`sensitivity_summary`* reduces a dict of `SweepResult` objects to a list of
  plain dicts (param_name, min_mean, max_mean, range, impact) that can be
  inspected, sorted, or printed without matplotlib.  The chart is a separate step.
- *Impact classification* uses relative thresholds (`rng < 5 %` of max → low,
  `5–20 %` → medium, `> 20 %` → high) rather than absolute thresholds so the
  categories remain meaningful across different cluster scales.

---

### `run.py` — CLI entry point

**What it does:** Provides the `python -m airesim.run` interface with three modes:
demo (no arguments), script (positional path to a Python sweep file), and one-way
sweep (`--sweep` / `--values` / `--params` / `--output`).

**Design decisions:**

- *Backward compatibility.* The positional `SCRIPT` argument preserves the original
  `python -m airesim.run examples/my_sweep.py` interface while the new flags add
  CLI-native sweeping.
- *`_load_params`* accepts both JSON and YAML.  PyYAML is only imported if a
  `.yaml` file is actually requested, keeping the hard dependency to stdlib for
  users who only need JSON.
- *Mutual-exclusion validation in `main()`* rather than using `argparse`'s
  `add_mutually_exclusive_group`.  This gives clearer error messages (e.g. "SCRIPT
  and --sweep are mutually exclusive") than argparse's generic output.

---

## Data-flow summary

```
Params
  │
  ├─► Simulator.run()
  │      │
  │      ├─ creates Servers, PoolManager, StatsCollector
  │      ├─ creates Coordinator (failure engine)
  │      ├─ creates Scheduler  (host selection + standbys)
  │      ├─ creates RepairShop (background repair processes)
  │      └─ runs simpy.Environment
  │           │
  │           ├─ _main_loop (foreground)
  │           │    yield Coordinator.run_until_failure(...)
  │           │         → (failed_server, duration)
  │           │    RepairShop.submit(failed_server)
  │           │         → background SimPy process
  │           │    Scheduler.swap_in_standby(failed_server)
  │           │
  │           └─ _repair_process × N (background, one per failed server)
  │                → pool_manager.return_to_working(server)
  │                → scheduler.return_server_to_job(server)  [callback]
  │                → repair_shop._signal_repaired()
  │
  └─► StatsCollector   (written throughout; returned to caller)

OneWaySweep / TwoWaySweep
  │  calls Simulator.run() × (len(values) × num_replications)
  └─► SweepResult
       ├─ summary()      — printed table
       ├─ to_csv()       — CSV string
       └─ [passed to plotting.py for charts]
```

---

## Dependency graph

```
run.py
 └─ sweep.py ──► simulator.py ──► coordinator.py
                │               ├─► repairs.py
                │               ├─► scheduler.py
                │               ├─► pool.py
                │               ├─► server.py
                │               ├─► params.py
                │               ├─► stats.py
                │               └─► policies.py
                └─ stats.py
plotting.py (no simulator imports — consumes SweepResult only)
```

No circular dependencies.  `plotting.py` uses a `TYPE_CHECKING` guard so
`SweepResult` is only imported for type checking, keeping it independent of the
simulation core at runtime.
