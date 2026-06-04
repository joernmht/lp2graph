"""Concrete instance data for grounding a formulation.

A :class:`Formulation` is a *template*: it declares index families,
parameter shapes, and quantified constraints, but no numbers. An
:class:`Instance` supplies the numbers needed to materialize and solve a
concrete model:

- ``cardinalities`` — the size of every index family (``{"I": 4, "T": 8}``).
- ``parameters`` — a concrete value for every parameter, keyed by name.
  A scalar parameter maps to a number; a shaped parameter maps to a
  nested list, a flat list (rank 1), or a mapping from index tuples to
  numbers.

Instances are plain data and load from JSON.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Instance:
    """Concrete numeric data for one grounding of a formulation."""

    cardinalities: dict[str, int]
    parameters: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Instance:
        cards = {str(k): int(v) for k, v in data.get("cardinalities", {}).items()}
        params = dict(data.get("parameters", {}))
        return Instance(cardinalities=cards, parameters=params)

    @staticmethod
    def load(path: str | Path) -> Instance:
        return Instance.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {"cardinalities": dict(self.cardinalities), "parameters": dict(self.parameters)}


def lookup(value: Any, key: tuple[int, ...]) -> float:
    """Read a numeric parameter value at an integer-index ``key``.

    Accepts scalars, flat/nested sequences, and tuple/stringified-tuple
    mappings — the shapes an instance JSON naturally produces.
    """
    if key == ():
        if isinstance(value, (int, float)):
            return float(value)
        raise TypeError(f"scalar parameter expected, got {type(value).__name__}")
    if isinstance(value, Mapping):
        for cand in (key, list(key), _strkey(key), key[0] if len(key) == 1 else None):
            if cand is not None and cand in value:
                return float(value[cand])
        raise KeyError(f"parameter value missing for index {key}")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        cur: Any = value
        for k in key:
            cur = cur[k]
        return float(cur)
    if len(key) == 0:
        return float(value)
    raise TypeError(f"cannot index parameter value of type {type(value).__name__}")


def _strkey(key: tuple[int, ...]) -> str:
    return ",".join(str(k) for k in key)


__all__ = ["Instance", "lookup"]
