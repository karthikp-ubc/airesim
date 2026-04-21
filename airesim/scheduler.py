"""Scheduler — host selection and warm standby management.

The scheduler assigns servers to the job, tracks remaining job length,
and manages the warm standby swap-in process.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import simpy

from airesim.scheduling_policies import HostSelectionPolicy
from airesim.server import Server, ServerState

if TYPE_CHECKING:
    from airesim.pool import PoolManager
    from airesim.stats import StatsCollector


class Scheduler:
    """Assigns servers to the AI training job and manages warm standbys."""

    def __init__(
        self,
        env: simpy.Environment,
        rng: random.Random,
        job_size: int,
        warm_standby_count: int,
        host_selection_time: float,
        host_selection_policy: HostSelectionPolicy,
        pool_manager: "PoolManager",
        stats: "StatsCollector",
    ):
        self.env = env
        self.rng = rng
        self.job_size = job_size
        self.warm_standby_count = warm_standby_count
        self.host_selection_time = host_selection_time
        self.host_selection_policy = host_selection_policy
        self.pool_manager = pool_manager
        self.stats = stats

        # Current assignment
        self.active_servers: list[Server] = []   # primary servers running the job
        self.warm_standbys: list[Server] = []     # standby servers ready to swap in

    def do_host_selection(self) -> bool:
        """Select servers from the working pool for the job.

        Returns True if enough servers were found, False otherwise.
        """
        available = self.pool_manager.available_in_working
        selected = self.host_selection_policy.select(
            available, self.job_size, self.warm_standby_count, self.rng
        )

        if len(selected) < self.job_size:
            return False  # not enough servers even without standbys

        self.active_servers = selected[: self.job_size]
        self.warm_standbys = selected[self.job_size :]
        self.stats.host_selection_count += 1
        return True

    def swap_in_standby(self, failed_server: Server) -> Server | None:
        """Try to replace a failed server with a warm standby.

        Returns the replacement server, or None if no standby available.
        """
        if failed_server in self.active_servers:
            self.active_servers.remove(failed_server)

        if self.warm_standbys:
            replacement = self.warm_standbys.pop(0)
            self.active_servers.append(replacement)
            return replacement

        return None

    def return_server_to_job(self, server: Server) -> None:
        """Return a repaired server to the warm standby list if it was in this job."""
        if server.state == ServerState.IDLE and len(self.warm_standbys) < self.warm_standby_count:
            self.warm_standbys.append(server)

    @property
    def all_assigned(self) -> list[Server]:
        """All servers currently assigned to the job (active + standbys)."""
        return self.active_servers + self.warm_standbys
