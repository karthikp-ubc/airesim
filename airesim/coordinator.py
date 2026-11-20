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
from statistics import NormalDist
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

        For Weibull and lognormal, samples each server's *residual* life given
        its current age (job-running time since it was last renewed) and takes
        the minimum (O(N) calls).  This is still fast because the expensive
        part of the original design was SimPy process overhead, not sampling.

        Every server in ``servers`` ages by the returned compute duration.

        Returns:
            (failed_server, compute_duration) — or (None, remaining_job_time)
            if the job completes without a failure.
        """
        time_to_failure, failed_server = self._find_first_failure(
            servers, remaining_job_time
        )

        yield self.env.timeout(time_to_failure)

        for s in servers:
            s.age += time_to_failure

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
        """Per-server residual-life sampling; take the minimum (O(N) RNG calls)."""
        min_ttf = float('inf')
        failed_server = None
        for s in servers:
            ttf = self._sample_residual(s.failure_rate, s.age)
            if ttf < min_ttf:
                min_ttf = ttf
                failed_server = s

        if min_ttf >= remaining_job_time:
            return remaining_job_time, None

        return min_ttf, failed_server

    def _sample_ttf(self, rate: float) -> float:
        """Sample a time-to-failure for a new (age-zero) server with the given rate."""
        return self._sample_residual(rate, 0.0)

    def _sample_residual(self, rate: float, age: float) -> float:
        """Sample the remaining life of a server of the given age, conditioned on survival.

        The distribution is parameterised so that its (unconditional) mean equals
        ``1/rate``, matching the exponential baseline.  Sampling is by inversion of
        the conditional survival function S(age + t) / S(age).
        """
        if rate <= 0:
            return float('inf')
        mean_ttf = 1.0 / rate
        e = self.rng.expovariate(1.0)  # -ln U, U ~ Uniform(0, 1]
        if self.failure_distribution == 'weibull':
            # S(t) = exp(-(t/alpha)^k), mean = alpha * Γ(1 + 1/k).
            # ((age + t)/alpha)^k = (age/alpha)^k + E
            k = self.weibull_shape
            alpha = mean_ttf / math.gamma(1.0 + 1.0 / k)
            return alpha * ((age / alpha) ** k + e) ** (1.0 / k) - age
        # lognormal: mean = exp(mu + sigma²/2)  →  mu = ln(mean_ttf) - sigma²/2
        sigma = self.lognormal_sigma
        mu = math.log(mean_ttf) - 0.5 * sigma * sigma
        # Survival at age, computed in the upper tail to keep precision for old servers.
        s_age = 1.0
        if age > 0:
            s_age = 0.5 * math.erfc((math.log(age) - mu) / sigma / math.sqrt(2.0))
        s = s_age * math.exp(-e)  # target survival S(age + t) = S(age) · U
        if s <= 0.0:
            return 0.0  # astronomically old server: fails immediately
        s = min(s, math.nextafter(1.0, 0.0))  # inv_cdf needs 0 < p < 1
        z = -NormalDist().inv_cdf(s)
        return max(0.0, math.exp(mu + sigma * z) - age)
