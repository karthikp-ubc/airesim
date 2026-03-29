"""Sensitivity analysis: where does ThresholdRemoval have a net benefit?

One-at-a-time parameter sweeps starting from the retirement-payoff regime.
Each sweep tests NeverRemove and ThresholdRemoval at two aggressiveness levels
(≥2/7d and ≥3/7d) and records training time and servers retired.

Seven simulation parameters swept:
  1. systematic_failure_rate_multiplier  [1, 2, 5, 10, 15, 20, 25, 30]
  2. manual_repair_fail_prob             [0.00, 0.20, 0.40, 0.60, 0.75, 0.90]
  3. working_pool_size  (headroom above  [4130, 4200, 4300, 4400, 4500, 4600, 4800]
     job_size + warm_standbys = 4112)
  4. systematic_failure_fraction         [0.01, 0.03, 0.05, 0.08, 0.12, 0.20]
  5. recovery_time (minutes)            [5, 10, 20, 40, 60, 90]
  6. auto_repair_fail_prob              [0.00, 0.20, 0.40, 0.60, 0.80]
  7. spare_pool_size                    [50, 100, 150, 200, 300, 500]

Base regime (held constant while each parameter varies):
  systematic_failure_rate_multiplier = 20×
  manual_repair_fail_prob            = 0.75
  working_pool_size                  = 4600  (488 headroom)
  systematic_failure_fraction        = 0.08  (~8% bad servers)
  recovery_time                      = 60 min
  auto_repair_fail_prob              = 0.60
  spare_pool_size                    = 200

Outputs (saved to examples/threshold_sensitivity_figures/):
  sweep_<param>.png         — one plot per parameter (Δtime + retired)
  overview.png              — single combined figure, all 7 sweeps
  sensitivity_summary.csv   — raw numbers for all cells

Expected runtime: ~20–30 minutes (8 reps × 44 cells × 3 policies).

Usage:
    python3 examples/threshold_sensitivity.py
"""

from __future__ import annotations

import csv
import os
import sys
import statistics
from dataclasses import dataclass, fields as dc_fields

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

from airesim.params import Params
from airesim.simulator import Simulator
from airesim.policies import NeverRemove, ThresholdRemoval

# ── Output ────────────────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "threshold_sensitivity_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Base (retirement-payoff regime) ──────────────────────────────────────────

DEFAULT_RATE = 0.01 / (24 * 60)
WINDOW       = 7 * 24 * 60
N_REPS       = 8

BASE = Params(
    job_size                           = 4096,
    warm_standbys                      = 16,
    working_pool_size                  = 4600,
    spare_pool_size                    = 200,
    job_length                         = 14 * 24 * 60,
    random_failure_rate                = 2 * DEFAULT_RATE,
    systematic_failure_rate_multiplier = 20.0,
    systematic_failure_fraction        = 0.08,
    recovery_time                      = 60.0,
    host_selection_time                = 3.0,
    preemption_wait_time               = 20.0,
    auto_repair_time                   = 120.0,
    manual_repair_time                 = 2880.0,
    prob_auto_to_manual                = 0.80,
    auto_repair_fail_prob              = 0.60,
    manual_repair_fail_prob            = 0.75,
    seed                               = 42,
    num_replications                   = N_REPS,
)

# Fix rate = P(auto success) + P(escalate)*P(manual success)
#          = (1-0.80)*(1-0.60) + 0.80*(1-0.75) ≈ 28%
BASE_FIX_RATE = (
    (1 - BASE.prob_auto_to_manual) * (1 - BASE.auto_repair_fail_prob)
    + BASE.prob_auto_to_manual * (1 - BASE.manual_repair_fail_prob)
)

THRESH_POLICIES = [
    ("Thresh ≥2/7d", ThresholdRemoval(max_failures=2, window_minutes=WINDOW)),
    ("Thresh ≥3/7d", ThresholdRemoval(max_failures=3, window_minutes=WINDOW)),
]


# ── Sweep definitions ─────────────────────────────────────────────────────────

@dataclass
class SweepDef:
    param:   str               # Params field name
    label:   str               # human-readable label
    values:  list              # values to sweep
    fmt:     callable          # x-tick formatter
    base_v:  object            # base value (highlighted on plots)
    x_note:  str = ""          # extra annotation for x-axis


def _headroom(pool: int) -> str:
    return f"+{pool - BASE.job_size - BASE.warm_standbys}"


