"""Parameter sweep drivers.

OneWaySweep: vary one parameter across a list of values.
TwoWaySweep: vary two parameters simultaneously (Cartesian product).

Each configuration is run for `num_replications` independent trials with
different RNG seeds, and aggregate statistics are collected.
"""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass, field
from typing import Any

from airesim.params import Params
from airesim.policies import HostSelectionPolicy, RepairEscalationPolicy, ServerRemovalPolicy
from airesim.simulator import Simulator
from airesim.stats import AggregateStats, StatsCollector


@dataclass
class SweepResult:
    """Collection of aggregate stats from a parameter sweep."""

    sweep_name: str
    param_name: str
    results: list[AggregateStats] = field(default_factory=list)

    # For two-way sweeps
    param2_name: str | None = None

    def summary(self, file: io.TextIOBase | None = None) -> None:
        """Print a summary table to stdout or a file."""
        out = file or sys.stdout
        print(f"\n{'='*70}", file=out)
        print(f"Sweep: {self.sweep_name}", file=out)
        print(f"{'='*70}", file=out)
        for agg in self.results:
            tt = agg.training_time_summary()
            fc = agg.failure_count_summary()
            print(
                f"  {agg.param_label}={str(agg.param_value):<20}  "
                f"training_time={tt.get('mean', 0):8.1f}±{tt.get('stdev', 0):5.1f} hrs  "
                f"failures={fc.get('mean', 0):6.1f}±{fc.get('stdev', 0):4.1f}",
                file=out,
            )

    def to_csv(self) -> str:
        """Export results as CSV string."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        header = ["param_value", "mean_training_hrs", "stdev_training_hrs",
                  "mean_failures", "stdev_failures", "mean_preemptions",
                  "p5_training_hrs", "p95_training_hrs"]
        writer.writerow(header)
        for agg in self.results:
            tt = agg.training_time_summary()
            fc = agg.failure_count_summary()
            pr = agg._summarize([r.preemption_count for r in agg.raw_results])
            writer.writerow([
                agg.param_value,
                f"{tt.get('mean', 0):.2f}",
                f"{tt.get('stdev', 0):.2f}",
                f"{fc.get('mean', 0):.2f}",
                f"{fc.get('stdev', 0):.2f}",
                f"{pr.get('mean', 0):.2f}",
                f"{tt.get('p5', 0):.2f}",
                f"{tt.get('p95', 0):.2f}",
            ])
        return buf.getvalue()


class OneWaySweep:
    """Sweep one parameter across a list of values."""

    def __init__(
        self,
        param_name: str,
        values: list[Any],
        base_params: Params | None = None,
        num_replications: int = 30,
        host_selection_policy: HostSelectionPolicy | None = None,
        escalation_policy: RepairEscalationPolicy | None = None,
        removal_policy: ServerRemovalPolicy | None = None,
    ):
        self.param_name = param_name
        self.values = values
        self.base_params = base_params or Params()
        self.num_replications = num_replications
        self.host_selection_policy = host_selection_policy
        self.escalation_policy = escalation_policy
        self.removal_policy = removal_policy

    def run(self, verbose: bool = True) -> SweepResult:
        """Execute the sweep and return aggregated results.

        For each value in ``self.values``, runs ``num_replications`` independent
        simulations with seeds ``base_params.seed + 0 … base_params.seed + N-1``
        and collects an ``AggregateStats`` object.

        Args:
            verbose: If True, print progress (parameter value and mean training time)
                     to stdout as each configuration completes.

        Returns:
            A ``SweepResult`` containing one ``AggregateStats`` per swept value.
        """
        result = SweepResult(
            sweep_name=f"OneWay({self.param_name})",
            param_name=self.param_name,
        )

        for val in self.values:
            if verbose:
                print(f"  {self.param_name}={val} ...", end=" ", flush=True)

            params = self.base_params.with_overrides(**{self.param_name: val})
            runs: list[StatsCollector] = []

            for rep in range(self.num_replications):
                sim = Simulator(
                    params=params,
                    host_selection_policy=self.host_selection_policy,
                    escalation_policy=self.escalation_policy,
                    removal_policy=self.removal_policy,
                    seed=self.base_params.seed + rep,
                )
                stats = sim.run()
                runs.append(stats)

            agg = AggregateStats(
                param_label=self.param_name,
                param_value=val,
                num_runs=self.num_replications,
                raw_results=runs,
            )
            result.results.append(agg)

            if verbose:
                tt = agg.training_time_summary()
                print(f"mean={tt.get('mean', 0):.1f} hrs")

        return result


class TwoWaySweep:
    """Sweep two parameters simultaneously (Cartesian product)."""

    def __init__(
        self,
        param1_name: str,
        param1_values: list[Any],
        param2_name: str,
        param2_values: list[Any],
        base_params: Params | None = None,
        num_replications: int = 30,
        host_selection_policy: HostSelectionPolicy | None = None,
        escalation_policy: RepairEscalationPolicy | None = None,
        removal_policy: ServerRemovalPolicy | None = None,
    ):
        self.param1_name = param1_name
        self.param1_values = param1_values
        self.param2_name = param2_name
        self.param2_values = param2_values
        self.base_params = base_params or Params()
        self.num_replications = num_replications
        self.host_selection_policy = host_selection_policy
        self.escalation_policy = escalation_policy
        self.removal_policy = removal_policy

    def run(self, verbose: bool = True) -> SweepResult:
        """Execute the Cartesian-product sweep and return aggregated results.

        Iterates over all ``(param1_value, param2_value)`` combinations in row-major
        order, running ``num_replications`` independent simulations per cell.

        Args:
            verbose: If True, print progress for each (param1, param2) pair to stdout.

        Returns:
            A ``SweepResult`` where each entry's ``param_value`` is a
            ``(param1_val, param2_val)`` tuple.
        """
        result = SweepResult(
            sweep_name=f"TwoWay({self.param1_name}, {self.param2_name})",
            param_name=self.param1_name,
            param2_name=self.param2_name,
        )

        for v1 in self.param1_values:
            for v2 in self.param2_values:
                label = f"{self.param1_name}={v1}, {self.param2_name}={v2}"
                if verbose:
                    print(f"  {label} ...", end=" ", flush=True)

                params = self.base_params.with_overrides(
                    **{self.param1_name: v1, self.param2_name: v2}
                )
                runs: list[StatsCollector] = []

                for rep in range(self.num_replications):
                    sim = Simulator(
                        params=params,
                        host_selection_policy=self.host_selection_policy,
                        escalation_policy=self.escalation_policy,
                        removal_policy=self.removal_policy,
                        seed=self.base_params.seed + rep,
                    )
                    stats = sim.run()
                    runs.append(stats)

                agg = AggregateStats(
                    param_label=label,
                    param_value=(v1, v2),
                    num_runs=self.num_replications,
                    raw_results=runs,
                )
                result.results.append(agg)

                if verbose:
                    tt = agg.training_time_summary()
                    print(f"mean={tt.get('mean', 0):.1f} hrs")

        return result
