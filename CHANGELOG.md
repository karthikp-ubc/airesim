# Changelog

All notable changes to AIReSim are recorded here.

---

## [Unreleased] — 2026-04-21

### Code Quality

#### Consistency pass: type annotations, docstrings, and line length

**Affected files:** `airesim/server.py`, `airesim/repairs.py`, `airesim/stats.py`,
`airesim/scheduling_policies.py`, `airesim/policies.py`, `airesim/sweep.py`,
`airesim/simulator.py`, `airesim/run.py`, `airesim/plotting.py`

Applied fixes to conform to the CONTRIBUTING.md guidelines (PEP 8, ≤100-char lines,
type annotations on all public functions, docstrings on all public items):

- Added docstrings to `ServerState` enum, `RepairResult` dataclass, and
  `StatsCollector.avg_run_duration` / `training_time_hours` properties.
- Added full type annotations (parameters + return types) to all concrete
  `select()` overrides in `scheduling_policies.py` and to the `should_escalate()`
  and `should_remove()` overrides in `policies.py`.
- Added `file: io.TextIOBase | None` type annotation to `SweepResult.summary()`.
- Broke 8 lines that exceeded 100 characters across `simulator.py`, `run.py`,
  `plotting.py`, `stats.py`, and `policies.py`.

#### Linter: ruff added for automatic style enforcement

**Affected files:** `pyproject.toml`, `.github/workflows/test.yml`

`ruff` (rules E, W, F, I — PEP 8 errors/warnings, unused imports, import
sorting) is now configured in `pyproject.toml` and runs as a CI step before
the test suite on every push and pull request.

Applied all violations ruff found in the existing codebase:
- Removed unused imports (`copy`, `field` in `params.py`; `numpy` in
  `plotting.py`; `pytest`, `DefaultHostSelection`, `FewestFailuresFirst`,
  `NeverRemove`, `ServerState` in test files).
- Sorted import blocks in all source and test modules (`I001`).
- Removed unused local assignments (`moved` in `simulator.py`; `rng` in
  `test_airesim.py`).
- Replaced `== True` boolean comparison with a bare truth check in
  `test_airesim.py` (`E712`).

`ruff` is added to the `[project.optional-dependencies] dev` group so
`pip install -e ".[dev]"` installs it automatically.

---

## [Unreleased] — 2026-03-30

### Bug Fixes

#### Bug: Floating-server deadlock at high `diagnosis_uncertainty`

**Affected file:** `airesim/simulator.py` (misdiagnosis branch)
**Commit:** `f437f10`

**Symptom:** When `diagnosis_uncertainty` was set to 0.4 or higher, the
simulation would silently exit with `total_training_time = 0.0` rather than
completing the job. The cluster never reported as depleted; SimPy simply ran
out of events.

**Root cause:** During a misdiagnosis event the actual failed server is removed
from `working_pool` (`pool_mgr.remove_from_working`) so that the innocent
server can be sent to the repair pipeline in its place. The code then rebound
the local variable `failed_server` to point at the innocent server, but
**never returned the actual bad server to any pool**. The bad server was
therefore stranded — its state was `IDLE` yet it appeared in neither
`working_pool` nor `spare_pool`. As misdiagnoses accumulated, the working pool
drained below the minimum needed to sustain the job. The stall loop waited for
a repair-completion event that would never fire (all repaired servers were
innocent), SimPy exhausted its event queue, and the environment exited without
the job ever completing.

**Fix:** Immediately before rebinding `failed_server = misdiagnosed`, the
actual bad server is now explicitly returned to the working pool and the repair
shop is notified that a server is available:

```python
failed_server.state = ServerState.IDLE
pool_mgr.return_to_working(failed_server)
repair_shop.notify_server_available()
failed_server = misdiagnosed   # now send the innocent server to repair
```

`notify_server_available()` is a thin public wrapper around the existing
`_signal_repaired()` private method on `RepairShop`, added in `airesim/repairs.py`
to expose the signal without coupling `simulator.py` to repair internals.

---

#### Bug: Active-server duplication after misdiagnosis

**Affected file:** `airesim/simulator.py` (misdiagnosis branch)
**Commit:** `abf8775`

**Symptom:** With `diagnosis_uncertainty = 1.0` and a small `warm_standbys`
count (e.g., 1), the simulator would intermittently record more active servers
than exist, inflating failure counts and corrupting statistics. In extreme cases
the job would complete with apparently impossible counts.

**Root cause:** An early version of the floating-server fix called
`repair_shop.on_server_returned(failed_server)` for the escaped bad server,
mirroring the code path used for legitimately missed diagnoses. However, the
two cases are not symmetric:

