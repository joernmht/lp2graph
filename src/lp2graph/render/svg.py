"""SVG rendering of a typed graph.

A simple deterministic layered layout: objective (and its instances) at
the top, constraints in the middle, variables (and their instances) at
the bottom. Indices, parameters, and operators get their own bands. No
force-directed simulation — layouts are a pure function of node
declaration order, so output is byte-stable.

For production use, callers should prefer the interactive viewer for
exploration. The static SVG is for figures, snapshot tests, and
markdown embedding.
"""

from __future__ import annotations

import html

from lp2graph.core.graph import Graph, Node
from lp2graph.render.palette import (
    CONSTRAINT_DASHED_KINDS,
    EDGE_STYLE,
    FONT_DISPLAY,
    FONT_MONO,
    NODE_FILL,
    NODE_STROKE,
    SUBTYPE_STROKE_WIDTH,
)

# Layered y-coordinates, top to bottom.
_LAYER_Y: dict[str, int] = {
    "objective": 80,
    "operator": 200,
    "constraint": 320,
    "instance_constraint": 320,
    "parameter": 460,
    "variable": 560,
    "instance_variable": 560,
    "index": 680,
}

_NODE_W = 110
_NODE_H = 44
_X_PAD = 30
_X_STEP = 140


def render_svg(g: Graph, *, title: str = "", width: int = 1200, height: int = 760) -> str:
    """Render the graph to an SVG document string."""
    layers: dict[str, list[Node]] = {}
    for n in g.nodes:
        layers.setdefault(n.cls, []).append(n)

    positions: dict[str, tuple[int, int]] = {}
    for cls, nodes in layers.items():
        y = _LAYER_Y.get(cls, 400)
        for i, node in enumerate(nodes):
            x = _X_PAD + i * _X_STEP + (_NODE_W // 2)
            positions[node.id] = (x, y)

    actual_width = max(
        width,
        max(
            (_X_PAD + len(nodes) * _X_STEP for nodes in layers.values()),
            default=width,
        ),
    )

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {actual_width} {height}" '
        f'width="{actual_width}" height="{height}" font-family={FONT_MONO!r}>'
    )
    parts.append(_defs())
    if title:
        parts.append(
            f'<text x="20" y="30" font-family={FONT_DISPLAY!r} font-size="22" '
            f'fill="#1a1a1a">{html.escape(title)}</text>'
        )
        parts.append(
            f'<text x="20" y="52" font-family={FONT_MONO!r} font-size="11" '
            f'fill="#666">view = {html.escape(g.view)}</text>'
        )

    # Edges first (so nodes overlay them).
    for e in g.edges:
        if e.src not in positions or e.dst not in positions:
            continue
        x1, y1 = positions[e.src]
        x2, y2 = positions[e.dst]
        style = EDGE_STYLE.get(e.role, EDGE_STYLE[""])
        marker = (
            ' marker-end="url(#arrow-soft)"'
            if e.role in ("slack", "aux")
            else ' marker-end="url(#arrow)"'
        )
        parts.append(
            f'<line x1="{x1}" y1="{y1 + _NODE_H // 2}" x2="{x2}" y2="{y2 - _NODE_H // 2}" '
            f'stroke="{style["stroke"]}" stroke-width="{style["stroke-width"]}" '
            f'stroke-dasharray="{style["stroke-dasharray"]}" opacity="0.78"{marker}/>'
        )
        if e.label:
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            parts.append(
                f'<text x="{mx + 4}" y="{my - 2}" font-size="9" fill="#444" '
                f"font-family={FONT_MONO!r}>{html.escape(str(e.label))}</text>"
            )

    # Operator-group brackets (drawn after edges, before nodes, so they
    # sit behind the operator rectangles but in front of the lines).
    for bracket in _operator_group_brackets(g, positions):
        parts.append(bracket)

    # Nodes.
    for n in g.nodes:
        x, y = positions[n.id]
        parts.append(_render_node(n, x, y))

    parts.append("</svg>")
    return "".join(parts)


def render_html(g: Graph, *, title: str = "") -> str:
    """Render an HTML page wrapping the SVG (useful for ``open file://``)."""
    svg = render_svg(g, title=title)
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>{html.escape(title or 'graph')}</title>"
        '<body style="margin:0;background:#fafafa;">'
        f"{svg}</body>"
    )


def _operator_group_brackets(g: Graph, positions: dict[str, tuple[int, int]]) -> list[str]:
    """Render a faint shared background behind operators feeding one objective.

    Makes it visually obvious that several sum/aggregation operators
    (e.g. the five slack groups in a weighted-sum objective) feed the
    same objective above. One bracket per objective with at least one
    incoming aggregation operator.
    """
    out: list[str] = []
    objectives = [n for n in g.nodes if n.cls == "objective"]
    for obj in objectives:
        op_ids: list[str] = []
        for e in g.edges:
            if e.src != obj.id or e.type != "operator_input":
                continue
            dst = g.node(e.dst) if g.has_node(e.dst) else None
            if dst is not None and dst.cls == "operator":
                op_ids.append(e.dst)
        if not op_ids:
            continue
        coords = [positions[i] for i in op_ids if i in positions]
        if not coords:
            continue
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        op_y = ys[0]
        pad_x = 16
        pad_y = 12
        x = min(xs) - _NODE_W // 2 - pad_x
        y = op_y - _NODE_H // 2 - pad_y
        w = (max(xs) - min(xs)) + _NODE_W + 2 * pad_x
        h = _NODE_H + 2 * pad_y
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" '
            f'fill="#e7f5e1" fill-opacity="0.35" stroke="#2f7a1f" '
            f'stroke-opacity="0.5" stroke-width="0.8" stroke-dasharray="3 2"/>'
        )
        label = html.escape(obj.label or obj.id)
        out.append(
            f'<text x="{x + 8}" y="{y - 4}" font-size="9" '
            f'fill="#2f7a1f" font-family={FONT_MONO!r}>'
            f"↑ {label}</text>"
        )
    return out


def _defs() -> str:
    return (
        "<defs>"
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#4a4a4a"/></marker>'
        '<marker id="arrow-soft" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#a8341d"/></marker>'
        "</defs>"
    )


def _render_node(n: Node, cx: int, cy: int) -> str:
    fill = NODE_FILL.get(n.cls, "#eee")
    stroke = NODE_STROKE.get(n.cls, "#333")
    stroke_w = SUBTYPE_STROKE_WIDTH.get((n.cls, n.subtype), 1.2)
    dasharray = ""
    if n.cls in ("constraint", "instance_constraint") and n.subtype in CONSTRAINT_DASHED_KINDS:
        dasharray = ' stroke-dasharray="6 3"'
    rx = (
        18
        if n.cls == "objective"
        else 8
        if n.cls.startswith("variable") or n.cls == "instance_variable"
        else 4
    )
    x = cx - _NODE_W // 2
    y = cy - _NODE_H // 2
    label = html.escape(n.label or n.id)
    subtype = html.escape(n.subtype or "")
    return (
        f'<g><rect x="{x}" y="{y}" width="{_NODE_W}" height="{_NODE_H}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"{dasharray}/>'
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="13" '
        f'font-family={FONT_MONO!r} fill="#1a1a1a">{label}</text>'
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" font-size="9" '
        f'font-family={FONT_MONO!r} fill="#666">{subtype}</text></g>'
    )


__all__ = ["render_html", "render_svg"]
