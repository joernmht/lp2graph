"""Export adapter tests."""

from __future__ import annotations

import pytest

from lp2graph import load
from lp2graph.export.latex import to_latex
from lp2graph.export.pyomo_stub import to_pyomo_stub
from lp2graph.views import schema


def test_to_networkx_round_trip() -> None:
    nx = pytest.importorskip("networkx")
    from lp2graph.export.networkx_adapter import to_networkx

    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    g = schema(f)
    nxg = to_networkx(g)
    assert isinstance(nxg, nx.MultiDiGraph)
    assert nxg.number_of_nodes() == len(g.nodes)
    assert nxg.number_of_edges() == len(g.edges)


def test_to_latex_emits_align_block() -> None:
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    out = to_latex(f)
    assert r"\begin{align*}" in out
    assert r"\end{align*}" in out
    assert r"\min" in out
    assert r"\sum" in out


def test_to_latex_handles_quantifier_restriction() -> None:
    f = load("formulations/constraints/mip_2_1_big_m.json")
    out = to_latex(f)
    assert r"\forall" in out
    assert r"\ne" in out


def test_to_pyomo_stub_emits_skeleton() -> None:
    f = load("formulations/constraints/mip_2_4_time_indexed.json")
    out = to_pyomo_stub(f)
    assert "ConcreteModel" in out
    assert "m.x = Var(m.I, m.T, domain=Binary" in out
    assert "Constraint(rule=_exactly_one_slot_rule" in out
    assert "Objective(rule=_obj_rule, sense=minimize)" in out
