# Changelog

All notable changes to AIReSim are recorded here.

---

## [Unreleased] — 2026-09-21

### Changes

#### Revert: default escalation policy restored to the DSN'26 paper's model

**Affected files:** `airesim/policies.py`, `airesim/repairs.py`,
`tests/test_repair_escalation_policy.py`, `tests/test_prefix_equivalence.py` (new),
`tests/prefix_cases.py` (new), `tests/generate_prefix_golden.py` (new),
`tests/data/prefix_golden.json` (new)

**What stands and what is reverted.** Commit `8896140` did two things. The
*wiring fix* stands: `RepairShop` consults the injected `RepairEscalationPolicy`
(and no longer takes a `prob_auto_to_manual` argument). The *semantics change* is
reverted: that commit made the default policy escalate only when auto repair had
failed.

**Why.** In the paper, `prob_auto_to_manual` is the probability that auto repair
determines the problem is beyond its scope and escalates. It is independent of
`auto_repair_fail_prob`, which is a *silent* failure (the status says the repair
succeeded), so escalation cannot condition on it. `8896140` inferred the intended
behaviour from `DefaultRepairEscalation`'s code and its `auto_repair_succeeded`
argument, which contradicted that class's own docstring ("escalate ... when auto
repair determines it cannot handle the issue"), and did not check it against the
paper. Under the reverted semantics the escalation rate was
`auto_repair_fail_prob x prob_auto_to_manual` (32% at the Table I defaults)
instead of `prob_auto_to_manual` (80%), so manual repairs, repair failure rates and
training times differed from the paper's model.

**Now.**
- `DefaultRepairEscalation` escalates with probability `prob_escalate` regardless of
  the auto-repair outcome.
- `EscalateOnDetectedFailure` keeps the `8896140` behaviour (escalate with
  probability `prob_escalate` only if auto repair failed). Its docstring states it
  assumes auto-repair failures are observable, which the paper does not.
- `RepairEscalationPolicy.uses_auto_outcome` (default `True`, so existing subclasses
  are unaffected) selects the random-number order: `False` policies decide first,
  receive `auto_repair_succeeded=None`, and the auto outcome is drawn only if the
  server is not escalated. This is the pre-`8896140` order, which is what makes the
  default bit-identical.

**Verification.** `tests/test_prefix_equivalence.py` compares against golden values
generated from `9c7168c` (the commit before `8896140`): six small-cluster cases, and
`config.yaml` at seeds 42-71 with `diagnosis_probability` 1.0 and 0.8 (the
`SIMULATION_REPORT.md` and `sanity.csv` seeds). Every statistic, including the exact
float training time, matches; the 60-run check is enabled with
`AIRESIM_FULL_EQUIVALENCE=1`. Custom policies remain honoured (`test_repair_escalation_policy.py`).

**Impact.** Anything generated between `8896140` and this change used the
outcome-conditioned semantics. For example, `config.yaml` seeds 42-71 give a mean
training time of 9,872.90 h under the paper's model versus 9,832.33 h under the
reverted semantics. The reports and CSVs from that period were regenerated on 2026-09-21 under the
paper's semantics (see the commits from `0cab8fb` onward).

---

### New Features

#### `Server.attributed_failure_count` and `FewestAttributedFailuresFirst`

**Affected files:** `airesim/server.py`, `airesim/simulator.py`, `airesim/stats.py`,
`airesim/scheduling_policies.py`, `airesim/policies.py` (re-export),
`tests/test_attributed_failures.py` (new)

