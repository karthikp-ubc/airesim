"""Pluggable host-selection (scheduling) policies.

A ``HostSelectionPolicy`` decides which servers from the available pool are
assigned to a job when host selection runs.  Subclass it to inject custom
scheduling strategies into the simulator.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from airesim.server import Server
    from airesim.policies import ScoredRemoval


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
        sorted_servers = sorted(
            available_servers, key=lambda s: (s.total_failure_count, rng.random())
        )
        return sorted_servers[:needed]


class HighestScoreFirst(HostSelectionPolicy):
    """Prefer servers with the highest reliability score from a ``ScoredRemoval`` policy.

    Servers are ranked by descending current score so that the most reliable
    servers are assigned to the job first.  Servers whose scores have not yet
    been recorded (e.g., brand-new servers that have never failed or run a full
    ``time_period``) are treated as having ``scored_removal.initial_score`` and
    therefore rank equally at the top of the list, broken by a random tiebreak.

    Parameters
    ----------
    scored_removal:
        A ``ScoredRemoval`` instance whose score dictionary is consulted on
        every host-selection call.  The same instance should be passed as
        ``removal_policy`` to ``Simulator`` so that scores stay in sync with
        the retirement decisions.
    """

    def __init__(self, scored_removal: "ScoredRemoval") -> None:
        self.scored_removal = scored_removal

    def select(self, available_servers, job_size, warm_standbys, rng):
        """Sort by descending reliability score (random tiebreak) and return the top servers."""
        needed = job_size + warm_standbys
        sorted_servers = sorted(
            available_servers,
            key=lambda s: (-self.scored_removal.get_score(s), rng.random()),
        )
        return sorted_servers[:needed]
