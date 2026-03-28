"""CLI entry point for AIReSim.

Usage:
    python -m airesim.run                          # run default demo sweep
    python -m airesim.run examples/my_sweep.py     # run a custom sweep file
"""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

from airesim.params import Params
from airesim.sweep import OneWaySweep, TwoWaySweep


def run_demo():
    """Run a small demo sweep to verify the simulator works."""
    print("AIReSim — Demo Sweep")
    print("=" * 50)

    base = Params(
        job_size=4096,
        warm_standbys=16,
        working_pool_size=4160,
        spare_pool_size=200,
        num_replications=5,  # small for demo speed
    )

    # One-way sweep: recovery time
    print("\n1) Recovery Time sweep:")
    sweep1 = OneWaySweep(
        param_name="recovery_time",
        values=[10, 20, 30],
        base_params=base,
        num_replications=5,
    )
    result1 = sweep1.run()
    result1.summary()

    # Two-way sweep: recovery time × working pool size
    print("\n2) Recovery Time × Working Pool Size sweep:")
    sweep2 = TwoWaySweep(
        param1_name="recovery_time",
        param1_values=[10, 20, 30],
        param2_name="working_pool_size",
        param2_values=[4128, 4160, 4192],
        base_params=base,
        num_replications=5,
    )
    result2 = sweep2.run()
    result2.summary()

    print("\nDone!")


def run_script(path: str):
    """Load and execute a user-provided sweep script."""
    spec = importlib.util.spec_from_file_location("user_sweep", path)
    if spec is None or spec.loader is None:
        print(f"Error: cannot load {path}")
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "main"):
        mod.main()
    else:
        print(f"Warning: {path} has no main() function.")


def main():
    if len(sys.argv) > 1:
        run_script(sys.argv[1])
    else:
        run_demo()


if __name__ == "__main__":
    main()