SWEEPS: list[SweepDef] = [
    SweepDef(
        param  = "systematic_failure_rate_multiplier",
        label  = "Failure-rate multiplier",
        values = [1, 2, 5, 10, 15, 20, 25, 30],
        fmt    = lambda v: f"{v}×",
        base_v = 20,
    ),
    SweepDef(
        param  = "manual_repair_fail_prob",
        label  = "Manual repair fail prob",
        values = [0.00, 0.20, 0.40, 0.60, 0.75, 0.90],
        fmt    = str,
        base_v = 0.75,
    ),
    SweepDef(
        param  = "working_pool_size",
        label  = "Pool headroom (servers above minimum)",
        values = [4130, 4200, 4300, 4400, 4500, 4600, 4800],
        fmt    = _headroom,
        base_v = 4600,
        x_note = "headroom",
    ),
    SweepDef(
        param  = "systematic_failure_fraction",
        label  = "Bad-server fraction",
        values = [0.01, 0.03, 0.05, 0.08, 0.12, 0.20],
        fmt    = lambda v: f"{v:.0%}",
        base_v = 0.08,
    ),
    SweepDef(
        param  = "recovery_time",
        label  = "Recovery time (min/failure)",
        values = [5, 10, 20, 40, 60, 90],
        fmt    = str,
        base_v = 60,
    ),
    SweepDef(
        param  = "auto_repair_fail_prob",
        label  = "Auto repair fail prob",
        values = [0.00, 0.20, 0.40, 0.60, 0.80],
        fmt    = str,
        base_v = 0.60,
    ),
    SweepDef(
        param  = "spare_pool_size",
        label  = "Spare pool size",
        values = [50, 100, 150, 200, 300, 500],
        fmt    = str,
        base_v = 200,
    ),
]


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class CellResult:
    policy_name:    str
    param_name:     str
    param_value:    object
    mean_time:      float
    stdev_time:     float
    mean_retired:   float
    stdev_retired:  float
    depleted_frac:  float


def run_cell(policy, params: Params) -> tuple[float, float, float, float, float]:
    """Return (mean_time, stdev_time, mean_retired, stdev_retired, depleted_frac)."""
    times, retired, ndepleted = [], [], 0
    for rep in range(params.num_replications):
        r = Simulator(params=params, removal_policy=policy, seed=params.seed + rep).run()
        times.append(r.training_time_hours)
        retired.append(float(r.servers_retired))
        if r.cluster_depleted:
            ndepleted += 1
    n = len(times)
    return (
        statistics.mean(times),
        statistics.stdev(times) if n > 1 else 0.0,
        statistics.mean(retired),
        statistics.stdev(retired) if n > 1 else 0.0,
        ndepleted / n,
    )


# ── Plotting ──────────────────────────────────────────────────────────────────

THRESH_COLORS = {
    "Thresh ≥2/7d": "#C44E52",
    "Thresh ≥3/7d": "#4C72B0",
}
THRESH_MARKERS = {"Thresh ≥2/7d": "o", "Thresh ≥3/7d": "s"}


def plot_sweep(
    sd: SweepDef,
    baseline_by_value: dict,      # param_value → (mean, stdev)
    thresh_by_policy_value: dict,  # policy_name → {param_value → CellResult}
    filename: str,
) -> None:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    x_labels = [sd.fmt(v) for v in sd.values]
    fig, (ax_delta, ax_ret) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)

    for pol_name, pol_results in thresh_by_policy_value.items():
        color  = THRESH_COLORS[pol_name]
        marker = THRESH_MARKERS[pol_name]
        deltas  = [pol_results[v].mean_time - baseline_by_value[v][0] for v in sd.values]
        errors  = [(pol_results[v].stdev_time**2 + baseline_by_value[v][1]**2)**0.5
                   for v in sd.values]
        retired = [pol_results[v].mean_retired for v in sd.values]

        ax_delta.plot(x_labels, deltas, color=color, marker=marker,
                      linewidth=2, markersize=7, label=pol_name)
        ax_delta.fill_between(
            x_labels,
            [d - e for d, e in zip(deltas, errors)],
            [d + e for d, e in zip(deltas, errors)],
            color=color, alpha=0.12,
        )
        ax_ret.plot(x_labels, retired, color=color, marker=marker,
                    linewidth=2, markersize=7, label=pol_name)

        # Mark depleted points
        for i, v in enumerate(sd.values):
            if pol_results[v].depleted_frac > 0:
                ax_delta.annotate(
                    f"dep\n{pol_results[v].depleted_frac:.0%}",
                    (i, deltas[i]), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=7, color="darkred",
                )

    ax_delta.axhline(0, color="black", linewidth=1.2, linestyle="--",
                     label="NeverRemove baseline")
    ax_delta.fill_between(ax_delta.get_xlim(), -9999, 0,
                          color="#55A868", alpha=0.06, zorder=0,
                          label="_benefit region")

    # Mark base value
    if sd.base_v in sd.values:
        bx = x_labels[sd.values.index(sd.base_v)]
        for ax in (ax_delta, ax_ret):
            ax.axvline(bx, color="grey", linewidth=1, linestyle=":",
                       zorder=0, label="_base")

    ax_delta.set_ylabel("Δ Training Time vs NeverRemove (hrs)", fontsize=9)
    ax_delta.set_title(
        f"Retirement sensitivity — {sd.label}\n"
        f"(base regime: 20× mult, 75% repair fail, "
        f"{N_REPS} reps; ↓ negative = faster)",
        fontsize=9,
    )
    ax_delta.legend(fontsize=8)
    ax_delta.grid(alpha=0.3)

    ax_ret.set_ylabel("Mean Servers Retired", fontsize=9)
    ax_ret.set_xlabel(sd.label, fontsize=9)
    ax_ret.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(filename, dpi=150, bbox_inches="tight")
    plt.close()


