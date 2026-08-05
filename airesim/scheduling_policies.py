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
    from airesim.policies import ScoredRemoval
    from airesim.server import Server


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

    def select(
        self,
        available_servers: list["Server"],
        job_size: int,
        warm_standbys: int,
        rng: random.Random,
    ) -> list["Server"]:
        """Return a uniform random sample of ``job_size + warm_standbys`` servers.

        Samples across the *entire* available pool (not just a prefix of it),
        so selection isn't biased by whatever order ``available_servers``
        happens to be in (e.g. after repaired servers are appended back to
        the working pool).
        """
        needed = job_size + warm_standbys
        return rng.sample(available_servers, min(needed, len(available_servers)))


class FewestFailuresFirst(HostSelectionPolicy):
    """Prefer servers with the fewest historical failures."""

    def select(
        self,
        available_servers: list["Server"],
        job_size: int,
        warm_standbys: int,
        rng: random.Random,
    ) -> list["Server"]:
        """Sort by ascending total failure count (random tiebreak) and return the top servers."""
        needed = job_size + warm_standbys
        sorted_servers = sorted(
            available_servers, key=lambda s: (s.total_failure_count, rng.random())
        )
        return sorted_servers[:needed]


class PackedByRackFirst(HostSelectionPolicy):
    """Prefer packing the job into as few racks as possible (network locality).

    Requires ``Params.enable_topology=True`` (servers must have a ``rack_id``
    set by ``airesim.topology.assign_racks``); untagged servers (``rack_id is
    None``) are treated as a single rack and simply grouped together.

    Available servers are grouped by ``rack_id``, each rack's members are
    shuffled to avoid list-order bias, and racks are then filled into the
    selection largest-first — a simple greedy heuristic that tends to
    minimize the number of distinct racks a job spans.
    """

    def select(
        self,
        available_servers: list["Server"],
        job_size: int,
        warm_standbys: int,
        rng: random.Random,
    ) -> list["Server"]:
        """Group by rack, order racks by descending size, and fill greedily."""
        needed = job_size + warm_standbys
        by_rack: dict[int | None, list["Server"]] = {}
        for s in available_servers:
            by_rack.setdefault(s.rack_id, []).append(s)

        for rack_servers in by_rack.values():
            rng.shuffle(rack_servers)
        ordered_racks = sorted(by_rack.values(), key=len, reverse=True)

        selected: list["Server"] = []
        for rack_servers in ordered_racks:
            selected.extend(rack_servers)
            if len(selected) >= needed:
                break
        return selected[:needed]


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

    def select(
        self,
        available_servers: list["Server"],
        job_size: int,
        warm_standbys: int,
        rng: random.Random,
    ) -> list["Server"]:
        """Sort by descending reliability score (random tiebreak) and return the top servers."""
        needed = job_size + warm_standbys
        sorted_servers = sorted(
            available_servers,
            key=lambda s: (-self.scored_removal.get_score(s), rng.random()),
        )
        return sorted_servers[:needed]
