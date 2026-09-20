"""Regression tests for RepairShop's use of RepairEscalationPolicy.

Bug (fixed): RepairShop._repair_process() computed the auto→manual escalation
decision inline (`rng.random() >= prob_auto_to_manual`, evaluated *before* the
auto-repair outcome was known) instead of calling the injected
`escalation_policy.should_escalate(server, auto_repair_succeeded, rng)`. The
policy object was constructed and stored on RepairShop but never consulted, so
a custom RepairEscalationPolicy subclass had no effect on simulation output,
and the default policy's "only escalate if auto repair actually failed" rule
was silently not enforced.

These tests fail against the old implementation and pass against the fix.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.params import Params
from airesim.policies import DefaultRepairEscalation, RepairEscalationPolicy
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
    DefaultRepairEscalation(prob_escalate=params.prob_auto_to_manual), which
    only escalates when the auto stage actually failed."""

    def test_should_escalate_conditions_on_success_directly(self):
        """Unit-level check of the class itself: a successful auto repair is
        never escalated, even at prob_escalate=1.0; a failed one always is."""
        policy = DefaultRepairEscalation(prob_escalate=1.0)
        rng = random.Random(0)

        assert policy.should_escalate(server=None, auto_repair_succeeded=True, rng=rng) is False
        assert policy.should_escalate(server=None, auto_repair_succeeded=False, rng=rng) is True

    def test_never_escalates_when_auto_repair_always_succeeds(self):
        """Even prob_auto_to_manual=1.0 must not send a successfully
        auto-repaired server to manual repair."""
        p = _params(prob_auto_to_manual=1.0, auto_repair_fail_prob=0.0)
        result = Simulator(params=p, seed=7).run()

        assert result.auto_repairs > 0
        assert result.manual_repairs == 0

    def test_always_escalates_failed_auto_repair_when_prob_is_one(self):
        """prob_auto_to_manual=1.0 with auto repair that always fails must
        escalate every repair to manual."""
        p = _params(prob_auto_to_manual=1.0, auto_repair_fail_prob=1.0)
        result = Simulator(params=p, seed=7).run()

        assert result.auto_repairs > 0
        assert result.manual_repairs == result.auto_repairs
