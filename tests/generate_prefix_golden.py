"""Generate tests/data/prefix_golden.json from a checkout of the pre-fix commit.

    git worktree add /tmp/airesim-prefix 9c7168c        # commit before 8896140
    python tests/generate_prefix_golden.py --repo /tmp/airesim-prefix

The pre-fix tree is put first on sys.path, so airesim resolves to it.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "prefix_golden.json")


def _default_job(args):
    prob, seed = args
    import prefix_cases
    return prob, seed, prefix_cases.run_default(prob, seed)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="pre-fix checkout (commit before 8896140)")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()

    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.abspath(a.repo))
    airesim = importlib.import_module("airesim")
    prefix_cases = importlib.import_module("prefix_cases")

    assert os.path.abspath(a.repo) in os.path.abspath(airesim.__file__), airesim.__file__
    commit = subprocess.check_output(["git", "-C", a.repo, "rev-parse", "HEAD"],
                                     text=True).strip()

    small = {n: {str(s): prefix_cases.run_small(n, s) for s in prefix_cases.SMALL_SEEDS}
             for n in prefix_cases.SMALL_CASES}
    jobs = [(p, s) for p in prefix_cases.DEFAULT_PROBS for s in prefix_cases.DEFAULT_SEEDS]
    with Pool(a.workers, initializer=lambda: os.nice(19)) as pool:
        res = pool.map(_default_job, jobs, chunksize=1)
    default: dict = {}
    for prob, seed, row in res:
        default.setdefault(str(prob), {})[str(seed)] = row

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"pre_fix_commit": commit, "default": default, "small": small},
                  f, indent=1, sort_keys=True)
    print("wrote", OUT, "from", commit)


if __name__ == "__main__":
    main()
