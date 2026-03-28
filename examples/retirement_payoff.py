"""Experiment: parameter regime where active server retirement pays dividends.

Why retirement usually doesn't help
------------------------------------
In a tight pool (working_pool_size ≈ job_size + standbys) every retired server
directly reduces capacity and forces spare-pool preemptions or job stalls.  The
failure-elimination saving rarely outweighs that capacity cost.

The regime where retirement wins
---------------------------------
Three conditions must hold simultaneously:

  1. Bad servers fail disproportionately fast.
     systematic_failure_rate_multiplier=20 → bad servers fail 21× faster than
     good ones.  At 2× the default failure rate, a bad server's mean TTF is
     ~2.4 days vs ~50 days for a good server.

  2. Repairs rarely fix bad servers.
     manual_repair_fail_prob=0.75 → 72 % of repairs return the server still
     broken (auto + manual combined success rate ≈ 28 %).  Without retirement
     a bad server cycles through the failure→repair loop almost indefinitely,
     spending ~45 % of its life in the repair shop and triggering 60-minute
     recovery overhead every 4.4 days.

  3. The working pool has enough headroom to absorb retirements.
     working_pool_size=4600 gives 488 idle servers above the minimum (4112).
     Retiring ~70 bad servers leaves 4530 in the pool — well above the floor.

Under these conditions ThresholdRemoval(max_failures=2, window=7 days) cuts
~60 hours (~2.8 %) off a 2200-hour training run while retiring only ~70 of the
368 bad servers (~19 %), confirming that targeted retirement of the worst
offenders beats keeping all servers alive.

The script also shows:
  * How the benefit scales with systematic_failure_rate_multiplier.
  * How the benefit degrades as manual_repair_fail_prob decreases (repairs
    become more effective, making retirement less necessary).
  * The cost of over-aggressive retirement (threshold=1 can hurt).

Output (examples/retirement_payoff_figures/):
  payoff_policies.png       — training time by policy for the target regime
  payoff_multiplier.png     — retirement benefit vs failure rate multiplier
  payoff_repair_fail.png    — retirement benefit vs manual_repair_fail_prob

Expected runtime: ~5–8 minutes.

Usage:
    python3 examples/retirement_payoff.py
    python -m airesim.run examples/retirement_payoff.py
"""

from __future__ import annotations

import os
import sys
import statistics

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_here))

from airesim.params import Params
from airesim.simulator import Simulator
from airesim.policies import NeverRemove, ThresholdRemoval

# ── Output directory ──────────────────────────────────────────────────────────

FIGURES_DIR = os.path.join(_here, "retirement_payoff_figures")
os.makedirs(FIGURES_DIR, exist_ok=True)

def fig_path(name: str) -> str:
    return os.path.join(FIGURES_DIR, name)


# ── Target regime ─────────────────────────────────────────────────────────────

DEFAULT_RATE = 0.01 / (24 * 60)
WINDOW       = 7 * 24 * 60      # 7-day rolling window for ThresholdRemoval
N_REPS       = 20

TARGET = Params(
    job_size=4096,
    warm_standbys=16,
    working_pool_size=4600,                    # 488 headroom above minimum (4112)
    spare_pool_size=200,
    job_length=14 * 24 * 60,                   # 14 days of compute time
    random_failure_rate=2 * DEFAULT_RATE,
    systematic_failure_rate_multiplier=20.0,   # bad servers fail 21× faster
    systematic_failure_fraction=0.08,          # 8 % bad → 368 bad servers
    recovery_time=60.0,                        # 60 min per failure (expensive)
    auto_repair_time=120.0,
    manual_repair_time=2880.0,
    prob_auto_to_manual=0.80,
    auto_repair_fail_prob=0.60,
    manual_repair_fail_prob=0.75,              # 72 % of repairs don't fix it
    seed=42,
    num_replications=N_REPS,
)


# ── Helper ────────────────────────────────────────────────────────────────────

def run_policy(base: Params, policy, n_reps: int):
    """Return (mean_time, stdev_time, mean_retired, stdev_retired) for a policy."""
    runs = [
        Simulator(base, removal_policy=policy, seed=base.seed + rep).run()
        for rep in range(n_reps)
    ]
    times   = [r.training_time_hours for r in runs]
    retired = [float(r.servers_retired) for r in runs]
    return (
        statistics.mean(times),
        statistics.stdev(times) if len(times) > 1 else 0.0,
        statistics.mean(retired),
        statistics.stdev(retired) if len(retired) > 1 else 0.0,
    )


