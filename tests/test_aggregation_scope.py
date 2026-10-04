"""One reading of an aggregation's loops, shared by emitter, ground view and grounder.

Regression tests for issue #60 (the grounder ignored ``operator_over``) and for
the defects found with it: the ground view dropped every summed term and wired
pair variables to the diagonal, the emitter printed unparseable or re-bound
binders and dropped the binder of a summed constant, and the hybrid view lost
one of two same-family bindings. Issue #61 (a where-predicate parameter had no
edge) is covered at the end.
"""

from __future__ import annotations

import pytest

from lp2graph import from_canonical_latex, to_canonical_latex
from lp2graph.core.model import Binding, Term
from lp2graph.core.scope import (
    AggregationError,
    Loop,
    aggregation_loops,
    binder_loops,
    binding_base,
)
from lp2graph.views import ground, hybrid, schema

_HEADER = r"""%@ meta id=scope_probe family=milp schema=0.1.0
%@ name :: scope probe
%@ index I ordered=0 cyclic=0 :: trains
%@ index J ordered=0 cyclic=0 :: slots
%@ index R ordered=1 cyclic=0 :: resources
%@ index T ordered=1 cyclic=0 :: periods
%@ param dur shape=R kind=vector domain=- :: durations
%@ param first shape=R kind=vector domain=- :: 1 iff the first resource
%@ var x shape=I,J domain=binary role=primary drole=- lo=- hi=- :: assignment
%@ var y shape=I,I domain=binary role=primary drole=- lo=- hi=- :: order
%@ var z shape=I domain=non_negative role=primary drole=- lo=- hi=- :: slack
%@ var u shape=T domain=non_negative role=primary drole=- lo=- hi=- :: level
%@ var t shape=I,R domain=non_negative role=primary drole=- lo=- hi=- :: times
%@ obj sense=min name=o combination=sum :: o
"""


def _doc(objective: str, *rows: tuple[str, str]) -> str:
    lines = [_HEADER.rstrip("\n")]
    lines += [f"%@ con {name} kind=linear domain=- indicator=- :: {name}" for name, _ in rows]
    lines.append(r"\begin{align}")
    lines.append(rf"  \min\quad & {objective} \tag{{o}} \\")
    lines += [rf"  & {row} \tag{{{name}}} \\" for name, row in rows]
    lines.append(r"\end{align}")
    return "\n".join(lines) + "\n"


def _term(*bindings: tuple[str, str], over: tuple[str, ...] = (), op: str = "sum") -> Term:
    return Term(
        ref="v",
        bindings=tuple(Binding(index=fam, expr=expr) for fam, expr in bindings),
        role="lhs",
        operator=op,  # type: ignore[arg-type]
        operator_over=over,
    )


# --- core.scope ---------------------------------------------------------------


def test_binding_base_strips_offsets() -> None:
    assert binding_base("t-1") == "t"
    assert binding_base(" tp + 2 ") == "tp"


def test_family_without_dummy_is_a_counting_loop() -> None:
    t = _term(("R", "r"), over=("I", "R"))
    assert aggregation_loops(t, ()) == (Loop("R", "r"), Loop("I", None))
    assert binder_loops(t, ()) == (Loop("I", None), Loop("R", "r"))


def test_same_family_dummy_bound_by_the_row_is_not_rebound() -> None:
    # \sum_{j \in I} y_{i,j} under \forall i \in I: the binder takes j, not i.
    t = _term(("I", "i"), ("I", "j"), over=("I",))
    assert aggregation_loops(t, {"i"}) == (Loop("I", "j"),)
    assert binder_loops(t, {"i"}) == (Loop("I", "j"),)


def test_offset_binding_loops_over_its_base() -> None:
    t = _term(("T", "t-1"), over=("T",))
    assert aggregation_loops(t, ()) == (Loop("T", "t"),)


def test_free_dummy_without_operator_over_is_summed() -> None:
    # abs terms (and sums from models written before operator_over existed).
    t = _term(("I", "i"), op="abs")
    assert aggregation_loops(t, ()) == (Loop("I", "i"),)


