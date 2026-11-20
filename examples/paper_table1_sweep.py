"""Reproduce the parameter sweeps from the AIReSim paper (Table I, Figure 2).

Every Table I parameter is swept across its "value range considered", crossed with
the four working-pool sizes (a two-way sweep), with all other parameters at their
Table I defaults -- the experimental setup of Section IV.

Outputs (default directory examples/paper_table1_figures/):
  replications.csv   one row per run (parameter, value, pool size, seed, metrics)
  results.csv        per-cell mean / stdev / 95% CI of training time and other metrics
  fig2a_recovery_time.png, fig2b_preemption_wait_time.png   (paper Figure 2)

Replication r of every cell uses seed BASE.seed + r (common random numbers), so two
runs of this script on different code versions can be compared run by run.

Usage:
    python3 examples/paper_table1_sweep.py --workers 12 --replications 10
    python3 examples/paper_table1_sweep.py --only recovery_time preemption_wait_time
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import sys
from multiprocessing import Pool

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

from airesim.params import Params  # noqa: E402
from airesim.simulator import Simulator  # noqa: E402

DAY = 24 * 60

# Base parameters from Table I ("Default Value" column).
BASE = Params(
    random_failure_rate=0.01 / DAY,
    systematic_failure_rate_multiplier=5.0,
    systematic_failure_fraction=0.15,
    recovery_time=20,
    warm_standbys=16,
    host_selection_time=3,
    preemption_wait_time=20,
    prob_auto_to_manual=0.80,
    auto_repair_fail_prob=0.40,
    manual_repair_fail_prob=0.20,
    auto_repair_time=120,
    manual_repair_time=2 * 1440,
    working_pool_size=4160,
    spare_pool_size=200,
    diagnosis_probability=0.8,
    job_size=4096,
    job_length=256 * DAY,
    seed=42,
)

WORKING_POOL_VALUES = [4112, 4128, 4160, 4192]

# Table I "Value Range Considered".
SWEEPS = [
    ("random_failure_rate", [0.005 / DAY, 0.01 / DAY, 0.025 / DAY, 0.05 / DAY]),
    ("systematic_failure_rate_multiplier", [3.0, 5.0, 10.0]),
    ("systematic_failure_fraction", [0.1, 0.15, 0.2]),
    ("recovery_time", [10, 20, 30]),
    ("warm_standbys", [4, 8, 16, 32]),
    ("host_selection_time", [1, 3, 5, 10]),
    ("preemption_wait_time", [10, 20, 30]),
    ("prob_auto_to_manual", [0.70, 0.80, 0.90]),
    ("auto_repair_fail_prob", [0.2, 0.4, 0.6]),
    ("manual_repair_fail_prob", [0.1, 0.2, 0.3]),
    ("auto_repair_time", [60, 120, 180]),
    ("manual_repair_time", [1440, 2 * 1440, 3 * 1440]),
    ("spare_pool_size", [200, 300, 400]),
    ("diagnosis_probability", [0.6, 0.8, 1.0]),
]

METRICS = [
    "training_time_hours", "effective_training_ratio", "total_failures",
    "systematic_failures", "auto_repairs", "manual_repairs", "preemption_count",
    "spare_return_count", "host_selection_count", "job_stall_count", "total_wait_time",
    "cluster_depleted",
]


def _run(task: tuple) -> dict:
    param, value, pool, seed, base_overrides = task
    overrides = {**base_overrides, param: value, "working_pool_size": pool}
    params = BASE.with_overrides(**overrides)
    if params.working_pool_size < params.total_servers_needed:
        return {"param": param, "value": value, "pool": pool, "seed": seed, "skipped": 1}
    stats = Simulator(params, seed=seed).run()
    row = {"param": param, "value": value, "pool": pool, "seed": seed, "skipped": 0}
    for m in METRICS:
        row[m] = getattr(stats, m, 0)  # spare_return_count is absent in older trees
    return row


def _cost(task: tuple) -> float:
    """Rough relative runtime, to schedule the slowest runs first."""
    param, value = task[0], task[1]
    return value / BASE.random_failure_rate if param == "random_failure_rate" else 1.0


def _summarize(rows: list[dict]) -> list[dict]:
    cells: dict[tuple, list[dict]] = {}
    for r in rows:
        if not r["skipped"]:
            cells.setdefault((r["param"], r["value"], r["pool"]), []).append(r)
    out = []
    for (param, value, pool), rs in cells.items():
        tt = [r["training_time_hours"] for r in rs]
        sd = statistics.stdev(tt) if len(tt) > 1 else 0.0
        out.append({
            "param": param, "value": value, "pool": pool, "n": len(rs),
            "mean_training_hrs": statistics.fmean(tt), "stdev_training_hrs": sd,
            "ci95_training_hrs": 1.96 * sd / math.sqrt(len(tt)),
            **{f"mean_{m}": statistics.fmean(float(r[m]) for r in rs)
               for m in METRICS if m != "training_time_hours"},
        })
    return out


def _plot(summary: list[dict], param: str, path: str, xlabel: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    for pool in WORKING_POOL_VALUES:
        pts = sorted((s["value"], s["mean_training_hrs"], s["ci95_training_hrs"])
                     for s in summary if s["param"] == param and s["pool"] == pool)
        if pts:
            xs, ys, es = zip(*pts)
            ax.errorbar(xs, ys, yerr=es, marker="o", capsize=3,
                        label=f"{pool} (+{pool - BASE.job_size - BASE.warm_standbys})")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Total training time (hours)")
    ax.legend(title="Working pool size", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--replications", type=int, default=10)
    ap.add_argument("--only", nargs="*", help="sweep only these parameters")
    ap.add_argument("--out", default=os.path.join(_here, "paper_table1_figures"))
    ap.add_argument("--base-diagnosis-probability", type=float, default=None,
                    help="override the Table I default (0.8), e.g. 1.0 to isolate its effect")
    a = ap.parse_args()

    base_overrides = {}
    if a.base_diagnosis_probability is not None:
        base_overrides["diagnosis_probability"] = a.base_diagnosis_probability

    sweeps = [s for s in SWEEPS if not a.only or s[0] in a.only]
    tasks = [(param, value, pool, BASE.seed + rep, base_overrides)
             for param, values in sweeps for value in values
             for pool in WORKING_POOL_VALUES for rep in range(a.replications)]
    tasks.sort(key=_cost, reverse=True)
    print(f"{len(tasks)} runs on {a.workers} workers; base overrides: {base_overrides}",
          flush=True)

    os.makedirs(a.out, exist_ok=True)
    rows = []
    with Pool(a.workers) as pool:
        for i, row in enumerate(pool.imap_unordered(_run, tasks), 1):
            rows.append(row)
            if i % 50 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)} runs done", flush=True)

    rows.sort(key=lambda r: (r["param"], r["value"], r["pool"], r["seed"]))
    with open(os.path.join(a.out, "replications.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["param", "value", "pool", "seed", "skipped",
                                          *METRICS], restval="")
        w.writeheader()
        w.writerows(rows)

    summary = sorted(_summarize(rows), key=lambda s: (s["param"], s["value"], s["pool"]))
    with open(os.path.join(a.out, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    for s in summary:
        print(f"{s['param']:>36} = {s['value']:<12.6g} pool={s['pool']}  "
              f"training={s['mean_training_hrs']:8.1f} ± {s['ci95_training_hrs']:5.1f} hrs  "
              f"preempt={s['mean_preemption_count']:6.1f}")

    _plot(summary, "recovery_time", os.path.join(a.out, "fig2a_recovery_time.png"),
          "Recovery time (minutes)")
    _plot(summary, "preemption_wait_time",
          os.path.join(a.out, "fig2b_preemption_wait_time.png"), "Waiting time (minutes)")


if __name__ == "__main__":
    main()
