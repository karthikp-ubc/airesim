"""Systematic vs random failures as a function of job length, at the paper defaults.

Runs config.yaml (Random + NeverRemove, bad_server_regeneration off) at job lengths of
15, 30, 60, 120 and 256 days with 10 replications each (seeds 42-51) and logs one row
per replication to examples/job_length_figures/replications.csv.  Because a successful
repair turns a bad server good and nothing turns good servers bad, systematic failures
saturate as the bad population is cured; this sweep measures that.

    python3 examples/job_length_sweep.py [--workers 6]
"""

from __future__ import annotations

import argparse
import os
import sys
from multiprocessing import Pool

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
sys.path.insert(0, _root)
sys.path.insert(0, _here)

import sweep_common  # noqa: E402

from airesim.run import _load_params  # noqa: E402

OUT = os.path.join(_here, "job_length_figures", "replications.csv")
JOB_LENGTH_DAYS = [15, 30, 60, 120, 256]
N_REPS = 10
BASE_SEED = 42


def _one(args):
    days, rep, commit = args
    params = _load_params(os.path.join(_root, "config.yaml")).with_overrides(
        job_length=days * 24 * 60, seed=BASE_SEED, num_replications=N_REPS)
    log = sweep_common.ReplicationLog(OUT, __file__, truncate=False, commit=commit)
    log.run(params, BASE_SEED + rep, f"job_length={days}d")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    log = sweep_common.ReplicationLog(OUT, __file__)
    jobs = [(days, rep, log.commit) for days in JOB_LENGTH_DAYS for rep in range(N_REPS)]
    with Pool(a.workers, initializer=lambda: os.nice(19)) as pool:
        for i, _ in enumerate(pool.imap_unordered(_one, jobs, chunksize=1), 1):
            print(f"  {i}/{len(jobs)} done", flush=True)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
