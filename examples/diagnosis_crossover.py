"""Where does retirement stop beating failure-aware scheduling as diagnosis gets worse?

At perfect diagnosis (diagnosis_probability = 1.0) aggressive retirement
(Random + ScoredRemoval SC_fast) beats FewestFailuresFirst + NeverRemove in the
high-failure cells of the 2-D heat map; at the Table I default of 0.8 FewestFailuresFirst
wins most cells.  This script sweeps diagnosis_probability in three regimes where
retirement wins at 1.0 and locates the crossover with paired (same-seed) contrasts.

Setup: the 2-D heat-map "payoff regime" (examples/2d_heatmap_sweep.py: working pool 4600,
14-day job, 2x random failure rate, 8% bad servers, 60-min recovery, auto-repair fail 0.6),
diagnosis_uncertainty = 0.  Replication r uses seed 42 + r for every cell and policy.

Outputs (examples/diagnosis_crossover_figures/):
  replications.csv   one row per run
  results.csv        per (regime, diagnosis, policy) mean / stdev / 95% CI
  contrasts.csv      paired contrasts vs FewestFailuresFirst+NeverRemove and vs baseline
  crossover.csv      interpolated crossover diagnosis_probability per regime and contrast
  crossover.png      training time and paired contrast vs diagnosis_probability
  crossover_report.md

Usage:
    python3 examples/run_logged.py --log examples/diagnosis_crossover_figures/run.log -- \\
        python3 examples/diagnosis_crossover.py --workers 12
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from multiprocessing import Pool

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)
sys.path.insert(0, _here)

from sweep_common import MonitoredSimulator  # noqa: E402

from airesim.params import Params  # noqa: E402
from airesim.policies import NeverRemove, ScoredRemoval, ThresholdRemoval  # noqa: E402
from airesim.scheduling_policies import (  # noqa: E402
    DefaultHostSelection,
    FewestFailuresFirst,
)

OUT = os.path.join(_here, "diagnosis_crossover_figures")
DEFAULT_RATE = 0.01 / (24 * 60)

BASE = Params(
    working_pool_size=4600,
    spare_pool_size=200,
    job_size=4096,
    warm_standbys=16,
    job_length=14 * 24 * 60,
    random_failure_rate=2 * DEFAULT_RATE,
    systematic_failure_fraction=0.08,
    recovery_time=60.0,
    prob_auto_to_manual=0.80,
    auto_repair_fail_prob=0.60,
    diagnosis_uncertainty=0.0,
    seed=42,
)

# (systematic_failure_rate_multiplier, manual_repair_fail_prob): heat-map cells where
# Random+ScoredRemoval beat FewestFailuresFirst+NeverRemove at diagnosis 1.0.
REGIMES = [(15.0, 0.75), (20.0, 0.75), (25.0, 0.90)]
DIAGNOSIS = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0]

SC_FAST = dict(initial_score=100.0, failure_penalty=60.0, success_increment=5.0,
               time_period=24 * 60, retirement_threshold=0.0)

POLICIES = {
    "Random+NeverRemove": lambda: (DefaultHostSelection(), NeverRemove()),
    "Random+ScoredRemoval(SC_fast)": lambda: (DefaultHostSelection(),
                                              ScoredRemoval(**SC_FAST)),
    "Random+Thresh>=2/7d": lambda: (DefaultHostSelection(),
                                    ThresholdRemoval(2, 7 * 24 * 60)),
    "FewestFailuresFirst+NeverRemove": lambda: (FewestFailuresFirst(), NeverRemove()),
    "FewestFailuresFirst+ScoredRemoval(SC_fast)": lambda: (FewestFailuresFirst(),
                                                           ScoredRemoval(**SC_FAST)),
}
BASELINE = "Random+NeverRemove"
SCHED = "FewestFailuresFirst+NeverRemove"
RETIRE = "Random+ScoredRemoval(SC_fast)"

METRICS = ["training_time_hrs", "total_failures", "systematic_failures", "servers_retired",
           "misattributed_repairs", "faulty_in_pool_timeavg", "faulty_in_active_timeavg",
           "host_selection_count", "preemption_count", "cluster_depleted"]


def run_one(task: tuple) -> dict:
    """Run one (regime, diagnosis, policy, rep) replication and return its CSV row."""
    commit, mult, fail, diag, policy, rep = task
    params = BASE.with_overrides(systematic_failure_rate_multiplier=mult,
                                 manual_repair_fail_prob=fail, diagnosis_probability=diag)
    host, removal = POLICIES[policy]()
    seed = BASE.seed + rep
    t0 = time.time()
    r = MonitoredSimulator(params=params, host_selection_policy=host,
                           removal_policy=removal, seed=seed).run()
    row = {"git_commit": commit, "multiplier": mult, "manual_repair_fail_prob": fail,
           "diagnosis_probability": diag, "policy": policy, "seed": seed, "rep": rep,
           "training_time_hrs": repr(r.training_time_hours),
           "total_failures": r.total_failures, "systematic_failures": r.systematic_failures,
           "servers_retired": r.servers_retired,
           "misattributed_repairs": r.misattributed_repairs,
           "faulty_in_pool_timeavg": repr(r.faulty_in_pool_timeavg),
           "faulty_in_active_timeavg": repr(r.faulty_in_active_timeavg),
           "host_selection_count": r.host_selection_count,
           "preemption_count": r.preemption_count,
           "cluster_depleted": int(r.cluster_depleted),
           "wall_seconds": round(time.time() - t0, 2),
           "params_json": json.dumps(asdict(params), sort_keys=True)}
    return row


def mean_ci(xs: list[float]) -> tuple[float, float]:
    """Mean and 95% normal-approximation half-width."""
    m = statistics.fmean(xs)
    return m, (1.96 * statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0)


def analyse(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Cell summaries, paired contrasts, and interpolated crossovers."""
    by: dict[tuple, dict[int, dict]] = {}
    for r in rows:
        key = (float(r["multiplier"]), float(r["manual_repair_fail_prob"]),
               float(r["diagnosis_probability"]), r["policy"])
        by.setdefault(key, {})[int(r["rep"])] = r

    results = []
    for (mult, fail, diag, pol), reps in sorted(by.items()):
        tt = [float(r["training_time_hrs"]) for r in reps.values()]
        m, ci = mean_ci(tt)
        results.append({
            "multiplier": mult, "manual_repair_fail_prob": fail,
            "diagnosis_probability": diag, "policy": pol, "n": len(tt),
            "mean_time_hrs": m, "stdev_time_hrs": statistics.stdev(tt), "ci95_hrs": ci,
            **{f"mean_{k}": statistics.fmean(float(r[k]) for r in reps.values())
               for k in METRICS if k != "training_time_hrs"}})

    contrasts = []
    for mult, fail in REGIMES:
        for diag in DIAGNOSIS:
            for ref in (SCHED, BASELINE):
                base = by.get((mult, fail, diag, ref), {})
                for pol in POLICIES:
                    if pol == ref:
                        continue
                    cur = by.get((mult, fail, diag, pol), {})
                    d = [float(cur[k]["training_time_hrs"]) - float(base[k]["training_time_hrs"])
                         for k in sorted(set(cur) & set(base))]
                    if len(d) < 2:
                        continue
                    m, ci = mean_ci(d)
                    contrasts.append({"multiplier": mult, "manual_repair_fail_prob": fail,
                                      "diagnosis_probability": diag, "policy": pol,
                                      "reference": ref, "n": len(d), "delta_hrs": m,
                                      "ci95_hrs": ci, "lo": m - ci, "hi": m + ci})

    crossovers = []
    for mult, fail in REGIMES:
        for pol, ref in [(RETIRE, SCHED), ("FewestFailuresFirst+ScoredRemoval(SC_fast)", SCHED),
                         ("Random+Thresh>=2/7d", SCHED), (RETIRE, BASELINE)]:
            pts = sorted((c["diagnosis_probability"], c["delta_hrs"], c["lo"], c["hi"])
                         for c in contrasts if c["multiplier"] == mult
                         and c["manual_repair_fail_prob"] == fail
                         and c["policy"] == pol and c["reference"] == ref)
            crossovers.append({"multiplier": mult, "manual_repair_fail_prob": fail,
                               "policy": pol, "reference": ref,
                               "crossover_mean": _cross(pts, 1),
                               # retirement "clearly wins" above where hi < 0 starts,
                               # "clearly loses" below where lo > 0 ends
                               "clearly_better_from": _first_from(pts, lambda p: p[3] < 0),
                               "clearly_worse_up_to": _last_upto(pts, lambda p: p[2] > 0)})
    return results, contrasts, crossovers


