"""Pytest fixtures shared across tests."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORMULATIONS = ROOT / "formulations"

# Note: the solver-dependent tests (test_solve.py) use ``importorskip`` and
# run only where ``pulp`` is importable. They are *not* wired to the
# Linux/cp312 vendored deps under corpus/validation/.deps, since putting
# those on sys.path would shadow the installed, ABI-matched pydantic_core on
# other Python versions. To run them locally:
#     PYTHONPATH=src:corpus/validation/.deps python3 -m pytest tests/test_solve.py


@pytest.fixture(scope="session")
def formulation_files() -> list[Path]:
    """Every formulation JSON file in the catalog."""
    return sorted(FORMULATIONS.rglob("*.json"))


@pytest.fixture(scope="session")
def instance_files() -> list[Path]:
    """Every codec-pipeline instance spec (formulation + data + optimum)."""
    return sorted((ROOT / "corpus/validation/codec_pipeline/instances").glob("*.json"))


@pytest.fixture(scope="session")
def schema_path() -> Path:
    return ROOT / "schema" / "canonical.schema.json"


@pytest.fixture
def stopped_solver():
    """A back-end that stops at a limit holding an incumbent, as CBC and HiGHS do.

    PuLP reports that outcome as ``Optimal``; only ``sol_status`` records that
    optimality was not proven. The values it leaves are irrelevant to the status.
    """
    pulp = pytest.importorskip("pulp")

    class StoppedAtLimit(pulp.LpSolver):
        def available(self):
            return True

        def actualSolve(self, lp, **kwargs):
            for v in lp.variables():
                v.varValue = 1.0
            lp.assignStatus(pulp.LpStatusOptimal, pulp.LpSolutionIntegerFeasible)
            return lp.status

    return StoppedAtLimit()
