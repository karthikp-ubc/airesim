"""Adaptive replication runner.

Runs independent simulation replications until the confidence interval (CI)
for mean training time is tight enough:

    half_width / mean  <=  relative_accuracy

where the CI uses a Student-t distribution at the requested confidence level.

Usage::

    from airesim.params import Params
    from airesim.adaptive import AdaptiveRunner

    params = Params(
        adaptive_replications=True,
        confidence_level=0.95,
        relative_accuracy=0.05,   # ±5 %
        num_replications=10,      # minimum runs before checking
        max_replications=500,
    )
    runner = AdaptiveRunner(params)
    report = runner.run(verbose=True)
    print(report)
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from airesim.params import Params
from airesim.policies import (
    HostSelectionPolicy,
    RepairEscalationPolicy,
    ServerRemovalPolicy,
)
from airesim.simulator import Simulator
from airesim.stats import StatsCollector


def _t_quantile(p: float, df: int) -> float:
    """Two-sided t quantile: P(T <= return_value) = p for T ~ t(df).

    Uses scipy.stats.t when available; falls back to a normal approximation
    (valid when df is large, i.e. many replications).

    Args:
        p: Cumulative probability (e.g. 0.975 for a 95 % two-sided CI).
        df: Degrees of freedom (number of replications minus 1).
    """
    try:
        from scipy.stats import t as t_dist  # type: ignore
        return float(t_dist.ppf(p, df))
    except ImportError:
        pass

    # Rational approximation of the normal quantile (Abramowitz & Stegun 26.2.17).
    # Accurate to ~4.5e-4; adequate for the normal approximation used when
    # scipy is absent and df is large.
    if p >= 1.0:
        return math.inf
    if p <= 0.0:
        return -math.inf

    sign = 1.0 if p >= 0.5 else -1.0
    q = p if p >= 0.5 else 1.0 - p
    t_val = math.sqrt(-2.0 * math.log(1.0 - q))
    c = (2.515517, 0.802853, 0.010328)
    d = (1.432788, 0.189269, 0.001308)
    num = c[0] + c[1] * t_val + c[2] * t_val ** 2
    den = 1.0 + d[0] * t_val + d[1] * t_val ** 2 + d[2] * t_val ** 3
    approx = t_val - num / den
    return sign * approx


@dataclass
class ConvergenceReport:
    """Summary of an adaptive run."""

    converged: bool
    num_runs: int
    mean_training_hrs: float
    ci_half_width_hrs: float
    relative_half_width: float
    confidence_level: float
    relative_accuracy_target: float
    raw_results: list[StatsCollector] = field(default_factory=list, repr=False)

    def __str__(self) -> str:
        status = "CONVERGED" if self.converged else "NOT CONVERGED (max_replications reached)"
        return (
            f"AdaptiveRunner [{status}]\n"
            f"  runs              : {self.num_runs}\n"
            f"  mean training time: {self.mean_training_hrs:.2f} hrs\n"
            f"  {int(self.confidence_level * 100):d}% CI half-width : "
            f"±{self.ci_half_width_hrs:.2f} hrs "
            f"({self.relative_half_width * 100:.1f}% of mean)\n"
            f"  target accuracy   : ±{self.relative_accuracy_target * 100:.1f}% of mean"
        )


class AdaptiveRunner:
    """Run replications until a CI-based accuracy criterion is satisfied.

    The runner adds one replication at a time after the minimum number of
    replications (``params.num_replications``) has been completed, until:

        half_width / mean <= params.relative_accuracy

    where ``half_width = t_{alpha/2, n-1} * std / sqrt(n)`` and alpha is
    derived from ``params.confidence_level``.

    Args:
        params: Simulation parameters.  ``adaptive_replications`` does not
            need to be ``True`` to use this class directly, but the CLI and
            sweep drivers check that flag before invoking it automatically.
        host_selection_policy: Optional custom host-selection policy.
        escalation_policy: Optional custom repair-escalation policy.
        removal_policy: Optional custom server-removal policy.
    """

    def __init__(
        self,
        params: Params,
        host_selection_policy: HostSelectionPolicy | None = None,
        escalation_policy: RepairEscalationPolicy | None = None,
        removal_policy: ServerRemovalPolicy | None = None,
    ):
        self.params = params
        self.host_selection_policy = host_selection_policy
        self.escalation_policy = escalation_policy
        self.removal_policy = removal_policy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, verbose: bool = False) -> ConvergenceReport:
        """Execute adaptive replications and return a convergence report.

        Args:
            verbose: Print a one-line status after each replication.

        Returns:
            A :class:`ConvergenceReport` describing the final outcome.
        """
        p = self.params
        min_reps = p.num_replications
        max_reps = p.max_replications
        alpha_half = (1.0 + p.confidence_level) / 2.0  # e.g. 0.975 for 95 % CI

        raw: list[StatsCollector] = []

        for rep in range(max_reps):
            sim = Simulator(
                params=p,
                host_selection_policy=self.host_selection_policy,
                escalation_policy=self.escalation_policy,
                removal_policy=self.removal_policy,
                seed=p.seed + rep,
            )
            stats = sim.run()
            raw.append(stats)
            n = len(raw)

            if verbose:
                print(
                    f"  rep {n:4d}: training_time={stats.training_time_hours:.2f} hrs",
                    flush=True,
                )

            # Need at least 2 samples for a standard deviation.
            if n < max(2, min_reps):
                continue

            times = [r.training_time_hours for r in raw]
            mean = statistics.mean(times)
            std = statistics.stdev(times)

            if mean == 0.0:
                # Degenerate case — all jobs finished instantly; treat as converged.
                return self._report(raw, converged=True, mean=mean, half=0.0, p=p)

            t_crit = _t_quantile(alpha_half, df=n - 1)
            half_width = t_crit * std / math.sqrt(n)
            rel = half_width / abs(mean)

            if verbose:
                print(
                    f"          CI: {mean:.2f} ± {half_width:.2f} hrs "
                    f"(rel={rel * 100:.1f}%, target={p.relative_accuracy * 100:.1f}%)",
                    flush=True,
                )

            if rel <= p.relative_accuracy:
                return self._report(raw, converged=True, mean=mean, half=half_width, p=p)

        # Max replications reached without convergence.
        times = [r.training_time_hours for r in raw]
        mean = statistics.mean(times)
        std = statistics.stdev(times) if len(raw) > 1 else 0.0
        n = len(raw)
        t_crit = _t_quantile(alpha_half, df=max(1, n - 1))
        half_width = t_crit * std / math.sqrt(n) if n > 0 else 0.0
        return self._report(raw, converged=False, mean=mean, half=half_width, p=p)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _report(
        raw: list[StatsCollector],
        converged: bool,
        mean: float,
        half: float,
        p: Params,
    ) -> ConvergenceReport:
        rel = half / abs(mean) if mean != 0.0 else 0.0
        return ConvergenceReport(
            converged=converged,
            num_runs=len(raw),
            mean_training_hrs=mean,
            ci_half_width_hrs=half,
            relative_half_width=rel,
            confidence_level=p.confidence_level,
            relative_accuracy_target=p.relative_accuracy,
            raw_results=raw,
        )
