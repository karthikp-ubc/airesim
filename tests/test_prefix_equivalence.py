"""The default escalation policy reproduces the pre-8896140 simulator bit-for-bit.

Golden values in tests/data/prefix_golden.json were produced by running the commit
*before* 8896140 (see tests/generate_prefix_golden.py).  With the default
``DefaultRepairEscalation`` (the DSN'26 paper's model) every statistic, including
the exact float training time, must match, because the RNG is consumed in the same
order: escalation draw first, then the auto-repair outcome only if not escalated.

- Small-cluster cases and one config.yaml run are always on.
- The full check (config.yaml at the SIMULATION_REPORT / sanity.csv seeds 42-71, at
  diagnosis_probability 1.0 and 0.8) takes a few minutes; enable it with
  ``AIRESIM_FULL_EQUIVALENCE=1 pytest tests/test_prefix_equivalence.py``.
"""

from __future__ import annotations

import json
import os
import sys
from multiprocessing import Pool

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import prefix_cases  # noqa: E402

with open(os.path.join(os.path.dirname(__file__), "data", "prefix_golden.json")) as _f:
    GOLDEN = json.load(_f)


def _assert_matches_golden(actual: dict, golden: dict, msg: str) -> None:
    """Compare a case's result dict against its golden value.

    ``training_time_hours`` is compared with a relative tolerance rather than
    exact string equality: it's a repr() of an accumulated float, and CPython
    3.10/3.11 vs. 3.12 can round the last bit or two of that sum differently
    (observed magnitude ~1e-13 relative) even when every discrete event in the
    run -- and therefore every integer count below -- is bit-for-bit identical.
    All other fields (failure/repair/retirement counts) must match exactly.
    """
    actual = dict(actual)
    golden = dict(golden)
    actual_time = float(actual.pop("training_time_hours"))
    golden_time = float(golden.pop("training_time_hours"))
    assert actual == golden, msg
    assert actual_time == pytest.approx(golden_time, rel=1e-9), msg


@pytest.mark.parametrize("name", list(prefix_cases.SMALL_CASES))
def test_small_cases_match_prefix(name):
    for seed in prefix_cases.SMALL_SEEDS:
        _assert_matches_golden(
            prefix_cases.run_small(name, seed), GOLDEN["small"][name][str(seed)],
            f"case {name!r} seed {seed} diverged from the pre-fix simulator",
        )


def test_default_config_single_seed_matches_prefix():
    _assert_matches_golden(
        prefix_cases.run_default(1.0, 42), GOLDEN["default"]["1.0"]["42"],
        "config.yaml prob=1.0 seed=42 diverged from the pre-fix simulator",
    )


def _default_job(args):
    prob, seed = args
    return prob, seed, prefix_cases.run_default(prob, seed)


@pytest.mark.skipif(not os.environ.get("AIRESIM_FULL_EQUIVALENCE"),
                    reason="set AIRESIM_FULL_EQUIVALENCE=1 (takes a few minutes)")
def test_default_config_all_sanity_seeds_match_prefix():
    jobs = [(p, s) for p in prefix_cases.DEFAULT_PROBS for s in prefix_cases.DEFAULT_SEEDS]
    with Pool(6) as pool:
        results = pool.map(_default_job, jobs, chunksize=1)
    assert len(results) == 60
    for prob, seed, row in results:
        _assert_matches_golden(
            row, GOLDEN["default"][str(prob)][str(seed)],
            f"config.yaml prob={prob} seed={seed} diverged from the pre-fix simulator"
        )
