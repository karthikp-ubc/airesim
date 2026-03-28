"""Reproduce Figure 2 from the AIReSim paper and generate a sensitivity tornado.

Produces three PNG files in a `figures/` directory next to this script:

  fig2a_recovery_time.png       — training time vs. recovery_time × pool size
  fig2b_preemption_wait_time.png — training time vs. wait_time × pool size
  fig_sensitivity_tornado.png   — all parameters ranked by impact (tornado)

The sweeps use a scaled-down cluster (64-node job) so the script finishes in
roughly 30–60 seconds on a laptop.  To reproduce the paper's exact scale,
change BASE to use job_size=4096 and adjust WORKING_POOL_VALUES accordingly.

Usage:
    python -m airesim.run examples/generate_paper_figures.py
    # or directly:
    python3 examples/generate_paper_figures.py
"""

import os
import sys

# Allow running directly (not via airesim.run) by putting the project root on
# sys.path when executed as a plain script.
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

from airesim.params import Params
from airesim.sweep import OneWaySweep, TwoWaySweep
from airesim.plotting import (
    plot_two_way_sweep,
    sensitivity_summary,
    print_sensitivity_table,
    plot_tornado_chart,
)

# ── Output directory ──────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Base parameters (scaled-down cluster) ────────────────────────────────────
# job_size=64, warm_standbys=8  →  total_servers_needed=72.
# Scale failure rate to match the paper's ~1 failure/day/server at 4096 nodes.

BASE = Params(
    job_size=64,
    warm_standbys=8,
    working_pool_size=80,          # 64 + 8 + 8 headroom
    spare_pool_size=16,
    job_length=60 * 24 * 60,       # 60 days in minutes
    random_failure_rate=0.01 / (24 * 60),
    systematic_failure_rate_multiplier=5.0,
    systematic_failure_fraction=0.15,
    recovery_time=20,
    host_selection_time=3,
    preemption_wait_time=20,
    auto_repair_time=120,
    manual_repair_time=2 * 1440,
    prob_auto_to_manual=0.80,
    auto_repair_fail_prob=0.40,
    manual_repair_fail_prob=0.20,
    seed=42,
    num_replications=15,
)

# Three pool sizes spanning tight → comfortable headroom
WORKING_POOL_VALUES = [72, 80, 96]   # needed=72, base=80, roomy=96

NUM_REPS = BASE.num_replications


# ── Figure 2a — training time vs. recovery_time × working_pool_size ──────────

def figure_2a():
    print("\n─── Figure 2a: recovery_time × working_pool_size ───")
    sweep = TwoWaySweep(
        param1_name="recovery_time",
        param1_values=[5, 20, 40],
        param2_name="working_pool_size",
        param2_values=WORKING_POOL_VALUES,
        base_params=BASE,
        num_replications=NUM_REPS,
    )
    result = sweep.run(verbose=True)
    result.summary()

    plot_two_way_sweep(
        result,
        param1_name="Recovery Time (min)",
        param2_name="Working Pool Size",
        title="Figure 2a — Training Time vs. Recovery Time × Pool Size",
        save_path=fig_path("fig2a_recovery_time.png"),
    )
    return result


# ── Figure 2b — training time vs. preemption_wait_time × working_pool_size ───

def figure_2b():
    print("\n─── Figure 2b: preemption_wait_time × working_pool_size ───")
    sweep = TwoWaySweep(
        param1_name="preemption_wait_time",
        param1_values=[5, 20, 40],
        param2_name="working_pool_size",
        param2_values=WORKING_POOL_VALUES,
        base_params=BASE,
        num_replications=NUM_REPS,
    )
    result = sweep.run(verbose=True)
    result.summary()

    plot_two_way_sweep(
        result,
        param1_name="Preemption Wait Time (min)",
        param2_name="Working Pool Size",
        title="Figure 2b — Training Time vs. Preemption Wait Time × Pool Size",
        save_path=fig_path("fig2b_preemption_wait_time.png"),
    )
    return result


# ── Sensitivity tornado — all parameters ranked by impact ────────────────────

# Each entry: (param_name, [low_value, mid_value, high_value])
# Mid value should match BASE so sensitivity is symmetric around baseline.
SENSITIVITY_PARAMS = [
    ("recovery_time",               [5,    20,   40  ]),
    ("preemption_wait_time",        [5,    20,   40  ]),
    ("warm_standbys",               [2,    8,    16  ]),
    ("random_failure_rate",         [0.005 / (24*60),
                                     0.01  / (24*60),
                                     0.02  / (24*60)]),
    ("systematic_failure_fraction", [0.05, 0.15, 0.25]),
    ("host_selection_time",         [1,    3,    10  ]),
    ("auto_repair_time",            [60,   120,  240 ]),
    ("manual_repair_time",          [720,  2880, 5760]),
    ("prob_auto_to_manual",         [0.50, 0.80, 0.95]),
    ("auto_repair_fail_prob",       [0.10, 0.40, 0.70]),
    ("manual_repair_fail_prob",     [0.05, 0.20, 0.40]),
    ("systematic_failure_rate_multiplier", [2.0, 5.0, 10.0]),
]


def sensitivity_tornado():
    print("\n─── Sensitivity tornado: one-way sweeps ───")

    one_way_results = {}
    for param_name, values in SENSITIVITY_PARAMS:
        print(f"\n  {param_name}")
        sweep = OneWaySweep(
            param_name=param_name,
            values=values,
            base_params=BASE,
            num_replications=NUM_REPS,
        )
        one_way_results[param_name] = sweep.run(verbose=True)

    # Compute baseline from a single replication at BASE params
    from airesim.simulator import Simulator
    baseline_runs = [
        Simulator(BASE, seed=BASE.seed + i).run().training_time_hours
        for i in range(NUM_REPS)
    ]
    import statistics
    baseline = statistics.mean(baseline_runs)
    print(f"\n  Baseline training time: {baseline:.1f} hrs")

    rows = sensitivity_summary(one_way_results, metric="training_time_hrs")
    print_sensitivity_table(rows)

    plot_tornado_chart(
        rows,
        baseline=baseline,
        title="Sensitivity Tornado — Impact on Training Time",
        save_path=fig_path("fig_sensitivity_tornado.png"),
    )
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("AIReSim — Paper Figure Generation")
    print("=" * 60)
    print(f"Cluster scale : {BASE.job_size}-node job, "
          f"{BASE.working_pool_size}-node working pool")
    print(f"Job length    : {BASE.job_length / (24*60):.0f} days")
    print(f"Replications  : {NUM_REPS} per configuration")
    print(f"Output dir    : {FIGURES_DIR}")

    figure_2a()
    figure_2b()
    sensitivity_tornado()

    print("\n" + "=" * 60)
    print("Done.  PNGs written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        if fname.endswith(".png"):
            path = os.path.join(FIGURES_DIR, fname)
            size_kb = os.path.getsize(path) // 1024
            print(f"  {fname}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
