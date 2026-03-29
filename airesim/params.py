"""Simulation parameters as a single dataclass.

All times are in **minutes** unless stated otherwise.
All rates are in **failures per minute** unless stated otherwise.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields, replace


@dataclass
class Params:
    """Complete parameter set for one AIReSim simulation run.

    Defaults match the illustrative values from the AIReSim paper (Table 1).
    """

    # ── Failure rates (per minute) ──────────────────────────────────────────
    random_failure_rate: float = 0.01 / (24 * 60)
    systematic_failure_rate_multiplier: float = 5.0  # systematic = multiplier × random
    systematic_failure_fraction: float = 0.15  # fraction of servers that are "bad"

    # ── Recovery ────────────────────────────────────────────────────────────
    recovery_time: float = 20.0  # minutes to recover job after a failure
    host_selection_time: float = 3.0  # minutes for host selection + job restart

    # ── Job ──────────────────────────────────────────────────────────────────
    job_size: int = 4096  # number of servers needed for the job
    job_length: float = 256 * 24 * 60  # total job length in minutes (no failures)
    warm_standbys: int = 16  # extra servers allocated to the job

    # ── Pools ────────────────────────────────────────────────────────────────
    working_pool_size: int = 4160  # total servers in working pool
    spare_pool_size: int = 200  # servers in spare pool

    # ── Preemption ───────────────────────────────────────────────────────────
    preemption_wait_time: float = 20.0  # minutes to preempt a job from spare pool

    # ── Repair pipeline ─────────────────────────────────────────────────────
    auto_repair_time: float = 120.0  # minutes for automated repair
    manual_repair_time: float = 2 * 1440.0  # minutes for manual repair (2 days)
    prob_auto_to_manual: float = 0.80  # P(auto repair doesn't work → manual)
    auto_repair_fail_prob: float = 0.40  # P(auto repair says success but didn't fix)
    manual_repair_fail_prob: float = 0.20  # P(manual repair says success but didn't fix)

    # ── Failure-time distribution ────────────────────────────────────────────
    failure_distribution: str = 'exponential'  # 'exponential' | 'weibull' | 'lognormal'
    weibull_shape: float = 1.0    # Weibull k; k=1 → exponential, k>1 → wear-out
    lognormal_sigma: float = 1.0  # lognormal σ (std-dev of the log); smaller → less spread

    # ── Diagnosis ────────────────────────────────────────────────────────────
    diagnosis_probability: float = 1.0  # P(failure triggers a repair attempt on any server)
    diagnosis_uncertainty: float = 0.0  # P(wrong server identified | failure diagnosed)

    # ── Bad-server regeneration ──────────────────────────────────────────────
    bad_server_regeneration: bool = False  # whether bad servers regenerate over time
    bad_server_regen_interval: float = 30 * 24 * 60  # interval in minutes (30 days)

    # ── Simulation control ──────────────────────────────────────────────────
    seed: int = 42
    num_replications: int = 30

    # ── Derived ──────────────────────────────────────────────────────────────
    @property
    def systematic_failure_rate(self) -> float:
        return self.systematic_failure_rate_multiplier * self.random_failure_rate

    @property
    def total_servers_needed(self) -> int:
        """Minimum servers to start a job (job_size + warm_standbys)."""
        return self.job_size + self.warm_standbys

    def validate(self) -> None:
        """Raise ValueError if parameters are inconsistent."""
        if self.working_pool_size < self.total_servers_needed:
            raise ValueError(
                f"working_pool_size ({self.working_pool_size}) must be >= "
                f"job_size + warm_standbys ({self.total_servers_needed})"
            )
        if not 0 <= self.systematic_failure_fraction <= 1:
            raise ValueError("systematic_failure_fraction must be in [0, 1]")
        if not 0 <= self.auto_repair_fail_prob <= 1:
            raise ValueError("auto_repair_fail_prob must be in [0, 1]")
        if not 0 <= self.manual_repair_fail_prob <= 1:
            raise ValueError("manual_repair_fail_prob must be in [0, 1]")
        if not 0 <= self.prob_auto_to_manual <= 1:
            raise ValueError("prob_auto_to_manual must be in [0, 1]")
        if not 0 <= self.diagnosis_probability <= 1:
            raise ValueError("diagnosis_probability must be in [0, 1]")
        if not 0 <= self.diagnosis_uncertainty <= 1:
            raise ValueError("diagnosis_uncertainty must be in [0, 1]")
        _valid_dists = ('exponential', 'weibull', 'lognormal')
        if self.failure_distribution not in _valid_dists:
            raise ValueError(
                f"failure_distribution must be one of {_valid_dists}, "
                f"got {self.failure_distribution!r}"
            )
        if self.weibull_shape <= 0:
            raise ValueError("weibull_shape must be > 0")
        if self.lognormal_sigma <= 0:
            raise ValueError("lognormal_sigma must be > 0")

    def with_overrides(self, **kwargs) -> "Params":
        """Return a new Params with selected fields overridden."""
        return replace(self, **kwargs)

    def param_names(self) -> list[str]:
        """Return list of all parameter field names."""
        return [f.name for f in fields(self) if f.name != "seed" and f.name != "num_replications"]
