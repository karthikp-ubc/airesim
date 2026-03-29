"""
Cross-product comparison: scheduling policy × retirement policy.

Scheduling policies
  • Random          — DefaultHostSelection (uniform random)
  • FewestFailures  — FewestFailuresFirst (prefer servers with fewer total failures)
  • HighestScore    — HighestScoreFirst   (prefer servers with higher ScoredRemoval score)

Retirement policies
  • NeverRemove         — baseline, no retirement
  • ThresholdRemoval    — retire after ≥2 failures in any 7-day window (best threshold config)
  • ScoredRemoval       — retire after 2 cumulative failures (SC_fast: penalty=60, threshold=0)

All 3×3 = 9 combinations are tested in the payoff regime established by earlier analysis:
  systematic_failure_rate_multiplier = 20×  (bad TTF ≈ 2.4 days)
  manual_repair_fail_prob = 0.75            (effective fix rate ≈ 28 %)
  working_pool_size = 4600                  (488 servers above the 4112 minimum)

For HighestScoreFirst + NeverRemove / ThresholdRemoval:
  A ScoredRemoval instance (retirement_threshold=-inf) provides scores for the
  scheduler while CompositeRemovalPolicy delegates the actual retirement decision
  to the intended policy.

Outputs (saved to examples/scheduling_comparison_figures/):
  results.csv           — raw data for all 9 combinations
  heatmap_delta.png     — Δ training time vs Random+NeverRemove baseline (3×3 heatmap)
  bars_by_retirement.png — grouped bar chart, grouped by retirement policy
  bars_by_scheduling.png — grouped bar chart, grouped by scheduling policy

Expected runtime: ~10–15 minutes.

Usage:
    python3 examples/scheduling_comparison.py
"""

from __future__ import annotations

import os
import sys
import csv
import statistics
from dataclasses import dataclass, field

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from airesim.params import Params
from airesim.simulator import Simulator
from airesim.policies import (
    NeverRemove, ThresholdRemoval, ScoredRemoval, CompositeRemovalPolicy,
)
from airesim.scheduling_policies import (
    DefaultHostSelection, FewestFailuresFirst, HighestScoreFirst,
)

# ── Output ─────────────────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "scheduling_comparison_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Payoff-regime base parameters ─────────────────────────────────────────────

DEFAULT_RATE = 0.01 / (24 * 60)
WINDOW       = 7 * 24 * 60      # 7-day rolling window for ThresholdRemoval

N_REPS = 15

BASE = Params(
    job_size              = 4096,
    warm_standbys         = 16,
    working_pool_size     = 4600,
    spare_pool_size       = 200,
    job_length            = 14 * 24 * 60,
    random_failure_rate   = 2 * DEFAULT_RATE,
    systematic_failure_rate_multiplier = 20.0,
    systematic_failure_fraction        = 0.08,
    recovery_time         = 60.0,
    host_selection_time   = 3.0,
    preemption_wait_time  = 20.0,
    auto_repair_time      = 120.0,
    manual_repair_time    = 2880.0,
    prob_auto_to_manual   = 0.80,
    auto_repair_fail_prob = 0.60,
    manual_repair_fail_prob = 0.75,
    seed                  = 42,
    num_replications      = N_REPS,
)


# ── Policy factories ───────────────────────────────────────────────────────────

def _sc_fast(retirement_threshold: float = 0.0) -> ScoredRemoval:
    """SC_fast: retire after 2 cumulative failures (ceil(100/60)=2)."""
    return ScoredRemoval(
        initial_score        = 100.0,
        failure_penalty      = 60.0,
        success_increment    = 10.0,
        time_period          = 24 * 60,
        retirement_threshold = retirement_threshold,
    )


@dataclass
class Config:
    label: str              # short label for plots
    sched_label: str        # scheduling policy name
    retire_label: str       # retirement policy name


