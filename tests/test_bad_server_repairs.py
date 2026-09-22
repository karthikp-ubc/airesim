"""Counters for repairs of bad servers: cures (bad -> good) and silent failures.

A silent repair failure only matters for a bad server; on a good server it leaves the
server good.  These counters draw no random numbers.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.params import Params
from airesim.simulator import Simulator


def _params(**overrides) -> Params:
    defaults = dict(
        job_size=8, warm_standbys=2, working_pool_size=20, spare_pool_size=5,
        job_length=10 * 24 * 60, random_failure_rate=0.3 / (24 * 60),
        systematic_failure_rate_multiplier=10.0, systematic_failure_fraction=0.3,
        recovery_time=5, host_selection_time=1, preemption_wait_time=5,
        auto_repair_time=30, manual_repair_time=120, diagnosis_probability=1.0,
        diagnosis_uncertainty=0.0, seed=42, num_replications=1,
    )
    defaults.update(overrides)
    return Params(**defaults)


def test_repairs_partition_into_good_cured_and_failed():
    r = Simulator(params=_params(auto_repair_fail_prob=0.4, manual_repair_fail_prob=0.4),
                  seed=3).run()

    on_bad = r.auto_repairs - r.nonfaulty_repairs
    assert on_bad > 0 and r.nonfaulty_repairs > 0
    assert r.bad_servers_cured + r.bad_server_repair_failures == on_bad


def test_perfect_repairs_cure_every_bad_server_repaired():
    r = Simulator(params=_params(auto_repair_fail_prob=0.0, manual_repair_fail_prob=0.0),
                  seed=3).run()

    assert r.bad_server_repair_failures == 0
    assert r.bad_servers_cured == r.auto_repairs - r.nonfaulty_repairs > 0


def test_always_failing_repairs_never_cure():
    r = Simulator(params=_params(auto_repair_fail_prob=1.0, manual_repair_fail_prob=1.0),
                  seed=3).run()

    assert r.bad_servers_cured == 0
    assert r.bad_server_repair_failures == r.auto_repairs - r.nonfaulty_repairs > 0
