"""Access to the canonical JSON Schema that defines the interchange format.

``schema/canonical.schema.json`` is the *published contract* of the
canonical formulation format: it carries a stable ``$id``, third parties
validate their artifacts against it, and ``docs/data-model.md`` points
readers at it. Until v0.3.1 it was reachable only from a git checkout --
the wheel shipped no data files at all, so ``pip install lp2graph`` gave a
user the reader but not the specification, while still forcing them to
install ``jsonschema``. See ADR-0013.

This module is the one supported way to reach the schema, from either a
wheel (packaged copy) or a source checkout (repo-root copy).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

#: Basename of the schema resource, shared by both lookup locations.
_SCHEMA_FILENAME = "canonical.schema.json"


def canonical_schema_path() -> Path:
    """Filesystem path of the canonical JSON Schema.

    Prefers the copy packaged inside ``lp2graph.schema`` (present in every
    wheel/sdist install). Falls back to the repo-root ``schema/`` copy so a
    plain ``PYTHONPATH=src`` source checkout -- the documented dev setup --
    resolves too.

    Raises:
        FileNotFoundError: if neither location holds the schema.
    """
    packaged = Path(__file__).resolve().parent / _SCHEMA_FILENAME
    if packaged.is_file():
        return packaged
    # src/lp2graph/schema/__init__.py -> repo root is four parents up.
    repo_root = Path(__file__).resolve().parents[3] / "schema" / _SCHEMA_FILENAME
    if repo_root.is_file():
        return repo_root
    raise FileNotFoundError(
        f"{_SCHEMA_FILENAME} not found: looked in {packaged} and {repo_root}. "
        "A wheel should carry the packaged copy; see ADR-0013."
    )


@lru_cache(maxsize=1)
def canonical_schema() -> dict[str, Any]:
    """The parsed canonical JSON Schema.

    Cached: the schema is immutable for the lifetime of the process and is
    read on every :func:`lp2graph.loads` call. Callers must treat the
    returned mapping as read-only -- it is shared.
    """
    text = canonical_schema_path().read_text(encoding="utf-8")
    return json.loads(text)  # type: ignore[no-any-return]


__all__ = ["canonical_schema", "canonical_schema_path"]
