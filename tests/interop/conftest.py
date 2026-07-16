"""Fixtures for the interop test matrix (models live in ``_models``)."""

from __future__ import annotations

import _models
import pytest

from lp2graph.core.model import Formulation


@pytest.fixture(params=_models.KNOWN_MODELS, ids=lambda p: p[0].__name__)
def known_model(request) -> tuple[Formulation, float]:
    """One (flat formulation, hand-verified optimum) pair per known model."""
    factory, optimum = request.param
    return factory(), optimum