# ── Experiment 1: policy comparison in the target regime ─────────────────────

def exp_policy_comparison():
    """Compare NeverRemove against three ThresholdRemoval thresholds."""
    print("\n─── Experiment 1: policy comparison (target regime) ───")
    print(f"  bad fraction : {TARGET.systematic_failure_fraction:.0%}  "
          f"({int(TARGET.systematic_failure_fraction * TARGET.working_pool_size)} bad servers)")
    print(f"  multiplier   : {TARGET.systematic_failure_rate_multiplier:.0f}×")
    print(f"  repair fix   : {100*(1 - TARGET.manual_repair_fail_prob):.0f}% effective  "
          f"(manual_repair_fail_prob={TARGET.manual_repair_fail_prob})")
    print(f"  recovery_time: {TARGET.recovery_time:.0f} min")
    print()

    policies = [
        ("NeverRemove", NeverRemove()),
        ("Thresh≥5/7d", ThresholdRemoval(5, WINDOW)),
        ("Thresh≥3/7d", ThresholdRemoval(3, WINDOW)),
        ("Thresh≥2/7d", ThresholdRemoval(2, WINDOW)),
        ("Thresh≥1/7d", ThresholdRemoval(1, WINDOW)),
    ]

    results = []
    never_mean = None
    print(f"  {'Policy':<14} {'Time (hrs)':>18}  {'Retired':>9}  {'vs Never':>9}")
    print("  " + "-" * 58)
    for label, policy in policies:
        mu_t, sd_t, mu_r, sd_r = run_policy(TARGET, policy, N_REPS)
        delta = f"{never_mean - mu_t:+.1f}h" if never_mean is not None else "—"
        print(f"  {label:<14} {mu_t:8.1f} ± {sd_t:5.1f}h   {mu_r:5.1f} ± {sd_r:3.1f}   {delta:>9}")
        results.append((label, mu_t, sd_t, mu_r, sd_r))
        if never_mean is None:
            never_mean = mu_t

    return results


# ── Experiment 2: retirement benefit vs failure rate multiplier ───────────────

def exp_vs_multiplier():
    """Show how the retirement benefit grows with systematic_failure_rate_multiplier."""
    print("\n─── Experiment 2: benefit vs systematic_failure_rate_multiplier ───")
    print("  (NeverRemove vs ThresholdRemoval(2, 7d), all other params fixed)")
    print()
    print(f"  {'mult':>6}  {'NeverRemove':>12}  {'Thresh=2/7d':>12}  {'delta':>8}  {'retired':>8}")
    print("  " + "-" * 55)

    results = []
    for mult in [5, 10, 15, 20, 25]:
        base = TARGET.with_overrides(systematic_failure_rate_multiplier=float(mult))
        mu_n, sd_n, _,   _   = run_policy(base, NeverRemove(),            N_REPS)
        mu_t, sd_t, mu_r, _  = run_policy(base, ThresholdRemoval(2, WINDOW), N_REPS)
        delta = mu_n - mu_t
        print(f"  {mult:>5}×  {mu_n:>12.1f}  {mu_t:>12.1f}  {delta:>+8.1f}h  {mu_r:>8.1f}")
        results.append((mult, mu_n, sd_n, mu_t, sd_t, mu_r, delta))

    return results


# ── Experiment 3: retirement benefit vs repair fix rate ───────────────────────

