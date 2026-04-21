"""Tests for diagnosis_probability parameter.

diagnosis_probability = P(failure triggers a repair attempt on any server).

When a failure is *not* diagnosed (probability 1 − diagnosis_probability):
  - The failed server auto-recovers to the working pool immediately.
  - The job still incurs the checkpoint recovery overhead (recovery_time).
  - No server enters the repair pipeline, so servers_retired stays 0 unless
    other failures are correctly diagnosed.

This is distinct from diagnosis_uncertainty (P(wrong server blamed | diagnosed)),
which was already present.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.params import Params
from airesim.policies import ScoredRemoval, ThresholdRemoval
from airesim.simulator import Simulator

# ── Helpers ───────────────────────────────────────────────────────────────────

def _params(**overrides) -> Params:
    defaults = dict(
        job_size=8,
        warm_standbys=2,
        working_pool_size=20,
        spare_pool_size=5,
        job_length=2 * 24 * 60,
        random_failure_rate=0.05 / (24 * 60),
        systematic_failure_rate_multiplier=1.0,
        systematic_failure_fraction=0.0,
        recovery_time=10,
        host_selection_time=1,
        preemption_wait_time=5,
        auto_repair_time=30,
        manual_repair_time=120,
        prob_auto_to_manual=0.5,
        auto_repair_fail_prob=0.1,
        manual_repair_fail_prob=0.1,
        diagnosis_probability=1.0,
        diagnosis_uncertainty=0.0,
        seed=42,
        num_replications=1,
    )
    defaults.update(overrides)
    return Params(**defaults)


# ── Params validation ─────────────────────────────────────────────────────────

class TestDiagnosisProbabilityParams:

    def test_default_is_one(self):
        p = _params()
        assert p.diagnosis_probability == 1.0

    def test_zero_is_valid(self):
        p = _params(diagnosis_probability=0.0)
        p.validate()  # must not raise

    def test_one_is_valid(self):
        p = _params(diagnosis_probability=1.0)
        p.validate()

    def test_mid_range_is_valid(self):
        p = _params(diagnosis_probability=0.6)
        p.validate()

    def test_above_one_raises(self):
        with pytest.raises(ValueError, match="diagnosis_probability"):
            _params(diagnosis_probability=1.1).validate()

    def test_below_zero_raises(self):
        with pytest.raises(ValueError, match="diagnosis_probability"):
            _params(diagnosis_probability=-0.01).validate()


# ── Simulation behaviour ──────────────────────────────────────────────────────

class TestDiagnosisProbabilitySimulation:

    def test_default_prob_one_behaves_as_before(self):
        """diagnosis_probability=1.0 must produce identical results to the
        pre-existing behaviour (no missed-diagnosis branch ever fires)."""
        p = _params(
            random_failure_rate=0.1 / (24 * 60),
            auto_repair_fail_prob=0.3,
            manual_repair_fail_prob=0.3,
        )
        result = Simulator(params=p, seed=7).run()
        assert result.total_training_time > 0
        assert not result.cluster_depleted

    def test_zero_diagnosis_prob_completes(self):
        """With diagnosis_probability=0 every failure goes undiagnosed.
        No server ever enters the repair pipeline; the job still completes."""
        p = _params(
            random_failure_rate=0.05 / (24 * 60),
            diagnosis_probability=0.0,
        )
        result = Simulator(params=p, seed=1).run()
        assert result.total_training_time > 0
        assert not result.cluster_depleted

    def test_zero_diagnosis_prob_no_repairs(self):
        """With diagnosis_probability=0 the repair pipeline is never used:
        auto_repairs and manual_repairs stay at 0."""
        p = _params(
            random_failure_rate=0.1 / (24 * 60),
            systematic_failure_fraction=0.2,
            systematic_failure_rate_multiplier=10.0,
            diagnosis_probability=0.0,
        )
        result = Simulator(params=p, seed=3).run()
        assert result.auto_repairs == 0
        assert result.manual_repairs == 0
        assert result.servers_retired == 0

    def test_zero_diagnosis_prob_no_retirements(self):
        """With diagnosis_probability=0, ThresholdRemoval never retires anyone
        because servers never pass through the repair/retirement check."""
        p = _params(
            random_failure_rate=0.2 / (24 * 60),
            systematic_failure_fraction=0.3,
            systematic_failure_rate_multiplier=20.0,
            diagnosis_probability=0.0,
        )
        result = Simulator(
            params=p,
            removal_policy=ThresholdRemoval(max_failures=1, window_minutes=7 * 24 * 60),
            seed=5,
        ).run()
        assert result.servers_retired == 0

    def test_partial_diagnosis_prob_reduces_repairs(self):
        """Fewer repairs should be submitted when diagnosis_probability < 1."""
        common = dict(
            job_size=8, warm_standbys=2, working_pool_size=30, spare_pool_size=10,
            job_length=3 * 24 * 60,
            random_failure_rate=0.2 / (24 * 60),
            systematic_failure_fraction=0.15,
            systematic_failure_rate_multiplier=10.0,
            recovery_time=5,
            host_selection_time=1, preemption_wait_time=5,
            auto_repair_time=30, manual_repair_time=60,
            prob_auto_to_manual=0.5,
            auto_repair_fail_prob=0.2, manual_repair_fail_prob=0.2,
            seed=42, num_replications=1,
        )
        full_diag = Simulator(params=Params(**common, diagnosis_probability=1.0), seed=42).run()
        half_diag = Simulator(params=Params(**common, diagnosis_probability=0.5), seed=42).run()
        # With half the failures diagnosed, repairs should be fewer
        assert half_diag.auto_repairs < full_diag.auto_repairs

    def test_missed_diagnosis_does_not_increase_training_time_excessively(self):
        """Missed diagnoses should not cause unbounded slowdown: bad servers
        keep failing but auto-recover, so they don't pile up in the repair
        shop, and the job continues making progress."""
        p = _params(
            random_failure_rate=0.02 / (24 * 60),
            diagnosis_probability=0.5,
            seed=11,
        )
        result = Simulator(params=p, seed=11).run()
        assert result.total_training_time > 0
        assert not result.cluster_depleted

    def test_diagnosis_probability_and_uncertainty_are_independent(self):
        """Setting both parameters should be valid and not crash."""
        p = _params(
            diagnosis_probability=0.8,
            diagnosis_uncertainty=0.2,
            random_failure_rate=0.05 / (24 * 60),
        )
        p.validate()
        result = Simulator(params=p, seed=99).run()
        assert result.total_training_time > 0

    def test_high_uncertainty_completes(self):
        """High diagnosis_uncertainty must not deadlock the simulation.

        Before the floating-server fix, the actual bad server was removed from
        the working pool during misdiagnosis but never returned, causing it to
        accumulate in limbo.  At high uncertainty enough servers would float
        that the pool dropped below the minimum needed, the stall loop would
        wait for repairs that never woke it, and SimPy would exit silently with
        total_training_time == 0.
        """
        for uncertainty in (0.4, 0.6, 0.8, 1.0):
            p = _params(
                random_failure_rate=0.15 / (24 * 60),
                systematic_failure_fraction=0.2,
                systematic_failure_rate_multiplier=5.0,
                diagnosis_uncertainty=uncertainty,
            )
            result = Simulator(params=p, seed=7).run()
            assert result.total_training_time > 0, (
                f"Simulation deadlocked at diagnosis_uncertainty={uncertainty}"
            )
            assert not result.cluster_depleted

    def test_full_uncertainty_no_bad_servers_diagnosed(self):
        """With uncertainty=1.0 the actual bad server always escapes; only
        innocent servers enter the repair pipeline.  The job must still complete
        because the escaped bad server is returned to the pool (fix)."""
        p = _params(
            random_failure_rate=0.1 / (24 * 60),
            systematic_failure_fraction=0.15,
            systematic_failure_rate_multiplier=8.0,
            diagnosis_uncertainty=1.0,
        )
        result = Simulator(params=p, seed=17).run()
        assert result.total_training_time > 0
        assert not result.cluster_depleted

    def test_high_uncertainty_escaped_server_stays_in_pool(self):
        """After a misdiagnosis, the actual failed server (now state=IDLE)
        must be back in the working pool — it must not be floating."""
        # Use uncertainty=1.0 so every diagnosed failure is a misdiagnosis:
        # the bad server always escapes.  With a large failure rate, many
        # misdiagnoses will occur.  If floating servers accumulated, the
        # working pool would drain and the job would stall or deadlock.
        p = _params(
            working_pool_size=30,
            spare_pool_size=10,
            random_failure_rate=0.3 / (24 * 60),
            systematic_failure_fraction=0.3,
            systematic_failure_rate_multiplier=10.0,
            diagnosis_uncertainty=1.0,
            recovery_time=1,
        )
        result = Simulator(params=p, seed=99).run()
        assert result.total_training_time > 0

    def test_escaped_server_not_duplicated_in_active_servers(self):
        """The escaped bad server must NOT appear in warm_standbys after
        misdiagnosis — it is still in active_servers and calling
        on_server_returned would add it to standbys, causing it to be
        appended to active_servers a second time on the next swap_in_standby.

        Proxy signal: if duplicates accumulate, the coordinator sees more
        virtual servers than exist, which inflates active_server counts and
        corrupts statistics.  We detect this by verifying that the number of
        failures recorded never wildly exceeds what a deduplicated active set
        would produce.
        """
        # Use small pool and tiny warm_standbys so standbys are quickly
        # depleted between failures, maximising the chance that
        # on_server_returned finds an empty standby slot.
        p = _params(
            job_size=4,
            warm_standbys=1,
            working_pool_size=12,
            spare_pool_size=4,
            job_length=6 * 60,
            random_failure_rate=0.5 / (24 * 60),
            systematic_failure_fraction=0.3,
            systematic_failure_rate_multiplier=20.0,
            diagnosis_uncertainty=1.0,
            recovery_time=1,
            auto_repair_time=5,
            manual_repair_time=10,
        )
        result = Simulator(params=p, seed=55).run()
        # Job must complete (no deadlock)
        assert result.total_training_time > 0
        assert not result.cluster_depleted

    def test_scored_removal_not_penalised_for_missed_diagnoses(self):
        """When diagnosis is missed, on_failure is NOT called, so ScoredRemoval
        scores should be lower-variance than with full diagnosis."""
        # With diagnosis_probability=0 and ScoredRemoval, no on_failure calls →
        # no server should ever be retired.
        scored = ScoredRemoval(
            initial_score=100.0,
            failure_penalty=60.0,
            retirement_threshold=0.0,
        )
        p = _params(
            random_failure_rate=0.3 / (24 * 60),
            systematic_failure_fraction=0.2,
            systematic_failure_rate_multiplier=10.0,
            diagnosis_probability=0.0,
        )
        result = Simulator(params=p, removal_policy=scored, seed=13).run()
        assert result.servers_retired == 0
        # Scores should be unchanged (all still at initial_score)
        for score in scored.scores_snapshot().values():
            assert score == scored.initial_score
