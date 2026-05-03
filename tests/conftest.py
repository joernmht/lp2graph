"""Pytest fixtures shared across tests."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORMULATIONS = ROOT / "formulations"


@pytest.fixture(scope="session")
def formulation_files() -> list[Path]:
    """Every formulation JSON file in the catalog."""
    return sorted(FORMULATIONS.rglob("*.json"))


@pytest.fixture(scope="session")
def schema_path() -> Path:
    return ROOT / "schema" / "canonical.schema.json"