def exp_vs_repair_fail():
    """Show how the benefit shrinks as repairs become more effective."""
    print("\n─── Experiment 3: benefit vs manual_repair_fail_prob ───")
    print("  (NeverRemove vs ThresholdRemoval(2, 7d), target regime otherwise)")
    print()
    print(f"  {'fail_prob':>10}  {'fix_rate':>9}  {'NeverRemove':>12}  "
          f"{'Thresh=2/7d':>12}  {'delta':>8}  {'retired':>8}")
    print("  " + "-" * 70)

    results = []
    for prob in [0.20, 0.40, 0.60, 0.75, 0.90]:
        base  = TARGET.with_overrides(manual_repair_fail_prob=prob)
        # Combined fix rate: P(auto path)×P(auto success) + P(manual path)×P(manual success)
        p_fix = (1 - TARGET.prob_auto_to_manual) * (1 - TARGET.auto_repair_fail_prob) \
              + TARGET.prob_auto_to_manual * (1 - prob)
        mu_n, sd_n, _,   _   = run_policy(base, NeverRemove(),               N_REPS)
        mu_t, sd_t, mu_r, _  = run_policy(base, ThresholdRemoval(2, WINDOW), N_REPS)
        delta = mu_n - mu_t
        print(f"  {prob:>10.2f}  {p_fix:>8.0%}   {mu_n:>12.1f}  {mu_t:>12.1f}  "
              f"{delta:>+8.1f}h  {mu_r:>8.1f}")
        results.append((prob, p_fix, mu_n, sd_n, mu_t, sd_t, mu_r, delta))

    return results


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_policy_comparison(results: list):
    import matplotlib.pyplot as plt
    import numpy as np

    labels  = [r[0] for r in results]
    means   = [r[1] for r in results]
    errs    = [r[2] for r in results]
    retired = [r[3] for r in results]
    never   = means[0]

    colors = ["#888888" if lab == "NeverRemove" else "#C44E52" if m < never else "#4C72B0"
              for lab, m in zip(labels, means)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Left: training time with error bars
    x = np.arange(len(labels))
    bars = ax1.bar(x, means, yerr=errs, capsize=4,
                   color=colors, edgecolor="black", alpha=0.88)
    ax1.axhline(never, color="#888888", linestyle="--", linewidth=1.2, label="NeverRemove baseline")
    for bar, m in zip(bars, means):
        delta = never - m
        ax1.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + max(errs) * 0.15,
                 f"{delta:+.0f}h", ha="center", va="bottom", fontsize=9,
                 color="darkred" if delta > 0 else "navy")
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=10)
    ax1.set_ylabel("Mean Training Time (hrs)")
    ax1.set_title("Training Time by Retirement Policy")
    ax1.set_ylim(bottom=min(means) * 0.93)
    ax1.legend(fontsize=8)
    ax1.grid(axis="y", alpha=0.3)

    # Right: servers retired
    ax2.bar(x, retired, color=colors, edgecolor="black", alpha=0.88)
    for bar, r in zip(ax2.patches, retired):
        if r > 0:
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                     f"{r:.0f}", ha="center", va="bottom", fontsize=9)
    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=10)
    ax2.set_ylabel("Mean Servers Retired")
    ax2.set_title("Servers Retired by Policy")
    ax2.grid(axis="y", alpha=0.3)

    n_bad = int(TARGET.systematic_failure_fraction * TARGET.working_pool_size)
    fig.suptitle(
        f"Target regime: mult={TARGET.systematic_failure_rate_multiplier:.0f}×, "
        f"manual_repair_fail={TARGET.manual_repair_fail_prob}, "
        f"recovery={TARGET.recovery_time:.0f}min, "
        f"{TARGET.systematic_failure_fraction:.0%} bad ({n_bad} servers)",
        fontsize=10,
    )
    plt.tight_layout()
    path = fig_path("payoff_policies.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"\n  Saved → {path}")
    plt.close()


def plot_vs_multiplier(results: list):
    import matplotlib.pyplot as plt
    import numpy as np

    mults  = [r[0] for r in results]
    never  = [r[1] for r in results]
    sd_n   = [r[2] for r in results]
    thresh = [r[3] for r in results]
    sd_t   = [r[4] for r in results]
    deltas = [r[6] for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    x = np.arange(len(mults))
    w = 0.38
    ax1.bar(x - w/2, never,  w, yerr=sd_n, capsize=3, label="NeverRemove",
            color="#888888", edgecolor="black", alpha=0.85)
    ax1.bar(x + w/2, thresh, w, yerr=sd_t, capsize=3, label="Thresh≥2/7d",
            color="#C44E52", edgecolor="black", alpha=0.85)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{m}×" for m in mults])
    ax1.set_xlabel("systematic_failure_rate_multiplier")
    ax1.set_ylabel("Mean Training Time (hrs)")
    ax1.set_title("Training Time: NeverRemove vs Thresh≥2/7d")
    ax1.legend()
    ax1.grid(axis="y", alpha=0.3)

    color = ["#C44E52" if d > 0 else "#4C72B0" for d in deltas]
    ax2.bar(x, deltas, color=color, edgecolor="black", alpha=0.85)
    ax2.axhline(0, color="black", linewidth=0.8)
    for bar, d in zip(ax2.patches, deltas):
        ax2.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + (2 if d >= 0 else -8),
                 f"{d:+.0f}h", ha="center", va="bottom", fontsize=9)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{m}×" for m in mults])
    ax2.set_xlabel("systematic_failure_rate_multiplier")
    ax2.set_ylabel("Time Saved by Retirement (hrs)")
    ax2.set_title("Retirement Benefit vs Failure Rate Multiplier\n"
                  "(positive = retirement wins)")
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    path = fig_path("payoff_multiplier.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


def plot_vs_repair_fail(results: list):
    import matplotlib.pyplot as plt
    import numpy as np

    probs   = [r[0] for r in results]
    p_fix   = [r[1] for r in results]
    never   = [r[2] for r in results]
    sd_n    = [r[3] for r in results]
    thresh  = [r[4] for r in results]
    sd_t    = [r[5] for r in results]
    deltas  = [r[7] for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    x = np.arange(len(probs))
    w = 0.38
    ax1.bar(x - w/2, never,  w, yerr=sd_n, capsize=3, label="NeverRemove",
            color="#888888", edgecolor="black", alpha=0.85)
    ax1.bar(x + w/2, thresh, w, yerr=sd_t, capsize=3, label="Thresh≥2/7d",
            color="#C44E52", edgecolor="black", alpha=0.85)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{p:.0%}\n(fix={f:.0%})" for p, f in zip(probs, p_fix)], fontsize=8)
    ax1.set_xlabel("manual_repair_fail_prob  (fix rate in parentheses)")
    ax1.set_ylabel("Mean Training Time (hrs)")
    ax1.set_title("Training Time vs Repair Effectiveness")
    ax1.legend()
    ax1.grid(axis="y", alpha=0.3)

    color = ["#C44E52" if d > 0 else "#4C72B0" for d in deltas]
    ax2.bar(x, deltas, color=color, edgecolor="black", alpha=0.85)
    ax2.axhline(0, color="black", linewidth=0.8)
    for bar, d in zip(ax2.patches, deltas):
        ax2.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + (1 if d >= 0 else -6),
                 f"{d:+.0f}h", ha="center", va="bottom", fontsize=9)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"{p:.0%}" for p in probs])
    ax2.set_xlabel("manual_repair_fail_prob")
    ax2.set_ylabel("Time Saved by Retirement (hrs)")
    ax2.set_title("Retirement Benefit vs Repair Effectiveness\n"
                  "(positive = retirement wins, shrinks as repairs improve)")
    ax2.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    path = fig_path("payoff_repair_fail.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    print(f"  Saved → {path}")
    plt.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("AIReSim — Retirement Payoff Experiment")
    print("=" * 65)
    p_fix = (
        (1 - TARGET.prob_auto_to_manual) * (1 - TARGET.auto_repair_fail_prob)
        + TARGET.prob_auto_to_manual * (1 - TARGET.manual_repair_fail_prob)
    )
    bad_ttf_days = 1.0 / (
        (1 + TARGET.systematic_failure_rate_multiplier) * TARGET.random_failure_rate * 24 * 60
    )
    print(f"\nTarget regime parameters:")
    print(f"  systematic_failure_rate_multiplier : {TARGET.systematic_failure_rate_multiplier:.0f}×")
    print(f"  bad-server mean TTF                : {bad_ttf_days:.1f} days  "
          f"(good = {1/(TARGET.random_failure_rate*24*60):.0f} days)")
    print(f"  manual_repair_fail_prob            : {TARGET.manual_repair_fail_prob}  "
          f"(effective fix rate ≈ {p_fix:.0%})")
    print(f"  recovery_time                      : {TARGET.recovery_time:.0f} min per failure")
    print(f"  bad servers                        : "
          f"{int(TARGET.systematic_failure_fraction * TARGET.working_pool_size)} "
          f"({TARGET.systematic_failure_fraction:.0%} of pool)")
    print(f"  pool headroom                      : "
          f"{TARGET.working_pool_size - TARGET.job_size - TARGET.warm_standbys} idle servers")
    print(f"  replications                       : {N_REPS}")

    res1 = exp_policy_comparison()
    res2 = exp_vs_multiplier()
    res3 = exp_vs_repair_fail()

    print("\nSaving plots …")
    plot_policy_comparison(res1)
    plot_vs_multiplier(res2)
    plot_vs_repair_fail(res3)

    print("\n" + "=" * 65)
    print("Done. PNGs written to:", FIGURES_DIR)
    for fname in sorted(os.listdir(FIGURES_DIR)):
        if fname.endswith(".png"):
            kb = os.path.getsize(fig_path(fname)) // 1024
            print(f"  {fname}  ({kb} KB)")


if __name__ == "__main__":
    main()