def make_config(sched_name: str, retire_name: str):
    """
    Build (host_selection_policy, removal_policy, Config) for one combination.

    For HighestScoreFirst paired with NeverRemove or ThresholdRemoval we need a
    ScoredRemoval for score-tracking only (retirement_threshold=-inf so it never
    retires), wired via CompositeRemovalPolicy so that on_failure/on_success hooks
    reach the scorer.
    """
    retire_label = retire_name
    sched_label  = sched_name

    # ── Build retirement policy ────────────────────────────────────────────────
    if retire_name == "NeverRemove":
        retire_policy = NeverRemove()
    elif retire_name == "ThresholdRemoval":
        retire_policy = ThresholdRemoval(max_failures=2, window_minutes=WINDOW)
    else:  # ScoredRemoval
        retire_policy = _sc_fast(retirement_threshold=0.0)

    # ── Build scheduling policy ────────────────────────────────────────────────
    if sched_name == "Random":
        sched_policy = DefaultHostSelection()

    elif sched_name == "FewestFailures":
        sched_policy = FewestFailuresFirst()

    else:  # HighestScore
        if retire_name == "ScoredRemoval":
            # Natural pairing: the scorer IS the retirement policy.
            scorer = retire_policy          # type: ScoredRemoval
        else:
            # Separate scorer (never retires) + composite retirement policy.
            scorer = _sc_fast(retirement_threshold=float("-inf"))
            retire_policy = CompositeRemovalPolicy(
                primary   = retire_policy,
                secondary = scorer,
            )
        sched_policy = HighestScoreFirst(scorer)

    label = f"{sched_name}\n+{retire_label}"
    cfg = Config(label=label, sched_label=sched_label, retire_label=retire_label)
    return sched_policy, retire_policy, cfg


# ── Simulation runner ──────────────────────────────────────────────────────────

