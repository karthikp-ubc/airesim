"""
Sweep diagnosis_probability and diagnosis_uncertainty across scheduling
and retirement policies in the retirement-payoff regime.

Two sweeps are run:

  Sweep A — diagnosis_probability  [0.0 → 1.0]  (diagnosis_uncertainty = 0)
    P(failure triggers a repair attempt on any server).  At 0, every failure
    goes undiagnosed: the failed server auto-recovers without repair.

  Sweep B — diagnosis_uncertainty  [0.0 → 1.0]  (diagnosis_probability = 1)
    P(wrong server blamed | failure is diagnosed).  At 1, every repair is
    sent to a random innocent server while the actual bad server escapes.

Both sweeps test six policy combinations:
  scheduling   × retirement
  Random       × NeverRemove
  Random       × ThresholdRemoval(≥2/7d)
  Random       × ScoredRemoval(SC_fast)
  FewestFailures × NeverRemove
  FewestFailures × ThresholdRemoval(≥2/7d)
  FewestFailures × ScoredRemoval(SC_fast)

HighestScoreFirst is omitted: at full diagnosis probability it is
structurally identical to FewestFailuresFirst (credits inert at 4096-server
scale), and at reduced diagnosis probability its scores become stale (missed
failures are not penalised), making it strictly worse than FewestFailuresFirst
— a finding discussed in the companion scheduling-comparison report.

Base regime: 20× failure multiplier, 75% manual repair fail prob, 4600-server pool.

Outputs (saved to examples/diagnosis_sweep_figures/):
  sweep_diag_prob.png       — training-time Δ vs diagnosis_probability
  sweep_diag_uncertainty.png — training-time Δ vs diagnosis_uncertainty
  overview.png               — both sweeps side-by-side
  diagnosis_sweep.csv        — raw numbers for all cells

Expected runtime: ~25–35 minutes (8 reps × 66 cells × 6 policies).

Usage:
    python3 examples/diagnosis_sweep.py
"""

from __future__ import annotations

import csv
import os
import sys
import statistics
from dataclasses import dataclass, field

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from airesim.params import Params
from airesim.simulator import Simulator
from airesim.policies import (
    NeverRemove, ThresholdRemoval, ScoredRemoval, CompositeRemovalPolicy,
)
from airesim.scheduling_policies import DefaultHostSelection, FewestFailuresFirst

# ── Output ─────────────────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "diagnosis_sweep_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Payoff-regime base parameters ─────────────────────────────────────────────

DEFAULT_RATE = 0.01 / (24 * 60)
WINDOW       = 7 * 24 * 60      # 7-day rolling window
N_REPS       = 8

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
    diagnosis_probability = 1.0,
    diagnosis_uncertainty = 0.0,
    seed                  = 42,
    num_replications      = N_REPS,
)

# ── Policy definitions ────────────────────────────────────────────────────────

def _sc_fast() -> ScoredRemoval:
    return ScoredRemoval(
        initial_score        = 100.0,
        failure_penalty      = 60.0,
        success_increment    = 10.0,
        time_period          = 24 * 60,
        retirement_threshold = 0.0,
    )


# Each combo: (sched_label, retire_label, sched_factory, retire_factory)
# Factories are callables so we get fresh policy objects each cell.
COMBOS = [
    ("Random",        "NeverRemove",
     lambda: DefaultHostSelection(),
     lambda: NeverRemove()),
    ("Random",        "Thresh ≥2/7d",
     lambda: DefaultHostSelection(),
     lambda: ThresholdRemoval(max_failures=2, window_minutes=WINDOW)),
    ("Random",        "ScoredRemoval",
     lambda: (lambda sc: (DefaultHostSelection(), sc))(_sc_fast()),
     None),   # handled specially below
    ("FewestFailures","NeverRemove",
     lambda: FewestFailuresFirst(),
     lambda: NeverRemove()),
    ("FewestFailures","Thresh ≥2/7d",
     lambda: FewestFailuresFirst(),
     lambda: ThresholdRemoval(max_failures=2, window_minutes=WINDOW)),
    ("FewestFailures","ScoredRemoval",
     lambda: (lambda sc: (FewestFailuresFirst(), sc))(_sc_fast()),
     None),   # handled specially below
]

# Rebuild as a cleaner structure:
@dataclass
class PolicyCombo:
    sched_label:  str
    retire_label: str
    color:        str
    linestyle:    str

    def make(self):
        """Return (host_selection_policy, removal_policy)."""
        if self.retire_label == "NeverRemove":
            return self._make_sched(), NeverRemove()
        if self.retire_label == "Thresh ≥2/7d":
            return self._make_sched(), ThresholdRemoval(max_failures=2, window_minutes=WINDOW)
        # ScoredRemoval — scheduler and removal policy share the same scorer
        scorer = _sc_fast()
        return self._make_sched(), scorer

    def _make_sched(self):
        if self.sched_label == "Random":
            return DefaultHostSelection()
        return FewestFailuresFirst()

    @property
    def label(self):
        return f"{self.sched_label}+{self.retire_label}"