- In the **missed-diagnosis** branch the failed server is *swapped out* of
  `active_servers` before the auto-recovery path runs; calling
  `on_server_returned` adds it to `warm_standbys`, and the subsequent
  `swap_in_standby` call correctly moves a standby into `active_servers`.
- In the **misdiagnosis** branch the escaped bad server is **never swapped out**
  — it remains in `active_servers`. Calling `on_server_returned` added it to
  `warm_standbys` as well, so it now appeared in both `active_servers` and
  `warm_standbys`. The next `swap_in_standby` call popped it from standbys and
  appended it to `active_servers` a second time, creating a duplicate entry.
  Each subsequent failure sampling drew against this inflated active set.

**Fix:** Do **not** call `on_server_returned` in the misdiagnosis branch. The
bad server is returned directly to `working_pool` (see the floating-server fix
above) without going through the standby machinery, because it is still present
in `active_servers` and must stay there.

---

### New Features

#### Parameters: `diagnosis_probability` and `diagnosis_uncertainty`

**Affected files:** `airesim/params.py`, `airesim/simulator.py`
**Commit:** `69d8efe`

Two new parameters model imperfect failure diagnosis:

- **`diagnosis_probability`** ∈ [0, 1] — probability that a failure triggers
  any repair attempt. At 0, every failure auto-recovers without entering the
  repair pipeline; the job still incurs the checkpoint recovery overhead.
- **`diagnosis_uncertainty`** ∈ [0, 1] — probability that the wrong server is
  blamed given that a failure was diagnosed. At 1, every repair is dispatched
  to a randomly chosen innocent server while the actual bad server escapes back
  to the working pool.

Both parameters default to their "ideal" values (`1.0` and `0.0` respectively)
so existing simulations are unaffected.

#### `RepairShop.notify_server_available()`

**Affected file:** `airesim/repairs.py`
**Commit:** `f437f10`

A new public method that fires the internal repair-available signal. This
allows `simulator.py` to wake the stall loop when a server is returned to the
pool outside the normal repair pipeline (i.e., after a misdiagnosis), without
exposing or duplicating repair internals.

---

### Improvements

#### Scheduling policies extracted to `scheduling_policies.py`

**Affected files:** `airesim/scheduling_policies.py` (new),
`airesim/policies.py` (re-exports for backward compatibility)
**Commit:** `c546fd6`

`HostSelectionPolicy`, `DefaultHostSelection`, `FewestFailuresFirst`, and
`HighestScoreFirst` were moved from `policies.py` to a dedicated
`scheduling_policies.py` module. `policies.py` re-exports all four names so
existing imports continue to work unchanged.

#### Race-condition fixes (warm-standby callback, misdiagnosis double-submit, missed-signal event)

**Affected files:** `airesim/simulator.py`, `airesim/scheduler.py`
**Commit:** `8776025`

Three race conditions in the original discrete-event loop were fixed:

1. **Warm-standby callback race** — a repair completion could fire while the
   main loop was still running, causing the standby to be registered before the
   job had advanced its clock.
2. **Misdiagnosis double-submit** — a server in the repair pipeline could
   receive a second repair request before the first completed, corrupting its
   state.
3. **Missed-signal event** — the stall-wait `Event` was re-used across loop
   iterations; if a repair signal arrived while the loop was processing (not
   yielded), the event was already triggered and the next `yield` returned
   immediately without checking the pool condition first. Fixed by owning the
   event in the main loop and replacing it after each wake.

---

### Testing

#### New test module: `tests/test_diagnosis_probability.py` (20 tests)

Covers `diagnosis_probability` and `diagnosis_uncertainty` parameter
validation and simulation behaviour, including regression tests for both bugs
described above:

- Parameter boundary validation (0.0, 1.0, out-of-range)
- Zero-probability: no repairs, no retirements, job completes
- Partial probability: fewer repairs than full-diagnosis baseline
- `test_high_uncertainty_completes` — regression for floating-server deadlock;
  asserts `total_training_time > 0` at uncertainty ∈ {0.4, 0.6, 0.8, 1.0}
- `test_escaped_server_not_duplicated_in_active_servers` — regression for
  duplication bug; uses small pool (job_size=4, warm_standbys=1) to maximise
  the probability of hitting the empty-standby-slot condition

#### New test modules

| Module | Cases | What it covers |
|--------|-------|----------------|
| `tests/test_edge_cases.py` | 5 | Race-condition regressions |
| `tests/test_scored_removal.py` | 22 | `ScoredRemoval` score arithmetic, thresholds, snapshot, integration |
| `tests/test_scheduling_policies.py` | 9 | `HighestScoreFirst` ordering, untracked servers, reset |
| `tests/test_diagnosis_probability.py` | 20 | Diagnosis parameter validation and simulation behaviour |

Total test suite: **79 tests**, all passing.

---

## Prior history

See `git log` for commit-level history prior to 2026-03-29.
