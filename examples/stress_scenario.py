"""Stress scenario: tight working pool, high failure rates, small spare pool.

Runs one-way sweeps in two high-stress regimes to identify parameter combinations
where warm_standbys, repair escalation probability, spare_pool_size, and
recovery_time each have measurable impact on total training time.

Regime definitions
------------------
Both regimes share:
  job_size          = 4096
  working_pool_size = 4128   (only 32 servers of headroom — no idle slack)
  spare_pool_size   = 50     (base; also swept)
  job_length        = 7 days of compute time

  2× stress: random_failure_rate = 2 × default  (~2 failures/100 days/server)
  5× stress: random_failure_rate = 5 × default  (~5 failures/100 days/server)

Swept parameters
----------------
  recovery_time        [5, 20, 40, 80]   minutes
  spare_pool_size      [10, 25, 50, 100] servers
  prob_auto_to_manual  [0.40, 0.60, 0.80, 0.95]
  warm_standbys        [4, 8, 16, 32]

Output
------
Saves PNG files to examples/stress_figures/:
  stress_{2x|5x}_{param_name}.png        — bar chart per sweep
  stress_{2x|5x}_tornado.png             — sensitivity tornado per regime
  stress_comparison.png                  — side-by-side sensitivity ranges

Expected runtime: ~5–8 minutes on a laptop (6 replications per configuration).

Usage:
    python3 examples/stress_scenario.py
    python -m airesim.run examples/stress_scenario.py
"""

from __future__ import annotations

import os
import sys
import statistics

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

from airesim.params import Params
from airesim.sweep import OneWaySweep
from airesim.simulator import Simulator
from airesim.plotting import (
    plot_one_way_sweep,
    sensitivity_summary,
    print_sensitivity_table,
    plot_tornado_chart,
)

# ── Output directory ──────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "stress_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Base configurations ───────────────────────────────────────────────────────

DEFAULT_RATE = 0.01 / (24 * 60)   # paper default: 0.01 failures/day/server

_STRESS_BASE = Params(
    job_size=4096,
    warm_standbys=16,
    working_pool_size=4128,        # 4096 + 32: no idle servers beyond standbys
    spare_pool_size=50,            # tight spare pool
    job_length=7 * 24 * 60,       # 7 days of uninterrupted compute
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
    num_replications=6,
)

STRESS_2X = _STRESS_BASE.with_overrides(random_failure_rate=2 * DEFAULT_RATE)
STRESS_5X = _STRESS_BASE.with_overrides(random_failure_rate=5 * DEFAULT_RATE)

# Each entry: (param_name, values_to_sweep)
SWEEP_PARAMS = [
    ("recovery_time",       [5, 20, 40, 80]),
    ("spare_pool_size",     [10, 25, 50, 100]),
    ("prob_auto_to_manual", [0.40, 0.60, 0.80, 0.95]),
    ("warm_standbys",       [4, 8, 16, 32]),
]


# ── Per-regime sweep runner ───────────────────────────────────────────────────

def run_regime(base: Params, label: str) -> tuple[list[dict], float]:
    """Run all sweeps for one stress regime; return (sensitivity_rows, baseline_hrs)."""
    rate_per_day = base.random_failure_rate * 24 * 60
    headroom = base.working_pool_size - base.job_size - base.warm_standbys

    print(f"\n{'='*65}")
    print(f"  Regime : {label}")
    print(f"  failure: {rate_per_day:.4f} failures/day/server  "
          f"({rate_per_day / DEFAULT_RATE:.0f}× default)")
    print(f"  pool   : working={base.working_pool_size} "
          f"(headroom={headroom}), spare={base.spare_pool_size}")
    print(f"  reps   : {base.num_replications} per configuration")
    print(f"{'='*65}")

    sweep_results = {}

    for param_name, values in SWEEP_PARAMS:
        print(f"\n  ── {param_name} = {values}")
        sweep = OneWaySweep(
            param_name=param_name,
            values=values,
            base_params=base,
            num_replications=base.num_replications,
        )
        result = sweep.run(verbose=True)
        result.summary()
        sweep_results[param_name] = result

        plot_one_way_sweep(
            result,
            title=f"[{label}] Training Time vs. {param_name}",
            save_path=fig_path(f"stress_{label}_{param_name}.png"),
        )

    # Sensitivity summary
    rows = sensitivity_summary(sweep_results, metric="training_time_hrs")
    print(f"\nSensitivity ranking ({label}):")
    print_sensitivity_table(rows)

    # Baseline: run the base params directly (no sweep override)
    print(f"\n  Computing baseline ({base.num_replications} reps)…")
    baseline_runs = [
        Simulator(base, seed=base.seed + i).run().training_time_hours
        for i in range(base.num_replications)
    ]
    baseline = statistics.mean(baseline_runs)
    stdev = statistics.stdev(baseline_runs)
    print(f"  Baseline training time: {baseline:.1f} ± {stdev:.1f} hrs")

    plot_tornado_chart(
        rows,
        baseline=baseline,
        title=f"Sensitivity Tornado — {label}",
        save_path=fig_path(f"stress_{label}_tornado.png"),
    )

    return rows, baseline


