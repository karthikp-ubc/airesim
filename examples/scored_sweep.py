"""Score-based retirement policy — one-at-a-time parameter sweep.

Runs five independent sweeps, one per ScoredRemoval parameter, holding all
others at DEFAULT_POLICY.  Each data point is the mean ± stdev across
NUM_REPS replications.  Results are compared against a NeverRemove baseline
run with the same seeds.

Simulation regime: AIReSim default parameters (Table 1) with a shortened
7-day job so the sweep completes in reasonable time.

  working_pool_size = 4160   (headroom = 48 over job_size+warm_standbys)
  random_failure_rate        = 0.01 / day / server
  systematic_multiplier      = 5×  (bad-server rate = 0.05 / day)
  systematic_fraction        = 15%  (~654 bad servers out of 4360 total)
  auto_repair_fail_prob      = 0.40
  manual_repair_fail_prob    = 0.20  (effective fix rate ≈ 64%)

Parameters swept:
  initial_score        — starting reliability score
  failure_penalty      — score decrement per failure
  success_increment    — score increment per complete time_period uptime
  time_period          — minimum uptime required to earn one increment
  retirement_threshold — score at or below which a server is retired

Outputs (saved to examples/scored_figures/):
  scored_sweep_time.png    — Δ training time vs NeverRemove, per sweep
  scored_sweep_retired.png — mean servers retired, per sweep

Expected runtime: ~3-5 minutes (10 reps × 5 sweeps × ~6 values each).

Usage:
    python3 examples/scored_sweep.py
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
from airesim.policies import NeverRemove, ScoredRemoval

# ── Output ────────────────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "scored_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Simulation base ───────────────────────────────────────────────────────────

NUM_REPS = 10
BASE = Params(
    job_length=7 * 24 * 60,   # 7 days compute (default 256 days is too slow for sweeps)
    num_replications=NUM_REPS,
    seed=42,
    # All other fields are Params defaults (Table 1):
    #   working_pool_size=4160, job_size=4096, warm_standbys=16  → headroom=48
    #   random_failure_rate=0.01/(24*60), systematic_multiplier=5.0
    #   systematic_fraction=0.15, recovery_time=20, auto_repair_time=120
    #   manual_repair_time=2880, prob_auto_to_manual=0.80
    #   auto_repair_fail_prob=0.40, manual_repair_fail_prob=0.20
)

# ── Default policy parameters (hold-constant during each sweep) ───────────────

DEFAULT_POLICY = dict(
    initial_score        = 100.0,
    failure_penalty      = 30.0,
    success_increment    = 10.0,
    time_period          = 24 * 60,   # 1 day in simulation minutes
    retirement_threshold = 0.0,
)

# ── Sweep definitions ─────────────────────────────────────────────────────────
# Each entry: (param_name, x_label, values, x_tick_formatter)

def _fmt_time_period(v: float) -> str:
    if v == 0:
        return "any"
    days = v / (24 * 60)
    if days < 1:
        return f"{v/60:.0f}h"
    return f"{days:.0f}d"

SWEEPS: list[tuple[str, str, list, callable]] = [
    (
        "initial_score",
        "initial_score",
        [25, 50, 100, 200, 500, 1000],
        str,
    ),
    (
        "failure_penalty",
        "failure_penalty",
        [5, 10, 20, 30, 50, 100],
        str,
    ),
    (
        "success_increment",
        "success_increment",
        [0, 5, 10, 20, 50],
        str,
    ),
    (
        "time_period",
        "time_period",
        [0, 6 * 60, 24 * 60, 7 * 24 * 60, 28 * 24 * 60],
        _fmt_time_period,
    ),
    (
        "retirement_threshold",
        "retirement_threshold",
        [0, 10, 25, 50, 75],
        str,
    ),
]


# ── Runner ────────────────────────────────────────────────────────────────────

@dataclass
class CellResult:
    mean_time:      float
    stdev_time:     float
    mean_retired:   float
    stdev_retired:  float
    depleted_frac:  float


def run_cell(policy, params: Params) -> CellResult:
    """Run NUM_REPS replications with *policy* and return aggregated stats."""
    times, retired = [], []
    depleted = 0
    for rep in range(params.num_replications):
        sim = Simulator(params=params, removal_policy=policy, seed=params.seed + rep)
        r = sim.run()
        times.append(r.training_time_hours)
        retired.append(float(r.servers_retired))
        if r.cluster_depleted:
            depleted += 1
    n = len(times)
    return CellResult(
        mean_time     = statistics.mean(times),
        stdev_time    = statistics.stdev(times) if n > 1 else 0.0,
        mean_retired  = statistics.mean(retired),
        stdev_retired = statistics.stdev(retired) if n > 1 else 0.0,
        depleted_frac = depleted / n,
    )


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_sweep_time(
    sweep_results: list[tuple[str, str, list, list[CellResult]]],
    baseline: CellResult,
) -> None:
    """5-row figure: Δ mean training time (hrs) vs NeverRemove, one row per sweep."""
    import matplotlib.pyplot as plt
    import numpy as np

    n_sweeps = len(sweep_results)
    fig, axes = plt.subplots(n_sweeps, 1, figsize=(9, 3.2 * n_sweeps))
    fig.suptitle(
        "ScoredRemoval — Δ Training Time vs NeverRemove\n"
        f"(default params, 7-day job, {NUM_REPS} reps; "
        f"baseline = {baseline.mean_time:.1f} ± {baseline.stdev_time:.1f} h)",
        fontsize=11,
    )

    for ax, (param_name, x_label, values, fmt, cells) in zip(axes, sweep_results):
        x_labels = [fmt(v) for v in values]
        deltas = [c.mean_time - baseline.mean_time for c in cells]
        errors = [
            (c.stdev_time**2 + baseline.stdev_time**2) ** 0.5
            for c in cells
        ]
        colors = ["#C44E52" if d > 0 else "#55A868" for d in deltas]

        bars = ax.bar(x_labels, deltas, color=colors, edgecolor="black",
                      alpha=0.85, width=0.6)
        ax.errorbar(x_labels, deltas, yerr=errors, fmt="none",
                    capsize=4, color="black", linewidth=1.2)
        ax.axhline(0, color="black", linewidth=1.0, linestyle="--")

        # Mark cells with any depletion
        for i, c in enumerate(cells):
            if c.depleted_frac > 0:
                ax.text(i, deltas[i] + (3 if deltas[i] >= 0 else -3),
                        f"dep\n{c.depleted_frac:.0%}",
                        ha="center", va="bottom" if deltas[i] >= 0 else "top",
                        fontsize=7, color="darkred", fontweight="bold")

        # Highlight the default value
        default_val = DEFAULT_POLICY[param_name]
        for i, v in enumerate(values):
            if v == default_val:
                bars[i].set_edgecolor("navy")
                bars[i].set_linewidth(2.5)

        ax.set_xlabel(x_label, fontsize=9)
        ax.set_ylabel("Δ time (hrs)", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(labelsize=8)

        # Annotate delta values on bars
        for i, (d, c) in enumerate(zip(deltas, cells)):
            va = "bottom" if d >= 0 else "top"
            offset = 0.5 if d >= 0 else -0.5
            ax.text(i, d + offset, f"{d:+.1f}h", ha="center", va=va,
                    fontsize=7, color="black")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = fig_path("scored_sweep_time.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


def plot_sweep_retired(
    sweep_results: list[tuple[str, str, list, list[CellResult]]],
) -> None:
    """5-row figure: mean servers retired, one row per sweep."""
    import matplotlib.pyplot as plt

    n_sweeps = len(sweep_results)
    fig, axes = plt.subplots(n_sweeps, 1, figsize=(9, 3.2 * n_sweeps))
    fig.suptitle(
        "ScoredRemoval — Mean Servers Retired\n"
        f"(default params, 7-day job, {NUM_REPS} reps)",
        fontsize=11,
    )

    for ax, (param_name, x_label, values, fmt, cells) in zip(axes, sweep_results):
        x_labels = [fmt(v) for v in values]
        means   = [c.mean_retired  for c in cells]
        errors  = [c.stdev_retired for c in cells]

        ax.bar(x_labels, means, color="#4C72B0", edgecolor="black",
               alpha=0.85, width=0.6)
        ax.errorbar(x_labels, means, yerr=errors, fmt="none",
                    capsize=4, color="black", linewidth=1.2)

        # Highlight default value
        default_val = DEFAULT_POLICY[param_name]
        for i, v in enumerate(values):
            if v == default_val:
                ax.patches[i].set_edgecolor("navy")
                ax.patches[i].set_linewidth(2.5)

        ax.set_xlabel(x_label, fontsize=9)
        ax.set_ylabel("Servers retired", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(labelsize=8)

        for i, (m, c) in enumerate(zip(means, cells)):
            if m > 0:
                ax.text(i, m + 0.2, f"{m:.1f}", ha="center", va="bottom",
                        fontsize=7, color="black")

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    path = fig_path("scored_sweep_retired.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


# ── Summary table ─────────────────────────────────────────────────────────────

def print_table(
    sweep_results: list[tuple],
    baseline: CellResult,
) -> None:
    print()
    for param_name, x_label, values, fmt, cells in sweep_results:
        print(f"  ── {x_label} ──")
        print(f"    {'value':<14}  {'time (hrs)':<18}  {'Δ vs Never':<12}  {'retired':<10}  depleted")
        print("    " + "-" * 70)
        for v, c in zip(values, cells):
            delta = c.mean_time - baseline.mean_time
            dep_str = f"{c.depleted_frac:.0%}" if c.depleted_frac > 0 else ""
            default_marker = " ←default" if v == DEFAULT_POLICY[param_name] else ""
            print(f"    {fmt(v):<14}  "
                  f"{c.mean_time:7.1f} ±{c.stdev_time:5.1f}   "
                  f"{delta:+8.1f}h     "
                  f"{c.mean_retired:5.1f} ±{c.stdev_retired:4.1f}  "
                  f"{dep_str:<8}{default_marker}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("AIReSim — ScoredRemoval Parameter Sweep")
    print("=" * 70)
    headroom = BASE.working_pool_size - BASE.job_size - BASE.warm_standbys
    print(f"  working_pool_size : {BASE.working_pool_size}  (headroom = {headroom})")
    print(f"  job_length        : {BASE.job_length / (24*60):.0f} days compute")
    print(f"  systematic_mult   : {BASE.systematic_failure_rate_multiplier}×")
    print(f"  bad_fraction      : {BASE.systematic_failure_fraction:.0%}")
    print(f"  auto_fail_prob    : {BASE.auto_repair_fail_prob}")
    print(f"  manual_fail_prob  : {BASE.manual_repair_fail_prob}")
    print(f"  replications      : {NUM_REPS}")
    print(f"  default policy    : {DEFAULT_POLICY}")
    print()

    # ── Baseline ──────────────────────────────────────────────────────────
    print("  Running NeverRemove baseline …", end=" ", flush=True)
    baseline = run_cell(NeverRemove(), BASE)
    print(f"time = {baseline.mean_time:.1f} ± {baseline.stdev_time:.1f} h")
    print()

    # ── Sweeps ────────────────────────────────────────────────────────────
    sweep_results = []

    for param_name, x_label, values, fmt in SWEEPS:
        print(f"  Sweep: {x_label}")
        cells = []
        for v in values:
            policy_kwargs = dict(DEFAULT_POLICY)
            policy_kwargs[param_name] = v
            policy = ScoredRemoval(**policy_kwargs)

            print(f"    {fmt(v):<10} …", end=" ", flush=True)
            cell = run_cell(policy, BASE)
            delta = cell.mean_time - baseline.mean_time
            dep_tag = f"  [depleted {cell.depleted_frac:.0%}]" if cell.depleted_frac > 0 else ""
            print(f"Δtime={delta:+.1f}h  retired={cell.mean_retired:.1f}{dep_tag}")
            cells.append(cell)

        sweep_results.append((param_name, x_label, values, fmt, cells))
        print()

    # ── Summary ───────────────────────────────────────────────────────────
    print("=" * 70)
    print("Summary (NeverRemove baseline:"
          f" {baseline.mean_time:.1f} ± {baseline.stdev_time:.1f} h)")
    print_table(sweep_results, baseline)

    # ── Best configuration found ───────────────────────────────────────────
    print("=" * 70)
    print("Best single-parameter improvement over baseline:")
    best_delta = 0.0
    best_desc  = None
    for param_name, x_label, values, fmt, cells in sweep_results:
        for v, c in zip(values, cells):
            delta = baseline.mean_time - c.mean_time
            if delta > best_delta and c.depleted_frac == 0:
                best_delta = delta
                best_desc  = (x_label, fmt(v), c)
    if best_desc:
        xlbl, xval, cell = best_desc
        print(f"  {xlbl} = {xval}  →  Δ = +{best_delta:.1f} h  "
              f"({best_delta/baseline.mean_time*100:.1f}% faster)  "
              f"retired = {cell.mean_retired:.1f}")
    else:
        print("  No parameter setting outperformed NeverRemove without depletion.")

    # ── Plots ──────────────────────────────────────────────────────────────
    print()
    print("Saving plots …")
    plot_sweep_time(sweep_results, baseline)
    plot_sweep_retired(sweep_results)

    print()
    print("=" * 70)
    print("Done. PNGs written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        if fname.endswith(".png"):
            kb = os.path.getsize(fig_path(fname)) // 1024
            print(f"  {fname}  ({kb} KB)")


if __name__ == "__main__":
    main()
