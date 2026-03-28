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
    """Decide whether a server should be permanently removed from the cluster.

    Subclasses may also override ``on_failure`` and ``on_success`` to maintain
    per-server state that informs the retirement decision.
    """

    @abstractmethod
    def should_remove(self, server: "Server", rng: random.Random) -> bool:
        """Return True if the server should be permanently retired."""
        ...

    def on_failure(self, server: "Server") -> None:
        """Called when a server is blamed for a failure (before repair submission).

        Override to update per-server state (e.g. decrement a reliability score).
        The default implementation is a no-op.
        """

    def on_success(self, server: "Server", duration: float) -> None:
        """Called for each server that completed a run chunk without failing.

        ``duration`` is the length of the successful run in simulation minutes.
        Override to update per-server state (e.g. increment a reliability score).
        The default implementation is a no-op.
        """


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


class ScoredRemoval(ServerRemovalPolicy):
    """Score-based server retirement policy.

    Each server starts with ``initial_score``.  The score evolves over the
    simulation:

    * **Failure penalty**: every time a server is blamed for a failure its
      score is reduced by ``failure_penalty``.
    * **Uptime credit**: after each uninterrupted run chunk of length
      ``duration``, the server earns ``success_increment`` for every complete
      ``time_period`` it stayed healthy:
      ``credit = floor(duration / time_period) * success_increment``.
    * **Retirement**: when a server's score falls to or below
      ``retirement_threshold`` it is permanently retired.

    Parameters
    ----------
    initial_score:
        Starting reliability score assigned to every server.
    failure_penalty:
        Amount subtracted from a server's score on each failure.
    success_increment:
        Amount added per complete ``time_period`` of uninterrupted uptime.
    time_period:
        Minimum continuous uptime (simulation minutes) required to earn one
        ``success_increment``.  Set to 0 to credit every successful run
        regardless of length.
    retirement_threshold:
        Score at or below which a server is permanently retired.
    """

    def __init__(
        self,
        initial_score: float = 100.0,
        failure_penalty: float = 30.0,
        success_increment: float = 10.0,
        time_period: float = 24 * 60,       # 1 day in simulation minutes
        retirement_threshold: float = 0.0,
    ):
        self.initial_score = initial_score
        self.failure_penalty = failure_penalty
        self.success_increment = success_increment
        self.time_period = time_period
        self.retirement_threshold = retirement_threshold
        self._scores: dict[int, float] = {}  # server_id → current score

    # ── Internal helpers ─────────────────────────────────────────────────

    def _get_score(self, server: "Server") -> float:
        """Return the current score for *server*, defaulting to ``initial_score``."""
        return self._scores.get(server.server_id, self.initial_score)

    # ── Lifecycle hooks ──────────────────────────────────────────────────

    def on_failure(self, server: "Server") -> None:
        """Decrement *server*'s score by ``failure_penalty``."""
        self._scores[server.server_id] = self._get_score(server) - self.failure_penalty

    def on_success(self, server: "Server", duration: float) -> None:
        """Credit *server* for each complete ``time_period`` it ran without failing."""
        if self.time_period <= 0:
            periods = 1
        else:
            periods = int(duration / self.time_period)
        if periods > 0:
            self._scores[server.server_id] = (
                self._get_score(server) + periods * self.success_increment
            )

    # ── Retirement decision ──────────────────────────────────────────────

    def should_remove(self, server: "Server", rng: random.Random) -> bool:
        """Return True if *server*'s score is at or below ``retirement_threshold``."""
        return self._get_score(server) <= self.retirement_threshold

    # ── Inspection ───────────────────────────────────────────────────────

    def get_score(self, server: "Server") -> float:
        """Return the current reliability score for *server*."""
        return self._get_score(server)

    def scores_snapshot(self) -> dict[int, float]:
        """Return a copy of all tracked scores keyed by server id."""
        return dict(self._scores)
