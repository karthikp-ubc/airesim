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

import math
import random
from typing import TYPE_CHECKING

import simpy

from airesim.server import Server, ServerState

if TYPE_CHECKING:
    from airesim.stats import StatsCollector


class Coordinator:
    """Coordinates the execution of an AI training job across a server group."""

    def __init__(
        self,
        env: simpy.Environment,
        stats: "StatsCollector",
        rng: random.Random,
        failure_distribution: str = 'exponential',
        weibull_shape: float = 1.0,
        lognormal_sigma: float = 1.0,
    ):
        self.env = env
        self.stats = stats
        self.rng = rng
        self.failure_distribution = failure_distribution
        self.weibull_shape = weibull_shape
        self.lognormal_sigma = lognormal_sigma

    def run_until_failure(
        self,
        servers: list[Server],
        remaining_job_time: float,
    ) -> tuple[Server | None, float]:
        """Run the job on all servers until the first failure or completion.

        For the exponential distribution, uses the analytical shortcut: the
        minimum of N independent Exp(λ_i) is Exp(Σλ_i), so only two RNG
        calls are needed regardless of N.

        For Weibull and lognormal, samples a TTF per server and takes the
        minimum directly (O(N) calls).  This is still fast because the
        expensive part of the original design was SimPy process overhead,
        not sampling.

        Returns:
            (failed_server, compute_duration) — or (None, remaining_job_time)
            if the job completes without a failure.
        """
        time_to_failure, failed_server = self._find_first_failure(
            servers, remaining_job_time
        )

        yield self.env.timeout(time_to_failure)

        if failed_server is None:
            return None, remaining_job_time

        # Determine if this failure is systematic or random
        if failed_server.is_bad:
            p_systematic = (
                failed_server.systematic_failure_rate / failed_server.failure_rate
            )
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

    # ── Sampling helpers ──────────────────────────────────────────────────

    def _find_first_failure(
        self,
        servers: list[Server],
        remaining_job_time: float,
    ) -> tuple[float, Server | None]:
        """Return (time_to_failure, failing_server).

        Returns (remaining_job_time, None) when the job completes first.
        Dispatches to the distribution-specific implementation.
        """
        if self.failure_distribution == 'exponential':
            return self._find_first_failure_exponential(servers, remaining_job_time)
        return self._find_first_failure_per_server(servers, remaining_job_time)

    def _find_first_failure_exponential(
        self,
        servers: list[Server],
        remaining_job_time: float,
    ) -> tuple[float, Server | None]:
        """Aggregated-rate exponential shortcut (O(1) RNG calls)."""
        rates = [(s, s.failure_rate) for s in servers]
        total_rate = sum(r for _, r in rates)

        if total_rate <= 0:
            return remaining_job_time, None

        ttf = self.rng.expovariate(total_rate)
        if ttf >= remaining_job_time:
            return remaining_job_time, None

        # Choose which server failed proportional to its rate
        r = self.rng.random() * total_rate
        cumulative = 0.0
        failed_server = servers[0]  # fallback
        for s, rate in rates:
            cumulative += rate
            if r <= cumulative:
                failed_server = s
                break

        return ttf, failed_server

    def _find_first_failure_per_server(
        self,
        servers: list[Server],
        remaining_job_time: float,
    ) -> tuple[float, Server | None]:
        """Per-server TTF sampling; take the minimum (O(N) RNG calls)."""
        min_ttf = float('inf')
        failed_server = None
        for s in servers:
            ttf = self._sample_ttf(s.failure_rate)
            if ttf < min_ttf:
                min_ttf = ttf
                failed_server = s

        if min_ttf >= remaining_job_time:
            return remaining_job_time, None

        return min_ttf, failed_server

    def _sample_ttf(self, rate: float) -> float:
        """Sample a single time-to-failure for a server with the given rate.

        The distribution is parameterised so that its mean equals 1/rate,
        matching the exponential baseline.
        """
        if rate <= 0:
            return float('inf')
        mean_ttf = 1.0 / rate
        if self.failure_distribution == 'weibull':
            # weibullvariate(alpha, beta): mean = alpha * Γ(1 + 1/beta)
            # Solve for alpha so that mean == mean_ttf.
            k = self.weibull_shape
            alpha = mean_ttf / math.gamma(1.0 + 1.0 / k)
            return self.rng.weibullvariate(alpha, k)
        # lognormal: mean = exp(mu + sigma²/2)  →  mu = ln(mean_ttf) - sigma²/2
        sigma = self.lognormal_sigma
        mu = math.log(mean_ttf) - 0.5 * sigma * sigma
        return self.rng.lognormvariate(mu, sigma)
