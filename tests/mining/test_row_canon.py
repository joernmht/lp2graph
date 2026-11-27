"""Structural row canonicalizer (M1b rules ``row_exact`` / ``row_widened``).

The reader restructures a row only when it can prove the row is a linear
relation over declared symbols; these tests pin the identities it applies,
the two recorded departures from exactness (derived parameters, widening)
and, above all, what it must leave untouched.
"""

from __future__ import annotations

from lp2graph.codec import to_canonical_latex
from lp2graph.mining.ingest import ingest_latex, normalize_latex
from lp2graph.mining.ingest.result import IngestionResult
from lp2graph.mining.ingest.row_canon import outline_row, scan_symbols

_HEADER = """%@ meta id=t family=milp schema=0.1.0
%@ name :: t
%@ index I ordered=0 cyclic=0 :: i
%@ index J ordered=0 cyclic=0 :: j
%@ index T ordered=1 cyclic=0 :: t
%@ param M shape=- kind=big_m domain=- :: M
%@ param c shape=I kind=vector domain=- :: c
%@ param w shape=- kind=scalar domain=- :: w
%@ param d shape=I,J kind=matrix domain=- :: d
%@ param H shape=- kind=scalar domain=- :: H
%@ var x shape=I,J domain=binary role=primary drole=- lo=- hi=- :: x
%@ var y shape=I domain=continuous role=primary drole=- lo=- hi=- :: y
%@ var f shape=I,T domain=continuous role=primary drole=- lo=- hi=- :: f
%@ var z shape=- domain=continuous role=primary drole=- lo=- hi=- :: z
%@ obj sense=min name=objective combination=sum :: o
"""
_OBJ = r"  \min\quad & z \tag{objective} \\"


def _doc(*rows: str, objective: str = _OBJ, header: str = _HEADER) -> str:
    return header + "\\begin{align}\n" + "\n".join([objective, *rows]) + "\n\\end{align}\n"


def _ingest(*rows: str, objective: str = _OBJ, header: str = _HEADER) -> IngestionResult:
    return ingest_latex(_doc(*rows, objective=objective, header=header), source="t.tex")


def _fired(r: IngestionResult) -> set[str]:
    return {rw.rule for rw in r.provenance.rewrites}


def _terms(r: IngestionResult, name: str, side: str) -> list[tuple]:
    (c,) = [c for c in r.formulation.constraints if c.name == name]
    return [
        (t.sign, t.coefficient, t.ref, tuple(b.expr for b in t.bindings), t.operator_over)
        for t in getattr(c, side)
    ]


def test_product_distributes_over_a_nested_parenthesised_sum():
    r = _ingest(
        r"  & y_{i} - y_{k} \leq M \left(1 - \left(x_{i j} - x_{k j}\right)\right)"
        r" \forall i \in I, k \in I, j \in J \tag{r} \\"
    )
    assert r.ok, r.failures
    assert _terms(r, "r", "rhs") == [
        (1, 1, "M", (), ()),
        (-1, "M", "x", ("i", "j"), ()),
        (1, "M", "x", ("k", "j"), ()),
    ]
    assert "row_exact" in _fired(r) and "row_widened" not in _fired(r)


def test_sum_of_a_sum_splits_and_outer_factor_moves_inside():
    r = _ingest(
        r"  & c_{i} \sum_{j \in J} \left(x_{i j} + 2 x_{i j}\right) \le H \forall i \in I \tag{r} \\"
    )
    assert r.ok, r.failures
    assert _terms(r, "r", "lhs") == [
        (1, "c", "x", ("i", "j"), ("J",)),
        (1, "n2_x_c", "x", ("i", "j"), ("J",)),
    ]


