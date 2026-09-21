"""Regression tests for RepairShop's use of RepairEscalationPolicy.

Bug (fixed): RepairShop._repair_process() computed the auto→manual escalation
decision inline (`rng.random() >= prob_auto_to_manual`, evaluated *before* the
auto-repair outcome was known) instead of calling the injected
`escalation_policy.should_escalate(server, auto_repair_succeeded, rng)`. The
policy object was constructed and stored on RepairShop but never consulted, so
a custom RepairEscalationPolicy subclass had no effect on simulation output.

The wiring fix stands; the *default* policy reproduces the DSN'26 paper (escalate
with probability prob_auto_to_manual, independent of the silent auto-repair
failure).  Outcome-conditioned escalation lives in EscalateOnDetectedFailure.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.params import Params
from airesim.policies import (
    DefaultRepairEscalation,
    EscalateOnDetectedFailure,
    RepairEscalationPolicy,
)
from airesim.simulator import Simulator

# ── Helpers ───────────────────────────────────────────────────────────────────

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
        diagnosis_probability=1.0,
        diagnosis_uncertainty=0.0,
        seed=42,
        num_replications=1,
    )
    defaults.update(overrides)
    return Params(**defaults)


class AlwaysEscalate(RepairEscalationPolicy):
    """Escalates every repair to manual, regardless of the auto outcome."""

    def should_escalate(self, server, auto_repair_succeeded, rng) -> bool:
        """Always return True."""
        return True


class NeverEscalate(RepairEscalationPolicy):
    """Never escalates a repair to manual."""

    def should_escalate(self, server, auto_repair_succeeded, rng) -> bool:
        """Always return False."""
        return False


class RecordingEscalationPolicy(RepairEscalationPolicy):
    """Records the auto_repair_succeeded value it was called with, then never escalates."""

    def __init__(self):
        self.calls: list[bool] = []

    def should_escalate(self, server, auto_repair_succeeded, rng) -> bool:
        """Record the observed outcome and decline to escalate."""
        self.calls.append(auto_repair_succeeded)
        return False


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCustomPolicyIsConsulted:
    """A custom RepairEscalationPolicy must actually drive escalation."""

    def test_always_escalate_overrides_prob_auto_to_manual_zero(self):
        """prob_auto_to_manual=0.0 would mean 'never escalate' if it still
        drove behavior directly. With AlwaysEscalate injected, every repair
        must go to manual regardless."""
        p = _params(prob_auto_to_manual=0.0, auto_repair_fail_prob=0.0)
        result = Simulator(params=p, escalation_policy=AlwaysEscalate(), seed=7).run()

        assert result.auto_repairs > 0, "test setup must produce at least one repair"
        assert result.manual_repairs == result.auto_repairs

    def test_never_escalate_overrides_prob_auto_to_manual_one(self):
        """prob_auto_to_manual=1.0 would mean 'always escalate' if it still
        drove behavior directly. With NeverEscalate injected, no repair may
        reach manual."""
        p = _params(prob_auto_to_manual=1.0, auto_repair_fail_prob=0.4)
        result = Simulator(params=p, escalation_policy=NeverEscalate(), seed=7).run()

        assert result.auto_repairs > 0, "test setup must produce at least one repair"
        assert result.manual_repairs == 0


class TestEscalationSeesRealOutcome:
    """should_escalate must be called with the auto stage's actual outcome,
    not a value guessed before that outcome is known."""

    def test_receives_false_when_auto_repair_always_fails(self):
        p = _params(auto_repair_fail_prob=1.0)
        policy = RecordingEscalationPolicy()
        Simulator(params=p, escalation_policy=policy, seed=7).run()

        assert policy.calls, "should_escalate was never called"
        assert all(call is False for call in policy.calls)

    def test_receives_true_when_auto_repair_always_succeeds(self):
        p = _params(auto_repair_fail_prob=0.0)
        policy = RecordingEscalationPolicy()
        Simulator(params=p, escalation_policy=policy, seed=7).run()

        assert policy.calls, "should_escalate was never called"
        assert all(call is True for call in policy.calls)


class TestDefaultEscalationPolicySemantics:
    """With no custom policy, Simulator builds
    DefaultRepairEscalation(prob_escalate=params.prob_auto_to_manual): the paper's
    model, in which escalation is independent of the (silent) auto-repair outcome."""

    def test_should_escalate_ignores_auto_outcome(self):
        policy = DefaultRepairEscalation(prob_escalate=1.0)
        rng = random.Random(0)
        for outcome in (True, False, None):
            assert policy.should_escalate(server=None, auto_repair_succeeded=outcome,
                                          rng=rng) is True
        assert DefaultRepairEscalation(prob_escalate=0.0).should_escalate(
            None, True, rng) is False

    def test_default_does_not_use_auto_outcome(self):
        assert DefaultRepairEscalation.uses_auto_outcome is False
        assert EscalateOnDetectedFailure.uses_auto_outcome is True

    def test_escalates_even_when_auto_repair_always_succeeds(self):
        """prob_auto_to_manual=1.0 escalates every repair regardless of
        auto_repair_fail_prob (a silent failure is not visible to escalation)."""
        p = _params(prob_auto_to_manual=1.0, auto_repair_fail_prob=0.0)
        result = Simulator(params=p, seed=7).run()

        assert result.auto_repairs > 0
        assert result.manual_repairs == result.auto_repairs

    def test_never_escalates_when_prob_is_zero_even_if_auto_always_fails(self):
        p = _params(prob_auto_to_manual=0.0, auto_repair_fail_prob=1.0)
        result = Simulator(params=p, seed=7).run()

        assert result.auto_repairs > 0
        assert result.manual_repairs == 0

    def test_escalation_rate_matches_prob_auto_to_manual(self):
        p = _params(prob_auto_to_manual=0.5, auto_repair_fail_prob=0.3,
                    job_length=300 * 24 * 60)
        result = Simulator(params=p, seed=7).run()

        rate = result.manual_repairs / result.auto_repairs
        assert result.auto_repairs > 400
        assert abs(rate - 0.5) < 0.1


class TestEscalateOnDetectedFailure:
    """The outcome-conditioned policy (assumes auto-repair failures are observable)."""

    def test_should_escalate_conditions_on_success_directly(self):
        policy = EscalateOnDetectedFailure(prob_escalate=1.0)
        rng = random.Random(0)

        assert policy.should_escalate(server=None, auto_repair_succeeded=True, rng=rng) is False
        assert policy.should_escalate(server=None, auto_repair_succeeded=False, rng=rng) is True

    def test_never_escalates_when_auto_repair_always_succeeds(self):
        p = _params(prob_auto_to_manual=1.0, auto_repair_fail_prob=0.0)
        result = Simulator(params=p, escalation_policy=EscalateOnDetectedFailure(1.0),
                           seed=7).run()

        assert result.auto_repairs > 0
        assert result.manual_repairs == 0

    def test_always_escalates_failed_auto_repair_when_prob_is_one(self):
        p = _params(prob_auto_to_manual=1.0, auto_repair_fail_prob=1.0)
        result = Simulator(params=p, escalation_policy=EscalateOnDetectedFailure(1.0),
                           seed=7).run()

        assert result.auto_repairs > 0
        assert result.manual_repairs == result.auto_repairs


class TestOutcomeContract:
    """uses_auto_outcome controls whether should_escalate receives a bool or None."""

    def test_outcome_free_policy_receives_none(self):
        class Recorder(RepairEscalationPolicy):
            uses_auto_outcome = False

            def __init__(self):
                self.calls = []

            def should_escalate(self, server, auto_repair_succeeded, rng):
                self.calls.append(auto_repair_succeeded)
                return False

        policy = Recorder()
        Simulator(params=_params(), escalation_policy=policy, seed=7).run()

        assert policy.calls and all(c is None for c in policy.calls)

    def test_subclass_without_flag_still_receives_real_outcome(self):
        # RecordingEscalationPolicy does not set uses_auto_outcome (inherits True)
        assert RecordingEscalationPolicy.uses_auto_outcome is True
