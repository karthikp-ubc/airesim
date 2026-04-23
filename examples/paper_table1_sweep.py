"""Example: reproduce the parameter sweeps from the AIReSim paper (Table 1).

This script runs two-way sweeps of each parameter × working pool size,
matching the experimental setup described in Section 4 of the paper.
"""

from airesim.params import Params
from airesim.sweep import TwoWaySweep

# Base parameters from Table 1
BASE = Params(
    random_failure_rate=0.01 / (24 * 60),
    systematic_failure_rate_multiplier=5.0,
    systematic_failure_fraction=0.15,
    recovery_time=20,
    warm_standbys=16,
    host_selection_time=3,
    preemption_wait_time=20,
    prob_auto_to_manual=0.80,
    auto_repair_fail_prob=0.40,
    manual_repair_fail_prob=0.20,
    auto_repair_time=120,
    manual_repair_time=2 * 1440,
    job_size=4096,
    job_length=256 * 24 * 60,
    working_pool_size=4160,
    spare_pool_size=200,
    num_replications=30,
)

WORKING_POOL_VALUES = [4112, 4128, 4160, 4192]


def main():
    print("AIReSim — Paper Table 1 Sweep Reproduction")
    print("=" * 60)

    sweeps = [
        ("recovery_time", [10, 20, 30]),
        ("preemption_wait_time", [10, 20, 30]),
        ("systematic_failure_fraction", [0.1, 0.15, 0.2]),
        ("warm_standbys", [4, 8, 16, 32]),
        ("host_selection_time", [1, 3, 5, 10]),
        ("auto_repair_fail_prob", [0.2, 0.4, 0.6]),
        ("manual_repair_fail_prob", [0.1, 0.2, 0.3]),
        ("auto_repair_time", [60, 120, 180]),
        ("manual_repair_time", [1440, 2 * 1440, 3 * 1440]),
        ("prob_auto_to_manual", [0.70, 0.80, 0.90]),
    ]

    for param_name, values in sweeps:
        print(f"\n--- Sweep: {param_name} × working_pool_size ---")
        sweep = TwoWaySweep(
            param1_name=param_name,
            param1_values=values,
            param2_name="working_pool_size",
            param2_values=WORKING_POOL_VALUES,
            base_params=BASE,
            num_replications=BASE.num_replications,
        )
        result = sweep.run(verbose=True)
        result.summary()
        print()


if __name__ == "__main__":
    main()
