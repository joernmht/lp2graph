"""Deterministic natural-language description of a formulation.

    from lp2graph import load
    from lp2graph.nl import describe

    print(describe(load("formulations/constraints/assignment.json")))

See :func:`lp2graph.nl.describe.describe`.
"""

from __future__ import annotations

from lp2graph.nl.describe import describe

__all__ = ["describe"]
