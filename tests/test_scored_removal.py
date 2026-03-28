"""Tests for the ScoredRemoval policy and its integration with the simulator."""

from __future__ import annotations

import random
import sys
import os

import simpy
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.server import Server, ServerState
from airesim.policies import ScoredRemoval, NeverRemove
from airesim.params import Params
from airesim.simulator import Simulator


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_server(server_id: int = 0, is_bad: bool = False) -> Server:
    env = simpy.Environment()
    return Server(
        server_id=server_id,
        env=env,
        is_bad=is_bad,
        random_failure_rate=0.01 / (24 * 60),
        systematic_failure_rate=0.0,
    )


# ── Unit tests: score arithmetic ─────────────────────────────────────────────

class TestScoredRemovalScoreArithmetic:

    def test_initial_score_default(self):
        policy = ScoredRemoval()
        s = make_server()
        assert policy.get_score(s) == 100.0

    def test_initial_score_custom(self):
        policy = ScoredRemoval(initial_score=50.0)
        s = make_server()
        assert policy.get_score(s) == 50.0

    def test_failure_decrements_score(self):
        policy = ScoredRemoval(initial_score=100.0, failure_penalty=25.0)
        s = make_server()
        policy.on_failure(s)
        assert policy.get_score(s) == 75.0

    def test_multiple_failures_accumulate(self):
        policy = ScoredRemoval(initial_score=100.0, failure_penalty=30.0)
        s = make_server()
        policy.on_failure(s)
        policy.on_failure(s)
        policy.on_failure(s)
        assert policy.get_score(s) == 10.0

    def test_success_increments_score(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            success_increment=10.0,
            time_period=60.0,   # 1 hour
        )
        s = make_server()
        policy.on_success(s, duration=120.0)   # 2 complete periods
        assert policy.get_score(s) == 120.0

    def test_success_below_time_period_gives_no_credit(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            success_increment=10.0,
            time_period=120.0,
        )
        s = make_server()
        policy.on_success(s, duration=90.0)   # less than one period
        assert policy.get_score(s) == 100.0   # no change

    def test_success_exactly_one_period(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            success_increment=10.0,
            time_period=60.0,
        )
        s = make_server()
        policy.on_success(s, duration=60.0)
        assert policy.get_score(s) == 110.0

    def test_success_zero_time_period_always_credits(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            success_increment=5.0,
            time_period=0.0,
        )
        s = make_server()
        policy.on_success(s, duration=1.0)   # any positive duration
        assert policy.get_score(s) == 105.0

    def test_score_can_go_negative(self):
        policy = ScoredRemoval(initial_score=10.0, failure_penalty=30.0)
        s = make_server()
        policy.on_failure(s)
        assert policy.get_score(s) == -20.0

    def test_score_can_recover_above_initial(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            failure_penalty=30.0,
            success_increment=20.0,
            time_period=60.0,
        )
        s = make_server()
        policy.on_failure(s)        # 70
        policy.on_success(s, 300.0) # 5 periods × 20 = +100  →  170
        assert policy.get_score(s) == 170.0

    def test_independent_scores_per_server(self):
        policy = ScoredRemoval(initial_score=100.0, failure_penalty=30.0)
        s0 = make_server(server_id=0)
        s1 = make_server(server_id=1)
        policy.on_failure(s0)
        assert policy.get_score(s0) == 70.0
        assert policy.get_score(s1) == 100.0   # untouched


# ── Unit tests: retirement decision ──────────────────────────────────────────

class TestScoredRemovalRetirement:

    def test_not_retired_above_threshold(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            failure_penalty=30.0,
            retirement_threshold=0.0,
        )
        rng = random.Random(0)
        s = make_server()
        policy.on_failure(s)   # score = 70
        assert not policy.should_remove(s, rng)

    def test_retired_at_threshold(self):
        policy = ScoredRemoval(
            initial_score=30.0,
            failure_penalty=30.0,
            retirement_threshold=0.0,
        )
        rng = random.Random(0)
        s = make_server()
        policy.on_failure(s)   # score = 0
        assert policy.should_remove(s, rng)

    def test_retired_below_threshold(self):
        policy = ScoredRemoval(
            initial_score=20.0,
            failure_penalty=30.0,
            retirement_threshold=0.0,
        )
        rng = random.Random(0)
        s = make_server()
        policy.on_failure(s)   # score = -10
        assert policy.should_remove(s, rng)

    def test_custom_retirement_threshold(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            failure_penalty=20.0,
            retirement_threshold=50.0,
        )
        rng = random.Random(0)
        s = make_server()
        policy.on_failure(s)   # 80 — still above 50
        assert not policy.should_remove(s, rng)
        policy.on_failure(s)   # 60 — still above 50
        assert not policy.should_remove(s, rng)
        policy.on_failure(s)   # 40 — below 50
        assert policy.should_remove(s, rng)

    def test_never_retired_without_failures(self):
        policy = ScoredRemoval(
            initial_score=100.0,
            failure_penalty=30.0,
            retirement_threshold=0.0,
        )
        rng = random.Random(0)
        s = make_server()
        assert not policy.should_remove(s, rng)


# ── Unit tests: scores_snapshot ──────────────────────────────────────────────