def test_products_and_ratios_of_parameters_become_derived_parameters():
    r = _ingest(
        r"  & y_{i} \ge \frac{d_{i j}}{H} x_{i j} \forall i \in I, j \in J \tag{r} \\",
        objective=r"  \min\quad & w \sum_{i \in I} c_{i} y_{i} + (1 - w) z \tag{objective} \\",
    )
    assert r.ok, r.failures
    params = {p.name: p for p in r.formulation.parameters}
    assert params["w_x_c"].shape == ("I",) and params["d_over_H"].shape == ("I", "J")
    assert params["w_x_c"].description == "derived: w * c"
    obj = [(t.sign, t.coefficient, t.ref) for t in r.formulation.objective.terms]
    assert obj == [(1, "w_x_c", "y"), (1, 1, "z"), (-1, "w", "z")]
    lines = [rw.after for rw in r.provenance.rewrites if rw.rule == "derived_parameter"]
    assert len(lines) == 2 and all(ln.startswith("%@ param ") for ln in lines)
    # the canonical document carries the derived parameters and reads back
    again = ingest_latex(to_canonical_latex(r.formulation), source="again.tex")
    assert again.ok and again.formulation == r.formulation


def test_a_denominator_that_is_a_sum_of_parameters_is_one_derived_parameter():
    r = _ingest(objective=r"  \min\quad & w \frac{z - H}{M - H} \tag{objective} \\")
    assert r.ok, r.failures
    names = {p.name for p in r.formulation.parameters}
    assert {"sum_p_M_m_H", "w_over_sum_p_M_m_H", "w_x_H_over_sum_p_M_m_H"} <= names


def test_rows_outside_the_linear_model_are_left_for_the_parser():
    for row, needle in (
        (r"  & x_{i j} y_{i} \le 1 \forall i \in I, j \in J \tag{r} \\", "trailing"),
        (r"  & y_{i}^{2} \le 1 \forall i \in I \tag{r} \\", "not a declared"),
        (r"  & q_{i} \le 1 \forall i \in I \tag{r} \\", "not a declared"),
        (r"  & y_{i} \le H , z \ge 1 \forall i \in I \tag{r} \\", ""),
    ):
        r = _ingest(row)
        assert not r.ok, row
        assert needle in r.failures[0].message, (row, r.failures[0].message)
        _text, prov = normalize_latex(_doc(row), source="t.tex")
        assert not {rw.rule for rw in prov.rewrites} & {"row_exact", "row_widened"}, row


def test_widening_is_its_own_rule_and_keeps_exact_restrictions():
    r = _ingest(
        r"  & y_{i} \le H \forall i \in I \setminus \{1\}, k \in I, i \neq k \tag{a} \\",
        r"  & \sum_{j = 1}^{n} x_{i j} \le 1 \forall i \in I \tag{b} \\",
        r"  & y_{i} \le c_{i} \forall i \in I : c_{i} \ge H \tag{c} \\",
    )
    assert r.ok, r.failures
    a, b, c = r.formulation.constraints
    assert [(q.index, q.over, q.restriction, q.restriction_other) for q in a.quantifiers] == [
        ("i", "I", "ne_other", "k"),
        ("k", "I", "none", None),
    ]
    assert b.lhs[0].operator_over == ("J",)
    assert [(q.index, q.over) for q in c.quantifiers] == [("i", "I")]
    assert "row_widened" in _fired(r)


def test_a_tail_condition_about_a_variable_is_never_dropped():
    r = _ingest(r"  & y_{i} \le H \forall i \in I : z \ge 1 \tag{r} \\")
    assert not r.ok
    assert "row_widened" not in {
        rw.rule
        for rw in normalize_latex(
            _doc(r"  & y_{i} \le H \forall i \in I : z \ge 1 \tag{r} \\"), source="t"
        )[1].rewrites
    }


def test_widening_that_would_merge_two_sums_is_refused():
    # in-arcs minus out-arcs: widened to the base family both sums are the
    # same term and the row a tautology
    row = (
        r"  & \sum_{j \in J_{i}^{+}} x_{i j} - \sum_{j \in J_{i}^{-}} x_{i j} = 0"
        r" \forall i \in I \tag{r} \\"
    )
    _text, prov = normalize_latex(_doc(row), source="t.tex")
    assert "row_widened" not in {rw.rule for rw in prov.rewrites}


def test_an_index_letter_used_as_a_number_is_the_value_parameter_of_its_family():
    r = _ingest(r"  & y_{i} = \sum_{t \in T} t \cdot f_{i t} \forall i \in I \tag{r} \\")
    assert r.ok, r.failures
    assert _terms(r, "r", "rhs") == [(1, "val_T", "f", ("i", "t"), ("T",))]
    assert {p.name: p.shape for p in r.formulation.parameters}["val_T"] == ("T",)


