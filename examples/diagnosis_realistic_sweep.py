"""Does diagnosis_uncertainty matter at the realistic (DSN'26 Table I) defaults?

Starts from config.yaml and varies only:
  diagnosis_uncertainty          [0.0, 0.1, 0.2, 0.3, 0.5]
  systematic failure multiplier  [3, 5, 10]
  diagnosis_probability          0.8 for the full grid, plus 1.0 at multiplier 5 only
Policies (all with NeverRemove): Random, FewestFailuresFirst (oracle),
FewestAttributedFailuresFirst.  20 replications per cell, seeds BASE_SEED..+19,
identical seed set for every cell and policy.  (All components share one RNG, so
runs from the same seed diverge after the first differing draw; the seed sets are
the same for reproducibility, they do not give variance-reducing common random
numbers.  The analysis therefore uses paired-t intervals, which stay valid.)

One CSV row per replication is appended and flushed as soon as it finishes; a
re-run skips rows already present, so the sweep is resumable.  Each row records
N_REPS, seed, git commit, and the full Params as JSON.

Usage:
    python3 examples/diagnosis_realistic_sweep.py [--workers 6]
    python3 examples/diagnosis_realistic_sweep.py --sanity   # exact-reproduction check
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from multiprocessing import Pool

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)

from airesim.params import Params  # noqa: E402
from airesim.policies import NeverRemove  # noqa: E402
from airesim.run import _load_params  # noqa: E402
from airesim.scheduling_policies import (  # noqa: E402
    DefaultHostSelection,
    FewestAttributedFailuresFirst,
    FewestFailuresFirst,
)
from airesim.simulator import Simulator  # noqa: E402

OUT_DIR = os.path.join(_here, "diagnosis_realistic_figures")
RESULTS_CSV = os.path.join(OUT_DIR, "results.csv")
SANITY_CSV = os.path.join(OUT_DIR, "sanity.csv")
CONFIG = os.path.join(_root, "config.yaml")

N_REPS = 20
BASE_SEED = 42
UNCERTAINTIES = [0.0, 0.1, 0.2, 0.3, 0.5]
MULTIPLIERS = [3.0, 5.0, 10.0]
MONITOR_INTERVAL = 360.0  # simulated minutes between faulty-server samples

POLICIES = {
    "Random": DefaultHostSelection,
    "FFF_oracle": FewestFailuresFirst,
    "FAFF": FewestAttributedFailuresFirst,
}

FIELDS = [
    "git_commit", "n_reps", "base_seed", "seed", "rep", "policy", "removal_policy",
    "diagnosis_probability", "diagnosis_uncertainty", "multiplier",
    "training_time_hrs", "etr", "total_failures", "systematic_failures",
    "misattributed_repairs", "nonfaulty_repairs", "servers_retired",
    "faulty_in_pool_timeavg", "faulty_in_active_timeavg", "n_monitor_samples",
    "host_selection_count", "preemption_count", "job_stall_count", "cluster_depleted",
    "wall_seconds", "params_json",
]


class MonitoredSimulator(Simulator):
    """Simulator that samples faulty-server counts every MONITOR_INTERVAL minutes.

    The monitor is read-only and draws no random numbers, so results are
    identical to the plain Simulator (checked by --sanity).
    """

    def _main_loop(self, env, rng, p, coordinator, scheduler, repair_shop,
                   pool_mgr, stats, all_servers):
        self._done = False
        self._pool_samples: list[int] = []
        self._active_samples: list[int] = []
        env.process(self._monitor(env, pool_mgr, scheduler))
        yield from super()._main_loop(
            env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats, all_servers
        )
        self._done = True

    def _monitor(self, env, pool_mgr, scheduler):
        while not self._done:
            self._pool_samples.append(sum(1 for s in pool_mgr.working_pool if s.is_bad))
            self._active_samples.append(sum(1 for s in scheduler.active_servers if s.is_bad))
            yield env.timeout(MONITOR_INTERVAL)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", _root, *args], text=True).strip()


def git_commit() -> str:
    return _git("rev-parse", "HEAD")


def dirty_paths() -> str:
    return _git("status", "--porcelain", "--", "airesim", "config.yaml",
                "examples/diagnosis_realistic_sweep.py")


def build_params(prob: float, unc: float, mult: float, seed: int) -> Params:
    return _load_params(CONFIG).with_overrides(
        diagnosis_probability=prob,
        diagnosis_uncertainty=unc,
        systematic_failure_rate_multiplier=mult,
        seed=seed,
        num_replications=N_REPS,
    )


def _init_worker() -> None:
    os.nice(19)


def run_one(job: tuple) -> dict:
    """Run one replication and return its CSV row (executed in a worker)."""
    commit, prob, unc, mult, policy, rep = job
    seed = BASE_SEED + rep
    params = build_params(prob, unc, mult, seed)
    t0 = time.time()
    sim = MonitoredSimulator(
        params=params, host_selection_policy=POLICIES[policy](),
        removal_policy=NeverRemove(), seed=seed,
    )
    r = sim.run()
    n = len(sim._pool_samples)
    return {
        "git_commit": commit, "n_reps": N_REPS, "base_seed": BASE_SEED, "seed": seed,
        "rep": rep, "policy": policy, "removal_policy": "NeverRemove",
        "diagnosis_probability": prob, "diagnosis_uncertainty": unc, "multiplier": mult,
        "training_time_hrs": repr(r.training_time_hours),
        "etr": repr(r.effective_training_ratio),
        "total_failures": r.total_failures,
        "systematic_failures": r.systematic_failures,
        "misattributed_repairs": r.misattributed_repairs,
        "nonfaulty_repairs": r.nonfaulty_repairs,
        "servers_retired": r.servers_retired,
        "faulty_in_pool_timeavg": repr(sum(sim._pool_samples) / n),
        "faulty_in_active_timeavg": repr(sum(sim._active_samples) / n),
        "n_monitor_samples": n,
        "host_selection_count": r.host_selection_count,
        "preemption_count": r.preemption_count,
        "job_stall_count": r.job_stall_count,
        "cluster_depleted": int(r.cluster_depleted),
        "wall_seconds": round(time.time() - t0, 2),
        "params_json": json.dumps(asdict(params), sort_keys=True),
    }


def key_of(row: dict) -> tuple:
    return (float(row["diagnosis_probability"]), float(row["diagnosis_uncertainty"]),
            float(row["multiplier"]), row["policy"], int(row["rep"]))


def main_grid() -> list[tuple[float, float, float]]:
    cells = [(0.8, u, m) for m in MULTIPLIERS for u in UNCERTAINTIES]
    cells += [(1.0, u, 5.0) for u in UNCERTAINTIES]
    return cells


def sanity_grid() -> list[tuple[float, float, float]]:
    return [(1.0, 0.0, 5.0), (0.8, 0.0, 5.0)]


def run_sweep(csv_path: str, cells, policies, n_reps: int, workers: int,
              allow_dirty: bool) -> None:
    dirty = dirty_paths()
    if dirty and not allow_dirty:
        sys.exit("Refusing to run: uncommitted changes in code/config/script:\n" + dirty)
    commit = git_commit()
    os.makedirs(OUT_DIR, exist_ok=True)

    done: set[tuple] = set()
    if os.path.exists(csv_path):
        with open(csv_path, newline="") as f:
            done = {key_of(r) for r in csv.DictReader(f)}
    # rep-major order so an interrupted sweep has balanced replications per cell
    jobs = [(commit, p, u, m, pol, rep)
            for rep in range(n_reps) for (p, u, m) in cells for pol in policies
            if (p, u, m, pol, rep) not in done]
    total = len(jobs) + len(done)
    print(f"{len(done)} rows already present, {len(jobs)} to run "
          f"(commit {commit[:10]}, workers={workers})", flush=True)
    if not jobs:
        return

    new_file = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
    t0 = time.time()
    with open(csv_path, "a", newline="") as f, Pool(workers, initializer=_init_worker) as pool:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(run_one, jobs, chunksize=1), 1):
            w.writerow(row)
            f.flush()
            if i % 20 == 0 or i == len(jobs):
                el = time.time() - t0
                eta = el / i * (len(jobs) - i)
                print(f"  {len(done) + i}/{total} rows  elapsed {el/60:.1f} min  "
                      f"ETA {eta/60:.1f} min", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sanity", action="store_true",
                    help="30-seed Random+NeverRemove check at probability 1.0 and 0.8")
    ap.add_argument("--allow-dirty", action="store_true")
    a = ap.parse_args()
    if a.sanity:
        global N_REPS
        N_REPS = 30
        run_sweep(SANITY_CSV, sanity_grid(), ["Random"], 30, a.workers, a.allow_dirty)
    else:
        run_sweep(RESULTS_CSV, main_grid(), list(POLICIES), N_REPS, a.workers, a.allow_dirty)


if __name__ == "__main__":
    main()
