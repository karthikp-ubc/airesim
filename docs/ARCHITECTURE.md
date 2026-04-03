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
  AdaptiveRunner             →  ConvergenceReport
  plotting.py  →  PNG charts
  run.py       →  CLI entry point
```

---

## Module-by-module reference

### `params.py` — `Params`

**What it does:** A single `@dataclass` holding every tunable knob for one
simulation run (failure rates, repair times, pool sizes, job parameters, RNG seed,
and so on).  All times are in **minutes**; all rates are in **failures per minute**.

**Adaptive-replication parameters** (used by `AdaptiveRunner`):

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `adaptive_replications` | `False` | Signal that adaptive mode is desired (checked by the CLI; `AdaptiveRunner` can also be called directly regardless of this flag) |
| `confidence_level` | `0.95` | Desired CI confidence level, e.g. `0.95` for a 95% two-sided interval |
| `relative_accuracy` | `0.05` | Target half-width as a fraction of the mean, e.g. `0.05` for ±5% |
| `num_replications` | `30` | Minimum runs to complete before the convergence check begins |
| `max_replications` | `1000` | Hard cap on total runs; the runner stops and reports non-convergence if reached |

All five fields are validated by `validate()` and loadable from a YAML or JSON params file.

**Diagnosis parameters** (added alongside the existing `diagnosis_uncertainty`):

| Parameter | Meaning |
|-----------|---------|
| `diagnosis_probability` | P(failure triggers a repair attempt on *any* server). At 0 the failed server auto-recovers instantly; no server enters the repair pipeline. |
| `diagnosis_uncertainty` | P(wrong server blamed \| failure diagnosed). At 1 every repair is sent to a randomly chosen innocent server while the actual bad server escapes. |

Both are validated in `[0, 1]` by `validate()`.

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
- *`notify_server_available()` public method.* Called by the simulator when a server
  is returned to the pool outside the normal repair pipeline (missed diagnosis or
  escaped bad server after misdiagnosis).  Fires `_signal_repaired()` so any stalled
  main-loop depletion guard can wake and re-check pool availability.
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

**Failure-handling and diagnosis pipeline** (`_main_loop`, failure branch):

```
pool_mgr.remove_from_working(failed_server)

if rng.random() >= diagnosis_probability:          # missed diagnosis
    failed_server.state = IDLE
    pool_mgr.return_to_working(failed_server)      # auto-recover, no repair
    repair_shop.notify_server_available()
else:                                               # failure attributed
    if rng.random() < diagnosis_uncertainty:        # wrong server blamed
        misdiagnosed = rng.choice(innocents)
        misdiagnosed.mark_failed()
        pool_mgr.remove_from_working(misdiagnosed)
        failed_server.state = IDLE
        pool_mgr.return_to_working(failed_server)  # bad server escapes back to pool
        # NOTE: on_server_returned is NOT called here — bad server stays in
        # active_servers and must not be added to warm_standbys (would duplicate it)
        repair_shop.notify_server_available()
        failed_server = misdiagnosed               # rebind: innocent goes to repair
    removal_policy.on_failure(failed_server)
    repair_shop.submit(failed_server)
