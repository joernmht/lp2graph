"""M1 -- heterogeneous ingestion front-end.

Turns idiosyncratic source artifacts (solver code, non-canonical author
LaTeX) into *validated* canonical :class:`~lp2graph.core.model.Formulation`
objects, with source-span provenance, never silently dropping a failure.

Public surface:

- :func:`ingest` -- the format dispatcher (route by path extension or
  explicit ``fmt``).
- :func:`ingest_latex` / :func:`normalize_latex` -- the M1b non-canonical
  LaTeX normalizer and its versioned rewrite-rule table
  (:data:`REWRITE_RULES`).
- :func:`from_pyomo` -- the M1a Pyomo importer.
- The code-importer registry entries (:func:`import_gams`,
  :func:`import_ampl`, :func:`import_jump`, :func:`import_python`).
- The result types :class:`IngestionResult` / :class:`IngestionFailure`
  / :class:`IngestionError`.
"""

from __future__ import annotations

from lp2graph.mining.ingest.code_importers import (
    CODE_IMPORTERS,
    import_ampl,
    import_gams,
    import_jump,
    import_python,
)
from lp2graph.mining.ingest.dispatch import ingest
from lp2graph.mining.ingest.latex_normalizer import (
    REWRITE_RULES,
    RewriteRule,
    ingest_latex,
    normalize_latex,
)
from lp2graph.mining.ingest.pyomo_importer import from_pyomo
from lp2graph.mining.ingest.result import (
    IngestionError,
    IngestionFailure,
    IngestionResult,
)

__all__ = [
    "CODE_IMPORTERS",
    "REWRITE_RULES",
    "IngestionError",
    "IngestionFailure",
    "IngestionResult",
    "RewriteRule",
    "from_pyomo",
    "import_ampl",
    "import_gams",
    "import_jump",
    "import_python",
    "ingest",
    "ingest_latex",
    "normalize_latex",
]
