"""SVG rendering smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

from lp2graph import load
from lp2graph.render.svg import render_html, render_svg
from lp2graph.views import hybrid, schema


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


def test_render_groups_sum_operators_under_objective() -> None:
    f = load("formulations/objectives/objective_lex_priority.json")
    out = render_svg(schema(f))
    # Two sum operators feed one objective; a bracket with the marker
    # opacity and an arrow label linking back to the objective should appear.
    assert 'fill-opacity="0.35"' in out
    assert "↑" in out


def test_render_omits_bracket_when_no_aggregation_operators(tmp_path: Path) -> None:
    doc = {
        "schema_version": "0.1.0",
        "id": "no_op_obj",
        "name": "no operator objective",
        "family": "lp",
        "indices": [],
        "variables": [{"name": "x", "domain": "non_negative"}],
        "constraints": [],
        "objective": {
            "sense": "min",
            "terms": [{"ref": "x", "ref_kind": "variable", "role": "objective"}],
        },
    }
    p = tmp_path / "obj.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    f = load(p)
    out = render_svg(schema(f))
    assert 'fill-opacity="0.35"' not in out
