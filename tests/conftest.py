"""Pytest fixtures shared across tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORMULATIONS = ROOT / "formulations"

# The solver suite (pulp/highspy) is vendored alongside the validation
# harness; make it importable so the solve/describe tests can run.
_DEPS = ROOT / "corpus" / "validation" / ".deps"
if _DEPS.is_dir() and str(_DEPS) not in sys.path:
    sys.path.insert(0, str(_DEPS))


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