def test_binder_and_shape_disagreeing_is_refused_for_evaluation() -> None:
    # \sum_{k \in K} v_{k} with v declared over I.
    t = _term(("I", "k"), over=("K",))
    with pytest.raises(AggregationError, match="do not pair"):
        aggregation_loops(t, ())
    # ... while the emitter reproduces the binder as written.
    assert binder_loops(t, ()) == (Loop("K", "k"),)


# --- solver back-end (issue #60) ------------------------------------------------


def test_sum_over_a_family_the_referent_does_not_use_scales() -> None:
    pytest.importorskip("pulp")
    from lp2graph.solve import Instance, solve

    f = from_canonical_latex(
        _doc(
            r"\sum_{i \in \mathcal{I}} z_{i} + \sum_{i \in \mathcal{I}, r \in \mathcal{R}} "
            r"\mathit{dur}_{r}",
            ("c", r"z_{i} \ge 0 \qquad \forall i \in \mathcal{I}"),
        )
    )
    cards = {"I": 0, "J": 1, "R": 2, "T": 1}
    params = {"dur": [1, 1], "first": [1, 0]}
    for n in (1, 2, 3):
        cards["I"] = n
        result = solve(f, Instance(cardinalities=cards, parameters=params), solver="cbc")
        assert result.objective == pytest.approx(2.0 * n)


def test_summed_constant_counts_the_elements() -> None:
    pytest.importorskip("pulp")
    from lp2graph.solve import Instance, solve

    f = from_canonical_latex(
        _doc(
            r"\sum_{i \in \mathcal{I}} z_{i} + \sum_{i \in \mathcal{I}} 5",
            ("c", r"z_{i} \ge 0 \qquad \forall i \in \mathcal{I}"),
        )
    )
    cards = {"I": 3, "J": 1, "R": 1, "T": 1}
    result = solve(f, Instance(cardinalities=cards, parameters={"dur": [1], "first": [1]}))
    assert result.objective == pytest.approx(15.0)


# --- ground view ----------------------------------------------------------------


def _assignment():
    return from_canonical_latex(
        _doc(
            r"\sum_{i \in \mathcal{I}, j \in \mathcal{J}} x_{i,j}",
            ("assign", r"\sum_{j \in \mathcal{J}} x_{i,j} = 1 \qquad \forall i \in \mathcal{I}"),
            (
                "pair",
                r"y_{i,j} + y_{j,i} = 1 \qquad \forall i \in \mathcal{I},\; "
                r"\forall j \in \mathcal{I},\; i \neq j",
            ),
        )
    )


def _cards(**over: int) -> dict[str, int]:
    return {"I": 2, "J": 3, "R": 1, "T": 1, **over}


def test_ground_view_expands_summed_terms() -> None:
    g = ground(_assignment(), _cards())
    by_src: dict[str, list[str]] = {}
    for e in g.edges:
        by_src.setdefault(e.src, []).append(e.dst)
    assert by_src["cinst:assign_i0"] == ["varinst:x_I0_J0", "varinst:x_I0_J1", "varinst:x_I0_J2"]
    assert by_src["cinst:assign_i1"] == ["varinst:x_I1_J0", "varinst:x_I1_J1", "varinst:x_I1_J2"]
    assert len(by_src["objinst:0"]) == 6


def test_ground_view_reaches_off_diagonal_pair_instances() -> None:
    g = ground(_assignment(), _cards())
    targets = [e.dst for e in g.edges if e.src == "cinst:pair_i0_j1"]
    assert targets == ["varinst:y_I0_I1", "varinst:y_I1_I0"]


