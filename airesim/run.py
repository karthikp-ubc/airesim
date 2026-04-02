"""CLI entry point for AIReSim.

Usage modes
-----------
Run the built-in demo sweep (no arguments):
    python -m airesim.run

Execute a custom Python sweep script (backward-compatible):
    python -m airesim.run examples/my_sweep.py

One-way parameter sweep from the command line:
    python -m airesim.run --sweep recovery_time --values 10,20,30
    python -m airesim.run --sweep recovery_time --values 10,20,30 \\
        --replications 30 --output results.csv
    python -m airesim.run --params config.json \\
        --sweep recovery_time --values 10,20,30 --output results.csv

Flags
-----
  --sweep PARAM         Name of the Params field to sweep over.
  --values V1,V2,...    Comma-separated numeric values for the sweep.
  --replications N      Number of independent replications (default: 30).
  --output FILE         Write sweep results as CSV to this file.
  --params FILE         Load base Params from a JSON or YAML file.
                        Overrides all simulator defaults for unlisted fields.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from airesim.params import Params
from airesim.sweep import OneWaySweep, TwoWaySweep
from airesim.adaptive import AdaptiveRunner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_values(values_str: str) -> list[int | float]:
    """Parse a comma-separated string of numbers into a typed list.

    Each token is converted to int when it contains no decimal point or
    exponent notation, and float otherwise.

    Examples:
        "10,20,30"               -> [10, 20, 30]
        "0.1,0.2,0.3"            -> [0.1, 0.2, 0.3]
        "1e-5,2e-5,4e-5"         -> [1e-05, 2e-05, 4e-05]
        "720,2880,5760"          -> [720, 2880, 5760]
    """
    result = []
    for token in values_str.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            # Use int only when the token parses cleanly as one (no dot/e)
            as_float = float(token)
            as_int = int(as_float)
            result.append(as_int if as_int == as_float and "." not in token and "e" not in token.lower() else as_float)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Cannot parse {token!r} as a number in --values"
            )
    return result


def _load_params(path: str) -> Params:
    """Load Params from a JSON or YAML file.

    The file should be a flat mapping of Params field names to values.
    Unknown keys are rejected by the Params dataclass constructor.

    Raises SystemExit with a helpful message if:
    - The file extension is not recognised.
    - PyYAML is not installed but a .yaml/.yml file is requested.
    - Any field value is invalid.
    """
    p = Path(path)
    if not p.exists():
        sys.exit(f"Error: params file not found: {path}")

    suffix = p.suffix.lower()
    if suffix == ".json":
        with p.open() as fh:
            data = json.load(fh)
    elif suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            sys.exit(
                "Error: PyYAML is required to load .yaml params files.\n"
                "Install it with:  pip install pyyaml"
            )
        with p.open() as fh:
            data = yaml.safe_load(fh)
    else:
        sys.exit(
            f"Error: unrecognised params file extension {suffix!r}. "
            "Expected .json, .yaml, or .yml."
        )

    try:
        return Params(**data)
    except TypeError as exc:
        sys.exit(f"Error loading params from {path}: {exc}")


# ── Helpers (continued) ───────────────────────────────────────────────────────

def run_adaptive(base_params: Params) -> None:
    """Run adaptive replications based on params loaded from a file."""
    print("AIReSim — Adaptive Replication")
    print(f"  confidence level : {base_params.confidence_level * 100:.0f}%")
    print(f"  relative accuracy: ±{base_params.relative_accuracy * 100:.1f}% of mean")
    print(f"  min replications : {base_params.num_replications}")
    print(f"  max replications : {base_params.max_replications}")
    print()

    runner = AdaptiveRunner(base_params)
    report = runner.run(verbose=True)

    print()
    print(report)


# ── Modes ─────────────────────────────────────────────────────────────────────

def run_demo():
    """Run a small built-in sweep to verify the simulator works."""
    print("AIReSim — Demo Sweep")
    print("=" * 50)

    base = Params(
        job_size=4096,
        warm_standbys=16,
        working_pool_size=4160,
        spare_pool_size=200,
        num_replications=5,
    )

    print("\n1) Recovery Time sweep:")
    sweep1 = OneWaySweep(
        param_name="recovery_time",
        values=[10, 20, 30],
        base_params=base,
        num_replications=5,
    )
    result1 = sweep1.run()
    result1.summary()

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
        sys.exit(f"Error: cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "main"):
        mod.main()
    else:
        print(f"Warning: {path} has no main() function.")


def run_sweep(
    param_name: str,
    values: list[int | float],
    base_params: Params,
    num_replications: int,
    output: str | None,
):
    """Execute a one-way sweep and optionally write results to CSV."""
    print(f"AIReSim — One-Way Sweep: {param_name}")
    print(f"  values        : {values}")
    print(f"  replications  : {num_replications}")
    print(f"  base params   : job_size={base_params.job_size}, "
          f"pool={base_params.working_pool_size}, seed={base_params.seed}")
    print()

    sweep = OneWaySweep(
        param_name=param_name,
        values=values,
        base_params=base_params,
        num_replications=num_replications,
    )
    result = sweep.run(verbose=True)
    result.summary()

    if output:
        out_path = Path(output)
        out_path.write_text(result.to_csv())
        print(f"\nResults written to {out_path}")


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the AIReSim CLI.

    Defines three mutually exclusive modes:
    - No arguments: run the built-in demo sweep.
    - Positional ``SCRIPT``: load and execute a user-provided Python sweep script.
    - ``--sweep`` / ``--values``: run a one-way CLI sweep with optional ``--params``
      and ``--output`` flags.
    """
    parser = argparse.ArgumentParser(
        prog="python -m airesim.run",
        description="AIReSim CLI — simulate AI cluster reliability.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Backward-compatible positional: path to a Python sweep script
    parser.add_argument(
        "script",
        nargs="?",
        metavar="SCRIPT",
        help="Python sweep script to execute (e.g. examples/my_sweep.py). "
             "Cannot be combined with --sweep.",
    )

    # ── Sweep flags ──────────────────────────────────────────────────────
    sweep = parser.add_argument_group("one-way sweep")
    sweep.add_argument(
        "--sweep",
        metavar="PARAM",
        help="Params field name to sweep (e.g. recovery_time).",
    )
    sweep.add_argument(
        "--values",
        metavar="V1,V2,...",
        help="Comma-separated values for --sweep (e.g. 10,20,30).",
    )
    sweep.add_argument(
        "--replications",
        type=int,
        default=30,
        metavar="N",
        help="Independent replications per configuration (default: 30).",
    )
    sweep.add_argument(
        "--output",
        metavar="FILE",
        help="Write sweep results as CSV to this file.",
    )

    # ── Base params flag ─────────────────────────────────────────────────
    parser.add_argument(
        "--params",
        metavar="FILE",
        help="JSON or YAML file of base Params overrides "
             "(fields not listed keep their defaults).",
    )

    # ── Adaptive flag ────────────────────────────────────────────────────
    parser.add_argument(
        "--adaptive",
        action="store_true",
        default=False,
        help="Run adaptive replications until the CI criterion in --params "
             "(confidence_level, relative_accuracy) is met.  Requires --params.",
    )

    return parser


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    """Parse CLI arguments and dispatch to the appropriate run mode.

    Validates mutual-exclusion constraints (``SCRIPT`` XOR ``--sweep``, and
    ``--values`` requires ``--sweep``), loads base ``Params`` from a file if
    ``--params`` is given, then delegates to ``run_demo``, ``run_script``, or
    ``run_sweep``.
    """
    parser = build_parser()
    args = parser.parse_args()

    # ── Validate mutually exclusive modes ────────────────────────────────
    if args.script and args.sweep:
        parser.error("SCRIPT and --sweep are mutually exclusive. "
                     "Use one or the other.")

    if args.sweep and not args.values:
        parser.error("--sweep requires --values.")

    if args.values and not args.sweep:
        parser.error("--values requires --sweep.")

    if args.adaptive and not args.params:
        parser.error("--adaptive requires --params (the YAML/JSON file must "
                     "contain confidence_level, relative_accuracy, etc.).")

    if args.adaptive and args.sweep:
        parser.error("--adaptive and --sweep are mutually exclusive.")

    if args.adaptive and args.script:
        parser.error("--adaptive and SCRIPT are mutually exclusive.")

    # ── Load base params (used by sweep mode; ignored in script mode) ────
    base_params = _load_params(args.params) if args.params else Params()

    # ── Dispatch ─────────────────────────────────────────────────────────
    if args.adaptive:
        run_adaptive(base_params)
    elif args.script:
        run_script(args.script)
    elif args.sweep:
        values = _parse_values(args.values)
        run_sweep(
            param_name=args.sweep,
            values=values,
            base_params=base_params,
            num_replications=args.replications,
            output=args.output,
        )
    else:
        run_demo()


if __name__ == "__main__":
    main()
