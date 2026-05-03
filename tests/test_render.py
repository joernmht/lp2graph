"""SVG rendering smoke tests."""

from __future__ import annotations

from optgraph import load
from optgraph.render.svg import render_html, render_svg
from optgraph.views import hybrid, schema


def test_render_svg_produces_well_formed_svg() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    out = render_svg(schema(f), title=f.name)
    assert out.startswith("<svg")
    assert out.endswith("</svg>")
    assert "Fraunces" in out
    assert "JetBrains Mono" in out


def test_render_html_wraps_svg() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    out = render_html(hybrid(f), title="hybrid")
    assert "<svg" in out
    assert "<body" in out


def test_render_is_deterministic() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    a = render_svg(schema(f))
    b = render_svg(schema(f))
    assert a == b