def test_ground_view_counts_a_repeated_summand_once_with_multiplicity() -> None:
    f = from_canonical_latex(
        _doc(
            r"\sum_{i \in \mathcal{I}, t \in \mathcal{T}} u_{t}",
            ("c", r"u_{t} \ge 0 \qquad \forall t \in \mathcal{T}"),
        )
    )
    g = ground(f, _cards(I=3, T=2))
    obj = [e for e in g.edges if e.src == "objinst:0"]
    assert [e.dst for e in obj] == ["varinst:u_T0", "varinst:u_T1"]
    assert all(e.data["multiplicity"] == 3 for e in obj)


def test_ground_view_aggregates_abs_like_the_grounder() -> None:
    f = from_canonical_latex(
        _doc(
            r"\left| z_{i} \right|",
            ("c", r"z_{i} \ge 0 \qquad \forall i \in \mathcal{I}"),
        )
    )
    g = ground(f, _cards(I=3))
    assert [e.dst for e in g.edges if e.src == "objinst:0"] == [
        "varinst:z_I0",
        "varinst:z_I1",
        "varinst:z_I2",
    ]


# --- emitter --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("objective", "row", "expected"),
    [
        # A windowed sum is summed over the dummy, not over the offset expression.
        (r"\sum_{t \in \mathcal{T}} u_{t-1}", "", r"\sum_{t \in \mathcal{T}} u_{t-1}"),
        # A summed constant keeps its binder.
        (r"\sum_{i \in \mathcal{I}} 5", "", r"\sum_{i \in \mathcal{I}} 5"),
        # The row's quantifier binds i; the binder's j is printed as j.
        (
            r"\sum_{i \in \mathcal{I}} z_{i}",
            r"\sum_{j \in \mathcal{I}} y_{i,j} \le 1 \qquad \forall i \in \mathcal{I}",
            r"\sum_{j \in \mathcal{I}} y_{i,j} \le 1",
        ),
        # A counting loop over I inside a row bound by i gets a fresh dummy.
        (
            r"\sum_{i \in \mathcal{I}} z_{i}",
            r"z_{i} - \sum_{j \in \mathcal{I}, t \in \mathcal{T}} u_{t} \ge 0 "
            r"\qquad \forall i \in \mathcal{I}",
            r"\sum_{ip \in \mathcal{I}, t \in \mathcal{T}} u_{t}",
        ),
    ],
)
def test_emitter_binders_round_trip(objective: str, row: str, expected: str) -> None:
    rows = [("r", row)] if row else [("r", r"z_{i} \ge 0 \qquad \forall i \in \mathcal{I}")]
    f = from_canonical_latex(_doc(objective, *rows))
    text = to_canonical_latex(f)
    assert expected in text
    again = from_canonical_latex(text)
    assert again == f
    assert to_canonical_latex(again) == text


# --- schema / hybrid views (issue #61) ------------------------------------------


def _where_model():
    return from_canonical_latex(
        _doc(
            r"\sum_{i \in \mathcal{I}, r \in \mathcal{R}} t_{i,r}",
            (
                "start",
                r"t_{i,r} \le 0 \qquad \forall i \in \mathcal{I},\; "
                r"\forall r \in \mathcal{R},\; \mathit{first}_{r} = 1",
            ),
        )
    )


def test_where_predicate_parameter_is_an_edge_in_the_schema_view() -> None:
    g = schema(_where_model())
    where = [e for e in g.edges if e.role == "where"]
    assert [(e.src, e.dst, e.type, e.label) for e in where] == [
        ("constraint:start", "param:first", "uses_parameter", "where[r]")
    ]


def test_where_predicate_edge_carries_the_value_in_the_hybrid_view() -> None:
    g = hybrid(_where_model())
    (edge,) = [e for e in g.edges if e.role == "where"]
    assert edge.label == "where[r] = 1"
    assert edge.data["equals"] == 1


def test_hybrid_view_keeps_both_same_family_bindings() -> None:
    g = hybrid(_assignment())
    offsets = [e.data["offsets"] for e in g.edges if e.src == "constraint:pair"]
    assert [{k: v["expr"] for k, v in o.items()} for o in offsets] == [
        {"I.1": "i", "I.2": "j"},
        {"I.1": "j", "I.2": "i"},
    ]
