"""Run an example script from a clean tree and keep a provenance log.

    python3 examples/run_logged.py --log examples/foo_figures/run.log -- \
        python3 examples/foo.py [args]

Refuses to run if airesim/, config.yaml or the script itself has uncommitted
changes; the log starts with the git commit, date and command, followed by the
script's combined stdout/stderr.
"""

from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = [c for c in a.cmd if c != "--"]
    if not cmd:
        sys.exit("no command given")

    script = next((c for c in cmd if c.endswith(".py")), None)
    paths = ["airesim", "config.yaml"] + ([script] if script else [])
    dirty = subprocess.check_output(["git", "-C", ROOT, "status", "--porcelain", "--", *paths],
                                    text=True).strip()
    if dirty and not a.allow_dirty:
        sys.exit("Refusing to run: uncommitted changes:\n" + dirty)
    commit = subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"],
                                     text=True).strip()

    os.makedirs(os.path.dirname(os.path.abspath(a.log)), exist_ok=True)
    env = dict(os.environ, MPLBACKEND="Agg", PYTHONUNBUFFERED="1")
    with open(a.log, "w") as log:
        log.write(f"# commit: {commit}\n# started: {datetime.datetime.now().isoformat()}\n"
                  f"# command: {' '.join(cmd)}\n\n")
        log.flush()
        p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            log.write(line)
            log.flush()
        rc = p.wait()
        log.write(f"\n# finished: {datetime.datetime.now().isoformat()} exit={rc}\n")
    sys.exit(rc)


if __name__ == "__main__":
    main()
