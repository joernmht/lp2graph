"""Result type returned by every metric."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricResult:
    """The output of a single metric.

    ``name`` is a stable machine identifier; ``value`` is whatever the
    metric produces (int, float, bool, dict). ``explanation`` is a short
    one-line human-readable description. ``data`` carries optional
    auxiliary fields (e.g. the diameter path along with the diameter
    length).
    """

    name: str
    value: Any
    explanation: str = ""
    data: dict[str, Any] = field(default_factory=dict)


__all__ = ["MetricResult"]
