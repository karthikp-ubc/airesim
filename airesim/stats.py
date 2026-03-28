"""Statistics collection and reporting.

StatsCollector gathers metrics from a single simulation run.
AggregateStats computes summary statistics across multiple replications.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


@dataclass
class StatsCollector:
    """Mutable statistics container for a single simulation run."""

    # Failures
    total_failures: int = 0
    random_failures: int = 0
    systematic_failures: int = 0

    # Repairs
    auto_repairs: int = 0
    manual_repairs: int = 0
    successful_repairs: int = 0
    failed_repairs: int = 0
    servers_retired: int = 0

    # Preemptions
    preemption_count: int = 0

    # Job metrics
    total_training_time: float = 0.0  # total wall-clock time including all overhead
    total_compute_time: float = 0.0   # time spent actually computing
    total_recovery_time: float = 0.0  # time spent in recovery
    total_host_selection_time: float = 0.0
    total_wait_time: float = 0.0      # time waiting for servers from spare pool
    job_stall_count: int = 0          # times the job stalled (no servers available)

    # Run durations (time between failures)
    run_durations: list[float] = field(default_factory=list)

    # Number of host selections
    host_selection_count: int = 0

    @property
    def avg_run_duration(self) -> float:
        if not self.run_durations:
            return 0.0
        return statistics.mean(self.run_durations)

    @property
    def training_time_hours(self) -> float:
        return self.total_training_time / 60.0

    def record_failure(self, is_systematic: bool) -> None:
        """Increment failure counters; distinguish random vs. systematic failures."""
        self.total_failures += 1
        if is_systematic:
            self.systematic_failures += 1
        else:
            self.random_failures += 1

    def record_run_duration(self, duration: float) -> None:
        """Append a run-segment duration (time between consecutive failures) in minutes."""
        self.run_durations.append(duration)

    def summary_dict(self) -> dict:
        """Return a flat dict of all key metrics suitable for logging or CSV export."""
        return {
            "total_training_time_hrs": round(self.training_time_hours, 2),
            "total_failures": self.total_failures,
            "random_failures": self.random_failures,
            "systematic_failures": self.systematic_failures,
            "auto_repairs": self.auto_repairs,
            "manual_repairs": self.manual_repairs,
            "successful_repairs": self.successful_repairs,
            "failed_repairs": self.failed_repairs,
            "servers_retired": self.servers_retired,
            "preemption_count": self.preemption_count,
            "host_selection_count": self.host_selection_count,
            "job_stall_count": self.job_stall_count,
            "avg_run_duration_mins": round(self.avg_run_duration, 2),
        }


@dataclass
class AggregateStats:
    """Summary statistics across multiple replications."""

    param_label: str
    param_value: object
    num_runs: int
    raw_results: list[StatsCollector] = field(default_factory=list)

    def _extract(self, field_name: str) -> list[float]:
        return [getattr(r, field_name) for r in self.raw_results]

    def _summarize(self, values: list[float]) -> dict:
        if not values:
            return {}
        n = len(values)
        s = sorted(values)
        return {
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if n > 1 else 0.0,
            "min": s[0],
            "max": s[-1],
            "p5": s[max(0, int(0.05 * n) - 1)],
            "p95": s[min(n - 1, int(0.95 * n))],
        }

    def training_time_summary(self) -> dict:
        """Return mean/stdev/percentile stats for total training time (hours) across replications."""
        times = [r.training_time_hours for r in self.raw_results]
        return self._summarize(times)

    def failure_count_summary(self) -> dict:
        """Return mean/stdev/percentile stats for total failure count across replications."""
        return self._summarize(self._extract("total_failures"))

    def summary_table(self) -> dict:
        """Return a dict with summaries for all key metrics."""
        return {
            "training_time_hrs": self.training_time_summary(),
            "total_failures": self.failure_count_summary(),
            "preemptions": self._summarize(self._extract("preemption_count")),
            "avg_run_duration_mins": self._summarize(
                [r.avg_run_duration for r in self.raw_results]
            ),
        }

    def __repr__(self):
        """Return a concise string showing parameter value and mean ± stdev training time."""
        tt = self.training_time_summary()
        return (
            f"AggregateStats({self.param_label}={self.param_value}, "
            f"n={self.num_runs}, "
            f"training_time_hrs={tt.get('mean', 0):.1f}±{tt.get('stdev', 0):.1f})"
        )
