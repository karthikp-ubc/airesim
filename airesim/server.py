"""Server entity — pure state machine with failure bookkeeping.

Failure *timing* is handled by the Coordinator using aggregated exponential
sampling (min of N exponentials).  The Server just tracks state, failure
counts, and repair history.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import simpy


class ServerState(enum.Enum):
    """Lifecycle states for a single server node."""

    IDLE = "idle"                      # in pool, available
    RUNNING = "running"                # executing AI job
    FAILED = "failed"                  # has failed, awaiting repair
    AUTO_REPAIR = "auto_repair"        # in automated repair
    MANUAL_REPAIR = "manual_repair"    # in manual repair
    RETIRED = "retired"                # permanently removed
    SPARE = "spare"                    # in spare pool, running other work


class Server:
    """Represents a single server (node) in the cluster.

    This is a bookkeeping entity — failure timing is sampled by the
    Coordinator, not by per-server SimPy processes.
    """

    def __init__(
        self,
        server_id: int,
        env: "simpy.Environment",
        is_bad: bool,
        random_failure_rate: float,
        systematic_failure_rate: float,
    ):
        self.server_id = server_id
        self.env = env

        # Failure characteristics
        self.is_bad = is_bad
        self.random_failure_rate = random_failure_rate
        self.systematic_failure_rate = systematic_failure_rate

        # State
        self.state = ServerState.IDLE

        # Bookkeeping
        self.total_failure_count = 0
        self.random_failure_count = 0
        self.systematic_failure_count = 0
        self.failure_timestamps: list[float] = []
        self.was_systematic: bool = False  # whether last failure was systematic

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def failure_rate(self) -> float:
        """Effective failure rate for this server."""
        if self.is_bad:
            return self.random_failure_rate + self.systematic_failure_rate
        return self.random_failure_rate

    # ── State transitions ────────────────────────────────────────────────

    def mark_running(self) -> None:
        """Transition server to RUNNING state (actively executing the AI job)."""
        self.state = ServerState.RUNNING

    def mark_failed(self) -> None:
        """Transition server to FAILED state, awaiting submission to the repair shop."""
        self.state = ServerState.FAILED

    def mark_idle(self) -> None:
        """Transition server to IDLE state (available for assignment in the pool)."""
        self.state = ServerState.IDLE

    def begin_auto_repair(self) -> None:
        """Transition server to AUTO_REPAIR state (undergoing automated repair)."""
        self.state = ServerState.AUTO_REPAIR

    def begin_manual_repair(self) -> None:
        """Transition server to MANUAL_REPAIR state (undergoing human-in-the-loop repair)."""
        self.state = ServerState.MANUAL_REPAIR

    def complete_repair(self, success: bool) -> None:
        """Complete repair.  If success and was bad, server becomes good."""
        if success and self.is_bad:
            self.is_bad = False
        self.state = ServerState.IDLE

    def retire(self) -> None:
        """Permanently retire the server; it will no longer be used in the cluster."""
        self.state = ServerState.RETIRED

    def move_to_spare(self) -> None:
        """Move server to the spare pool (runs background work, not the AI job)."""
        self.state = ServerState.SPARE

    def return_from_spare(self) -> None:
        """Return server from spare pool to IDLE in the working pool."""
        self.state = ServerState.IDLE

    def make_bad(self) -> None:
        """Regenerate this server as a 'bad' server."""
        self.is_bad = True

    # ── Query ────────────────────────────────────────────────────────────

    def failures_in_window(self, window_minutes: float) -> int:
        """Count failures within the last ``window_minutes``."""
        cutoff = self.env.now - window_minutes
        return sum(1 for t in self.failure_timestamps if t >= cutoff)

    def __repr__(self):
        """Return a concise string representation showing id, bad-server flag, and state."""
        return f"Server({self.server_id}, bad={self.is_bad}, state={self.state.value})"
