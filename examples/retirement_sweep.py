"""Two-way sweep: auto_repair_fail_prob × retirement threshold.

Tests the regime where server retirement (ThresholdRemoval) actually matters:
tight working pool (4128 = job_size + 32), high failure rate (5×), small spare
pool (200).  Tracks both training time and the number of servers retired so the
capacity cost of aggressive retirement is visible.

Grid:
  auto_repair_fail_prob : [0.2, 0.4, 0.6, 0.8]
  retirement threshold  : [None (never), 5, 3, 2]  failures in 7 days

When threshold is None the default NeverRemove policy is used.

Outputs (saved to examples/retirement_figures/):
  retirement_heatmaps.png  — training time and servers retired as colour maps
  retirement_bars.png      — grouped bar charts with error bars per metric

Expected runtime: ~4–6 minutes (10 replications × 16 cells).

Usage:
    python3 examples/retirement_sweep.py
    python -m airesim.run examples/retirement_sweep.py
"""

from __future__ import annotations

import os
import sys
import statistics
from dataclasses import dataclass

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

from airesim.params import Params
from airesim.simulator import Simulator
from airesim.policies import NeverRemove, ThresholdRemoval
from airesim.stats import StatsCollector

# ── Output directory ──────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "retirement_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Sweep axes ────────────────────────────────────────────────────────────────

REPAIR_FAIL_PROBS = [0.2, 0.4, 0.6, 0.8]

# None → NeverRemove; int → ThresholdRemoval(max_failures=N, window=7 days)
THRESHOLDS: list[int | None] = [None, 5, 3, 2]
THRESHOLD_LABELS = ["Never", "5 / 7d", "3 / 7d", "2 / 7d"]
WINDOW_MINUTES = 7 * 24 * 60

DEFAULT_RATE = 0.01 / (24 * 60)

BASE = Params(
    job_size=4096,
    warm_standbys=16,
    working_pool_size=4128,        # only 32 headroom — tight
    spare_pool_size=200,           # buffer to absorb retirements
    job_length=14 * 24 * 60,      # 14 days of compute time
    random_failure_rate=5 * DEFAULT_RATE,
    systematic_failure_rate_multiplier=5.0,
    systematic_failure_fraction=0.15,
    recovery_time=20,
    host_selection_time=3,
    preemption_wait_time=20,
    auto_repair_time=120,
    manual_repair_time=2 * 1440,
    prob_auto_to_manual=0.80,
    auto_repair_fail_prob=0.40,    # swept below
    manual_repair_fail_prob=0.20,
    seed=42,
    num_replications=10,
)


# ── Per-cell runner ───────────────────────────────────────────────────────────

@dataclass
class CellResult:
    mean_time:       float
    stdev_time:      float
    mean_retired:    float
    stdev_retired:   float
    depleted_frac:   float   # fraction of reps that hit cluster depletion