POLICY_COMBOS = [
    PolicyCombo("Random",        "NeverRemove",   "#333333", "-"),
    PolicyCombo("Random",        "Thresh ≥2/7d",  "#1f77b4", "--"),
    PolicyCombo("Random",        "ScoredRemoval", "#1f77b4", "-"),
    PolicyCombo("FewestFailures","NeverRemove",   "#d62728", "-"),
    PolicyCombo("FewestFailures","Thresh ≥2/7d",  "#2ca02c", "--"),
    PolicyCombo("FewestFailures","ScoredRemoval", "#2ca02c", "-"),
]

# ── Sweep definitions ─────────────────────────────────────────────────────────

@dataclass
class SweepDef:
    param:  str         # 'diagnosis_probability' or 'diagnosis_uncertainty'
    values: list[float]
    fixed:  dict        # other diagnosis param held constant
    xlabel: str
    title:  str

SWEEPS = [
    SweepDef(
        param  = "diagnosis_probability",
        values = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        fixed  = {"diagnosis_uncertainty": 0.0},
        xlabel = "Diagnosis probability  P(failure attributed to any server)",
        title  = "Effect of missed diagnosis  (diagnosis_uncertainty = 0)",
    ),
    SweepDef(
        param  = "diagnosis_uncertainty",
        values = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        fixed  = {"diagnosis_probability": 1.0},
        xlabel = "Diagnosis uncertainty  P(wrong server blamed | diagnosed)",
        title  = "Effect of misattribution  (diagnosis_probability = 1)",
    ),
]

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class CellResult:
    sweep_param:   str
    param_value:   float
    sched_label:   str
    retire_label:  str
    times:         list[float] = field(default_factory=list)
    retired:       list[float] = field(default_factory=list)
    auto_repairs:  list[float] = field(default_factory=list)
    depleted:      int = 0

    @property
    def mean_time(self): return statistics.mean(self.times)
    @property
    def std_time(self):  return statistics.stdev(self.times) if len(self.times) > 1 else 0.0
    @property
    def mean_retired(self): return statistics.mean(self.retired)
    @property
    def mean_auto_repairs(self): return statistics.mean(self.auto_repairs)


# ── Runner ────────────────────────────────────────────────────────────────────

def run_cell(combo: PolicyCombo, params: Params) -> CellResult:
    cell = CellResult(
        sweep_param  = "",   # filled by caller
        param_value  = 0.0,  # filled by caller
        sched_label  = combo.sched_label,
        retire_label = combo.retire_label,
    )
    sched, retire = combo.make()
    sim = Simulator(
        params                = params,
        host_selection_policy = sched,
        removal_policy        = retire,
        seed                  = params.seed,
    )
    for rep in range(params.num_replications):
        sim.seed = params.seed + rep
        stats = sim.run()
        cell.times.append(stats.total_training_time / 60)
        cell.retired.append(stats.servers_retired)
        cell.auto_repairs.append(stats.auto_repairs)
        if stats.cluster_depleted:
            cell.depleted += 1
    return cell


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_sweep(sweep: SweepDef,
               results: dict[tuple, CellResult],
               baseline_mean: float,
               fname: str) -> None:
    fig, (ax_delta, ax_ret) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)

    for combo in POLICY_COMBOS:
        xs, deltas, errs, rets = [], [], [], []
        for v in sweep.values:
            key = (sweep.param, v, combo.sched_label, combo.retire_label)
            cell = results.get(key)
            if cell is None:
                continue
            xs.append(v)
            deltas.append(cell.mean_time - baseline_mean)
            errs.append(cell.std_time)
            rets.append(cell.mean_retired)

        ax_delta.errorbar(xs, deltas, yerr=errs,
                          label=combo.label,
                          color=combo.color, linestyle=combo.linestyle,
                          linewidth=1.8, marker="o", markersize=5,
                          capsize=3)
        ax_ret.plot(xs, rets,
                    color=combo.color, linestyle=combo.linestyle,
                    linewidth=1.8, marker="o", markersize=5)

    ax_delta.axhline(0, color="gray", linewidth=0.8, linestyle=":")
    ax_delta.set_ylabel("Δ Training time vs baseline (hrs)\n(negative = faster)", fontsize=10)
    ax_delta.set_title(sweep.title, fontsize=11)
    ax_delta.legend(fontsize=8, loc="upper left" if sweep.param == "diagnosis_probability" else "lower left")
    ax_delta.yaxis.grid(True, alpha=0.3)

    ax_ret.set_ylabel("Mean servers retired", fontsize=10)
    ax_ret.set_xlabel(sweep.xlabel, fontsize=10)
    ax_ret.yaxis.grid(True, alpha=0.3)

    fig.tight_layout()
    path = fig_path(fname)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {path}")


