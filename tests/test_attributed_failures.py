"""Tests for attributed_failure_count and FewestAttributedFailuresFirst.

``total_failure_count`` is incremented on the server that truly failed (ground
truth).  ``attributed_failure_count`` is incremented only on the server that the
diagnosis step blames, so the two diverge under misattribution and missed
diagnosis.
"""

from __future__ import annotations

import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.coordinator import Coordinator
from airesim.params import Params
from airesim.policies import NeverRemove
from airesim.scheduling_policies import (
    FewestAttributedFailuresFirst,
    FewestFailuresFirst,
)
from airesim.server import Server
from airesim.simulator import Simulator


def _params(**overrides) -> Params:
    defaults = dict(
        job_size=8,
        warm_standbys=2,
        working_pool_size=20,
        spare_pool_size=5,
        job_length=3 * 24 * 60,
        random_failure_rate=0.3 / (24 * 60),
        systematic_failure_rate_multiplier=10.0,
        systematic_failure_fraction=0.3,
        recovery_time=5,
        host_selection_time=1,
        preemption_wait_time=5,
        auto_repair_time=30,
        manual_repair_time=120,
        seed=42,
        num_replications=1,
    )
    defaults.update(overrides)
    return Params(**defaults)


class _Capturing(Simulator):
    """Simulator that exposes the server list created inside run()."""

    def _main_loop(self, env, rng, p, coordinator, scheduler, repair_shop,
                   pool_mgr, stats, all_servers):
        self.all_servers = all_servers
        yield from super()._main_loop(
            env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats, all_servers
        )


class _BlameSpy(NeverRemove):
    """Records every server the diagnosis step sends to on_failure."""

    def __init__(self):
        self.blamed: list[Server] = []

    def on_failure(self, server):
        self.blamed.append(server)


def _record_true_failures(monkeypatch) -> list[Server]:
    true_failed: list[Server] = []
    orig = Coordinator._find_first_failure

    def wrapper(self, servers, remaining):
        ttf, s = orig(self, servers, remaining)
        if s is not None:
            true_failed.append(s)
        return ttf, s

    monkeypatch.setattr(Coordinator, "_find_first_failure", wrapper)
    return true_failed


# ── (a) misattribution moves the attributed count to the blamed server ───────

def test_full_misattribution_counts_blamed_not_true_server(monkeypatch):
    true_failed = _record_true_failures(monkeypatch)
    spy = _BlameSpy()
    p = _params(diagnosis_probability=1.0, diagnosis_uncertainty=1.0)
    sim = _Capturing(params=p, removal_policy=spy, seed=7)
    sim.run()

    assert len(true_failed) > 5, "test setup must produce several failures"
    assert len(spy.blamed) == len(true_failed)
    # uncertainty=1: every diagnosed failure blames a different (innocent) server
    assert all(b is not t for b, t in zip(spy.blamed, true_failed))

    true_tally = Counter(id(s) for s in true_failed)
    blame_tally = Counter(id(s) for s in spy.blamed)
    for s in sim.all_servers:
        assert s.total_failure_count == true_tally[id(s)]
        assert s.attributed_failure_count == blame_tally[id(s)]
    # ground truth and attribution genuinely differ for some server
    assert any(s.total_failure_count != s.attributed_failure_count for s in sim.all_servers)


def test_undiagnosed_failures_are_not_attributed():
    p = _params(diagnosis_probability=0.0, diagnosis_uncertainty=0.0)
    sim = _Capturing(params=p, seed=7)
    result = sim.run()

    assert result.total_failures > 5
    assert sum(s.total_failure_count for s in sim.all_servers) == result.total_failures
    assert all(s.attributed_failure_count == 0 for s in sim.all_servers)


# ── (b) perfect diagnosis: the two counters agree everywhere ─────────────────

def test_counters_equal_with_perfect_diagnosis():
    p = _params(diagnosis_probability=1.0, diagnosis_uncertainty=0.0)
    sim = _Capturing(params=p, seed=7)
    result = sim.run()

    assert result.total_failures > 5
    for s in sim.all_servers:
        assert s.attributed_failure_count == s.total_failure_count
    assert result.misattributed_repairs == 0


def test_misattributed_repairs_counted():
    p = _params(diagnosis_probability=1.0, diagnosis_uncertainty=1.0)
    result = Simulator(params=p, seed=7).run()
    assert result.misattributed_repairs == result.total_failures


# ── (c) the scheduler actually invokes the new policy ────────────────────────

class _SpyPolicy(FewestAttributedFailuresFirst):
    def __init__(self):
        self.calls = []

    def select(self, available_servers, job_size, warm_standbys, rng):
        counts_before = {id(s): s.attributed_failure_count for s in available_servers}
        chosen = super().select(available_servers, job_size, warm_standbys, rng)
        self.calls.append((counts_before, chosen))
        return chosen


def test_scheduler_invokes_attributed_policy():
    spy = _SpyPolicy()
    p = _params(diagnosis_probability=1.0, diagnosis_uncertainty=0.2)
    Simulator(params=p, host_selection_policy=spy, seed=7).run()

    assert len(spy.calls) >= 1
    counts_before, chosen = spy.calls[-1]
    chosen_counts = [counts_before[id(s)] for s in chosen]
    assert chosen_counts == sorted(chosen_counts)


def _server(i, total, attributed):
    s = Server(i, None, False, 0.0, 0.0)
    s.total_failure_count = total
    s.attributed_failure_count = attributed
    return s


def test_policy_orders_by_attributed_not_true_count():
    # server 0: many true failures but never blamed; server 1: blamed but never failed
    servers = [_server(0, total=9, attributed=0), _server(1, total=0, attributed=9),
               _server(2, total=3, attributed=3)]
    rng = random.Random(0)

    attributed = FewestAttributedFailuresFirst().select(servers, 2, 0, rng)
    oracle = FewestFailuresFirst().select(servers, 2, 0, rng)

    assert [s.server_id for s in attributed] == [0, 2]
    assert [s.server_id for s in oracle] == [1, 2]