def plot_overview(
    all_sweeps: list[tuple[SweepDef, dict, dict]],
) -> None:
    """Compact 7-row overview: each row is one parameter, showing Δtime for both thresholds."""
    import matplotlib.pyplot as plt
    import numpy as np

    n = len(all_sweeps)
    fig, axes = plt.subplots(n, 1, figsize=(11, 3 * n))
    fig.suptitle(
        "ThresholdRemoval — Sensitivity of Retirement Benefit\n"
        f"(base: 20× mult, 75% repair fail, 8% bad, 60-min recovery, {N_REPS} reps)",
        fontsize=11,
    )

    for ax, (sd, baseline_by_value, thresh_by_policy_value) in zip(axes, all_sweeps):
        x_labels = [sd.fmt(v) for v in sd.values]
        for pol_name, pol_results in thresh_by_policy_value.items():
            color  = THRESH_COLORS[pol_name]
            marker = THRESH_MARKERS[pol_name]
            deltas = [pol_results[v].mean_time - baseline_by_value[v][0] for v in sd.values]
            errors = [(pol_results[v].stdev_time**2 + baseline_by_value[v][1]**2)**0.5
                      for v in sd.values]
            ax.plot(x_labels, deltas, color=color, marker=marker,
                    linewidth=1.8, markersize=5, label=pol_name)
            ax.fill_between(x_labels,
                            [d - e for d, e in zip(deltas, errors)],
                            [d + e for d, e in zip(deltas, errors)],
                            color=color, alpha=0.10)
            # Mark depleted
            for i, v in enumerate(sd.values):
                if pol_results[v].depleted_frac > 0:
                    ax.text(i, deltas[i], "▲", ha="center", va="bottom",
                            fontsize=7, color="darkred")

        ax.axhline(0, color="black", linewidth=1, linestyle="--")
        ax.fill_between(range(len(sd.values)), -9999, 0,
                        color="#55A868", alpha=0.05, zorder=0)
        if sd.base_v in sd.values:
            bx = sd.values.index(sd.base_v)
            ax.axvline(bx, color="grey", linewidth=0.8, linestyle=":", zorder=0)

        ax.set_ylabel("Δ time (hrs)", fontsize=8)
        ax.set_xticks(range(len(x_labels)))
        ax.set_xticklabels(x_labels, fontsize=8)
        ax.set_title(sd.label, fontsize=9, loc="left", pad=2)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, loc="lower left")

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    path = fig_path("overview.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


# ── CSV export ────────────────────────────────────────────────────────────────

def write_csv(all_results: list[CellResult]) -> None:
    path = fig_path("sensitivity_summary.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "parameter", "param_value", "policy",
            "mean_time_hrs", "stdev_time_hrs",
            "mean_retired", "stdev_retired", "depleted_frac",
        ])
        for r in all_results:
            writer.writerow([
                r.param_name, r.param_value, r.policy_name,
                f"{r.mean_time:.2f}", f"{r.stdev_time:.2f}",
                f"{r.mean_retired:.1f}", f"{r.stdev_retired:.1f}",
                f"{r.depleted_frac:.2f}",
            ])
    print(f"  Saved → {path}")


# ── Crossover analysis ────────────────────────────────────────────────────────

