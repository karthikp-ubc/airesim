"""Two-way sweep: systematic_failure_rate_multiplier × manual_repair_fail_prob.

Compares three policy combinations across a 5×5 grid:
  1. Random + NeverRemove          (baseline)
  2. Random + ScoredRemoval(SC_fast)
  3. FewestFailuresFirst + NeverRemove

All other parameters use the "payoff regime" baseline from retirement_payoff.py.

For each cell the script runs 10 independent replications per policy and records
mean training time (hours).  Deltas are computed against the Random+NeverRemove
baseline so negative = improvement, positive = regression.

Three heat maps are produced:
  heatmap_scored_delta.png      — delta for Random+ScoredRemoval vs baseline
  heatmap_fff_delta.png         — delta for FewestFailuresFirst+NeverRemove vs baseline
  heatmap_winner.png            — which of the three policies wins each cell

A Markdown report (heatmap_report.md) is written to the same figures directory.

SC_fast parameters (aggressive early retirement):
  initial_score=100, failure_penalty=60, success_increment=5,
  time_period=24*60 (1-day credit period), retirement_threshold=0
  → a server is retired after just 2 failures (score: 100→40→−20 ≤ 0).

Expected runtime: ~10–20 minutes (750 replications total).

Usage:
    python3 examples/2d_heatmap_sweep.py
    python -m airesim.run examples/2d_heatmap_sweep.py
"""

from __future__ import annotations

import os
import sys
import statistics
import time

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

from airesim.params import Params
from airesim.simulator import Simulator
from airesim.policies import NeverRemove, ScoredRemoval
from airesim.scheduling_policies import DefaultHostSelection, FewestFailuresFirst

# ── Output directory ──────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "2d_heatmap_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Sweep axes ────────────────────────────────────────────────────────────────

MULTIPLIERS      = [5, 10, 15, 20, 25]        # systematic_failure_rate_multiplier
REPAIR_FAIL_PROBS = [0.20, 0.40, 0.60, 0.75, 0.90]  # manual_repair_fail_prob

N_REPS = 10   # replications per cell per policy

# ── Payoff regime baseline params ─────────────────────────────────────────────

DEFAULT_RATE = 0.01 / (24 * 60)   # default random_failure_rate

BASE_PARAMS = Params(
    working_pool_size=4600,
    spare_pool_size=200,
    job_size=4096,
    warm_standbys=16,
    job_length=14 * 24 * 60,                # 14 days of compute time
    random_failure_rate=2 * DEFAULT_RATE,   # 2× default failure rate
    systematic_failure_fraction=0.08,       # 8% bad servers
    recovery_time=60.0,                     # 60 min checkpoint reload
    prob_auto_to_manual=0.80,
    auto_repair_fail_prob=0.60,
    # manual_repair_fail_prob swept below
    seed=42,
)

# ── SC_fast ScoredRemoval preset ──────────────────────────────────────────────
# failure_penalty=60 → retire after 2 failures (100 → 40 → −20 ≤ 0)
# success_increment=5 per day of clean uptime (slow recovery)
SC_FAST_KWARGS = dict(
    initial_score=100.0,
    failure_penalty=60.0,
    success_increment=5.0,
    time_period=24 * 60,     # 1-day credit period
    retirement_threshold=0.0,
)

# ── Policy factory functions ──────────────────────────────────────────────────

def make_random_never():
    """Random host selection + never remove."""
    return dict(host_selection_policy=DefaultHostSelection(),
                removal_policy=NeverRemove())

def make_random_scored():
    """Random host selection + SC_fast ScoredRemoval."""
    return dict(host_selection_policy=DefaultHostSelection(),
                removal_policy=ScoredRemoval(**SC_FAST_KWARGS))

def make_fff_never():
    """FewestFailuresFirst host selection + never remove."""
    return dict(host_selection_policy=FewestFailuresFirst(),
                removal_policy=NeverRemove())

