"""Color palette and stroke styles for the rendered output.

Deliberate, role-based. Variables, constraints, objectives, indices,
parameters, and operators each have a distinct hue. Subtype drives
stroke style (e.g. binary variables get a doubled stroke).

These choices implement the visual identity in
``docs/design-context.md`` and are not configurable in v0.1. Downstream
consumers who want different styling consume the typed
:class:`~lp2graph.core.graph.Graph` and render it themselves.
"""

from __future__ import annotations

from typing import Final

# Node fill colors by class.
NODE_FILL: Final[dict[str, str]] = {
    "variable": "#e9f1ff",
    "instance_variable": "#dceaff",
    "constraint": "#fde8e1",
    "instance_constraint": "#f9d8cf",
    "objective": "#e7f5e1",
    "index": "#f4eedb",
    "parameter": "#ede0f2",
    "operator": "#dde7e8",
}

# Node stroke colors by class.
NODE_STROKE: Final[dict[str, str]] = {
    "variable": "#1f4fbb",
    "instance_variable": "#1f4fbb",
    "constraint": "#a8341d",
    "instance_constraint": "#a8341d",
    "objective": "#2f7a1f",
    "index": "#856404",
    "parameter": "#5b2772",
    "operator": "#0f3a3c",
}

# Subtype-driven stroke modifiers. Maps (cls, subtype) → stroke-width.
SUBTYPE_STROKE_WIDTH: Final[dict[tuple[str, str], float]] = {
    ("variable", "continuous"): 1.2,
    ("variable", "non_negative"): 1.2,
    ("variable", "integer"): 2.0,
    ("variable", "binary"): 2.6,
    ("instance_variable", "continuous"): 1.2,
    ("instance_variable", "non_negative"): 1.2,
    ("instance_variable", "integer"): 2.0,
    ("instance_variable", "binary"): 2.6,
}

# Constraint subtypes that trigger a dashed border.
CONSTRAINT_DASHED_KINDS: Final[set[str]] = {"big_m", "soft", "robust"}

# Edge color and style by role.
EDGE_STYLE: Final[dict[str, dict[str, str]]] = {
    "lhs": {"stroke": "#4a4a4a", "stroke-dasharray": "0", "stroke-width": "1.4"},
    "rhs": {"stroke": "#4a4a4a", "stroke-dasharray": "0", "stroke-width": "2.0"},
    "objective": {"stroke": "#2f7a1f", "stroke-dasharray": "0", "stroke-width": "1.6"},
    "slack": {"stroke": "#a8341d", "stroke-dasharray": "4 3", "stroke-width": "1.4"},
    "aux": {"stroke": "#5b2772", "stroke-dasharray": "1 2", "stroke-width": "1.2"},
    "shape": {"stroke": "#856404", "stroke-dasharray": "3 2", "stroke-width": "0.8"},
    "": {"stroke": "#888", "stroke-dasharray": "0", "stroke-width": "1.0"},
}

# Typography. JetBrains Mono is the workhorse.
FONT_DISPLAY: Final[str] = (
    '"Fraunces", "Iowan Old Style", "Cambria", Georgia, serif'
)
FONT_MONO: Final[str] = (
    '"JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace'
)


__all__ = [
    "CONSTRAINT_DASHED_KINDS",
    "EDGE_STYLE",
    "FONT_DISPLAY",
    "FONT_MONO",
    "NODE_FILL",
    "NODE_STROKE",
    "SUBTYPE_STROKE_WIDTH",
]
