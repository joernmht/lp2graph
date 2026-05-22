"""lp2graph — typed-graph representation of LP, MIP, and MILP formulations.

The public API is intentionally small. The canonical entry points are:

    from lp2graph import load, validate
    from lp2graph import views, metrics, render, export

See ``docs/data-model.md`` for the schema and ``docs/views.md`` for the
view derivations.
"""

from __future__ import annotations

from lp2graph.core.loader import load, loads
from lp2graph.core.model import (
    Binding,
    ConstraintTemplate,
    Formulation,
    Index,
    Objective,
    Parameter,
    Quantifier,
    Term,
    VariableTemplate,
)
from lp2graph.core.validate import ValidationError, validate

__all__ = [
    "Binding",
    "ConstraintTemplate",
    "Formulation",
    "Index",
    "Objective",
    "Parameter",
    "Quantifier",
    "Term",
    "ValidationError",
    "VariableTemplate",
    "load",
    "loads",
    "validate",
]

__version__ = "0.2.0"
