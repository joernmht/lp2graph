"""lp2graph — typed-graph representation of LP, MIP, and MILP formulations.

The public API is intentionally small. The canonical entry points are:

    from lp2graph import load, validate
    from lp2graph import views, metrics, render, export

See ``docs/data-model.md`` for the schema and ``docs/views.md`` for the
view derivations.
"""

from __future__ import annotations

from lp2graph.codec import (
    canonical_normal_form,
    from_canonical_latex,
    to_canonical_latex,
)
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
from lp2graph.nl import describe

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
    "canonical_normal_form",
    "describe",
    "from_canonical_latex",
    "load",
    "loads",
    "to_canonical_latex",
    "validate",
]

__version__ = "0.3.0"
