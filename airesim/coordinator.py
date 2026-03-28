"""Coordinator — manages the execution of an AI job across a group of servers.

When any server in the group fails, the coordinator:
1. Stops all other servers in the group
2. Initiates recovery (loading checkpoint)
3. Triggers host selection if warm standbys are exhausted

Performance note: instead of spawning N SimPy processes (one per server) and
using AnyOf, we use the analytical property that the minimum of N independent
exponential random variables with rates lambda_1..lambda_n is exponential with
rate sum(lambda_i), and the failing server is chosen proportional to its rate.
This makes the coordinator O(N) per failure rather than O(N) SimPy processes.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import simpy

from airesim.server import Server, ServerState

if TYPE_CHECKING:
    from airesim.stats import StatsCollector


class Coordinator:
    """Coordinates the execution of an AI training job across a server group."""

    def __init__(
        self, env: simpy.Environment, stats: "StatsCollector", rng: random.Random
    ):
        self.env = env
        self.stats = stats
        self.rng = rng

    def run_until_failure(
        self,
        servers: list[Server],
        remaining_job_time: float,
    ) -> tuple[Server | None, float]:
        """Run the job on all servers until the first failure or completion.

        Uses aggregated exponential sampling: the time to the first failure
        across N servers with independent exponential failure processes is
        itself exponential with rate = sum of individual rates.

        Args:
            servers: List of servers to run the job on.
            remaining_job_time: How much compute time remains for the job.

        Returns:
            (failed_server, compute_duration) — the server that failed and
            how long the job ran before the failure.  If no failure occurs
            (job completes), returns (None, remaining_job_time).
        """
        # Compute aggregate failure rate
        rates = [(s, s.failure_rate) for s in servers]
        total_rate = sum(r for _, r in rates)

        if total_rate <= 0:
            # No failures possible — job completes
            yield self.env.timeout(remaining_job_time)
            return None, remaining_job_time

        # Sample time to first failure (exponential with aggregate rate)
        time_to_failure = self.rng.expovariate(total_rate)

        if time_to_failure >= remaining_job_time:
            # Job completes before any failure
            yield self.env.timeout(remaining_job_time)
            return None, remaining_job_time

        # A failure occurs at time_to_failure
        yield self.env.timeout(time_to_failure)

        # Choose which server failed (proportional to its rate)
        r = self.rng.random() * total_rate
        cumulative = 0.0
        failed_server = servers[0]  # fallback
        for s, rate in rates:
            cumulative += rate
            if r <= cumulative:
                failed_server = s
                break

        # Determine if this failure is systematic or random
        if failed_server.is_bad:
            p_systematic = failed_server.systematic_failure_rate / failed_server.failure_rate
            failed_server.was_systematic = self.rng.random() < p_systematic
        else:
            failed_server.was_systematic = False

        # Update server bookkeeping
        failed_server.total_failure_count += 1
        if failed_server.was_systematic:
            failed_server.systematic_failure_count += 1
        else:
            failed_server.random_failure_count += 1
        failed_server.failure_timestamps.append(self.env.now)
        failed_server.state = ServerState.FAILED

        # Record stats
        self.stats.record_failure(failed_server.was_systematic)
        self.stats.record_run_duration(time_to_failure)

        return failed_server, time_to_failure