def test_header_letters_make_unbound_scripts_indices():
    header = _HEADER + "%@ letter i over=I :: index letter\n%@ letter j over=J :: index letter\n"
    r = _ingest(r"  & x_{i}^{j} \le 1 \tag{r} \\", header=header)
    assert r.ok, r.failures
    assert _terms(r, "r", "lhs") == [(1, 1, "x", ("i", "j"), ())]
    (c,) = r.formulation.constraints
    assert [(q.index, q.over) for q in c.quantifiers] == [("i", "I"), ("j", "J")]


def test_label_words_are_never_split_into_index_letters():
    header = _HEADER.replace("%@ param H shape=-", "%@ param H_min shape=-") + (
        "%@ letter m over=I :: l\n%@ letter i over=I :: l\n%@ letter n over=I :: l\n"
    )
    r = _ingest(r"  & y_{i} \ge H_{min} \tag{r} \\", header=header)
    assert r.ok, r.failures
    assert _terms(r, "r", "rhs") == [(1, 1, "H_min", (), ())]


def test_canonical_documents_are_a_fixed_point():
    r = _ingest(
        r"  & y_{i} - y_{k} \leq M \left(1 - x_{i j}\right) \forall i \in I, k \in I, j \in J \tag{r} \\",
        objective=r"  \min\quad & w \sum_{i \in I} c_{i} y_{i} \tag{objective} \\",
    )
    assert r.ok, r.failures
    canonical = to_canonical_latex(r.formulation)
    text, prov = normalize_latex(canonical, source="c.tex")
    assert text.split() == canonical.split()
    assert {rw.rule for rw in prov.rewrites} <= {"collapse_ws"}


def test_scan_and_outline_read_a_row_without_interpreting_it():
    row = r"& \sum_{j \in \mathcal{J}} d_{i,j} \cdot x_{i j}^{k} - t_arr_{i+1} \le M \qquad \forall i \in \mathcal{I}"
    uses = scan_symbols(row)
    assert [(u.name, u.pieces, u.sup, u.multiplies) for u in uses if not u.in_tail] == [
        ("d", ("i", "j"), None, "x"),
        ("x", ("i", "j"), "k", None),
        ("t_arr", ("i+1",), None, None),
        ("M", (), None, None),
    ]
    o = outline_row(r"u_{i} = \sum_{j \in \mathcal{J}} x_{i,j} , i \in I", frozenset({"u", "x"}))
    assert o is not None and o.comparators == ("eq",) and o.alone == (True, False)
    assert [u.name for u in o.sides[1]] == ["x"]


def test_an_absolute_value_bound_is_the_two_sided_chain():
    r = _ingest(r"  & \left| y_{i} - c_{i} \right| \le H \forall i \in I \tag{r} \\")
    assert r.ok, r.failures
    assert [(c.name, c.comparator) for c in r.formulation.constraints] == [
        ("r_lo", "le"),
        ("r_up", "le"),
    ]
    lo, up = r.formulation.constraints
    assert [(t.sign, t.ref) for t in lo.lhs] == [(-1, "H")]
    assert [(t.sign, t.ref) for t in lo.rhs] == [(1, "y"), (-1, "c")]
    assert [(t.sign, t.ref) for t in up.rhs] == [(1, "H")]
    # anywhere else an absolute value has no linear spelling and is refused
    for row in (
        r"  & \left| y_{i} - c_{i} \right| \ge H \forall i \in I \tag{r} \\",
        r"  & z + \left| y_{i} \right| \le H \forall i \in I \tag{r} \\",
    ):
        _text, prov = normalize_latex(_doc(row), source="t.tex")
        assert not {rw.rule for rw in prov.rewrites} & {"row_exact", "row_widened"}, row