@dataclass
class RunResult:
    cfg: Config
    times: list[float] = field(default_factory=list)
    retired: list[float] = field(default_factory=list)
    depleted: int = 0

    @property
    def mean_time(self) -> float:
        return statistics.mean(self.times)

    @property
    def stdev_time(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0.0

    @property
    def mean_retired(self) -> float:
        return statistics.mean(self.retired)

    @property
    def depleted_frac(self) -> float:
        return self.depleted / len(self.times)


def run_config(sched_policy, retire_policy, cfg: Config, params: Params) -> RunResult:
    result = RunResult(cfg=cfg)
    sim = Simulator(
        params                = params,
        host_selection_policy = sched_policy,
        removal_policy        = retire_policy,
        seed                  = params.seed,
    )
    for rep in range(params.num_replications):
        sim.seed = params.seed + rep
        stats = sim.run()
        result.times.append(stats.total_training_time / 60)  # → hours
        result.retired.append(stats.servers_retired)
        if stats.cluster_depleted:
            result.depleted += 1
    return result


# ── Plotting ───────────────────────────────────────────────────────────────────

SCHED_NAMES   = ["Random", "FewestFailures", "HighestScore"]
RETIRE_NAMES  = ["NeverRemove", "ThresholdRemoval", "ScoredRemoval"]

SCHED_COLORS  = {
    "Random":        "#4878CF",
    "FewestFailures":"#6ACC65",
    "HighestScore":  "#D65F5F",
}
RETIRE_HATCHES = {
    "NeverRemove":      "",
    "ThresholdRemoval": "//",
    "ScoredRemoval":    "xx",
}
RETIRE_DISPLAY = {
    "NeverRemove":      "NeverRemove",
    "ThresholdRemoval": "Thresh ≥2/7d",
    "ScoredRemoval":    "SC_fast",
}


def plot_heatmap(results: dict[tuple, RunResult], baseline_mean: float) -> None:
    """3×3 heatmap: rows=scheduling, cols=retirement, cell=Δ vs Random+NeverRemove."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))

    delta_matrix  = np.zeros((3, 3))
    time_matrix   = np.zeros((3, 3))
    retire_matrix = np.zeros((3, 3))

    for ri, rn in enumerate(RETIRE_NAMES):
        for si, sn in enumerate(SCHED_NAMES):
            res = results[(sn, rn)]
            delta_matrix[si, ri]  = res.mean_time - baseline_mean
            time_matrix[si, ri]   = res.mean_time
            retire_matrix[si, ri] = res.mean_retired

    col_labels = [RETIRE_DISPLAY[r] for r in RETIRE_NAMES]
    row_labels = SCHED_NAMES

    # Left: Δ vs baseline
    ax = axes[0]
    vmax = max(abs(delta_matrix.min()), abs(delta_matrix.max()))
    im = ax.imshow(delta_matrix, cmap="RdYlGn_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(3)); ax.set_xticklabels(col_labels, fontsize=10)
    ax.set_yticks(range(3)); ax.set_yticklabels(row_labels, fontsize=10)
    ax.set_title("Δ Training Time vs Random+NeverRemove (hrs)\n(green = faster)", fontsize=11)
    for si in range(3):
        for ri in range(3):
            val = delta_matrix[si, ri]
            ax.text(ri, si, f"{val:+.0f}h", ha="center", va="center",
                    fontsize=10, fontweight="bold",
                    color="white" if abs(val) > vmax * 0.55 else "black")
    plt.colorbar(im, ax=ax, shrink=0.8)

    # Right: servers retired
    ax2 = axes[1]
    im2 = ax2.imshow(retire_matrix, cmap="Blues", aspect="auto")
    ax2.set_xticks(range(3)); ax2.set_xticklabels(col_labels, fontsize=10)
    ax2.set_yticks(range(3)); ax2.set_yticklabels(row_labels, fontsize=10)
    ax2.set_title("Mean Servers Retired", fontsize=11)
    for si in range(3):
        for ri in range(3):
            ax2.text(ri, si, f"{retire_matrix[si, ri]:.0f}", ha="center", va="center",
                     fontsize=10, fontweight="bold",
                     color="white" if retire_matrix[si, ri] > retire_matrix.max() * 0.6 else "black")
    plt.colorbar(im2, ax=ax2, shrink=0.8)

    fig.suptitle("Scheduling × Retirement Policy Comparison (20× multiplier, 75% repair fail prob)",
                 fontsize=12, y=1.01)
    fig.tight_layout()
    path = fig_path("heatmap.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {path}")


def plot_grouped_bars(results: dict[tuple, RunResult],
                      groupby: str) -> None:
    """Grouped bar chart.  groupby='retirement' or groupby='scheduling'."""
    if groupby == "retirement":
        groups     = RETIRE_NAMES
        within     = SCHED_NAMES
        get_result = lambda g, w: results[(w, g)]
        group_disp = RETIRE_DISPLAY
        bar_color  = lambda w: SCHED_COLORS[w]
        bar_hatch  = lambda w: ""
        legend_label = lambda w: w
        xlabel = "Retirement policy"
    else:
        groups     = SCHED_NAMES
        within     = RETIRE_NAMES
        get_result = lambda g, w: results[(g, w)]
        group_disp = {s: s for s in SCHED_NAMES}
        bar_color  = lambda w: "#888888"
        bar_hatch  = lambda w: RETIRE_HATCHES[w]
        legend_label = lambda w: RETIRE_DISPLAY[w]
        xlabel = "Scheduling policy"

    n_groups = len(groups)
    n_bars   = len(within)
    width    = 0.8 / n_bars
    x        = np.arange(n_groups)

    fig, (ax_time, ax_ret) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    for i, w in enumerate(within):
        means  = [get_result(g, w).mean_time   for g in groups]
        stdevs = [get_result(g, w).stdev_time  for g in groups]
        retired= [get_result(g, w).mean_retired for g in groups]
        offsets = x + (i - n_bars / 2 + 0.5) * width

        ax_time.bar(offsets, means, width * 0.9,
                    color=bar_color(w), hatch=bar_hatch(w),
                    label=legend_label(w),
                    yerr=stdevs, capsize=3, error_kw={"elinewidth": 0.8})
        ax_ret.bar(offsets, retired, width * 0.9,
                   color=bar_color(w), hatch=bar_hatch(w))

    ax_time.set_ylabel("Mean training time (hrs)", fontsize=10)
    ax_time.set_title(
        f"Training time by {xlabel.lower()}  (20× multiplier, 75% repair fail prob)",
        fontsize=11
    )
    ax_time.legend(title=("Scheduling" if groupby == "retirement" else "Retirement"),
                   fontsize=9, loc="upper right")
    ax_time.set_xticks(x)
    ax_time.set_xticklabels([group_disp[g] for g in groups], fontsize=10)
    ax_time.yaxis.grid(True, alpha=0.4)

    ax_ret.set_ylabel("Mean servers retired", fontsize=10)
    ax_ret.set_xlabel(xlabel, fontsize=10)
    ax_ret.set_xticks(x)
    ax_ret.set_xticklabels([group_disp[g] for g in groups], fontsize=10)
    ax_ret.yaxis.grid(True, alpha=0.4)

    fig.tight_layout()
    fname = f"bars_by_{groupby}.png"
    path = fig_path(fname)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {path}")


def save_csv(results: dict[tuple, RunResult]) -> None:
    path = fig_path("results.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "scheduling", "retirement",
            "mean_time_hrs", "stdev_time_hrs",
            "mean_retired", "stdev_retired", "depleted_frac",
        ])
        for (sn, rn), res in sorted(results.items()):
            writer.writerow([
                sn, rn,
                f"{res.mean_time:.2f}",
                f"{res.stdev_time:.2f}",
                f"{res.mean_retired:.1f}",
                f"{statistics.stdev(res.retired) if len(res.retired)>1 else 0.0:.1f}",
                f"{res.depleted_frac:.2f}",
            ])
    print(f"  Saved → {path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    results: dict[tuple, RunResult] = {}

    print("=" * 70)
    print("Scheduling × Retirement policy comparison")
    print(f"Regime: 20× multiplier | 75% manual repair fail | 4600-server pool")
    print(f"Replications per cell: {N_REPS}")
    print("=" * 70)

    header = f"  {'Scheduling':<16} {'Retirement':<18} {'Mean (hrs)':>12} {'Std':>7} {'Retired':>9} {'Depleted':>9}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for sched_name in SCHED_NAMES:
        for retire_name in RETIRE_NAMES:
            sched_policy, retire_policy, cfg = make_config(sched_name, retire_name)
            res = run_config(sched_policy, retire_policy, cfg, BASE)
            results[(sched_name, retire_name)] = res

            depleted_str = f"{res.depleted_frac*100:.0f}% depleted" if res.depleted > 0 else ""
            print(f"  {sched_name:<16} {retire_name:<18}"
                  f" {res.mean_time:>10.1f}h"
                  f" ±{res.stdev_time:>5.1f}"
                  f" {res.mean_retired:>8.1f}ret"
                  f"  {depleted_str}")

    print()
    baseline = results[("Random", "NeverRemove")]
    print(f"Baseline (Random+NeverRemove): {baseline.mean_time:.1f} ± {baseline.stdev_time:.1f} hrs")
    print()
    print("Δ vs baseline (negative = faster):")
    for sn in SCHED_NAMES:
        for rn in RETIRE_NAMES:
            res = results[(sn, rn)]
            delta = res.mean_time - baseline.mean_time
            print(f"  {sn:<16} + {rn:<18}  {delta:+.1f}h  ({res.mean_retired:.0f} retired)")

    print()
    print("Saving plots …")
    plot_heatmap(results, baseline.mean_time)
    plot_grouped_bars(results, groupby="retirement")
    plot_grouped_bars(results, groupby="scheduling")
    save_csv(results)

    print()
    print("=" * 70)
    print(f"Done. Output written to: {FIGURES_DIR}")
    for f in os.listdir(FIGURES_DIR):
        size_kb = os.path.getsize(os.path.join(FIGURES_DIR, f)) // 1024
        print(f"  {f}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
