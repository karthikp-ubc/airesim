"""Repair module — automated and manual repair pipeline.

Models the two-stage repair process:
1. Automated repair (fast, limited scope)
2. Manual repair (slow, broader scope, only if auto escalates)

Both stages can silently fail (report success when the issue persists).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

import simpy

from airesim.policies import RepairEscalationPolicy, ServerRemovalPolicy
from airesim.server import Server

if TYPE_CHECKING:
    from airesim.pool import PoolManager
    from airesim.stats import StatsCollector


@dataclass
class RepairResult:
    """Outcome record returned after a server completes the full repair pipeline."""

    server: Server
    went_to_manual: bool
    repair_succeeded: bool  # whether the underlying issue was actually fixed
    total_repair_time: float


class RepairShop:
    """Manages the repair pipeline for failed servers.

    Each failed server is processed as a SimPy process:
      auto repair → (maybe) manual repair → reintegrate or retire.
    """

    def __init__(
        self,
        env: simpy.Environment,
        rng: random.Random,
        auto_repair_time: float,
        manual_repair_time: float,
        auto_repair_fail_prob: float,
        manual_repair_fail_prob: float,
        escalation_policy: RepairEscalationPolicy,
        removal_policy: ServerRemovalPolicy,
        pool_manager: "PoolManager",
        stats: "StatsCollector",
    ):
        self.env = env
        self.rng = rng

        self.auto_repair_time = auto_repair_time
        self.manual_repair_time = manual_repair_time
        self.auto_repair_fail_prob = auto_repair_fail_prob
        self.manual_repair_fail_prob = manual_repair_fail_prob

        self.escalation_policy = escalation_policy
        self.removal_policy = removal_policy
        self.pool_manager = pool_manager
        self.stats = stats

        # Event signaled whenever a server completes repair and is available.
        # The main loop resets this event after waking — see simulator._main_loop.
        self.server_repaired_event: simpy.Event = env.event()

        # Optional callback invoked after a server is returned to the working
        # pool.  Set by the Simulator to wire repaired servers back into the
        # scheduler's warm-standby list mid-job.
        self.on_server_returned = None

    def submit(self, server: Server) -> simpy.Process:
        """Submit a server to the repair pipeline. Returns the SimPy process."""
        return self.env.process(self._repair_process(server))

    def _repair_process(self, server: Server):
        """SimPy process: run the server through auto (and maybe manual) repair."""
        start_time = self.env.now

        # ── Stage 1: Automated repair ────────────────────────────────────
        server.begin_auto_repair()
        repair_duration = self.rng.expovariate(1.0 / self.auto_repair_time)
        yield self.env.timeout(repair_duration)

        self.stats.auto_repairs += 1

        # Policies that ignore the auto outcome (the paper's model) decide first and
        # the outcome is only sampled if the server is not escalated; policies that
        # use it get the sampled outcome up front.
        auto_repair_succeeded: bool | None = None
        if self.escalation_policy.uses_auto_outcome:
            auto_repair_succeeded = self.rng.random() >= self.auto_repair_fail_prob
        went_to_manual = self.escalation_policy.should_escalate(
            server, auto_repair_succeeded, self.rng
        )

        if went_to_manual:
            # ── Stage 2: Manual repair ───────────────────────────────────
            server.begin_manual_repair()
            manual_duration = self.rng.expovariate(1.0 / self.manual_repair_time)
            yield self.env.timeout(manual_duration)

            self.stats.manual_repairs += 1
            actual_success = self.rng.random() >= self.manual_repair_fail_prob
        else:
            # Auto repair reports success -- but did it actually fix the issue?
            if auto_repair_succeeded is None:
                auto_repair_succeeded = self.rng.random() >= self.auto_repair_fail_prob
            actual_success = auto_repair_succeeded

        # ── Post-repair decision ─────────────────────────────────────────
        server.complete_repair(success=actual_success)

        if actual_success:
            self.stats.successful_repairs += 1
        else:
            self.stats.failed_repairs += 1

        # Check removal policy
        if self.removal_policy.should_remove(server, self.rng):
            self.pool_manager.retire_server(server)
            self.stats.servers_retired += 1
            # Wake the main loop so it can re-check the depletion guard.
            # Without this, when every repaired server is retired the
            # server_repaired_event never fires and the stall loop waits
            # forever, leaving total_training_time = 0 and env.run() to
            # exit silently once no further events remain.
            self._signal_repaired()
        else:
            # Return to working pool
            self.pool_manager.return_to_working(server)
            # Notify the scheduler so it can re-add the server as a warm standby
            if self.on_server_returned is not None:
                self.on_server_returned(server)
            # Signal that a server is available
            self._signal_repaired()

        total_time = self.env.now - start_time
        return RepairResult(
            server=server,
            went_to_manual=went_to_manual,
            repair_succeeded=actual_success,
            total_repair_time=total_time,
        )

    def notify_server_available(self) -> None:
        """Signal that a server became available outside the normal repair pipeline.

        Called by the simulator when a failed server is returned to the pool
        directly (e.g. missed diagnosis / auto-recovery) so that any stalled
        main-loop depletion guard can wake up and re-check pool availability.
        """
        self._signal_repaired()

    def _signal_repaired(self):
        """Fire the server_repaired event.

        The event is NOT replaced here.  The main loop owns the event
        lifecycle: it checks ``triggered`` before yielding and creates a
        fresh event after waking.  This prevents the missed-signal race
        where the event is replaced before a new waiter can grab it.
        """
        if not self.server_repaired_event.triggered:
            self.server_repaired_event.succeed()