def run_cell(
    auto_repair_fail_prob: float,
    threshold: int | None,
    base: Params,
) -> CellResult:
    """Run ``base.num_replications`` independent sims for one grid cell."""
    params = base.with_overrides(auto_repair_fail_prob=auto_repair_fail_prob)
    removal_policy = (
        NeverRemove()
        if threshold is None
        else ThresholdRemoval(max_failures=threshold, window_minutes=WINDOW_MINUTES)
    )

    runs: list[StatsCollector] = []
    for rep in range(base.num_replications):
        sim = Simulator(
            params=params,
            removal_policy=removal_policy,
            seed=base.seed + rep,
        )
        runs.append(sim.run())

    times    = [r.training_time_hours for r in runs]
    retired  = [float(r.servers_retired) for r in runs]
    depleted = sum(1 for r in runs if r.cluster_depleted) / len(runs)

    return CellResult(
        mean_time     = statistics.mean(times),
        stdev_time    = statistics.stdev(times) if len(times) > 1 else 0.0,
        mean_retired  = statistics.mean(retired),
        stdev_retired = statistics.stdev(retired) if len(retired) > 1 else 0.0,
        depleted_frac = depleted,
    )


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_heatmaps(
    grid_time:    list[list[float]],
    grid_retired: list[list[float]],
    grid_depleted: list[list[float]],
) -> None:
    """Two side-by-side heatmaps: training time and servers retired.

    Rows = retirement threshold (y-axis, top = Never, bottom = aggressive).
    Cols = auto_repair_fail_prob (x-axis, left = low, right = high).
    Cells with any depleted fraction are hatched with '//'.
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    time_arr    = np.array(grid_time)
    retired_arr = np.array(grid_retired)
    depleted_arr = np.array(grid_depleted)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, data, title, cmap in [
        (axes[0], time_arr,    "Mean Training Time (hrs)",   "YlOrRd"),
        (axes[1], retired_arr, "Mean Servers Retired",        "YlOrBr"),
    ]:
        im = ax.imshow(data, cmap=cmap, aspect="auto")
        plt.colorbar(im, ax=ax, shrink=0.85)

        # Annotate each cell
        for i in range(len(THRESHOLDS)):
            for j in range(len(REPAIR_FAIL_PROBS)):
                val = data[i, j]
                text_color = "white" if data[i, j] > (data.max() * 0.65) else "black"
                label = f"{val:.0f}"
                if depleted_arr[i, j] > 0:
                    label += f"\n({depleted_arr[i,j]:.0%} dep.)"
                ax.text(j, i, label, ha="center", va="center",
                        fontsize=8.5, color=text_color, fontweight="bold")

                # Hatch depleted cells
                if depleted_arr[i, j] > 0:
                    ax.add_patch(plt.Rectangle(
                        (j - 0.5, i - 0.5), 1, 1,
                        fill=False, hatch="//", edgecolor="grey", linewidth=0,
                    ))

        ax.set_xticks(range(len(REPAIR_FAIL_PROBS)))
        ax.set_xticklabels([str(p) for p in REPAIR_FAIL_PROBS])
        ax.set_xlabel("auto_repair_fail_prob")
        ax.set_yticks(range(len(THRESHOLDS)))
        ax.set_yticklabels(THRESHOLD_LABELS)
        ax.set_ylabel("Retirement threshold")
        ax.set_title(title)

    dep_patch = mpatches.Patch(
        facecolor="white", edgecolor="grey", hatch="//",
        label="Cluster depleted in ≥1 rep",
    )
    fig.legend(handles=[dep_patch], loc="lower center", ncol=1, fontsize=9,
               bbox_to_anchor=(0.5, -0.04))

    fig.suptitle(
        f"Retirement Sweep  —  5× failure rate, working_pool={BASE.working_pool_size}, "
        f"spare={BASE.spare_pool_size}, {BASE.num_replications} reps",
        fontsize=11,
    )
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    path = fig_path("retirement_heatmaps.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


def plot_bar_charts(
    grid_time:    list[list[float]],
    grid_time_sd: list[list[float]],
    grid_retired: list[list[float]],
    grid_ret_sd:  list[list[float]],
) -> None:
    """Grouped bar charts: x = auto_repair_fail_prob, groups = threshold."""
    import matplotlib.pyplot as plt
    import numpy as np

    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]
    x = np.arange(len(REPAIR_FAIL_PROBS))
    n_groups = len(THRESHOLDS)
    width = 0.8 / n_groups

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, title, ylabel, grid, sd_grid in [
        (axes[0], "Training Time", "Mean Training Time (hrs)",
         grid_time, grid_time_sd),
        (axes[1], "Servers Retired", "Mean Servers Retired",
         grid_retired, grid_ret_sd),
    ]:
        for i, (label, color) in enumerate(zip(THRESHOLD_LABELS, colors)):
            offsets = x + (i - (n_groups - 1) / 2) * width
            means  = [grid[i][j]    for j in range(len(REPAIR_FAIL_PROBS))]
            errors = [sd_grid[i][j] for j in range(len(REPAIR_FAIL_PROBS))]
            ax.bar(offsets, means, width * 0.9,
                   label=f"Threshold: {label}",
                   yerr=errors, capsize=3,
                   color=color, edgecolor="black", alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels([str(p) for p in REPAIR_FAIL_PROBS])
        ax.set_xlabel("auto_repair_fail_prob")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle(
        f"Retirement Sweep  —  5× failure rate, working_pool={BASE.working_pool_size}, "
        f"spare={BASE.spare_pool_size}",
        fontsize=11,
    )
    plt.tight_layout()
    path = fig_path("retirement_bars.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("AIReSim — Retirement Sweep")
    print("=" * 70)
    rate_per_day = BASE.random_failure_rate * 24 * 60
    headroom = BASE.working_pool_size - BASE.job_size - BASE.warm_standbys
    print(f"  failure rate : {rate_per_day:.4f}/day/server "
          f"({rate_per_day / DEFAULT_RATE:.0f}× default)")
    print(f"  working pool : {BASE.working_pool_size}  (headroom = {headroom})")
    print(f"  spare pool   : {BASE.spare_pool_size}")
    print(f"  job length   : {BASE.job_length / (24*60):.0f} days compute")
    print(f"  replications : {BASE.num_replications}")
    print(f"  grid         : {len(REPAIR_FAIL_PROBS)} repair-fail-probs × "
          f"{len(THRESHOLDS)} thresholds = {len(REPAIR_FAIL_PROBS)*len(THRESHOLDS)} cells")
    print(f"  output dir   : {FIGURES_DIR}")
    print()

    # Build result grid  [threshold_idx][prob_idx]
    grid_time:     list[list[float]] = []
    grid_time_sd:  list[list[float]] = []
    grid_retired:  list[list[float]] = []
    grid_ret_sd:   list[list[float]] = []
    grid_depleted: list[list[float]] = []

    for thresh, t_label in zip(THRESHOLDS, THRESHOLD_LABELS):
        row_t, row_t_sd, row_r, row_r_sd, row_dep = [], [], [], [], []
        for prob in REPAIR_FAIL_PROBS:
            label = f"threshold={t_label:<7}  auto_fail={prob}"
            print(f"  Running  {label} …", end=" ", flush=True)
            cell = run_cell(prob, thresh, BASE)
            print(f"time={cell.mean_time:7.1f}±{cell.stdev_time:5.1f}h  "
                  f"retired={cell.mean_retired:5.1f}±{cell.stdev_retired:4.1f}"
                  + (f"  [depleted {cell.depleted_frac:.0%}]"
                     if cell.depleted_frac > 0 else ""))
            row_t.append(cell.mean_time)
            row_t_sd.append(cell.stdev_time)
            row_r.append(cell.mean_retired)
            row_r_sd.append(cell.stdev_retired)
            row_dep.append(cell.depleted_frac)
        grid_time.append(row_t)
        grid_time_sd.append(row_t_sd)
        grid_retired.append(row_r)
        grid_ret_sd.append(row_r_sd)
        grid_depleted.append(row_dep)

    # ── Summary table ─────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("Summary: mean training time (hrs) / mean servers retired")
    print("=" * 70)
    prob_header = "".join(f"  fail={p:<4}" for p in REPAIR_FAIL_PROBS)
    print(f"  {'Threshold':<12}{prob_header}")
    print("  " + "-" * 66)
    for i, label in enumerate(THRESHOLD_LABELS):
        cells = "".join(
            f"  {grid_time[i][j]:6.0f}/{grid_retired[i][j]:3.0f}"
            for j in range(len(REPAIR_FAIL_PROBS))
        )
        print(f"  {label:<12}{cells}")

    # ── Plots ─────────────────────────────────────────────────────────────
    print()
    print("Saving plots …")
    plot_heatmaps(grid_time, grid_retired, grid_depleted)
    plot_bar_charts(grid_time, grid_time_sd, grid_retired, grid_ret_sd)

    print()
    print("=" * 70)
    print("Done. PNGs written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        if fname.endswith(".png"):
            kb = os.path.getsize(fig_path(fname)) // 1024
            print(f"  {fname}  ({kb} KB)")


if __name__ == "__main__":
    main()