`total_failure_count` is incremented on the server that truly failed, so
`FewestFailuresFirst` sees ground truth even when diagnosis blames the wrong
server. `attributed_failure_count` is incremented only on the server diagnosis
blames (nothing for undiagnosed failures), and `FewestAttributedFailuresFirst`
sorts by it, giving a scheduler that uses only operator-visible information.
The existing `FewestFailuresFirst` is unchanged. `StatsCollector` also gains
`misattributed_repairs` (repair sent to a server that did not fail) and
`nonfaulty_repairs` (repair submitted for a server with `is_bad == False`).
None of this consumes RNG: seeds 42-71 on `config.yaml` reproduced the then-current
`SIMULATION_REPORT.md` mean (9,832.325 h, outcome-conditioned escalation; see the
revert entry above) exactly.

---

### Correction

#### The 2026-08-05 `DefaultHostSelection` fix (`2028107`) changed results by ≈8% in the payoff regime, not "<0.1%" everywhere

**Affected files:** none (documentation-only correction; the code from `2028107` is
unchanged and correct)

**What changed, and why (recap of `2028107`, 2026-08-05):** `DefaultHostSelection.select()`
took `available_servers[:needed]` and shuffled only that prefix, so servers beyond index
`needed` in `available_servers` could never be chosen regardless of RNG seed. This was
silent because a freshly-initialized pool's list order happens to line up with rack
boundaries, and because nothing in the test suite asserted on which specific servers were
selected — but `pool.py`'s `return_to_working` appends repaired servers to the *end* of
`working_pool`, so as the pool churns, `DefaultHostSelection` increasingly favored
early-list (i.e. not-recently-repaired) servers while documented and named as uniform
random. The fix replaced the prefix-shuffle with `rng.sample(available_servers, needed)`,
a true uniform sample of the full pool.

**Why this correction:** the `2028107` CHANGELOG entry claimed the fix left "mean training
time ... statistically unchanged (< 0.1% relative difference across 15 seeds, both under
normal and high-churn conditions)". That check was run only in a low-churn regime. Re-run
here at 15 seeds each, old prefix-shuffle vs current `rng.sample`, `NeverRemove`, same
seeds paired:

| Regime | Old (prefix-shuffle) | New (`rng.sample`) | Δ (new − old) |
|---|---|---|---|
| Paper defaults (`config.yaml`) | 9,861.7 ± 10.3 h | 9,874.4 ± 9.1 h | +12.7 h (+0.13%), SE 8.7 h — within noise, consistent with the original "<0.1%" claim |
| Payoff regime (`examples/scheduling_comparison.py`'s `BASE`: 20× multiplier, 75% manual repair fail, 4,600-server pool) | 2,208.7 ± 9.3 h | 2,394.8 ± 12.6 h | **+186.1 h (+8.4%), SE 15.5 h — a real effect, not noise** |

The payoff regime churns the pool much harder (more failures, more repairs returning
servers to the end of `working_pool`), which is exactly the condition under which the old
prefix bias was worst — so the "<0.1%" claim, true in the low-churn regime it was measured
in, does not generalize. `FewestFailuresFirst`/`HighestScoreFirst`/`PackedByRackFirst`
never call `rng.sample` (they sort deterministically), so they are bit-for-bit unaffected;
only `DefaultHostSelection` ("Random" in the reports) changed.

**Which reports predate the fix (their `Random`/`DefaultHostSelection` rows use the biased
prefix-shuffle selection; everything else about them is unaffected):** the original
`SIMULATION_REPORT.md` and `SCHEDULING_COMPARISON_REPORT.md` (2026-04-02),
`RETIREMENT_POLICY_REPORT.md`, `2D-HEAT_MAP_REPORT.md`, `THRESHOLD_SENSITIVITY_REPORT.md`,
and `DIAGNOSIS_SWEEP_REPORT.md`. All of these have since been regenerated (see the
2026-09-21 entries above and the commits from `8d2f3d1` onward) under the current
`rng.sample`-based selection, so the reports currently in `docs/` are not affected by this
correction — it applies only to anyone comparing against a pre-2026-08-05 checkout or an
archived copy of the original reports.

---

## [Unreleased] — 2026-09-20

### Bug Fixes

#### Bug: injected `RepairEscalationPolicy` was never consulted

> **Status (2026-09-21):** the wiring fix below stands, but the *semantics change*
> (escalating only when auto repair failed, and the Impact paragraph's conclusions
> about escalation rates) is reverted; see "Revert: default escalation policy
> restored to the DSN'26 paper's model" above.

**Affected files:** `airesim/repairs.py`, `airesim/simulator.py`, `tests/test_edge_cases.py`

**Symptom:** `RepairShop` stored the `escalation_policy` it was constructed with
(`self.escalation_policy = escalation_policy`) but `_repair_process` never called
`escalation_policy.should_escalate(...)`. Instead it recomputed the same decision
inline with a bare probability draw, and did so *before* the auto-repair
outcome was known:

```python
auto_handled = self.rng.random() >= self.prob_auto_to_manual
```

This broke `CLAUDE.md`'s "pluggable policies via dependency injection"
invariant for `RepairEscalationPolicy` specifically: a user-supplied subclass
of `RepairEscalationPolicy` had zero effect on simulation output, no matter
what it returned. It also meant the *default* policy's own documented rule —
`DefaultRepairEscalation.should_escalate` returns `False` whenever auto repair
already succeeded, i.e. "only escalate work that's actually still broken" —
was never enforced; escalation instead fired for a fixed fraction of *all*
repairs regardless of outcome.

**How it was found:** During an architecture-conformance review that traced
every constructor-injected policy to its call site. `test_edge_cases.py`'s
`make_repair_shop` helper always set both `prob_auto_to_manual` and
`DefaultRepairEscalation(prob_escalate=...)` to the same value, so the two
code paths were numerically indistinguishable in every existing test.

**Fix:** `_repair_process` now computes `auto_repair_succeeded` first, then
calls `self.escalation_policy.should_escalate(server, auto_repair_succeeded,
self.rng)` to decide escalation — mirroring how `removal_policy.should_remove`
is already called later in the same method. `RepairShop.__init__` no longer
takes a `prob_auto_to_manual` parameter (it was only ever used by the inline
check being removed); `Simulator` still builds
`DefaultRepairEscalation(prob_escalate=params.prob_auto_to_manual)` as the
default when no custom policy is supplied.

**Impact:** This is a genuine simulation-semantics change for anyone relying
on the default escalation policy, not just a fix for custom policies. Auto
repairs that succeed are no longer sent to manual repair at all (previously
~`prob_auto_to_manual` of them were, wasting `manual_repair_time` for no
reason); only auto repairs that actually fail can escalate, and only with
probability `prob_auto_to_manual`. This lowers the effective manual-repair
rate and total repair time for any run with `auto_repair_fail_prob < 1.0`
(the paper-default config uses `auto_repair_fail_prob=0.40`). Existing
`docs/*_REPORT.md` figures that cite an "escalation rate" derived from
`prob_auto_to_manual` alone predate this fix and should be regenerated before
being cited again. All 97 pre-existing tests still pass unchanged — none
asserted on absolute escalation/manual-repair counts.

**New tests:** `tests/test_repair_escalation_policy.py` (7 tests) — proves a
custom policy overrides `prob_auto_to_manual` in both directions, that
`should_escalate` receives the real post-repair outcome rather than a
precomputed guess, and that the default policy now correctly never escalates
an auto repair that already succeeded.

---

## [Unreleased] — 2026-08-05

### Bug Fixes

#### Bug: `DefaultHostSelection` sampled from a prefix, not the full pool

**Affected files:** `airesim/scheduling_policies.py`, `tests/test_scheduling_policies.py`

**Symptom:** `DefaultHostSelection.select()` is documented as "uniform random," but
took `available_servers[:needed]` first and only shuffled *within* that prefix.
Servers beyond index `needed` in `available_servers` could never be selected,
regardless of RNG seed.

**How it was found:** Discovered while verifying the new rack-topology feature.
`PackedByRackFirst` and `DefaultHostSelection` produced *identical* racks-spanned
results on a freshly-initialized pool, because `assign_racks` assigns rack IDs in
the same contiguous order the pool was constructed in — so the old prefix-based
"random" selection happened to line up with rack boundaries by construction. The
bug only became visible once the pool churned (repaired servers are appended to
the *end* of `working_pool` via `pool.py`'s `return_to_working`), at which point
`DefaultHostSelection` continued favoring early-list servers while claiming to be
uniform random.

**Fix:** `select()` now uses `rng.sample(available_servers, needed)` to draw a
true uniform sample from the entire available pool.

**Impact:** This changes *which* specific servers `DefaultHostSelection` picks
(and therefore RNG-call sequencing) but not simulation semantics — mean training
time was verified statistically unchanged (< 0.1% relative difference across
15 seeds, both under normal and high-churn conditions). No existing test asserted
on the specific servers selected, so no other test needed updating.

**New tests:** `tests/test_scheduling_policies.py::TestDefaultHostSelection` —
5 tests, including a regression test (`test_samples_across_entire_pool_not_just_a_prefix`)
that sweeps 50 seeds to confirm servers outside the old prefix window are
selectable, and `test_every_server_selectable_over_many_seeds`.

---

### New Features

#### Rack topology: `Params.enable_topology`, `airesim/topology.py`, `PackedByRackFirst`

**Affected files:** `airesim/topology.py` (new), `airesim/server.py`, `airesim/params.py`,
`airesim/simulator.py`, `airesim/scheduling_policies.py`, `airesim/policies.py` (re-export),
`tests/test_topology.py` (new)

A first step toward hierarchical-cluster modeling: an opt-in rack layer on top of the
flat working/spare pool.

- **`Server.rack_id: int | None`** — new field, defaults to `None` (topology not
  modeled).
- **`airesim/topology.py`** — new module; `assign_racks(servers, rack_size)` tags
  each server with `rack_id = index // rack_size` in place. No other component
  (`Coordinator`, `RepairShop`, `PoolManager`) needs to know about racks.
- **`Params.enable_topology`** (default `False`) and **`Params.rack_size`** (default
  `8`) — when `enable_topology` is `True`, `Simulator.run()` calls `assign_racks` on
  the full server list (after the bad-server shuffle, so rack membership isn't
  correlated with reliability). `rack_size` is validated `> 0`.
- **`PackedByRackFirst`** — new `HostSelectionPolicy` that groups available servers
  by `rack_id` and fills the job from the largest rack(s) first, minimizing the
  number of racks a job spans (network-locality heuristic). Servers with
  `rack_id is None` are grouped into a single implicit rack, so the policy is safe
  to use even with `enable_topology=False` (it just degrades to one rack).

Both new params default to values that leave existing simulations byte-for-byte
unaffected (`enable_topology=False` means every server's `rack_id` stays `None` and
no behavior changes).

#### New test module: `tests/test_topology.py` (13 tests)

Covers `assign_racks` (contiguous blocks, partial last rack), `rack_size`
validation, `PackedByRackFirst` unit behavior (packing, spanning multiple racks,
undersized pools, untagged/topology-disabled servers), and end-to-end `Simulator`
integration with `enable_topology` on and off.

Total test suite: **97 tests**, all passing.

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

#### New test module: `tests/test_diagnosis_probability.py` (18 tests)

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
| `tests/test_scored_removal.py` | 24 | `ScoredRemoval` score arithmetic, thresholds, snapshot, integration |
| `tests/test_scheduling_policies.py` | 9 | `HighestScoreFirst` ordering, untracked servers, reset |
| `tests/test_diagnosis_probability.py` | 18 | Diagnosis parameter validation and simulation behaviour |

Total test suite: **79 tests**, all passing.

---

## Prior history

See `git log` for commit-level history prior to 2026-03-29.