def _cross(pts: list[tuple], i: int) -> float | None:
    """Highest diagnosis value where the contrast changes sign (linear interpolation).

    Contrast < 0 means the policy is faster than the reference.  Scanning from 1.0
    downward, return where it first rises through zero; None if it never does.
    """
    for (x0, *a), (x1, *b) in zip(reversed(pts[:-1]), reversed(pts[1:])):
        y0, y1 = a[i - 1], b[i - 1]
        if y1 < 0 <= y0:
            return x0 + (x1 - x0) * (0 - y0) / (y1 - y0)
    return None


def _first_from(pts: list[tuple], ok) -> float | None:
    """Smallest x such that ok() holds for every point at or above x."""
    out = None
    for p in reversed(pts):
        if not ok(p):
            break
        out = p[0]
    return out


def _last_upto(pts: list[tuple], ok) -> float | None:
    """Largest x such that ok() holds for every point at or below x."""
    out = None
    for p in pts:
        if not ok(p):
            break
        out = p[0]
    return out


def plot(results: list[dict], contrasts: list[dict], path: str) -> None:
    """Top row: training time per policy; bottom row: paired contrast vs FFF+Never."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, axes = plt.subplots(2, len(REGIMES), figsize=(5 * len(REGIMES), 8), sharex=True,
                             squeeze=False)
    colors = {"Random+NeverRemove": "#888888", RETIRE: "#C44E52",
              "Random+Thresh>=2/7d": "#DD8452", SCHED: "#4C72B0",
              "FewestFailuresFirst+ScoredRemoval(SC_fast)": "#55A868"}
    for j, (mult, fail) in enumerate(REGIMES):
        ax = axes[0][j]
        for pol in POLICIES:
            pts = sorted((r["diagnosis_probability"], r["mean_time_hrs"], r["ci95_hrs"])
                         for r in results if r["multiplier"] == mult
                         and r["manual_repair_fail_prob"] == fail and r["policy"] == pol)
            if pts:
                xs, ys, es = zip(*pts)
                ax.errorbar(xs, ys, yerr=es, marker="o", ms=3, capsize=2,
                            color=colors[pol], label=pol)
        ax.set_title(f"multiplier {mult:g}x, manual repair fail {fail:.0%}")
        ax.set_ylabel("Training time (hours)")
        ax.grid(alpha=0.3)
        ax = axes[1][j]
        for pol in POLICIES:
            pts = sorted((c["diagnosis_probability"], c["delta_hrs"], c["lo"], c["hi"])
                         for c in contrasts if c["multiplier"] == mult
                         and c["manual_repair_fail_prob"] == fail and c["policy"] == pol
                         and c["reference"] == SCHED)
            if pts:
                xs, ys, lo, hi = zip(*pts)
                ax.plot(xs, ys, marker="o", ms=3, color=colors[pol])
                ax.fill_between(xs, lo, hi, color=colors[pol], alpha=0.15)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xlabel("diagnosis_probability")
        ax.set_ylabel("Δ vs FewestFailuresFirst+NeverRemove (hours)\nnegative = faster")
        ax.grid(alpha=0.3)
    axes[0][0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_csv(path: str, rows: list[dict]) -> None:
    """Write a list of dicts as CSV."""
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def report(results: list[dict], contrasts: list[dict], crossovers: list[dict],
           commit: str, n_reps: int, path: str) -> None:
    """Markdown summary: contrast tables per regime and the crossover table."""
    def fx(x):
        return "—" if x is None else f"{x:.2f}"
    lines = ["# Diagnosis crossover: retirement vs failure-aware scheduling", "",
             f"Commit `{commit[:10]}`, {n_reps} paired replications (seeds "
             f"{BASE.seed}–{BASE.seed + n_reps - 1}) per cell. Δ = policy − reference, "
             "paired by seed; negative = policy faster. ± is the 95% CI.", ""]
    for mult, fail in REGIMES:
        lines += [f"## Multiplier {mult:g}×, manual repair fail {fail:.0%}", "",
                  "| diagnosis | " + " | ".join(p for p in POLICIES if p != SCHED)
                  + " | retired (Random+Scored) |", "|---" * len(POLICIES) + "|---|"]
        for diag in DIAGNOSIS:
            cells = []
            for pol in POLICIES:
                if pol == SCHED:
                    continue
                c = next((c for c in contrasts if c["multiplier"] == mult
                          and c["manual_repair_fail_prob"] == fail
                          and c["diagnosis_probability"] == diag and c["policy"] == pol
                          and c["reference"] == SCHED), None)
                cells.append("—" if c is None else f"{c['delta_hrs']:+.0f} ± {c['ci95_hrs']:.0f}")
            ret = next((r["mean_servers_retired"] for r in results if r["multiplier"] == mult
                        and r["manual_repair_fail_prob"] == fail
                        and r["diagnosis_probability"] == diag and r["policy"] == RETIRE), 0)
            lines.append(f"| {diag:g} | " + " | ".join(cells) + f" | {ret:.0f} |")
        lines += ["", "Reference: FewestFailuresFirst+NeverRemove.", ""]
    lines += ["## Crossovers", "",
              "`crossover` is where the mean contrast changes sign scanning down from 1.0 "
              "(linear interpolation); `clearly better from` is the lowest diagnosis value "
              "from which every point up to 1.0 has its CI below zero; `clearly worse up to` "
              "is the highest value up to which every point has its CI above zero.", "",
              "| regime | policy | vs | crossover | clearly better from | clearly worse up to |",
              "|---|---|---|---|---|---|"]
    for c in crossovers:
        lines.append(f"| {c['multiplier']:g}×, {c['manual_repair_fail_prob']:.0%} | "
                     f"{c['policy']} | {c['reference']} | {fx(c['crossover_mean'])} | "
                     f"{fx(c['clearly_better_from'])} | {fx(c['clearly_worse_up_to'])} |")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    """Run the sweep (or re-analyse an existing replications.csv)."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--replications", type=int, default=30)
    ap.add_argument("--analyse-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    rep_path = os.path.join(OUT, "replications.csv")
    commit = subprocess.check_output(["git", "-C", _root, "rev-parse", "HEAD"],
                                     text=True).strip()

    if a.analyse_only:
        with open(rep_path, newline="") as f:
            rows = list(csv.DictReader(f))
        commit = rows[0]["git_commit"]
    else:
        tasks = [(commit, m, fp, d, pol, rep) for m, fp in REGIMES for d in DIAGNOSIS
                 for pol in POLICIES for rep in range(a.replications)]
        print(f"{len(tasks)} runs on {a.workers} workers (commit {commit[:10]})", flush=True)
        rows, t0 = [], time.time()
        with Pool(a.workers) as pool:
            for i, row in enumerate(pool.imap_unordered(run_one, tasks), 1):
                rows.append(row)
                if i % 100 == 0 or i == len(tasks):
                    el = (time.time() - t0) / 60
                    print(f"  {i}/{len(tasks)} runs  {el:.1f} min  "
                          f"ETA {el * (len(tasks) - i) / i:.1f} min", flush=True)
        rows.sort(key=lambda r: (r["multiplier"], r["manual_repair_fail_prob"],
                                 r["diagnosis_probability"], r["policy"], r["rep"]))
        write_csv(rep_path, rows)

    results, contrasts, crossovers = analyse(rows)
    write_csv(os.path.join(OUT, "results.csv"), results)
    write_csv(os.path.join(OUT, "contrasts.csv"), contrasts)
    write_csv(os.path.join(OUT, "crossover.csv"), crossovers)
    plot(results, contrasts, os.path.join(OUT, "crossover.png"))
    n_reps = max(r["n"] for r in results)
    report(results, contrasts, crossovers, commit, n_reps,
           os.path.join(OUT, "crossover_report.md"))
    with open(os.path.join(OUT, "crossover_report.md")) as f:
        print(f.read())


if __name__ == "__main__":
    main()
