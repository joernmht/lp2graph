"""Tests for the reversible LaTeX <-> graph codec."""

from __future__ import annotations

import pytest

from lp2graph import load
from lp2graph.codec import (
    canonical_normal_form,
    from_canonical_latex,
    to_canonical_latex,
)


def test_roundtrip_normal_form(formulation_files):
    """JSON -> LaTeX -> JSON preserves the canonical normal form."""
    for fp in formulation_files:
        f = load(fp)
        g = from_canonical_latex(to_canonical_latex(f))
        assert canonical_normal_form(f) == canonical_normal_form(g), fp.name


def test_text_idempotence(formulation_files):
    """The LaTeX serialization is a fixed point: to(from(to(f))) == to(f)."""
    for fp in formulation_files:
        f = load(fp)
        tex = to_canonical_latex(f)
        again = to_canonical_latex(from_canonical_latex(tex))
        assert tex == again, fp.name


def test_emitted_latex_is_paper_style(formulation_files):
    """The body uses genuine paper notation (mathcal sets, align, tags)."""
    for fp in formulation_files:
        tex = to_canonical_latex(load(fp))
        assert r"\begin{align}" in tex and r"\end{align}" in tex
        assert "%@ meta" in tex  # reversible annotation header


def test_mathcal_and_sum_present():
    tex = to_canonical_latex(load("formulations/constraints/mip_2_8_pesp.json"))
    assert r"\mathcal{E}" in tex
    assert r"\sum_" in tex
    assert r"\forall" in tex


def test_determinism():
    """Parsing the same text twice yields identical models."""
    f = load("formulations/constraints/assignment.json")
    tex = to_canonical_latex(f)
    a = from_canonical_latex(tex)
    b = from_canonical_latex(tex)
    assert a == b


def test_parse_reconstructs_symbols():
    f = load("formulations/constraints/mip_2_1_big_m.json")
    g = from_canonical_latex(to_canonical_latex(f))
    assert {v.name for v in g.variables} == {v.name for v in f.variables}
    assert {p.name for p in g.parameters} == {p.name for p in f.parameters}
    assert {c.name for c in g.constraints} == {c.name for c in f.constraints}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