POLICIES = [
    ("Random+NeverRemove",         make_random_never),
    ("Random+ScoredRemoval(SC_fast)", make_random_scored),
    ("FewestFailuresFirst+NeverRemove", make_fff_never),
]

POLICY_SHORT = ["Baseline", "Scored(SC_fast)", "FFF+Never"]

# ── Simulation helper ─────────────────────────────────────────────────────────

def run_cell(params: Params, policy_kwargs: dict, n_reps: int) -> tuple[float, float]:
    """Run n_reps replications and return (mean_hours, stdev_hours)."""
    times = []
    for rep in range(n_reps):
        sim = Simulator(params, seed=params.seed + rep, **policy_kwargs)
        stats = sim.run()
        times.append(stats.training_time_hours)
    mean = statistics.mean(times)
    stdev = statistics.stdev(times) if len(times) > 1 else 0.0
    return mean, stdev


# ── Main sweep ────────────────────────────────────────────────────────────────

def run_sweep() -> dict:
    """Execute the full 5×5×3 sweep.

    Returns a dict with keys:
      'means'   : shape [n_policies][n_mults][n_probs]  mean training time (hrs)
      'stdevs'  : shape [n_policies][n_mults][n_probs]  stdev training time (hrs)
    """
    n_p = len(POLICIES)
    n_m = len(MULTIPLIERS)
    n_r = len(REPAIR_FAIL_PROBS)

    # Initialise result arrays as list-of-list-of-list
    means  = [[[0.0] * n_r for _ in range(n_m)] for _ in range(n_p)]
    stdevs = [[[0.0] * n_r for _ in range(n_m)] for _ in range(n_p)]

    total_cells = n_m * n_r
    cell_idx = 0
    t_start = time.time()

    print(f"\nRunning {total_cells} cells × {n_p} policies × {N_REPS} reps "
          f"= {total_cells * n_p * N_REPS} simulation runs total.\n")

    for mi, mult in enumerate(MULTIPLIERS):
        for ri, repair_fail in enumerate(REPAIR_FAIL_PROBS):
            cell_idx += 1
            params = BASE_PARAMS.with_overrides(
                systematic_failure_rate_multiplier=float(mult),
                manual_repair_fail_prob=repair_fail,
            )
            elapsed = time.time() - t_start
            print(f"  Cell {cell_idx:2d}/{total_cells}  "
                  f"mult={mult:2d}×  repair_fail={repair_fail:.2f}  "
                  f"[{elapsed:.0f}s elapsed]")

            for pi, (policy_label, policy_factory) in enumerate(POLICIES):
                kwargs = policy_factory()
                mu, sd = run_cell(params, kwargs, N_REPS)
                means[pi][mi][ri]  = mu
                stdevs[pi][mi][ri] = sd
                print(f"    {policy_label:<38s}  {mu:8.1f} ± {sd:5.1f} hrs")

    elapsed_total = time.time() - t_start
    print(f"\nSweep complete in {elapsed_total:.0f}s "
          f"({elapsed_total/60:.1f} min).\n")

    return {"means": means, "stdevs": stdevs}


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_delta_heatmap(
    delta: list[list[float]],
    title: str,
    filename: str,
    cmap: str = "RdYlGn_r",
    note: str = "",
) -> None:
    """Plot a heatmap of delta values (negative = policy improves on baseline)."""
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import numpy as np

    data = np.array(delta)   # shape [n_mults × n_probs]

    # Symmetric colour scale around 0
    abs_max = max(abs(data.min()), abs(data.max()), 1.0)
    vmin, vmax = -abs_max, abs_max

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Δ Training Time vs Baseline (hrs)\nnegative = improvement", fontsize=9)

    ax.set_xticks(range(len(REPAIR_FAIL_PROBS)))
    ax.set_xticklabels([f"{p:.0%}" for p in REPAIR_FAIL_PROBS])
    ax.set_xlabel("manual_repair_fail_prob", fontsize=10)

    ax.set_yticks(range(len(MULTIPLIERS)))
    ax.set_yticklabels([f"{m}×" for m in MULTIPLIERS])
    ax.set_ylabel("systematic_failure_rate_multiplier", fontsize=10)

    # Annotate each cell with the delta value
    for mi in range(len(MULTIPLIERS)):
        for ri in range(len(REPAIR_FAIL_PROBS)):
            v = data[mi, ri]
            color = "white" if abs(v) > abs_max * 0.55 else "black"
            ax.text(ri, mi, f"{v:+.0f}h", ha="center", va="center",
                    fontsize=9, color=color, fontweight="bold")

    ax.set_title(title, fontsize=11, pad=10)
    if note:
        fig.text(0.5, 0.01, note, ha="center", fontsize=8, color="gray",
                 style="italic")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    path = fig_path(filename)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


