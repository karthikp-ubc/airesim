"""Tests for scheduling policies, including HighestScoreFirst."""

from __future__ import annotations

import os
import random
import sys

import simpy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.params import Params
from airesim.policies import ScoredRemoval
from airesim.scheduling_policies import (
    DefaultHostSelection,
    HighestScoreFirst,
)
from airesim.server import Server
from airesim.simulator import Simulator

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_server(server_id: int = 0, is_bad: bool = False) -> Server:
    env = simpy.Environment()
    return Server(
        server_id=server_id,
        env=env,
        is_bad=is_bad,
        random_failure_rate=0.0,
        systematic_failure_rate=0.0,
    )


def _rng() -> random.Random:
    return random.Random(42)


# ── DefaultHostSelection unit tests ───────────────────────────────────────────

class TestDefaultHostSelection:

    def test_returns_needed_count(self):
        policy = DefaultHostSelection()
        servers = [make_server(i) for i in range(20)]
        selected = policy.select(servers, job_size=5, warm_standbys=2, rng=_rng())
        assert len(selected) == 7

    def test_returns_fewer_when_pool_too_small(self):
        policy = DefaultHostSelection()
        servers = [make_server(i) for i in range(3)]
        selected = policy.select(servers, job_size=5, warm_standbys=2, rng=_rng())
        assert len(selected) == 3

    def test_no_duplicates_in_selection(self):
        policy = DefaultHostSelection()
        servers = [make_server(i) for i in range(20)]
        selected = policy.select(servers, job_size=5, warm_standbys=2, rng=_rng())
        assert len(set(selected)) == len(selected)

    def test_samples_across_entire_pool_not_just_a_prefix(self):
        """Regression test: selection must be a uniform sample of the whole
        available pool, not a shuffle restricted to available_servers[:needed].

        Before the fix, DefaultHostSelection took available_servers[:needed]
        first and only shuffled *within* that prefix, so a server at index
        >= needed could never be selected regardless of rng seed. Here we
        sweep many seeds with needed=5 out of 20 servers and confirm servers
        beyond index 5 do get selected.
        """
        policy = DefaultHostSelection()
        servers = [make_server(i) for i in range(20)]
        prefix_ids = {s.server_id for s in servers[:5]}

        selected_beyond_prefix = False
        for seed in range(50):
            selected = policy.select(servers, job_size=5, warm_standbys=0,
                                      rng=random.Random(seed))
            if any(s.server_id not in prefix_ids for s in selected):
                selected_beyond_prefix = True
                break

        assert selected_beyond_prefix, (
            "DefaultHostSelection never selected a server outside the first "
            "`needed` positions across 50 seeds — selection is not sampling "
            "the full available pool"
        )

    def test_every_server_selectable_over_many_seeds(self):
        """Every server in the pool should be selectable, not just a fixed subset."""
        policy = DefaultHostSelection()
        servers = [make_server(i) for i in range(10)]
        ever_selected = set()
        for seed in range(200):
            selected = policy.select(servers, job_size=3, warm_standbys=0,
                                      rng=random.Random(seed))
            ever_selected.update(s.server_id for s in selected)
        assert ever_selected == set(range(10))


# ── HighestScoreFirst unit tests ──────────────────────────────────────────────