def plot_overview(sweep_results_list: list,
                  baseline_mean: float) -> None:
    """Two-panel overview: one column per sweep."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex="col")

    for col, (sweep, results) in enumerate(sweep_results_list):
        ax_d = axes[0, col]
        ax_r = axes[1, col]

        for combo in POLICY_COMBOS:
            xs, deltas, rets = [], [], []
            for v in sweep.values:
                key = (sweep.param, v, combo.sched_label, combo.retire_label)
                cell = results.get(key)
                if cell is None:
                    continue
                xs.append(v)
                deltas.append(cell.mean_time - baseline_mean)
                rets.append(cell.mean_retired)

            ax_d.plot(xs, deltas, label=combo.label,
                      color=combo.color, linestyle=combo.linestyle,
                      linewidth=1.5, marker="o", markersize=4)
            ax_r.plot(xs, rets,
                      color=combo.color, linestyle=combo.linestyle,
                      linewidth=1.5, marker="o", markersize=4)

        ax_d.axhline(0, color="gray", linewidth=0.7, linestyle=":")
        ax_d.set_title(sweep.title, fontsize=10)
        ax_d.set_ylabel("Δ Training time (hrs)", fontsize=9)
        ax_d.yaxis.grid(True, alpha=0.3)
        if col == 0:
            ax_d.legend(fontsize=7, loc="upper left")

        ax_r.set_xlabel(sweep.xlabel, fontsize=9)
        ax_r.set_ylabel("Servers retired", fontsize=9)
        ax_r.yaxis.grid(True, alpha=0.3)

    fig.suptitle("Diagnosis Parameter Sweep — Payoff Regime (20×, 75% repair fail)",
                 fontsize=12)
    fig.tight_layout()
    path = fig_path("overview.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → {path}")


# ── CSV export ────────────────────────────────────────────────────────────────

def save_csv(all_results: list[CellResult]) -> None:
    path = fig_path("diagnosis_sweep.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "sweep_param", "param_value", "scheduling", "retirement",
            "mean_time_hrs", "std_time_hrs",
            "mean_retired", "mean_auto_repairs", "depleted_frac",
        ])
        for cell in all_results:
            writer.writerow([
                cell.sweep_param, cell.param_value,
                cell.sched_label, cell.retire_label,
                f"{cell.mean_time:.2f}", f"{cell.std_time:.2f}",
                f"{cell.mean_retired:.1f}", f"{cell.mean_auto_repairs:.1f}",
                f"{cell.depleted / len(cell.times):.2f}",
            ])
    print(f"  Saved → {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 72)
    print("Diagnosis parameter sweep")
    print("Regime: 20× multiplier | 75% manual repair fail | 4600-server pool")
    print(f"Replications per cell: {N_REPS}")
    print("=" * 72)

    # Establish baseline (Random+NeverRemove, full diagnosis, no uncertainty)
    baseline_params = BASE.with_overrides(
        diagnosis_probability=1.0,
        diagnosis_uncertainty=0.0,
    )
    baseline_combo = POLICY_COMBOS[0]   # Random + NeverRemove
    print("\nRunning baseline (Random + NeverRemove, full diagnosis)…")
    baseline_cell = run_cell(baseline_combo, baseline_params)
    baseline_mean = baseline_cell.mean_time
    print(f"  Baseline: {baseline_mean:.1f} ± {baseline_cell.std_time:.1f} hrs")

    sweep_results_list = []
    all_cells: list[CellResult] = [baseline_cell]

    for sweep in SWEEPS:
        print(f"\n{'═'*72}")
        print(f"Sweep: {sweep.param}  (fixed: {sweep.fixed})")
        print(f"{'═'*72}")
        header = (f"  {'Scheduling':<16} {'Retirement':<14}"
                  f" {'Value':>6}  {'Mean (hrs)':>10}  {'Std':>5}"
                  f"  {'Δ':>7}  {'Retired':>7}")
        print(header)
        print("  " + "-" * (len(header) - 2))

        sweep_results: dict[tuple, CellResult] = {}

        for v in sweep.values:
            params = BASE.with_overrides(**{sweep.param: v}, **sweep.fixed)
            for combo in POLICY_COMBOS:
                cell = run_cell(combo, params)
                cell.sweep_param  = sweep.param
                cell.param_value  = v
                key = (sweep.param, v, combo.sched_label, combo.retire_label)
                sweep_results[key] = cell
                all_cells.append(cell)

                delta = cell.mean_time - baseline_mean
                dep   = f" DEPLETED" if cell.depleted > 0 else ""
                print(f"  {combo.sched_label:<16} {combo.retire_label:<14}"
                      f" {v:>6.2f}  {cell.mean_time:>9.1f}h"
                      f" ±{cell.std_time:>4.1f}"
                      f"  {delta:>+7.1f}h"
                      f"  {cell.mean_retired:>6.1f}ret"
                      f"{dep}")

        sweep_results_list.append((sweep, sweep_results))
        fname = f"sweep_{sweep.param}.png"
        plot_sweep(sweep, sweep_results, baseline_mean, fname)

    print("\nSaving combined overview …")
    plot_overview(sweep_results_list, baseline_mean)
    save_csv(all_cells)

    print()
    print("=" * 72)
    print(f"Done.  Output → {FIGURES_DIR}")
    for fname in sorted(os.listdir(FIGURES_DIR)):
        kb = os.path.getsize(os.path.join(FIGURES_DIR, fname)) // 1024
        print(f"  {fname}  ({kb} KB)")


if __name__ == "__main__":
    main()
