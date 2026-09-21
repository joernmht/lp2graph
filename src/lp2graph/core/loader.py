"""Load and parse formulation files.

The loader is the *interchange boundary*: everything that enters the
library from a file or a wire format passes through here. It therefore
enforces the published contract in full, in three phases:

1. **JSON Schema** (``schema/canonical.schema.json``) -- the contract third
   parties validate against, giving spec-grounded error messages.
2. **pydantic** (:class:`~lp2graph.core.model.Formulation`) -- the typed
   model and its parse-time normalizations.
3. **semantic invariants** (:func:`lp2graph.core.validate.validate`).

Phase 1 is not redundant with phase 2. The pydantic model deliberately
carries ergonomic defaults for in-Python construction (``schema_version``
and ``constraints`` both default), so on their own they would accept an
*unversioned* or *constraint-less* document that the published schema
rejects. Silently treating an unversioned file as ``0.1.0`` would defeat
the only forward-compatibility mechanism the format has (ADR-0004), and a
constraint-less formulation is a silent extraction failure in a mined
corpus. Documents get the strict contract; Python callers keep the
defaults. See ADR-0013.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError as PydanticValidationError

from lp2graph.core.model import Formulation
from lp2graph.core.validate import validate as _validate


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
    from lp2graph.core.validate import ValidationError

    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValidationError(f"{source}: invalid JSON: {e}") from e
    _check_schema(data, source)
    try:
        formulation = Formulation.model_validate(data)
    except PydanticValidationError as e:
        # Anchor the failure to the artifact: a caller loading a directory of
        # corpus files otherwise gets a pydantic error that never names which
        # file was bad. `add_note` rather than a wrapping raise, so the public
        # exception type callers already catch is preserved (py3.11+).
        e.add_note(f"while loading {source}")
        raise
    _validate(formulation)
    return formulation


@lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    """The compiled validator for the canonical schema.

    Cached: compiling a Draft 2020-12 validator costs more than running it,
    and mining ingests load many files per run.
    """
    from lp2graph.schema import canonical_schema

    return jsonschema.Draft202012Validator(canonical_schema())


def _check_schema(data: Any, source: str) -> None:
    """Validate ``data`` against the published canonical JSON Schema.

    ``jsonschema`` is a core dependency precisely for this call; before
    ADR-0013 it was declared, installed, and never imported.
    """
    from lp2graph.core.validate import ValidationError

    errors = sorted(_validator().iter_errors(data), key=lambda e: list(e.path))
    if not errors:
        return
    messages = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
    raise ValidationError(f"{source}: does not conform to canonical.schema.json", messages)


__all__ = ["load", "loads"]