def test_a_coefficient_the_term_cannot_index_becomes_a_parameter_over_the_referent():
    # t_{k-1} x_{i,k}: the canonical coefficient is a bare name whose indices
    # are implied; an offset (or two letters of one family) has no such reading
    header = _HEADER + "%@ param tm shape=T kind=vector domain=- :: times\n"
    r = _ingest(
        r"  & \sum_{t \in T} tm_{t - 1} f_{i t} \le H \forall i \in I \tag{r} \\", header=header
    )
    assert r.ok, r.failures
    assert _terms(r, "r", "lhs") == [(1, "tm_tm1_on_f", "f", ("i", "t"), ("T",))]
    assert {p.name: p.shape for p in r.formulation.parameters}["tm_tm1_on_f"] == ("I", "T")
    # the plain case keeps the paper's own parameter
    r = _ingest(
        r"  & \sum_{j \in J} d_{i j} x_{i j} \le c_{i} \cdot y_{i} \forall i \in I \tag{r} \\"
    )
    assert r.ok, r.failures
    assert _terms(r, "r", "lhs") == [(1, "d", "x", ("i", "j"), ("J",))]
    assert _terms(r, "r", "rhs") == [(1, "c", "y", ("i",), ())]


def test_extrema_bounding_from_the_convex_side_are_conjunctions():
    r = _ingest(
        r"  & \max \left\{ y_{i} , c_{i} \right\} \le z \forall i \in I \tag{a} \\",
        r"  & z \le \min \left( y_{i} , H \right) \forall i \in I \tag{b} \\",
        r"  & \max_{j \in J} d_{i j} x_{i j} \le y_{i} \forall i \in I \tag{c} \\",
    )
    assert r.ok, r.failures
    got = [
        (c.name, c.comparator, [t.ref for t in c.lhs], [t.ref for t in c.rhs])
        for c in r.formulation.constraints
    ]
    assert got == [
        ("a_1", "le", ["y"], ["z"]),
        ("a_2", "ge", ["z"], ["c"]),
        ("b_1", "ge", ["y"], ["z"]),
        ("b_2", "le", ["z"], ["H"]),
        ("c", "le", ["x"], ["y"]),
    ]
    (c,) = [c for c in r.formulation.constraints if c.name == "c"]
    assert [(q.index, q.over) for q in c.quantifiers] == [("i", "I"), ("j", "J")]
    # the non-convex side has no linear spelling
    row = r"  & z = \max \left\{ y_{i} , c_{i} \right\} \forall i \in I \tag{a} \\"
    _text, prov = normalize_latex(_doc(row), source="t.tex")
    assert not {rw.rule for rw in prov.rewrites} & {"row_exact", "row_widened"}


def test_a_minimised_deviation_becomes_an_explicit_auxiliary_variable():
    r = _ingest(
        objective=r"  \min\quad & \sum_{i \in I} c_{i} \left| y_{i} - H \right| + z \tag{objective} \\"
    )
    assert r.ok, r.failures
    aux = {v.name: v for v in r.formulation.variables}["aux_objective_1"]
    assert (aux.shape, aux.domain, aux.role) == (("I",), "non_negative", "auxiliary")
    assert [(t.sign, t.coefficient, t.ref) for t in r.formulation.objective.terms] == [
        (1, "c", "aux_objective_1"),
        (1, 1, "z"),
    ]
    rows = {c.name: c for c in r.formulation.constraints}
    assert set(rows) == {"objective_aux1_1", "objective_aux1_2"}
    up = rows["objective_aux1_1"]
    assert up.comparator == "ge" and [(t.sign, t.ref) for t in up.rhs] == [(1, "y"), (-1, "H")]
    assert [(q.index, q.over) for q in up.quantifiers] == [("i", "I")]
    lo = rows["objective_aux1_2"]
    assert [(t.sign, t.ref) for t in lo.rhs] == [(-1, "y"), (1, "H")]
    fired = _fired(r)
    assert "derived_variable" in fired
    # the canonical document reads back unchanged
    again = ingest_latex(to_canonical_latex(r.formulation), source="again.tex")
    assert again.ok and again.formulation == r.formulation


def test_min_max_objective_and_the_non_convex_direction():
    r = _ingest(objective=r"  \min\quad & \max_{i \in I} y_{i} \tag{objective} \\")
    assert r.ok, r.failures
    (row,) = r.formulation.constraints
    assert row.comparator == "ge" and [t.ref for t in row.lhs] == ["aux_objective_1"]
    assert [(q.index, q.over) for q in row.quantifiers] == [("i", "I")]
    # maximising a maximum is not a linear program
    r = _ingest(objective=r"  \max\quad & \max_{i \in I} y_{i} \tag{objective} \\")
    assert not r.ok
