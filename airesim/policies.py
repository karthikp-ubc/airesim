"""Pluggable policy interfaces.

Users can subclass these to inject custom strategies into the simulator.
Each policy has a sensible default implementation matching the paper's description.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airesim.server import Server


# ── Host selection ───────────────────────────────────────────────────────────

class HostSelectionPolicy(ABC):
    """Decide which servers from the available pool to assign to a job."""

    @abstractmethod
    def select(
        self,
        available_servers: list["Server"],
        job_size: int,
        warm_standbys: int,
        rng: random.Random,
    ) -> list["Server"]:
        """Return an ordered list of servers to assign.

        The first ``job_size`` are primary; the rest (up to ``warm_standbys``)
        are warm standbys.  May return fewer than requested if not enough
        servers are available.
        """
        ...


class DefaultHostSelection(HostSelectionPolicy):
    """Select servers randomly (uniform) from the available pool."""

    def select(self, available_servers, job_size, warm_standbys, rng):
        """Shuffle the available pool and return the first ``job_size + warm_standbys`` servers."""
        needed = job_size + warm_standbys
        chosen = available_servers[:needed]  # pool is already shuffled or ordered
        rng.shuffle(chosen)
        return chosen[:needed]


class FewestFailuresFirst(HostSelectionPolicy):
    """Prefer servers with the fewest historical failures."""

    def select(self, available_servers, job_size, warm_standbys, rng):
        """Sort by ascending total failure count (random tiebreak) and return the top servers."""
        needed = job_size + warm_standbys
        # Sort by failure count ascending, break ties randomly
        sorted_servers = sorted(available_servers, key=lambda s: (s.total_failure_count, rng.random()))
        return sorted_servers[:needed]


# ── Repair escalation ────────────────────────────────────────────────────────

class RepairEscalationPolicy(ABC):
    """Decide whether a server should be escalated from auto to manual repair."""

    @abstractmethod
    def should_escalate(self, server: "Server", auto_repair_succeeded: bool, rng: random.Random) -> bool:
        """Return True if the server should go to manual repair."""
        ...


class DefaultRepairEscalation(RepairEscalationPolicy):
    """Escalate to manual repair with a fixed probability when auto repair
    determines it cannot handle the issue."""

    def __init__(self, prob_escalate: float = 0.80):
        self.prob_escalate = prob_escalate

    def should_escalate(self, server, auto_repair_succeeded, rng):
        """Return True with probability ``prob_escalate`` when auto repair failed."""
        if auto_repair_succeeded:
            return False
        return rng.random() < self.prob_escalate


# ── Server removal ───────────────────────────────────────────────────────────

class ServerRemovalPolicy(ABC):
    """Decide whether a server should be permanently removed from the cluster."""

    @abstractmethod
    def should_remove(self, server: "Server", rng: random.Random) -> bool:
        """Return True if the server should be permanently retired."""
        ...


class NeverRemove(ServerRemovalPolicy):
    """Never permanently remove servers (always reintegrate after repair)."""

    def should_remove(self, server, rng):
        """Always return False — every repaired server is returned to the working pool."""
        return False


class ThresholdRemoval(ServerRemovalPolicy):
    """Remove a server if it has exceeded a failure count within a time window."""

    def __init__(self, max_failures: int = 5, window_minutes: float = 7 * 24 * 60):
        self.max_failures = max_failures
        self.window_minutes = window_minutes

    def should_remove(self, server, rng):
        """Return True if the server has reached ``max_failures`` within the rolling window."""
        recent = server.failures_in_window(self.window_minutes)
        return recent >= self.max_failures