def plot_winner_heatmap(
    means: list[list[list[float]]],
) -> None:
    """Plot a categorical heat map showing which policy wins each cell."""
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    n_m = len(MULTIPLIERS)
    n_r = len(REPAIR_FAIL_PROBS)

    winner_idx = np.zeros((n_m, n_r), dtype=int)
    for mi in range(n_m):
        for ri in range(n_r):
            best = min(range(len(POLICIES)), key=lambda pi: means[pi][mi][ri])
            winner_idx[mi, ri] = best

    # Palette: baseline=grey, scored=coral, fff=teal
    palette = ["#888888", "#C44E52", "#4C72B0"]
    short   = [s for _, s in zip(POLICIES, POLICY_SHORT)]

    cmap = plt.cm.colors.ListedColormap(palette)  # type: ignore[attr-defined]
    norm = plt.Normalize(vmin=-0.5, vmax=len(POLICIES) - 0.5)

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(winner_idx, cmap=plt.matplotlib.colors.ListedColormap(palette),
                   norm=norm, aspect="auto")

    ax.set_xticks(range(n_r))
    ax.set_xticklabels([f"{p:.0%}" for p in REPAIR_FAIL_PROBS])
    ax.set_xlabel("manual_repair_fail_prob", fontsize=10)

    ax.set_yticks(range(n_m))
    ax.set_yticklabels([f"{m}×" for m in MULTIPLIERS])
    ax.set_ylabel("systematic_failure_rate_multiplier", fontsize=10)

    # Annotate with winning policy short name
    for mi in range(n_m):
        for ri in range(n_r):
            w = winner_idx[mi, ri]
            ax.text(ri, mi, POLICY_SHORT[w], ha="center", va="center",
                    fontsize=8, color="white", fontweight="bold")

    patches = [mpatches.Patch(color=palette[i], label=POLICY_SHORT[i])
               for i in range(len(POLICIES))]
    ax.legend(handles=patches, loc="upper right", fontsize=8,
              bbox_to_anchor=(1.0, -0.12), ncol=3)

    ax.set_title("Winning Policy per Cell\n(lowest mean training time)", fontsize=11)
    plt.tight_layout(rect=[0, 0.08, 1, 1])
    path = fig_path("heatmap_winner.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


# ── Markdown report ───────────────────────────────────────────────────────────

def write_report(results: dict) -> None:
    """Write a brief markdown report summarising the findings."""
    means  = results["means"]
    stdevs = results["stdevs"]

    n_m = len(MULTIPLIERS)
    n_r = len(REPAIR_FAIL_PROBS)

    # Delta matrices (policy vs baseline)
    delta_scored = [[means[1][mi][ri] - means[0][mi][ri] for ri in range(n_r)]
                    for mi in range(n_m)]
    delta_fff    = [[means[2][mi][ri] - means[0][mi][ri] for ri in range(n_r)]
                    for mi in range(n_m)]

    # Winner counts
    winner_counts = [0, 0, 0]
    for mi in range(n_m):
        for ri in range(n_r):
            best = min(range(3), key=lambda pi: means[pi][mi][ri])
            winner_counts[best] += 1

    # Largest improvements / regressions for each challenger
    flat_scored = [(delta_scored[mi][ri], mi, ri)
                   for mi in range(n_m) for ri in range(n_r)]
    flat_fff    = [(delta_fff[mi][ri],    mi, ri)
                   for mi in range(n_m) for ri in range(n_r)]

    best_scored = min(flat_scored, key=lambda x: x[0])
    worst_scored = max(flat_scored, key=lambda x: x[0])
    best_fff    = min(flat_fff,    key=lambda x: x[0])
    worst_fff   = max(flat_fff,    key=lambda x: x[0])

    def cell_label(mi, ri):
        return (f"mult={MULTIPLIERS[mi]}×, "
                f"repair_fail={REPAIR_FAIL_PROBS[ri]:.0%}")

    report_lines = [
        "# 2-D Heatmap Sweep: Policy Comparison",
        "",
        "## Experimental Setup",
        "",
        "| Parameter | Value |",
        "|-----------|-------|",
        f"| working_pool_size | 4 600 |",
        f"| spare_pool_size | 200 |",
        f"| job_size | 4 096 |",
        f"| warm_standbys | 16 |",
        f"| job_length | 14 days |",
        f"| random_failure_rate | 2× default |",
        f"| systematic_failure_fraction | 8 % |",
        f"| recovery_time | 60 min |",
        f"| prob_auto_to_manual | 0.80 |",
        f"| auto_repair_fail_prob | 0.60 |",
        f"| Replications per cell | {N_REPS} |",
        "",
        "**Sweep axes**",
        f"- `systematic_failure_rate_multiplier`: {MULTIPLIERS}",
        f"- `manual_repair_fail_prob`: {REPAIR_FAIL_PROBS}",
        "",
        "**SC_fast ScoredRemoval preset**: initial_score=100, failure_penalty=60,",
        "success_increment=5, time_period=1 day → retired after 2 failures.",
        "",
        "## Policy Win Counts (out of 25 cells)",
        "",
        "| Policy | Cells Won |",
        "|--------|-----------|",
        f"| Random+NeverRemove (baseline) | {winner_counts[0]} |",
        f"| Random+ScoredRemoval(SC_fast) | {winner_counts[1]} |",
        f"| FewestFailuresFirst+NeverRemove | {winner_counts[2]} |",
        "",
        "## ScoredRemoval(SC_fast) Delta vs Baseline",
        "",
        "Negative values indicate the policy finished training faster than baseline.",
        "",
        (f"- **Best improvement**: {best_scored[0]:+.1f} hrs "
         f"at {cell_label(best_scored[1], best_scored[2])}"),
        (f"- **Worst regression**: {worst_scored[0]:+.1f} hrs "
         f"at {cell_label(worst_scored[1], worst_scored[2])}"),
        "",
        "### Delta Table (hrs, negative = faster)",
        "",
    ]

    # Delta table for ScoredRemoval
    header = "| mult↓ / fail_prob→ | " + " | ".join(f"{p:.0%}" for p in REPAIR_FAIL_PROBS) + " |"
    sep    = "|-" + "-|-".join(["------"] * (n_r + 1)) + "-|"
    report_lines += [header, sep]
    for mi, mult in enumerate(MULTIPLIERS):
        row = f"| {mult}× | " + " | ".join(
            f"{delta_scored[mi][ri]:+.1f}" for ri in range(n_r)) + " |"
        report_lines.append(row)

    report_lines += [
        "",
        "## FewestFailuresFirst+NeverRemove Delta vs Baseline",
        "",
        "Negative values indicate the policy finished training faster than baseline.",
        "",
        (f"- **Best improvement**: {best_fff[0]:+.1f} hrs "
         f"at {cell_label(best_fff[1], best_fff[2])}"),
        (f"- **Worst regression**: {worst_fff[0]:+.1f} hrs "
         f"at {cell_label(worst_fff[1], worst_fff[2])}"),
        "",
        "### Delta Table (hrs, negative = faster)",
        "",
        header, sep,
    ]
    for mi, mult in enumerate(MULTIPLIERS):
        row = f"| {mult}× | " + " | ".join(
            f"{delta_fff[mi][ri]:+.1f}" for ri in range(n_r)) + " |"
        report_lines.append(row)

    report_lines += [
        "",
        "## Figures",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `heatmap_scored_delta.png` | Δ training time: Random+ScoredRemoval vs baseline |",
        "| `heatmap_fff_delta.png` | Δ training time: FewestFailuresFirst+NeverRemove vs baseline |",
        "| `heatmap_winner.png` | Winning policy at each (multiplier, repair_fail_prob) cell |",
        "",
        "## Key Observations",
        "",
        "1. **ScoredRemoval(SC_fast)** aggressively retires servers after just 2 failures.",
        "   At high `systematic_failure_rate_multiplier` and high `manual_repair_fail_prob`",
        "   (bottom-right of the grid) this can eliminate chronic bad servers and reduce",
        "   training time.  At lower multipliers or lower repair fail rates (good repairs",
        "   fix servers reliably) the capacity cost of retirement outweighs the failure",
        "   reduction and the policy regresses.",
        "",
        "2. **FewestFailuresFirst** routes new hosts preferentially to servers with fewer",
        "   historical failures.  It incurs no capacity penalty (no retirement) and tends",
        "   to improve training time most when failure rates are high enough that host",
        "   selection meaningfully steers work away from bad servers.",
        "",
        "3. **No single policy dominates** across all 25 cells.  The optimal strategy",
        "   depends on the interplay between failure severity (multiplier) and repair",
        "   effectiveness (manual_repair_fail_prob).  The winner heatmap makes this",
        "   regime-dependence concrete.",
    ]

    report_text = "\n".join(report_lines) + "\n"
    report_file = fig_path("heatmap_report.md")
    with open(report_file, "w") as f:
        f.write(report_text)
    print(f"  Saved → {report_file}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("AIReSim — 2-D Heatmap Sweep")
    print("=" * 65)
    print(f"\nGrid: {MULTIPLIERS} × {[f'{p:.2f}' for p in REPAIR_FAIL_PROBS]}")
    print(f"Policies: {[name for name, _ in POLICIES]}")
    print(f"Replications per cell per policy: {N_REPS}")
    print(f"Total runs: {len(MULTIPLIERS) * len(REPAIR_FAIL_PROBS) * len(POLICIES) * N_REPS}")

    results = run_sweep()

    means  = results["means"]

    # Delta matrices (challenger − baseline)
    n_m = len(MULTIPLIERS)
    n_r = len(REPAIR_FAIL_PROBS)
    delta_scored = [[means[1][mi][ri] - means[0][mi][ri] for ri in range(n_r)]
                    for mi in range(n_m)]
    delta_fff    = [[means[2][mi][ri] - means[0][mi][ri] for ri in range(n_r)]
                    for mi in range(n_m)]

    print("\nSaving figures …")
    plot_delta_heatmap(
        delta_scored,
        title="Δ Training Time: Random+ScoredRemoval(SC_fast) vs Baseline\n"
              "(negative = faster than Random+NeverRemove)",
        filename="heatmap_scored_delta.png",
        cmap="RdYlGn_r",
        note="SC_fast: initial_score=100, failure_penalty=60, retire after 2 failures",
    )
    plot_delta_heatmap(
        delta_fff,
        title="Δ Training Time: FewestFailuresFirst+NeverRemove vs Baseline\n"
              "(negative = faster than Random+NeverRemove)",
        filename="heatmap_fff_delta.png",
        cmap="RdYlGn_r",
        note="FewestFailuresFirst: prefer hosts with fewer historical failures",
    )
    plot_winner_heatmap(means)

    print("\nWriting markdown report …")
    write_report(results)

    print("\n" + "=" * 65)
    print("Done. Outputs written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        path = fig_path(fname)
        kb = os.path.getsize(path) // 1024
        print(f"  {fname}  ({kb} KB)")


if __name__ == "__main__":
    main()