def find_crossover(
    sd: SweepDef,
    baseline_by_value: dict,
    pol_results: dict,       # param_value → CellResult
) -> str:
    """Return a string describing where benefit first appears (Δ becomes negative)."""
    for v in sd.values:
        delta = pol_results[v].mean_time - baseline_by_value[v][0]
        if delta < 0 and pol_results[v].depleted_frac == 0:
            return sd.fmt(v)
    return "never (in range tested)"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("AIReSim — ThresholdRemoval Sensitivity Analysis")
    print("=" * 70)
    headroom = BASE.working_pool_size - BASE.job_size - BASE.warm_standbys
    bad_count = int((BASE.working_pool_size + BASE.spare_pool_size) * BASE.systematic_failure_fraction)
    print(f"  Base regime:")
    print(f"    working_pool_size = {BASE.working_pool_size}  (headroom {headroom})")
    print(f"    bad servers       = {bad_count} ({BASE.systematic_failure_fraction:.0%})")
    print(f"    multiplier        = {BASE.systematic_failure_rate_multiplier}×")
    print(f"    manual_fail_prob  = {BASE.manual_repair_fail_prob}  "
          f"(fix rate ≈ {BASE_FIX_RATE:.0%})")
    print(f"    recovery_time     = {BASE.recovery_time:.0f} min")
    print(f"    job_length        = {BASE.job_length/(24*60):.0f} days compute")
    print(f"    replications      = {N_REPS}")
    print()

    all_results: list[CellResult] = []
    all_sweep_data = []   # for overview plot

    for sd in SWEEPS:
        print(f"── Sweep: {sd.label} ──")
        print(f"   {'value':<14}  {'NeverRemove':<18}  "
              + "  ".join(f"{n:<25}" for n, _ in THRESH_POLICIES))
        print("   " + "-" * 85)

        baseline_by_value: dict = {}
        thresh_by_policy_value: dict = {n: {} for n, _ in THRESH_POLICIES}

        for v in sd.values:
            override = {sd.param: v}
            params = BASE.with_overrides(**override)

            # Baseline
            mt, st, mr, sr, df = run_cell(NeverRemove(), params)
            baseline_by_value[v] = (mt, st)
            all_results.append(CellResult("NeverRemove", sd.param, v, mt, st, mr, sr, df))

            line = f"   {sd.fmt(v):<14}  {mt:7.1f}±{st:5.1f}  "

            for pol_name, pol in THRESH_POLICIES:
                mt2, st2, mr2, sr2, df2 = run_cell(pol, params)
                delta = mt2 - mt
                dep   = f" dep{df2:.0%}" if df2 > 0 else ""
                thresh_by_policy_value[pol_name][v] = CellResult(
                    pol_name, sd.param, v, mt2, st2, mr2, sr2, df2
                )
                all_results.append(CellResult(pol_name, sd.param, v, mt2, st2, mr2, sr2, df2))
                sign  = "+" if delta >= 0 else ""
                line += f"  {sign}{delta:.1f}h / {mr2:.0f}ret{dep:<10}"

            print(line)

        # Crossover points
        print()
        for pol_name, pol_results in thresh_by_policy_value.items():
            co = find_crossover(sd, baseline_by_value, pol_results)
            print(f"   {pol_name} benefit starts at: {co}")
        print()

        # Per-parameter plot
        fname = fig_path(f"sweep_{sd.param}.png")
        plot_sweep(sd, baseline_by_value, thresh_by_policy_value, fname)
        print(f"   Saved → {fname}")
        print()

        all_sweep_data.append((sd, baseline_by_value, thresh_by_policy_value))

    # Overview plot
    print("Saving overview plot …")
    plot_overview(all_sweep_data)

    # CSV
    write_csv(all_results)

    # Crossover summary table
    print()
    print("=" * 70)
    print("Crossover summary — first value where retirement saves time (no depletion)")
    print("=" * 70)
    print(f"  {'Parameter':<40}  {'Thresh ≥2/7d':<20}  {'Thresh ≥3/7d'}")
    print("  " + "-" * 70)
    for sd, baseline_by_value, thresh_by_policy_value in all_sweep_data:
        co2 = find_crossover(sd, baseline_by_value, thresh_by_policy_value["Thresh ≥2/7d"])
        co3 = find_crossover(sd, baseline_by_value, thresh_by_policy_value["Thresh ≥3/7d"])
        print(f"  {sd.label:<40}  {co2:<20}  {co3}")

    print()
    print("=" * 70)
    print("Done. Output written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        kb = os.path.getsize(fig_path(fname)) // 1024
        print(f"  {fname}  ({kb} KB)")


if __name__ == "__main__":
    main()
