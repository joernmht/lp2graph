"""Load and parse formulation files.

The loader is intentionally thin: it reads JSON, validates against the
canonical pydantic model, and returns a :class:`~optgraph.core.model.Formulation`.
Schema validation against the JSON Schema runs first to give clear,
spec-grounded error messages; pydantic then enforces the typed model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from optgraph.core.model import Formulation
from optgraph.core.validate import validate as _validate


def load(path: str | Path) -> Formulation:
    """Load a formulation from a JSON file path.

    Args:
        path: Filesystem path to a JSON file conforming to
            ``schema/canonical.schema.json``.

    Returns:
        A validated :class:`Formulation`.

    Raises:
        ValidationError: if the file does not conform to the canonical
            schema or violates a model invariant.
        FileNotFoundError: if ``path`` does not exist.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    return loads(text, source=str(p))


def loads(text: str, *, source: str = "<string>") -> Formulation:
    """Parse a formulation from a JSON string.

    Args:
        text: JSON document text.
        source: Identifier used in error messages.

    Returns:
        A validated :class:`Formulation`.

    Raises:
        ValidationError: if the document does not conform.
    """
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as e:
        from optgraph.core.validate import ValidationError

        raise ValidationError(f"{source}: invalid JSON: {e}") from e
    formulation = Formulation.model_validate(data)
    _validate(formulation)
    return formulation


__all__ = ["load", "loads"]