class TestHighestScoreFirst:

    def test_selects_highest_scored_servers(self):
        """Servers with higher scores should be selected first."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=20.0)
        policy = HighestScoreFirst(scored)

        servers = [make_server(i) for i in range(5)]
        # Penalise servers 0 and 1 so they have lower scores
        scored.on_failure(servers[0])  # score 80
        scored.on_failure(servers[0])  # score 60
        scored.on_failure(servers[1])  # score 80

        selected = policy.select(servers, job_size=3, warm_standbys=0, rng=_rng())
        assert len(selected) == 3
        # servers 2, 3, 4 all have score 100 and should beat 0 (60) and 1 (80)
        assert servers[0] not in selected
        assert servers[1] not in selected

    def test_selects_all_when_fewer_available(self):
        """Returns fewer than requested when pool is small."""
        scored = ScoredRemoval()
        policy = HighestScoreFirst(scored)
        servers = [make_server(i) for i in range(3)]
        selected = policy.select(servers, job_size=5, warm_standbys=2, rng=_rng())
        assert len(selected) == 3

    def test_untracked_servers_get_initial_score(self):
        """Servers with no score entry are treated as having initial_score."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=30.0)
        policy = HighestScoreFirst(scored)

        s_fresh = make_server(0)
        s_penalised = make_server(1)
        scored.on_failure(s_penalised)  # 70

        selected = policy.select([s_fresh, s_penalised], job_size=1, warm_standbys=0, rng=_rng())
        assert selected == [s_fresh]

    def test_includes_warm_standbys(self):
        """job_size + warm_standbys servers are returned total."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=10.0)
        policy = HighestScoreFirst(scored)
        servers = [make_server(i) for i in range(10)]
        selected = policy.select(servers, job_size=4, warm_standbys=2, rng=_rng())
        assert len(selected) == 6

    def test_lowest_scored_server_assigned_last_as_standby(self):
        """The worst server should appear last (as standby) or not at all."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=40.0)
        policy = HighestScoreFirst(scored)

        servers = [make_server(i) for i in range(4)]
        # server 0 is the worst: 2 failures → score 20
        scored.on_failure(servers[0])
        scored.on_failure(servers[0])

        selected = policy.select(servers, job_size=3, warm_standbys=0, rng=_rng())
        assert servers[0] not in selected

    def test_score_ordering_is_descending(self):
        """The first returned server should have the highest score."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=10.0)
        policy = HighestScoreFirst(scored)

        servers = [make_server(i) for i in range(5)]
        # Give each server a distinct score
        for i, s in enumerate(servers):
            for _ in range(i):          # server i has score 100 - i*10
                scored.on_failure(s)

        # Use seed that won't break ties in the wrong direction (all unique scores)
        selected = policy.select(servers, job_size=5, warm_standbys=0, rng=random.Random(0))
        scores = [scored.get_score(s) for s in selected]
        assert scores == sorted(scores, reverse=True)

    def test_reset_restores_initial_ordering(self):
        """After reset(), previously penalised servers rank equal to fresh ones."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=50.0)
        policy = HighestScoreFirst(scored)

        servers = [make_server(0), make_server(1)]
        scored.on_failure(servers[0])  # score 50 — worse than server 1

        before = policy.select(servers, job_size=1, warm_standbys=0, rng=random.Random(0))
        assert before == [servers[1]]

        scored.reset()
        # Now both have initial_score=100; result is random but both are candidates
        selected = policy.select(servers, job_size=2, warm_standbys=0, rng=random.Random(0))
        assert set(selected) == {servers[0], servers[1]}


# ── Integration test: HighestScoreFirst + ScoredRemoval end-to-end ─────────────

class TestHighestScoreFirstIntegration:

    def _base_params(self, **overrides) -> Params:
        defaults = dict(
            job_size=8,
            warm_standbys=2,
            working_pool_size=20,
            spare_pool_size=5,
            job_length=2 * 24 * 60,
            random_failure_rate=0.02 / (24 * 60),
            systematic_failure_rate_multiplier=5.0,
            systematic_failure_fraction=0.10,
            recovery_time=10,
            host_selection_time=1,
            preemption_wait_time=5,
            auto_repair_time=30,
            manual_repair_time=120,
            prob_auto_to_manual=0.5,
            auto_repair_fail_prob=0.3,
            manual_repair_fail_prob=0.3,
            seed=0,
            num_replications=1,
        )
        defaults.update(overrides)
        return Params(**defaults)

    def test_simulation_completes_with_highest_score_first(self):
        """Simulator must complete cleanly when HighestScoreFirst is the scheduling policy."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=30.0, retirement_threshold=0.0)
        params = self._base_params()
        sim = Simulator(
            params=params,
            host_selection_policy=HighestScoreFirst(scored),
            removal_policy=scored,
            seed=1,
        )
        result = sim.run()
        assert result.total_training_time > 0
        assert not result.cluster_depleted

    def test_same_policy_object_shared_safely(self):
        """Passing the same ScoredRemoval to both HighestScoreFirst and removal_policy
        must not cause state corruption across two sequential runs."""
        scored = ScoredRemoval(initial_score=100.0, failure_penalty=30.0, retirement_threshold=0.0)
        params = self._base_params()
        sim = Simulator(
            params=params,
            host_selection_policy=HighestScoreFirst(scored),
            removal_policy=scored,
            seed=2,
        )
        r1 = sim.run()
        r2 = sim.run()  # reset() is called between runs
        # Both runs should complete and produce reasonable times
        assert r1.total_training_time > 0
        assert r2.total_training_time > 0
        # Scores should be cleared at the start of each run so results are comparable
        assert abs(r1.total_training_time - r2.total_training_time) < r1.total_training_time * 0.5