# ── Comparison chart ──────────────────────────────────────────────────────────

def plot_comparison(
    rows_2x: list[dict],
    rows_5x: list[dict],
) -> None:
    """Grouped bar chart: sensitivity range (Δ hrs) per parameter, 2× vs 5× side by side."""
    import matplotlib.pyplot as plt
    import numpy as np

    # Align both row lists by param_name using union of keys
    all_params = list({r["param_name"] for r in rows_2x + rows_5x})
    range_2x = {r["param_name"]: r["range"] for r in rows_2x}
    range_5x = {r["param_name"]: r["range"] for r in rows_5x}

    # Sort by 5× sensitivity descending
    all_params.sort(key=lambda p: range_5x.get(p, 0), reverse=True)

    x = np.arange(len(all_params))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    bars_2x = ax.bar(x - width / 2,
                     [range_2x.get(p, 0) for p in all_params],
                     width, label="2× failure rate",
                     color="#4C72B0", edgecolor="black", alpha=0.85)
    bars_5x = ax.bar(x + width / 2,
                     [range_5x.get(p, 0) for p in all_params],
                     width, label="5× failure rate",
                     color="#C44E52", edgecolor="black", alpha=0.85)

    # Value labels
    for bar in list(bars_2x) + list(bars_5x):
        h = bar.get_height()
        if h > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, h + 2,
                    f"{h:.0f}h", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(all_params, rotation=15, ha="right")
    ax.set_ylabel("Sensitivity Range (Δ Training Hours)")
    ax.set_title("Parameter Sensitivity: 2× vs 5× Failure Rate")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    path = fig_path("stress_comparison.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved plot to {path}")
    plt.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("AIReSim — Stress Scenario")
    print("=" * 65)
    print(f"Output directory: {FIGURES_DIR}")

    rows_2x, baseline_2x = run_regime(STRESS_2X, "2x")
    rows_5x, baseline_5x = run_regime(STRESS_5X, "5x")

    print("\n\n" + "=" * 65)
    print("Cross-regime comparison")
    print("=" * 65)
    print(f"\n  Baseline training time: 2× = {baseline_2x:.1f} hrs, "
          f"5× = {baseline_5x:.1f} hrs")

    print("\n  Sensitivity ranges:")
    range_2x = {r["param_name"]: r for r in rows_2x}
    range_5x = {r["param_name"]: r for r in rows_5x}
    all_params = sorted(range_5x, key=lambda p: range_5x[p]["range"], reverse=True)
    header = f"  {'Parameter':<25} {'2× range':>12} {'5× range':>12} {'amplification':>14}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for p in all_params:
        r2 = range_2x.get(p, {}).get("range", 0.0)
        r5 = range_5x.get(p, {}).get("range", 0.0)
        amp = f"{r5 / r2:.1f}×" if r2 > 0 else "—"
        print(f"  {p:<25} {r2:>11.1f}h {r5:>11.1f}h {amp:>14}")

    plot_comparison(rows_2x, rows_5x)

    print("\n" + "=" * 65)
    print("Done. PNGs written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        if fname.endswith(".png"):
            path = fig_path(fname)
            size_kb = os.path.getsize(path) // 1024
            print(f"  {fname}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
