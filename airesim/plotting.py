"""Plotting utilities for AIReSim sweep results.

Generates bar charts and sensitivity summaries from SweepResult objects.
Requires matplotlib (optional dependency).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airesim.sweep import SweepResult


def plot_one_way_sweep(
    result: "SweepResult",
    metric: str = "training_time_hrs",
    ylabel: str = "Total Training Time (Hours)",
    title: str | None = None,
    save_path: str | None = None,
):
    """Bar chart for a one-way parameter sweep.

    Args:
        result: SweepResult from a OneWaySweep.
        metric: Which metric to plot (key in AggregateStats.summary_table()).
        ylabel: Y-axis label.
        title: Chart title (auto-generated if None).
        save_path: If provided, save the figure to this path instead of showing.
    """
    import matplotlib.pyplot as plt

    labels = [str(agg.param_value) for agg in result.results]
    means = []
    stdevs = []
    for agg in result.results:
        summary = agg.summary_table().get(metric, agg.training_time_summary())
        means.append(summary.get("mean", 0))
        stdevs.append(summary.get("stdev", 0))

    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(labels))
    bars = ax.bar(x, means, yerr=stdevs, capsize=4, color="#4C72B0", edgecolor="black", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel(result.param_name)
    ax.set_ylabel(ylabel)
    ax.set_title(title or f"{ylabel} vs. {result.param_name}")
    ax.grid(axis="y", alpha=0.3)

    # Add value labels on bars
    for bar, m in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                f"{m:.1f}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Saved plot to {save_path}")
    else:
        plt.show()
    plt.close()


def plot_two_way_sweep(
    result: "SweepResult",
    param1_name: str,
    param2_name: str,
    metric: str = "training_time_hrs",
    ylabel: str = "Total Training Time (Hours)",
    title: str | None = None,
    save_path: str | None = None,
):
    """Grouped bar chart for a two-way parameter sweep.

    Produces a chart similar to Figure 2 in the AIReSim paper,
    with groups on the x-axis for (param1, param2) combinations.

    Args:
        result: SweepResult from a TwoWaySweep.
        param1_name: Name of the first parameter (used for labeling).
        param2_name: Name of the second parameter (used for legend).
        metric: Which metric to plot.
        ylabel: Y-axis label.
        title: Chart title.
        save_path: If provided, save figure to this path.
    """
    import matplotlib.pyplot as plt
    import numpy as np

    # Extract unique param2 values for the legend
    param2_vals = sorted(set(v[1] for agg in result.results for v in [agg.param_value] if isinstance(v, tuple)))
    param1_vals = sorted(set(v[0] for agg in result.results for v in [agg.param_value] if isinstance(v, tuple)))

    if not param2_vals or not param1_vals:
        print("Warning: Could not parse two-way sweep structure for plotting.")
        return

    # Build data matrix
    data = {}
    for agg in result.results:
        if isinstance(agg.param_value, tuple):
            v1, v2 = agg.param_value
            summary = agg.summary_table().get(metric, agg.training_time_summary())
            data[(v1, v2)] = summary.get("mean", 0)

    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3"]
    n_groups = len(param1_vals)
    n_bars = len(param2_vals)
    bar_width = 0.8 / n_bars

    fig, ax = plt.subplots(figsize=(max(8, n_groups * n_bars * 0.6), 5))

    for i, v2 in enumerate(param2_vals):
        positions = [j + i * bar_width for j in range(n_groups)]
        heights = [data.get((v1, v2), 0) for v1 in param1_vals]
        ax.bar(positions, heights, bar_width * 0.9,
               label=f"{param2_name}={v2}",
               color=colors[i % len(colors)],
               edgecolor="black", alpha=0.85)

    # X-axis labels
    ax.set_xticks([j + bar_width * (n_bars - 1) / 2 for j in range(n_groups)])
    ax.set_xticklabels([str(v) for v in param1_vals])
    ax.set_xlabel(param1_name)
    ax.set_ylabel(ylabel)
    ax.set_title(title or f"{ylabel} vs. ({param1_name}, {param2_name})")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Saved plot to {save_path}")
    else:
        plt.show()
    plt.close()


def sensitivity_summary(
    sweep_results: dict[str, "SweepResult"],
    metric: str = "training_time_hrs",
) -> list[dict]:
    """Compute a sensitivity summary across multiple one-way sweeps.

    For each parameter, computes the range (max - min) of the mean metric
    value across the swept values.  A larger range indicates higher sensitivity.

    Args:
        sweep_results: Dict mapping parameter name to its SweepResult.
        metric: Which metric to analyze.

    Returns:
        List of dicts sorted by sensitivity (descending), each containing:
        - param_name, min_val, max_val, range, impact (high/medium/low)
    """
    rows = []
    for param_name, result in sweep_results.items():
        means = []
        for agg in result.results:
            summary = agg.summary_table().get(metric, agg.training_time_summary())
            means.append(summary.get("mean", 0))

        if means:
            mn, mx = min(means), max(means)
            rng = mx - mn
            # Classify impact
            if rng == 0:
                impact = "none"
            elif rng < 0.05 * mx:
                impact = "low"
            elif rng < 0.20 * mx:
                impact = "medium"
            else:
                impact = "high"

            rows.append({
                "param_name": param_name,
                "min_mean": round(mn, 2),
                "max_mean": round(mx, 2),
                "range": round(rng, 2),
                "impact": impact,
            })

    rows.sort(key=lambda r: r["range"], reverse=True)
    return rows


def print_sensitivity_table(rows: list[dict]) -> None:
    """Pretty-print the sensitivity summary table."""
    print(f"\n{'Parameter':<35} {'Min':>10} {'Max':>10} {'Range':>10} {'Impact':>8}")
    print("-" * 78)
    for r in rows:
        print(
            f"{r['param_name']:<35} {r['min_mean']:>10.1f} {r['max_mean']:>10.1f} "
            f"{r['range']:>10.1f} {r['impact']:>8}"
        )


def plot_tornado_chart(
    rows: list[dict],
    baseline: float,
    title: str = "Sensitivity Tornado Chart",
    xlabel: str = "Total Training Time (Hours)",
    save_path: str | None = None,
    max_params: int = 15,
):
    """Horizontal tornado chart ranking parameters by their impact on a metric.

    Each bar spans from the minimum to the maximum mean value observed across
    the swept range for that parameter, centered on the chart.  Parameters are
    sorted so the highest-impact one appears at the top.

    Args:
        rows: List of dicts from ``sensitivity_summary()``.
        baseline: Baseline metric value (drawn as a vertical reference line).
        title: Chart title.
        xlabel: X-axis label.
        save_path: If provided, save the figure to this path.
        max_params: Show at most this many parameters (top by range).
    """
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    # Keep top-N by range; draw highest-impact at the top of the chart.
    display = sorted(rows, key=lambda r: r["range"], reverse=True)[:max_params]
    display_bottom_to_top = list(reversed(display))   # reversed so y=0 is bottom

    impact_colors = {
        "high":   "#C44E52",
        "medium": "#DD8452",
        "low":    "#4C72B0",
        "none":   "#AAAAAA",
    }

    fig_height = max(4, len(display) * 0.55 + 1.5)
    fig, ax = plt.subplots(figsize=(11, fig_height))

    for y, row in enumerate(display_bottom_to_top):
        color = impact_colors.get(row["impact"], "#4C72B0")
        bar_left  = row["min_mean"]
        bar_width = row["max_mean"] - row["min_mean"]
        ax.barh(y, bar_width, left=bar_left, height=0.6,
                color=color, edgecolor="black", linewidth=0.7, alpha=0.85)
        # Annotate the delta to the right of the bar
        ax.text(row["max_mean"] + 0.3, y, f"  Δ{row['range']:.1f}h",
                va="center", fontsize=8, color="#333333")

    # Baseline reference line
    ax.axvline(baseline, color="black", linestyle="--", linewidth=1.5)

    param_labels = [r["param_name"] for r in display_bottom_to_top]
    ax.set_yticks(range(len(display)))
    ax.set_yticklabels(param_labels, fontsize=9)
    ax.set_xlabel(xlabel)
    ax.set_title(title)

    # Legend
    impact_order = [("high", "High impact"), ("medium", "Medium impact"),
                    ("low", "Low impact")]
    legend_handles = [
        mpatches.Patch(color=impact_colors[k], label=lbl)
        for k, lbl in impact_order
    ]
    legend_handles.append(
        plt.Line2D([0], [0], color="black", linestyle="--", linewidth=1.5,
                   label="Baseline")
    )
    ax.legend(handles=legend_handles, loc="lower right", fontsize=8)
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Saved plot to {save_path}")
    else:
        plt.show()
    plt.close()
