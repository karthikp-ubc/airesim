"""Statistics behind docs/SIMULATION_REPORT.md: adaptive replication on config.yaml.

Runs AdaptiveRunner (95% CI, +-5% relative accuracy, minimum 30 replications, seed
42+rep) on the paper-default config and writes one row per replication to
examples/simulation_report_figures/results.csv (commit, seed, all StatsCollector
fields, full Params as JSON).  The report's tables are computed from that CSV.

    python3 examples/simulation_report_stats.py
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from dataclasses import asdict

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)

from airesim.adaptive import AdaptiveRunner  # noqa: E402
from airesim.run import _load_params  # noqa: E402

OUT = os.path.join(_here, "simulation_report_figures", "results.csv")


def main() -> None:
    params = _load_params(os.path.join(_root, "config.yaml"))
    commit = subprocess.check_output(["git", "-C", _root, "rev-parse", "HEAD"],
                                     text=True).strip()
    report = AdaptiveRunner(params).run(verbose=True)
    print(report)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fields = ["git_commit", "seed", "rep", "training_time_hrs", "etr", "total_failures",
              "random_failures", "systematic_failures", "auto_repairs", "manual_repairs",
              "successful_repairs", "failed_repairs", "servers_retired", "preemption_count",
              "host_selection_count", "job_stall_count", "cluster_depleted",
              "compute_hrs", "recovery_hrs", "host_selection_hrs", "wait_hrs",
              "avg_run_duration_mins", "converged", "params_json"]
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for rep, r in enumerate(report.raw_results):
            w.writerow({
                "git_commit": commit, "seed": params.seed + rep, "rep": rep,
                "training_time_hrs": repr(r.training_time_hours),
                "etr": repr(r.effective_training_ratio),
                "total_failures": r.total_failures, "random_failures": r.random_failures,
                "systematic_failures": r.systematic_failures,
                "auto_repairs": r.auto_repairs, "manual_repairs": r.manual_repairs,
                "successful_repairs": r.successful_repairs,
                "failed_repairs": r.failed_repairs, "servers_retired": r.servers_retired,
                "preemption_count": r.preemption_count,
                "host_selection_count": r.host_selection_count,
                "job_stall_count": r.job_stall_count,
                "cluster_depleted": int(r.cluster_depleted),
                "compute_hrs": repr(r.total_compute_time / 60.0),
                "recovery_hrs": repr(r.total_recovery_time / 60.0),
                "host_selection_hrs": repr(r.total_host_selection_time / 60.0),
                "wait_hrs": repr(r.total_wait_time / 60.0),
                "avg_run_duration_mins": repr(r.avg_run_duration),
                "converged": int(report.converged),
                "params_json": json.dumps(asdict(params), sort_keys=True),
            })
    print("wrote", OUT)


if __name__ == "__main__":
    main()
