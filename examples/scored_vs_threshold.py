"""ScoredRemoval vs ThresholdRemoval in the retirement-payoff regime.

Uses the same parameter regime established in retirement_payoff.py:
  systematic_failure_rate_multiplier = 20×   (bad TTF ≈ 2.4 days)
  manual_repair_fail_prob = 0.75             (effective fix rate ≈ 28 %)
  working_pool_size = 4600                   (488 headroom)

ScoredRemoval configurations are calibrated against the bad/good server TTF
ratio in this regime (bad ≈ 2.4 d, good ≈ 50 d):

  SC_fast       — time_period=1d  → bad earns 2 credits/cycle, good earns 50.
                  Net for bad = −40/cycle → retires in ~2.5 cycles (~6 days).
  SC_moderate   — penalty lighter, takes ~5 cycles (~12 days) to retire.
  SC_long_period — time_period=4d > bad TTF → bad earns 0 credits → retired
                  after just 2 failures.  Good servers (TTF=50d) earn 12
                  credits per run — their scores climb indefinitely.
  SC_calibrated — time_period=3d, a sharper version of SC_long_period.

Three experiments:
  1. Head-to-head comparison of all policies at the payoff regime.
  2. Benefit vs systematic_failure_rate_multiplier [5–30×].
  3. Benefit vs manual_repair_fail_prob [0.20–0.90].

Outputs (saved to examples/scored_vs_threshold_figures/):
  head_to_head.png          — full policy comparison (Section 1)
  vs_multiplier.png         — Δ training time vs failure-rate multiplier
  vs_repair_fail_prob.png   — Δ training time vs manual repair fail prob
  vs_multiplier_retired.png — servers retired vs failure-rate multiplier

Expected runtime: ~8–12 minutes.

Usage:
    python3 examples/scored_vs_threshold.py
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
from airesim.policies import NeverRemove, ThresholdRemoval, ScoredRemoval

# ── Output ────────────────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "scored_vs_threshold_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Payoff-regime base parameters ────────────────────────────────────────────

DEFAULT_RATE = 0.01 / (24 * 60)
WINDOW       = 7 * 24 * 60      # 7-day rolling window

N_REPS = 15                     # replications per data point

BASE = Params(
    job_size              = 4096,
    warm_standbys         = 16,
    working_pool_size     = 4600,           # 488 headroom above minimum (4112)
    spare_pool_size       = 200,
    job_length            = 14 * 24 * 60,   # 14 days compute time
    random_failure_rate   = 2 * DEFAULT_RATE,
    systematic_failure_rate_multiplier = 20.0,
    systematic_failure_fraction        = 0.08,   # 8 % bad ≈ 368 bad servers
    recovery_time         = 60.0,
    host_selection_time   = 3.0,
    preemption_wait_time  = 20.0,
    auto_repair_time      = 120.0,
    manual_repair_time    = 2880.0,
    prob_auto_to_manual   = 0.80,
    auto_repair_fail_prob = 0.60,
    manual_repair_fail_prob = 0.75,          # 72 % of repairs don't actually fix it
    seed                  = 42,
    num_replications      = N_REPS,
)

# Bad server mean TTF (minutes) at BASE:
#   rate = 2*DEFAULT_RATE * (1 + 20) = 2*DEFAULT_RATE*21 = 0.02*21/1440 per min
#   TTF  = 1/rate ≈ 3429 min ≈ 2.4 days
BAD_SERVER_TTF_DAYS  = 1.0 / (BASE.random_failure_rate * (1 + BASE.systematic_failure_rate_multiplier) * 24 * 60)
GOOD_SERVER_TTF_DAYS = 1.0 / (BASE.random_failure_rate * 24 * 60)


# ── Policy catalogue ──────────────────────────────────────────────────────────
#
# ThresholdRemoval: retire if ≥ N failures in any rolling 7-day window.
# ScoredRemoval calibrated for the regime:
#   bad  TTF ≈ 2.4 days, good TTF ≈ 50 days.
#
# For ScoredRemoval the "credits per bad-server cycle" depends on time_period:
#   time_period=1d : floor(2.4) = 2 credits per run → some positive reinforcement
#   time_period=3d : floor(2.4/3) = 0 credits  → bad servers are purely penalised
#   time_period=4d : floor(2.4/4) = 0 credits  → same
#
# ┌──────────────────┬──────┬──────┬───────────┬───────────┬──────────┬───────────────────┐
# │ config           │ init │ pen  │ increment │ period(d) │ thresh   │ bad cycles→retire │
# ├──────────────────┼──────┼──────┼───────────┼───────────┼──────────┼───────────────────┤
# │ SC_fast          │ 100  │  60  │    10     │   1       │   0      │ ~2.5 (~6 days)    │
# │ SC_moderate      │ 100  │  50  │    15     │   1       │   0      │ ~5   (~12 days)   │
# │ SC_long_period   │ 100  │  50  │    10     │   4       │   0      │  2   (pure pen.)  │
# │ SC_calibrated    │ 100  │  40  │    10     │   3       │   0      │  2-3 (pure pen.)  │
# └──────────────────┴──────┴──────┴───────────┴───────────┴──────────┴───────────────────┘

POLICIES: list[tuple[str, str, object]] = [
    # (display_name, group, policy_object)
    ("NeverRemove",          "baseline",   NeverRemove()),
    ("Thresh ≥5/7d",         "threshold",  ThresholdRemoval(max_failures=5, window_minutes=WINDOW)),
    ("Thresh ≥3/7d",         "threshold",  ThresholdRemoval(max_failures=3, window_minutes=WINDOW)),
    ("Thresh ≥2/7d",         "threshold",  ThresholdRemoval(max_failures=2, window_minutes=WINDOW)),
    ("Thresh ≥1/7d",         "threshold",  ThresholdRemoval(max_failures=1, window_minutes=WINDOW)),
    ("SC_fast",              "scored",     ScoredRemoval(initial_score=100, failure_penalty=60,
                                                         success_increment=10, time_period=1*24*60,
                                                         retirement_threshold=0)),
    ("SC_moderate",          "scored",     ScoredRemoval(initial_score=100, failure_penalty=50,
                                                         success_increment=15, time_period=1*24*60,
                                                         retirement_threshold=0)),
    ("SC_long_period",       "scored",     ScoredRemoval(initial_score=100, failure_penalty=50,
                                                         success_increment=10, time_period=4*24*60,
                                                         retirement_threshold=0)),
    ("SC_calibrated",        "scored",     ScoredRemoval(initial_score=100, failure_penalty=40,
                                                         success_increment=10, time_period=3*24*60,
                                                         retirement_threshold=0)),
]

GROUP_COLORS = {
    "baseline":  "#888888",
    "threshold": "#4C72B0",
    "scored":    "#C44E52",
}


# ── Data containers ───────────────────────────────────────────────────────────

@dataclass
class PolicyResult:
    name:           str
    group:          str
    mean_time:      float
    stdev_time:     float
    mean_retired:   float
    stdev_retired:  float
    depleted_frac:  float


def run_policy(policy, params: Params, name: str = "", group: str = "") -> PolicyResult:
    times, retired, depleted = [], [], 0
    for rep in range(params.num_replications):
        r = Simulator(params=params, removal_policy=policy, seed=params.seed + rep).run()
        times.append(r.training_time_hours)
        retired.append(float(r.servers_retired))
        if r.cluster_depleted:
            depleted += 1
    n = len(times)
    return PolicyResult(
        name          = name,
        group         = group,
        mean_time     = statistics.mean(times),
        stdev_time    = statistics.stdev(times) if n > 1 else 0.0,
        mean_retired  = statistics.mean(retired),
        stdev_retired = statistics.stdev(retired) if n > 1 else 0.0,
        depleted_frac = depleted / n,
    )


# ── Plotting helpers ──────────────────────────────────────────────────────────

def plot_head_to_head(results: list[PolicyResult]) -> None:
    """Grouped bar chart: training time and servers retired for every policy."""
    import matplotlib.pyplot as plt
    import numpy as np

    names   = [r.name         for r in results]
    times   = [r.mean_time    for r in results]
    t_err   = [r.stdev_time   for r in results]
    retired = [r.mean_retired for r in results]
    r_err   = [r.stdev_retired for r in results]
    colors  = [GROUP_COLORS[r.group] for r in results]
    baseline_time = results[0].mean_time

    x = np.arange(len(results))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)

    # ── Training time ──────────────────────────────────────────────────
    bars = ax1.bar(x, times, color=colors, edgecolor="black", alpha=0.85)
    ax1.errorbar(x, times, yerr=t_err, fmt="none", capsize=4,
                 color="black", linewidth=1.2)
    ax1.axhline(baseline_time, color="grey", linestyle="--", linewidth=1,
                label=f"NeverRemove = {baseline_time:.0f} h")

    for i, r in enumerate(results):
        delta = r.mean_time - baseline_time
        sign  = "+" if delta >= 0 else ""
        label = f"{sign}{delta:.0f}h"
        if r.depleted_frac > 0:
            label += f"\n({r.depleted_frac:.0%} dep.)"
        y_off = r.mean_time + r.stdev_time + 5
        ax1.text(i, y_off, label, ha="center", va="bottom", fontsize=7.5)

    ax1.set_ylabel("Mean Training Time (hrs)", fontsize=10)
    ax1.set_title("Head-to-head: ThresholdRemoval vs ScoredRemoval\n"
                  f"Payoff regime  (20× multiplier, 75% manual repair fail prob, "
                  f"{N_REPS} reps)", fontsize=10)
    ax1.legend(fontsize=9)
    ax1.grid(axis="y", alpha=0.3)

    # ── Servers retired ────────────────────────────────────────────────
    ax2.bar(x, retired, color=colors, edgecolor="black", alpha=0.85)
    ax2.errorbar(x, retired, yerr=r_err, fmt="none", capsize=4,
                 color="black", linewidth=1.2)
    for i, r in enumerate(results):
        if r.mean_retired > 0:
            ax2.text(i, r.mean_retired + 1, f"{r.mean_retired:.0f}",
                     ha="center", va="bottom", fontsize=7.5)

    ax2.set_ylabel("Mean Servers Retired", fontsize=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=25, ha="right", fontsize=9)
    ax2.grid(axis="y", alpha=0.3)

    # Legend patches for groups
    import matplotlib.patches as mpatches
    legend_patches = [mpatches.Patch(color=c, label=g)
                      for g, c in GROUP_COLORS.items()]
    fig.legend(handles=legend_patches, loc="upper right", fontsize=8,
               bbox_to_anchor=(0.98, 0.98))

    plt.tight_layout()
    path = fig_path("head_to_head.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


def plot_sweep(
    x_values:      list,
    x_label:       str,
    results_by_policy: dict[str, list[PolicyResult]],
    baseline_results:  list[PolicyResult],
    filename:      str,
    title:         str,
    x_formatter:   callable = str,
) -> None:
    """Line plot: Δ training time vs a swept parameter, one line per policy."""
    import matplotlib.pyplot as plt
    import numpy as np

    fig, (ax_delta, ax_retired) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    x_ticks = [x_formatter(v) for v in x_values]

    # Colour and marker per policy
    line_styles = {
        "NeverRemove":    ("#888888", "o",  "--"),
        "Thresh ≥5/7d":  ("#4C72B0", "s",  ":"),
        "Thresh ≥3/7d":  ("#4C72B0", "^",  "-."),
        "Thresh ≥2/7d":  ("#4C72B0", "D",  "-"),
        "Thresh ≥1/7d":  ("#4C72B0", "v",  ":"),
        "SC_fast":        ("#C44E52", "o",  "-"),
        "SC_moderate":    ("#DD8452", "s",  "-"),
        "SC_long_period": ("#E05555", "^",  "--"),
        "SC_calibrated":  ("#A0111F", "D",  "-."),
    }

    baseline_times = [r.mean_time for r in baseline_results]

    for pol_name, pol_results in results_by_policy.items():
        color, marker, ls = line_styles.get(pol_name, ("#333333", "o", "-"))
        deltas  = [r.mean_time - b for r, b in zip(pol_results, baseline_times)]
        errors  = [(r.stdev_time**2 + b.stdev_time**2)**0.5
                   for r, b in zip(pol_results, baseline_results)]
        retired = [r.mean_retired for r in pol_results]

        ax_delta.plot(x_ticks, deltas, color=color, marker=marker,
                      linestyle=ls, label=pol_name, linewidth=1.8, markersize=6)
        ax_delta.fill_between(
            x_ticks,
            [d - e for d, e in zip(deltas, errors)],
            [d + e for d, e in zip(deltas, errors)],
            color=color, alpha=0.1,
        )
        ax_retired.plot(x_ticks, retired, color=color, marker=marker,
                        linestyle=ls, label=pol_name, linewidth=1.8, markersize=6)

    ax_delta.axhline(0, color="black", linewidth=1, linestyle="--")
    ax_delta.set_ylabel("Δ Mean Training Time vs NeverRemove (hrs)", fontsize=10)
    ax_delta.set_title(title, fontsize=10)
    ax_delta.legend(fontsize=8, loc="best")
    ax_delta.grid(alpha=0.3)

    ax_retired.set_ylabel("Mean Servers Retired", fontsize=10)
    ax_retired.set_xlabel(x_label, fontsize=10)
    ax_retired.grid(alpha=0.3)

    # Shade the "better than NeverRemove" region
    ax_delta.fill_between(ax_delta.get_xlim(), -1000, 0,
                          color="green", alpha=0.04, zorder=0)

    plt.tight_layout()
    path = fig_path(filename)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


# ── Printing helpers ──────────────────────────────────────────────────────────

def print_results_table(results: list[PolicyResult], baseline_time: float) -> None:
    print(f"  {'Policy':<22}  {'Time (hrs)':<20}  {'Δ vs Never':<12}  {'Retired':<14}  Dep.")
    print("  " + "-" * 76)
    for r in results:
        delta    = r.mean_time - baseline_time
        dep_str  = f"{r.depleted_frac:.0%}" if r.depleted_frac > 0 else ""
        marker   = " ◀ best" if delta == min(res.mean_time - baseline_time
                                              for res in results
                                              if res.depleted_frac == 0) else ""
        print(f"  {r.name:<22}  "
              f"{r.mean_time:7.1f} ±{r.stdev_time:5.1f}   "
              f"{delta:+8.1f}h     "
              f"{r.mean_retired:5.1f} ±{r.stdev_retired:4.1f}   "
              f"{dep_str:<6}{marker}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    bad_ttf  = BAD_SERVER_TTF_DAYS
    good_ttf = GOOD_SERVER_TTF_DAYS
    headroom = BASE.working_pool_size - BASE.job_size - BASE.warm_standbys
    bad_count = int((BASE.working_pool_size + BASE.spare_pool_size)
                    * BASE.systematic_failure_fraction)

    print("AIReSim — ScoredRemoval vs ThresholdRemoval")
    print("=" * 70)
    print(f"  working_pool_size  : {BASE.working_pool_size}  (headroom = {headroom})")
    print(f"  bad servers        : {bad_count} ({BASE.systematic_failure_fraction:.0%} of pool)")
    print(f"  bad  server TTF    : {bad_ttf:.1f} days")
    print(f"  good server TTF    : {good_ttf:.0f} days")
    print(f"  manual repair fail : {BASE.manual_repair_fail_prob} "
          f"(effective fix rate ≈ "
          f"{(1-BASE.prob_auto_to_manual)*(1-BASE.auto_repair_fail_prob) + BASE.prob_auto_to_manual*(1-BASE.manual_repair_fail_prob):.0%})")
    print(f"  replications       : {N_REPS}")
    print()


    # ═══════════════════════════════════════════════════════════════════════
    # Section 1: Head-to-head at the payoff regime
    # ═══════════════════════════════════════════════════════════════════════
    print("─── Section 1: Head-to-head comparison ───")
    print()

    s1_results: list[PolicyResult] = []
    for name, group, policy in POLICIES:
        print(f"  {name:<22} …", end=" ", flush=True)
        r = run_policy(policy, BASE, name=name, group=group)
        dep = f"  [depleted {r.depleted_frac:.0%}]" if r.depleted_frac > 0 else ""
        print(f"time={r.mean_time:7.1f}±{r.stdev_time:4.1f}h  "
              f"retired={r.mean_retired:5.1f}±{r.stdev_retired:3.1f}{dep}")
        s1_results.append(r)

    baseline_time = s1_results[0].mean_time
    print()
    print_results_table(s1_results, baseline_time)

    # Identify winners
    non_depleted = [r for r in s1_results if r.depleted_frac == 0]
    best_thresh  = min((r for r in non_depleted if r.group == "threshold"),
                       key=lambda r: r.mean_time, default=None)
    best_scored  = min((r for r in non_depleted if r.group == "scored"),
                       key=lambda r: r.mean_time, default=None)
    print()
    if best_thresh:
        print(f"  Best ThresholdRemoval : {best_thresh.name}  "
              f"({best_thresh.mean_time:.1f}h, "
              f"Δ={best_thresh.mean_time - baseline_time:+.1f}h, "
              f"retired={best_thresh.mean_retired:.0f})")
    if best_scored:
        print(f"  Best ScoredRemoval    : {best_scored.name}  "
              f"({best_scored.mean_time:.1f}h, "
              f"Δ={best_scored.mean_time - baseline_time:+.1f}h, "
              f"retired={best_scored.mean_retired:.0f})")
    if best_thresh and best_scored:
        diff = best_scored.mean_time - best_thresh.mean_time
        winner = "ScoredRemoval" if diff < 0 else "ThresholdRemoval"
        print(f"  Head-to-head winner   : {winner}  "
              f"(Δ = {abs(diff):.1f}h)")


    # ═══════════════════════════════════════════════════════════════════════
    # Section 2: Δtime vs systematic_failure_rate_multiplier
    # ═══════════════════════════════════════════════════════════════════════
    print()
    print("─── Section 2: Benefit vs systematic_failure_rate_multiplier ───")
    print()

    MULTIPLIERS = [5, 10, 15, 20, 25, 30]

    # Policies to compare in sweeps: NeverRemove + best Threshold + all Scored
    sweep_policies = (
        [("NeverRemove", "baseline", NeverRemove())]
        + [(n, g, p) for n, g, p in POLICIES if g == "threshold" and n in ("Thresh ≥3/7d", "Thresh ≥2/7d")]
        + [(n, g, p) for n, g, p in POLICIES if g == "scored"]
    )

    sweep2_results: dict[str, list[PolicyResult]] = {n: [] for n, _, _ in sweep_policies}
    sweep2_baseline: list[PolicyResult] = []

    for mult in MULTIPLIERS:
        params = BASE.with_overrides(systematic_failure_rate_multiplier=mult)
        print(f"  multiplier = {mult}×")
        for name, group, policy in sweep_policies:
            r = run_policy(policy, params, name=name, group=group)
            sweep2_results[name].append(r)
            dep = f" [dep {r.depleted_frac:.0%}]" if r.depleted_frac > 0 else ""
            print(f"    {name:<22}  Δ={r.mean_time - sweep2_results['NeverRemove'][-1].mean_time:+.1f}h"
                  f"  retired={r.mean_retired:.0f}{dep}")
        sweep2_baseline.append(sweep2_results["NeverRemove"][-1])
        print()


    # ═══════════════════════════════════════════════════════════════════════
    # Section 3: Δtime vs manual_repair_fail_prob
    # ═══════════════════════════════════════════════════════════════════════
    print("─── Section 3: Benefit vs manual_repair_fail_prob ───")
    print()

    REPAIR_FAIL_PROBS = [0.20, 0.40, 0.60, 0.75, 0.90]

    sweep3_results: dict[str, list[PolicyResult]] = {n: [] for n, _, _ in sweep_policies}
    sweep3_baseline: list[PolicyResult] = []

    for fail_prob in REPAIR_FAIL_PROBS:
        params = BASE.with_overrides(manual_repair_fail_prob=fail_prob)
        fix_rate = (1 - BASE.prob_auto_to_manual) * (1 - BASE.auto_repair_fail_prob) \
                 + BASE.prob_auto_to_manual * (1 - fail_prob)
        print(f"  manual_repair_fail_prob = {fail_prob}  (fix rate ≈ {fix_rate:.0%})")
        for name, group, policy in sweep_policies:
            r = run_policy(policy, params, name=name, group=group)
            sweep3_results[name].append(r)
            dep = f" [dep {r.depleted_frac:.0%}]" if r.depleted_frac > 0 else ""
            print(f"    {name:<22}  Δ={r.mean_time - sweep3_results['NeverRemove'][-1].mean_time:+.1f}h"
                  f"  retired={r.mean_retired:.0f}{dep}")
        sweep3_baseline.append(sweep3_results["NeverRemove"][-1])
        print()


    # ═══════════════════════════════════════════════════════════════════════
    # Analysis: when does ScoredRemoval outperform ThresholdRemoval?
    # ═══════════════════════════════════════════════════════════════════════
    print("─── Analysis: ScoredRemoval vs ThresholdRemoval crossover ───")
    print()

    scored_names    = [n for n, g, _ in sweep_policies if g == "scored"]
    threshold_names = [n for n, g, _ in sweep_policies if g == "threshold"]

    print("  By multiplier (best Scored vs best Threshold, Δ from NeverRemove):")
    print(f"    {'mult':<6}  {'best Thresh':<22}  {'Δ_T':<8}  {'best Scored':<22}  {'Δ_S':<8}  winner")
    print("    " + "-" * 78)
    for i, mult in enumerate(MULTIPLIERS):
        base_t = sweep2_baseline[i].mean_time
        t_delta = min(sweep2_results[n][i].mean_time - base_t for n in threshold_names
                      if sweep2_results[n][i].depleted_frac == 0)
        s_delta = min(sweep2_results[n][i].mean_time - base_t for n in scored_names
                      if sweep2_results[n][i].depleted_frac == 0)
        best_t_name = min(threshold_names, key=lambda n: sweep2_results[n][i].mean_time
                          if sweep2_results[n][i].depleted_frac == 0 else float("inf"))
        best_s_name = min(scored_names,    key=lambda n: sweep2_results[n][i].mean_time
                          if sweep2_results[n][i].depleted_frac == 0 else float("inf"))
        winner = "Scored ◀" if s_delta < t_delta else "Threshold"
        print(f"    {mult}×     {best_t_name:<22}  {t_delta:+6.1f}h   "
              f"{best_s_name:<22}  {s_delta:+6.1f}h   {winner}")

    print()
    print("  By repair-fail-prob (best Scored vs best Threshold, Δ from NeverRemove):")
    print(f"    {'fail_p':<8}  {'best Thresh':<22}  {'Δ_T':<8}  {'best Scored':<22}  {'Δ_S':<8}  winner")
    print("    " + "-" * 80)
    for i, fp in enumerate(REPAIR_FAIL_PROBS):
        base_t = sweep3_baseline[i].mean_time
        t_delta = min(sweep3_results[n][i].mean_time - base_t for n in threshold_names
                      if sweep3_results[n][i].depleted_frac == 0)
        s_delta = min(sweep3_results[n][i].mean_time - base_t for n in scored_names
                      if sweep3_results[n][i].depleted_frac == 0)
        best_t_name = min(threshold_names, key=lambda n: sweep3_results[n][i].mean_time
                          if sweep3_results[n][i].depleted_frac == 0 else float("inf"))
        best_s_name = min(scored_names,    key=lambda n: sweep3_results[n][i].mean_time
                          if sweep3_results[n][i].depleted_frac == 0 else float("inf"))
        winner = "Scored ◀" if s_delta < t_delta else "Threshold"
        print(f"    {fp:<8.2f}  {best_t_name:<22}  {t_delta:+6.1f}h   "
              f"{best_s_name:<22}  {s_delta:+6.1f}h   {winner}")


    # ═══════════════════════════════════════════════════════════════════════
    # Plots
    # ═══════════════════════════════════════════════════════════════════════
    print()
    print("Saving plots …")

    plot_head_to_head(s1_results)

    # Build dict excluding NeverRemove for the line plots (it's the baseline)
    sweep2_no_never = {n: v for n, v in sweep2_results.items() if n != "NeverRemove"}
    sweep3_no_never = {n: v for n, v in sweep3_results.items() if n != "NeverRemove"}

    plot_sweep(
        x_values           = MULTIPLIERS,
        x_label            = "systematic_failure_rate_multiplier",
        results_by_policy  = sweep2_no_never,
        baseline_results   = sweep2_baseline,
        filename           = "vs_multiplier.png",
        title              = ("Δ Training Time vs Failure-Rate Multiplier\n"
                              f"(manual_repair_fail_prob={BASE.manual_repair_fail_prob}, "
                              f"{N_REPS} reps; negative = faster than NeverRemove)"),
        x_formatter        = lambda v: f"{v}×",
    )

    plot_sweep(
        x_values           = REPAIR_FAIL_PROBS,
        x_label            = "manual_repair_fail_prob",
        results_by_policy  = sweep3_no_never,
        baseline_results   = sweep3_baseline,
        filename           = "vs_repair_fail_prob.png",
        title              = ("Δ Training Time vs Manual Repair Fail Prob\n"
                              f"(multiplier={BASE.systematic_failure_rate_multiplier}×, "
                              f"{N_REPS} reps; negative = faster than NeverRemove)"),
        x_formatter        = str,
    )

    print()
    print("=" * 70)
    print("Done. PNGs written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        if fname.endswith(".png"):
            kb = os.path.getsize(fig_path(fname)) // 1024
            print(f"  {fname}  ({kb} KB)")


if __name__ == "__main__":
    main()