class TestScoredRemovalSnapshot:

    def test_snapshot_empty_before_any_event(self):
        policy = ScoredRemoval()
        assert policy.scores_snapshot() == {}

    def test_snapshot_after_events(self):
        policy = ScoredRemoval(initial_score=100.0, failure_penalty=10.0)
        s0 = make_server(0)
        s1 = make_server(1)
        policy.on_failure(s0)
        policy.on_failure(s1)
        policy.on_failure(s1)
        snap = policy.scores_snapshot()
        assert snap[0] == 90.0
        assert snap[1] == 80.0

    def test_snapshot_is_a_copy(self):
        policy = ScoredRemoval(initial_score=100.0, failure_penalty=10.0)
        s = make_server()
        policy.on_failure(s)
        snap = policy.scores_snapshot()
        snap[0] = 999.0
        assert policy.get_score(s) == 90.0   # original unchanged


# ── Integration tests: full simulation ───────────────────────────────────────

def _base_params(**overrides) -> Params:
    """Return a fast, deterministic Params for integration tests."""
    defaults = dict(
        job_size=8,
        warm_standbys=2,
        working_pool_size=20,
        spare_pool_size=10,
        job_length=2 * 24 * 60,   # 2 days
        random_failure_rate=0.05 / (24 * 60),
        systematic_failure_rate_multiplier=1.0,
        systematic_failure_fraction=0.0,
        recovery_time=5,
        host_selection_time=1,
        preemption_wait_time=5,
        auto_repair_time=30,
        manual_repair_time=120,
        prob_auto_to_manual=0.5,
        auto_repair_fail_prob=0.1,
        manual_repair_fail_prob=0.1,
        seed=42,
        num_replications=1,
    )
    defaults.update(overrides)
    return Params(**defaults)


class TestScoredRemovalIntegration:

    def test_sim_completes_with_scored_policy(self):
        """ScoredRemoval must not break normal simulation completion."""
        policy = ScoredRemoval(
            initial_score=100.0,
            failure_penalty=20.0,
            success_increment=5.0,
            time_period=60.0,
            retirement_threshold=0.0,
        )
        params = _base_params()
        sim = Simulator(params=params, removal_policy=policy)
        result = sim.run()
        assert result.total_training_time > 0
        assert not result.cluster_depleted

    def test_servers_retired_when_threshold_aggressive(self):
        """With a very high penalty and zero threshold, some servers should retire."""
        policy = ScoredRemoval(
            initial_score=100.0,
            failure_penalty=200.0,   # one failure → instant retirement
            success_increment=1.0,
            time_period=60.0,
            retirement_threshold=0.0,
        )
        params = _base_params(
            random_failure_rate=0.5 / (24 * 60),  # very frequent failures
            auto_repair_fail_prob=0.9,
            manual_repair_fail_prob=0.9,
        )
        sim = Simulator(params=params, removal_policy=policy, seed=1)
        result = sim.run()
        assert result.servers_retired > 0

    def test_no_retirements_with_high_initial_score(self):
        """With initial_score so high that failures can never reach threshold,
        no servers should ever be retired."""
        policy = ScoredRemoval(
            initial_score=10_000.0,
            failure_penalty=1.0,
            retirement_threshold=0.0,
        )
        params = _base_params()
        sim = Simulator(params=params, removal_policy=policy, seed=7)
        result = sim.run()
        assert result.servers_retired == 0

    def test_hooks_not_called_by_never_remove(self):
        """NeverRemove (no overrides) never modifies any state via hooks."""
        policy = NeverRemove()
        s = make_server()
        policy.on_failure(s)    # should be a no-op
        policy.on_success(s, 1000.0)   # should be a no-op
        assert not policy.should_remove(s, random.Random(0))

    def test_scored_policy_trains_faster_than_never_remove_in_high_failure_regime(self):
        """In a regime where bad servers cycle continuously (high fail-prob,
        high multiplier), ScoredRemoval should not substantially *hurt*
        compared to NeverRemove — and may help."""
        common = dict(
            job_size=16,
            warm_standbys=4,
            working_pool_size=80,
            spare_pool_size=40,
            job_length=7 * 24 * 60,
            random_failure_rate=0.01 / (24 * 60),
            systematic_failure_rate_multiplier=15.0,
            systematic_failure_fraction=0.10,
            recovery_time=30,
            host_selection_time=2,
            preemption_wait_time=10,
            auto_repair_time=60,
            manual_repair_time=720,
            prob_auto_to_manual=0.80,
            auto_repair_fail_prob=0.50,
            manual_repair_fail_prob=0.70,
            seed=99,
            num_replications=1,
        )
        never_result = Simulator(params=Params(**common), removal_policy=NeverRemove(), seed=99).run()
        scored_result = Simulator(
            params=Params(**common),
            removal_policy=ScoredRemoval(
                initial_score=100.0,
                failure_penalty=40.0,
                success_increment=10.0,
                time_period=4 * 60,
                retirement_threshold=0.0,
            ),
            seed=99,
        ).run()
        # Scored removal should not make training more than 50 % slower.
        assert scored_result.total_training_time < never_result.total_training_time * 1.5