```

**Bug fixes in this path:**

1. *Floating-server deadlock (fixed).* Before the fix, when misdiagnosis fired the
   bad server was removed from `working_pool` (line above the branch) but never
   returned.  After host selection replaced `active_servers`, the bad server existed
   in no pool and was not tracked anywhere — it was "floating".  Accumulated floating
   servers drained `available_in_working` below `total_servers_needed`, causing the
   stall loop to wait forever on a repair event that would never come, and SimPy to
   exit silently with `total_training_time = 0`.  Fix: `pool_mgr.return_to_working`
   is called for the escaped bad server before rebinding `failed_server`.

2. *Active-server duplication (fixed).* An earlier version of the fix also called
   `repair_shop.on_server_returned` for the escaped bad server.  That callback
   (`scheduler.return_server_to_job`) adds the server to `warm_standbys` if a slot is
   free.  Since the bad server was still in `active_servers`, the next
   `swap_in_standby` call could pop it from `warm_standbys` and append it to
   `active_servers` a second time, creating a duplicate.  Fix: `on_server_returned`
   is not called for the escaped bad server — it continues running in `active_servers`
   unchanged.

---

### `scheduling_policies.py` — host-selection strategies

**What it does:** Defines the `HostSelectionPolicy` ABC and all concrete
implementations.  Refactored out of `policies.py` to keep the two orthogonal
concerns (scheduling vs. retirement) in separate files.  `policies.py` re-exports
these names for backward compatibility.

| Class | Strategy |
|-------|----------|
| `DefaultHostSelection` | Uniform random selection |
| `FewestFailuresFirst` | Sort ascending by `total_failure_count`; fewest-failures servers run first |
| `HighestScoreFirst` | Sort descending by `ScoredRemoval` score; highest-scored servers run first |

**Design decisions:**

- *`HighestScoreFirst` takes a `ScoredRemoval` instance.* The scheduler and the
  removal policy share one scorer object so scores stay in sync.  When paired with a
  non-ScoredRemoval retirement policy, use `CompositeRemovalPolicy` (see below) to
  maintain scores for scheduling while delegating retirement decisions to a separate
  policy.
- *`HighestScoreFirst` ≡ `FewestFailuresFirst` at large scale with short chunks.*
  Credits are earned per `floor(chunk / time_period)` periods.  When mean run chunks
  are much shorter than `time_period` (e.g. 7-minute chunks vs. 1-day periods), no
  credits are ever awarded, and score = `initial − penalty × failures` — a strictly
  decreasing linear function of failure count, identical to `FewestFailuresFirst`'s
  ordering.

---

### `policies.py` — repair-escalation and server-removal strategies

**What it does:** Defines two ABCs and their implementations for repair and
retirement decisions.  Also re-exports all `scheduling_policies` names for
backward compatibility.

| Class | Type | Description |
|-------|------|-------------|
| `RepairEscalationPolicy` | ABC | Should auto repair escalate to manual? |
| `DefaultRepairEscalation` | concrete | Fixed probability of escalation |
| `ServerRemovalPolicy` | ABC | Should a repaired server be permanently retired? |
| `NeverRemove` | concrete | Always reintegrate |
| `ThresholdRemoval` | concrete | Retire if failures in rolling window ≥ threshold |
| `ScoredRemoval` | concrete | Retire when score drops below threshold; score tracks history via penalty/credit |
| `CompositeRemovalPolicy` | concrete | Fan-out to two policies; `should_remove` delegates to primary |

**`ScoredRemoval` design:**

- Each server starts at `initial_score`.  Every call to `on_failure` deducts
  `failure_penalty`.  Every call to `on_success(duration)` adds
  `success_increment × floor(duration / time_period)`.
- `should_remove` retires the server if its score ≤ `retirement_threshold`.
- `scores_snapshot()` returns a read-only copy of all current scores (used in tests
  and analysis scripts).
- `reset()` clears all scores so the same policy object can be reused across
  independent replications.

**`CompositeRemovalPolicy` design:**

Enables `HighestScoreFirst` scheduling paired with a non-`ScoredRemoval` retirement
policy (e.g. `ThresholdRemoval`).  The composite fans out `on_failure`, `on_success`,
and `reset` to both the primary and secondary policy, but delegates `should_remove` to
the primary alone.  A typical pairing:

```python
scorer = ScoredRemoval(retirement_threshold=float('-inf'))  # scores only, never retires
policy = CompositeRemovalPolicy(
    primary=ThresholdRemoval(max_failures=2, window_minutes=7*24*60),
    secondary=scorer,
)
scheduler = HighestScoreFirst(scorer)
```

**Design decisions:**

- *Strategy pattern.* All policies are injected into `Simulator` at construction
  time, keeping the simulator core policy-agnostic.
- *`rng` passed into every `should_remove` call.* Policies that need randomness
  share the simulation's RNG for reproducibility.

---

### `stats.py` — `StatsCollector`, `AggregateStats`

**What it does:** Two-level statistics system.

- `StatsCollector` — mutable counters for a **single run** (failures, repairs,
  training time, stalls, etc.).  Written to by the simulator components during the
  run; read by the sweep layer afterwards.
- `AggregateStats` — wraps a list of `StatsCollector` objects from multiple
  replications and computes mean / stdev / percentiles via `_summarize`.

**Key derived properties on `StatsCollector`:**

| Property | Formula | Meaning |
|----------|---------|---------|
| `training_time_hours` | `total_training_time / 60` | Wall-clock time in hours |
| `avg_run_duration` | `mean(run_durations)` | Mean inter-failure interval (minutes) |
| `effective_training_ratio` | `total_compute_time / total_training_time` | Fraction of wall-clock time spent doing useful computation; 1.0 = no overhead |

`effective_training_ratio` (ETR) is included in `summary_dict()` (available in every
CSV/logging export) and in `AggregateStats.effective_training_ratio_summary()` /
`summary_table()` (available to sweep results and plotting).  ETR is the primary
single-number summary of cluster efficiency: every percentage-point improvement in ETR
translates directly to a proportional reduction in total training time.

**Design decisions:**

- *Dataclass for `StatsCollector`.* Using a dataclass with typed fields rather than
  a plain dict catches typos at import time and makes the fields self-documenting.
- *`AggregateStats` is separate from the sweep.* Sweeps produce it, but
  `AggregateStats` doesn't import `sweep.py`.  This keeps the stats layer usable
  without the sweep layer (e.g. for one-off analysis scripts).
- *`summary_table() → dict`* provides a stable interface that the plotting layer
  queries by metric name, so new metrics can be added without changing plotting code.
- *ETR as a computed property, not a stored field.* ETR depends on two already-stored
  fields (`total_compute_time`, `total_training_time`), so storing it separately would
  risk inconsistency.  Computing it on demand avoids that and costs nothing.

---

### `adaptive.py` — `AdaptiveRunner`, `ConvergenceReport`

**What it does:** Runs independent simulation replications one at a time and
stops as soon as the Student-t confidence interval for mean training time is
tight enough to satisfy the caller's accuracy requirement:

```
half_width / mean  ≤  params.relative_accuracy
```

where `half_width = t_{α/2, n−1} × std / sqrt(n)` and `α` comes from
`params.confidence_level`.

**`ConvergenceReport`** is the return value of `AdaptiveRunner.run()`.  It
contains:

| Field | Type | Meaning |
|-------|------|---------|
| `converged` | `bool` | `True` if the criterion was met before `max_replications` |
| `num_runs` | `int` | Total replications executed |
| `mean_training_hrs` | `float` | Sample mean of training time across all runs |
| `ci_half_width_hrs` | `float` | Absolute half-width of the CI in hours |
| `relative_half_width` | `float` | `ci_half_width_hrs / mean_training_hrs` |
| `confidence_level` | `float` | The requested confidence level |
| `relative_accuracy_target` | `float` | The requested relative accuracy |
| `raw_results` | `list[StatsCollector]` | All per-run stats objects |

**Design decisions:**

- *One replication at a time.* Runs are added one by one so the check can fire
  as soon as convergence is reached.  This avoids over-running: adding a batch
  of N runs when only 1 was needed wastes compute, which matters for expensive
  configurations.
- *Student-t CI, not normal.* With small sample sizes (especially near the
  minimum of `num_replications`) the t-distribution gives a wider, more honest
  interval than the normal approximation.  `scipy.stats.t.ppf` is used when
  `scipy` is available; a rational normal approximation (Abramowitz & Stegun
  26.2.17) is used as a fallback.  The fallback is accurate to ~4.5 × 10⁻⁴,
  adequate for the normal approximation that applies when the sample is large.
- *`num_replications` as minimum.* Reusing the existing field avoids adding
  yet another "min_replications" knob; the semantics change slightly
  (from "exact count" to "lower bound") only when `adaptive_replications` is
  active, which must be explicitly opted in to.
- *`max_replications` as safety cap.* Without a cap a pathological configuration
  (high variance relative to mean) could run indefinitely.  When the cap is
  reached the runner returns a `ConvergenceReport` with `converged=False` so
  callers can detect and handle the situation.
- *Seed threading.* Each replication uses `params.seed + rep` for the same
  deterministic, independent-replication guarantee as the fixed-count sweeps.

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

**`config.yaml`** — the repository ships a ready-to-use YAML parameter file at the
project root.  It contains all `Params` fields with inline comments explaining every
knob, and has `adaptive_replications: true` pre-configured so that
`python -m airesim.run --params config.yaml --adaptive` runs out of the box.  Users
can copy and modify it rather than writing a Python script for simple one-off runs.

**What it does:** Provides the `python -m airesim.run` interface with four modes:

| Mode | Invocation | Description |
|------|-----------|-------------|
| Demo | *(no arguments)* | Built-in recovery-time sweep to verify installation |
| Script | `SCRIPT` positional | Load and execute a user-provided Python sweep file |
| One-way sweep | `--sweep PARAM --values V1,V2,...` | CLI-native parameter sweep with optional `--params` and `--output` |
| Adaptive | `--adaptive --params FILE` | Run until CI criterion in the YAML/JSON file is met |

The `--adaptive` flag calls `AdaptiveRunner` with the params loaded from `--params`
and prints a live progress line per replication followed by a `ConvergenceReport`.

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
- *`--adaptive` requires `--params`.*  Adaptive mode is only meaningful when
  `confidence_level`, `relative_accuracy`, and the replication bounds are explicitly
  specified in a config file; running it against hard-coded defaults would be
  surprising.

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

AdaptiveRunner
  │  calls Simulator.run() repeatedly (seed + rep)
  │  after each run: compute t-CI, check half_width/mean ≤ relative_accuracy
  └─► ConvergenceReport
       ├─ converged, num_runs, mean_training_hrs, ci_half_width_hrs
       └─ raw_results: list[StatsCollector]
```

---

## Dependency graph

```
run.py
 ├─ sweep.py    ──► simulator.py ──► coordinator.py
 │               │               ├─► repairs.py
 │               │               ├─► scheduler.py ──► scheduling_policies.py
 │               │               ├─► pool.py
 │               │               ├─► server.py
 │               │               ├─► params.py
 │               │               ├─► stats.py
 │               │               ├─► policies.py ──► scheduling_policies.py (re-export)
 │               │               └─► scheduling_policies.py
 │               └─ stats.py
 └─ adaptive.py ──► simulator.py (same core, no new deps)
                 └─► params.py, stats.py
plotting.py (no simulator imports — consumes SweepResult only)
```

No circular dependencies.  `adaptive.py` imports only `params.py`, `simulator.py`,
`stats.py`, and `policies.py` (for type hints) — the same set as `sweep.py`.
`policies.py` imports from `scheduling_policies.py` for re-export only;
`scheduling_policies.py` does not import `policies.py`.
`plotting.py` uses a `TYPE_CHECKING` guard so `SweepResult` is only imported for
type checking, keeping it independent of the simulation core at runtime.
