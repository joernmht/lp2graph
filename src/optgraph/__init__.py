"""lp2graph — typed-graph representation of LP, MIP, and MILP formulations.

The public API is intentionally small. The canonical entry points are:

    from optgraph import load, validate
    from optgraph import views, metrics, render, export

See ``docs/data-model.md`` for the schema and ``docs/views.md`` for the
view derivations.
"""

from __future__ import annotations

from optgraph.core.loader import load, loads
from optgraph.core.model import (
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
from optgraph.core.validate import ValidationError, validate

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

__version__ = "0.1.0"
