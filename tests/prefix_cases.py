"""Shared case definitions for the pre-fix equivalence golden values.

Used by tests/generate_prefix_golden.py (run against a checkout of the commit
*before* 8896140) and tests/test_prefix_equivalence.py (run against the current
tree).  airesim is imported lazily so the generator can point at either tree.
"""

from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.yaml")

FIELDS = [
    "training_time_hours", "total_failures", "systematic_failures", "auto_repairs",
    "manual_repairs", "successful_repairs", "failed_repairs", "servers_retired",
    "preemption_count", "host_selection_count", "job_stall_count",
]

# config.yaml (SIMULATION_REPORT default config) at the seeds used by both
# SIMULATION_REPORT.md (adaptive, seed 42+rep) and sanity.csv.
DEFAULT_SEEDS = list(range(42, 72))
DEFAULT_PROBS = [1.0, 0.8]  # diagnosis_probability

_SMALL_BASE = dict(
    job_size=8, warm_standbys=2, working_pool_size=20, spare_pool_size=5,
    job_length=3 * 24 * 60, random_failure_rate=0.3 / (24 * 60),
    systematic_failure_rate_multiplier=10.0, systematic_failure_fraction=0.3,
    recovery_time=5, host_selection_time=1, preemption_wait_time=5,
    auto_repair_time=30, manual_repair_time=120,
    prob_auto_to_manual=0.5, auto_repair_fail_prob=0.3, manual_repair_fail_prob=0.3,
    num_replications=1,
)

# name -> (param overrides, removal policy name)
SMALL_CASES = {
    "base": ({}, "never"),
    "misdiagnosis": (dict(diagnosis_probability=0.8, diagnosis_uncertainty=0.3), "never"),
    "never_escalate": (dict(prob_auto_to_manual=0.0, auto_repair_fail_prob=0.6), "never"),
    "always_escalate": (dict(prob_auto_to_manual=1.0, auto_repair_fail_prob=0.6), "never"),
    "auto_always_fails": (dict(auto_repair_fail_prob=1.0, manual_repair_fail_prob=1.0),
                          "threshold"),
    "weibull": (dict(failure_distribution="weibull", weibull_shape=2.0), "never"),
}
SMALL_SEEDS = [1, 2, 3, 4, 5]


def _summarize(stats) -> dict:
    return {f: (repr(getattr(stats, f)) if f == "training_time_hours"
                else getattr(stats, f)) for f in FIELDS}


def run_default(prob: float, seed: int) -> dict:
    """One config.yaml run at the given diagnosis_probability and seed."""
    from airesim.run import _load_params
    from airesim.simulator import Simulator

    params = _load_params(CONFIG).with_overrides(diagnosis_probability=prob)
    return _summarize(Simulator(params=params, seed=seed).run())


def run_small(name: str, seed: int) -> dict:
    """One small-cluster run for the named case."""
    from airesim.params import Params
    from airesim.policies import NeverRemove, ThresholdRemoval
    from airesim.simulator import Simulator

    overrides, removal = SMALL_CASES[name]
    params = Params(**{**_SMALL_BASE, **overrides, "seed": seed})
    policy = (ThresholdRemoval(max_failures=2, window_minutes=7 * 24 * 60)
              if removal == "threshold" else NeverRemove())
    return _summarize(Simulator(params=params, removal_policy=policy, seed=seed).run())
