"""Shared per-replication logging for the example sweeps.

``ReplicationLog.run`` runs one replication with a ``MonitoredSimulator`` (results are
identical to the plain ``Simulator``; the monitor is read-only and draws no random
numbers) and appends one CSV row: commit, script, label, seed, all headline statistics,
host-selection count, systematic/random failures, faulty servers in the pool, and the
full ``Params`` as JSON.  The caller keeps aggregating from the returned ``StatsCollector``.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)

from airesim.simulator import Simulator  # noqa: E402

MONITOR_INTERVAL = 360.0  # simulated minutes between faulty-server samples

FIELDS = [
    "git_commit", "script", "label", "host_policy", "removal_policy", "seed", "rep",
    "training_time_hrs", "etr", "total_failures", "random_failures", "systematic_failures",
    "auto_repairs", "manual_repairs", "successful_repairs", "failed_repairs",
    "bad_servers_cured", "bad_server_repair_failures", "nonfaulty_repairs",
    "misattributed_repairs", "servers_retired", "preemption_count", "host_selection_count",
    "job_stall_count", "cluster_depleted", "faulty_in_pool_initial", "faulty_in_pool_timeavg",
    "faulty_in_pool_final", "faulty_in_active_timeavg", "n_monitor_samples",
    "wall_seconds", "params_json",
]


class MonitoredSimulator(Simulator):
    """Simulator that samples faulty-server counts every MONITOR_INTERVAL minutes."""

    def _main_loop(self, env, rng, p, coordinator, scheduler, repair_shop,
                   pool_mgr, stats, all_servers):
        self._done = False
        self._pool_samples: list[int] = []
        self._active_samples: list[int] = []
        env.process(self._monitor(env, pool_mgr, scheduler))
        yield from super()._main_loop(
            env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats, all_servers
        )
        self._done = True

    def _monitor(self, env, pool_mgr, scheduler):
        while not self._done:
            self._pool_samples.append(sum(1 for s in pool_mgr.working_pool if s.is_bad))
            self._active_samples.append(sum(1 for s in scheduler.active_servers if s.is_bad))
            yield env.timeout(MONITOR_INTERVAL)

    def run(self):
        """Run and attach the monitor summary to the returned stats object."""
        stats = super().run()
        n = len(self._pool_samples)
        stats.faulty_in_pool_initial = self._pool_samples[0]
        stats.faulty_in_pool_final = self._pool_samples[-1]
        stats.faulty_in_pool_timeavg = sum(self._pool_samples) / n
        stats.faulty_in_active_timeavg = sum(self._active_samples) / n
        stats.n_monitor_samples = n
        return stats


def describe(obj) -> str:
    """Class name plus public scalar attributes, e.g. ``ThresholdRemoval(max_failures=2, ...)``."""
    if obj is None:
        return "default"
    attrs = {k: v for k, v in vars(obj).items()
             if not k.startswith("_") and isinstance(v, (int, float, str, bool))}
    return f"{type(obj).__name__}({', '.join(f'{k}={v}' for k, v in attrs.items())})"


class ReplicationLog:
    """Append-only per-replication CSV.

    ``truncate=True`` (the default) starts a new file with a header; worker processes pass
    ``truncate=False`` to append single-row writes to the parent's file.
    """

    def __init__(self, path: str, script: str, truncate: bool = True, commit: str | None = None):
        self.path = path
        self.script = os.path.basename(script)
        self.commit = commit or subprocess.check_output(
            ["git", "-C", _root, "rev-parse", "HEAD"], text=True).strip()
        if truncate:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writeheader()

    def run(self, params, seed: int, label: str, host_selection_policy=None,
            removal_policy=None, escalation_policy=None):
        """Run one replication, log its row, and return the StatsCollector."""
        sim = MonitoredSimulator(params=params, host_selection_policy=host_selection_policy,
                                 escalation_policy=escalation_policy,
                                 removal_policy=removal_policy, seed=seed)
        t0 = time.time()
        r = sim.run()
        row = {
            "git_commit": self.commit, "script": self.script, "label": label,
            "host_policy": describe(sim.host_selection_policy),
            "removal_policy": describe(sim.removal_policy),
            "seed": seed, "rep": seed - params.seed,
            "training_time_hrs": repr(r.training_time_hours),
            "etr": repr(r.effective_training_ratio),
            "total_failures": r.total_failures, "random_failures": r.random_failures,
            "systematic_failures": r.systematic_failures, "auto_repairs": r.auto_repairs,
            "manual_repairs": r.manual_repairs, "successful_repairs": r.successful_repairs,
            "failed_repairs": r.failed_repairs, "bad_servers_cured": r.bad_servers_cured,
            "bad_server_repair_failures": r.bad_server_repair_failures,
            "nonfaulty_repairs": r.nonfaulty_repairs,
            "misattributed_repairs": r.misattributed_repairs,
            "servers_retired": r.servers_retired, "preemption_count": r.preemption_count,
            "host_selection_count": r.host_selection_count,
            "job_stall_count": r.job_stall_count, "cluster_depleted": int(r.cluster_depleted),
            "faulty_in_pool_initial": r.faulty_in_pool_initial,
            "faulty_in_pool_timeavg": repr(r.faulty_in_pool_timeavg),
            "faulty_in_pool_final": r.faulty_in_pool_final,
            "faulty_in_active_timeavg": repr(r.faulty_in_active_timeavg),
            "n_monitor_samples": r.n_monitor_samples,
            "wall_seconds": round(time.time() - t0, 2),
            "params_json": json.dumps(asdict(params), sort_keys=True),
        }
        with open(self.path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
        return r
