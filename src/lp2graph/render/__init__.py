"""SVG rendering for typed graphs.

Three layout primitives are provided: ``layered`` (objective on top,
constraints in the middle, variables and parameters at the bottom),
``circular``, and ``radial``. The default is ``layered``, matching the
visual identity established in ``docs/design-context.md``.
"""

from lp2graph.render.svg import render_html, render_svg

__all__ = ["render_html", "render_svg"]
