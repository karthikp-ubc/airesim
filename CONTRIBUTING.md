# Contributing to AIReSim

Thank you for your interest in contributing!  This document explains how to set
up a development environment, run the tests, and submit changes.

---

## Getting started

### Prerequisites

- Python 3.10 or later
- [SimPy](https://simpy.readthedocs.io/) (installed automatically)

### Install in editable mode

```bash
git clone <repo-url>
cd airesim
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"        # installs simpy + matplotlib + pytest
```

---

## Running the tests

```bash
pytest tests/
```

All tests should pass before you open a pull request.  The CI workflow runs the
suite on Python 3.10, 3.11, and 3.12 — please check that your changes do not
introduce version-specific issues.

---

## Code conventions

- **Style:** follow PEP 8.  Line length ≤ 100 characters.
- **Types:** add type annotations to all new public functions and methods.
- **Docstrings:** every public class, method, and function should have a docstring.
  One-liners are fine for simple methods; use the Args/Returns style for anything
  non-trivial.
- **No new dependencies** in the core simulator (`airesim/`) without prior
  discussion.  Optional dependencies (e.g. matplotlib) belong in
  `[project.optional-dependencies]` in `pyproject.toml`.

---

## Making changes

### Adding a new parameter

1. Add the field to `Params` in `airesim/params.py` with a sensible default.
2. Add validation in `Params.validate()` if the value has constraints.
3. Pass the new value through to whichever component uses it (usually
   `Coordinator`, `RepairShop`, or `Scheduler`).
4. Add at least one test in `tests/` that exercises the new parameter.
5. Update `docs/ARCHITECTURE.md` and/or `docs/TUTORIAL.md` if the change is
   user-facing.

### Adding a new policy

Subclass the appropriate ABC in `airesim/policies.py`:

| What you want to customise | ABC to subclass |
|---|---|
| Which servers run the job | `HostSelectionPolicy` |
| Auto → manual repair escalation | `RepairEscalationPolicy` |
| Permanently retiring servers | `ServerRemovalPolicy` |

See `docs/TUTORIAL.md` §3 for a worked example.

### Adding a new failure distribution

1. Add the distribution name to `_valid_dists` in `Params.validate()`.
2. Add sampling logic to `Coordinator._sample_ttf()` in `airesim/coordinator.py`.
3. Add a test to `tests/test_airesim.py` alongside the existing
   `test_failure_distributions` test.

---

## Pull request checklist

- [ ] `pytest tests/` passes locally
- [ ] New or changed behaviour is covered by tests
- [ ] Docstrings added/updated for all touched public methods
- [ ] `ARCHITECTURE.md` or `TUTORIAL.md` updated if the change is user-facing
- [ ] No unrelated formatting changes mixed into the diff

---

## Reporting issues

Please open a GitHub issue with:

1. A minimal reproducible example (the `Params` values and the code that triggers
   the problem).
2. The full traceback or unexpected output.
3. Your Python version (`python --version`) and SimPy version
   (`pip show simpy`).
