"""Tests for the grounding solver back-end and the full text->solve pipeline."""

from __future__ import annotations

import json
import math

import pytest

from lp2graph import from_canonical_latex, load, to_canonical_latex

pulp = pytest.importorskip("pulp")
from lp2graph.solve import Instance, solve  # noqa: E402


def _spec(path):
    data = json.loads(path.read_text())
    f = load(path.parents[4] / data["formulation"])
    inst = Instance(cardinalities=data["cardinalities"], parameters=data["parameters"])
    return f, inst, data["expected_optimum"]


def test_matches_known_optimum(instance_files):
    for ip in instance_files:
        f, inst, expected = _spec(ip)
        obj = solve(f, inst).objective
        assert obj is not None and math.isclose(obj, expected, abs_tol=1e-4), ip.name


def test_pipeline_equals_direct(instance_files):
    """Solving the model reconstructed from LaTeX equals solving the JSON."""
    for ip in instance_files:
        f, inst, _ = _spec(ip)
        g = from_canonical_latex(to_canonical_latex(f))
        assert math.isclose(solve(f, inst).objective, solve(g, inst).objective, abs_tol=1e-6), (
            ip.name
        )


def test_cross_solver_agreement(instance_files):
    from lp2graph.solve import default_solver

    f, inst, expected = _spec(next(p for p in instance_files if p.stem == "assignment_4x4"))
    cbc = solve(f, inst, solver=default_solver(msg=False)).objective
    highs = solve(f, inst, solver=pulp.HiGHS(msg=False)).objective
    assert math.isclose(cbc, highs, abs_tol=1e-6)
    assert math.isclose(cbc, expected, abs_tol=1e-4)


def test_make_solver_and_solve_by_name(instance_files):
    """The library exposes the CBC/HiGHS/Gurobi back-end by name, and
    `solve()` accepts a solver name string — agreeing across installed
    back-ends."""
    from lp2graph.solve import available_solvers, make_solver

    assert "cbc" in available_solvers()  # CBC ships with pulp
    assert isinstance(make_solver("highs"), pulp.LpSolver)

    f, inst, expected = _spec(next(p for p in instance_files if p.stem == "assignment_4x4"))
    objs = [solve(f, inst, solver=name).objective for name in available_solvers()]
    assert all(math.isclose(o, expected, abs_tol=1e-4) for o in objs)
    assert all(math.isclose(o, objs[0], abs_tol=1e-6) for o in objs)


def test_make_solver_rejects_unknown():
    from lp2graph.solve import make_solver

    with pytest.raises(ValueError, match="unknown solver"):
        make_solver("clp")


def test_offset_constraints_skipped_at_boundary():
    """A `t_{i-1}` term at i=0 must drop the whole headway instance, not
    degrade it to `t_0 >= h`."""
    f = load("formulations/constraints/lp_1_1_fixed_sequence.json")
    inst = Instance(
        cardinalities={"I": 3}, parameters={"h": 2, "r": [1, 1, 1], "earliest": [0, 0, 0]}
    )
    res = solve(f, inst)
    assert math.isclose(res.objective, 6.0, abs_tol=1e-6)  # 0 + 2 + 4


def test_unsupported_operator_raises():
    from lp2graph.core.model import Formulation
    from lp2graph.solve import UnsupportedModel

    f = Formulation.model_validate(
        {
            **_ABS_PROBE,
            "objective": {
                "sense": "min",
                "terms": [
                    {
                        "ref": "t",
                        "ref_kind": "variable",
                        "bindings": [{"index": "I", "expr": "i"}],
                        "operator": "max",
                        "role": "objective",
                    }
                ],
            },
        }
    )
    with pytest.raises(UnsupportedModel, match="max"):
        solve(f, Instance(cardinalities={"I": 2}, parameters={"target": [0, 0]}))


# --------------------------------------------------------------------------- #
# abs terms (epigraph lifting)
# --------------------------------------------------------------------------- #

#: ``min/max sign*sum_i |t_i|`` over free ``t`` under ``t_i <cmp> target_i``.
#: The bound is what stops the magnitude collapsing to zero, so the optimum
#: is a hand-computable function of ``target`` and the lifting is actually
#: exercised rather than trivially satisfied.
_ABS_PROBE = {
    "schema_version": "0.1.0",
    "id": "abs_probe",
    "name": "abs probe",
    "family": "lp",
    "indices": [{"name": "I"}],
    "parameters": [{"name": "target", "shape": ["I"], "kind": "vector"}],
    "variables": [{"name": "t", "shape": ["I"], "domain": "continuous"}],
    "constraints": [
        {
            "name": "floor",
            "kind": "linear",
            "quantifiers": [{"index": "i", "over": "I"}],
            "comparator": "ge",
            "lhs": [
                {
                    "ref": "t",
                    "ref_kind": "variable",
                    "bindings": [{"index": "I", "expr": "i"}],
                    "role": "lhs",
                }
            ],
            "rhs": [
                {
                    "ref": "target",
                    "ref_kind": "parameter",
                    "bindings": [{"index": "I", "expr": "i"}],
                    "role": "rhs",
                }
            ],
        }
    ],
}


def _abs_probe(sense="min", sign=1, comparator="ge"):
    from lp2graph.core.model import Formulation

    spec = json.loads(json.dumps(_ABS_PROBE))  # deep copy
    spec["constraints"][0]["comparator"] = comparator
    spec["objective"] = {
        "sense": sense,
        "name": "l1",
        "terms": [
            {
                "ref": "t",
                "ref_kind": "variable",
                "bindings": [{"index": "I", "expr": "i"}],
                "operator": "abs",
                "sign": sign,
                "role": "objective",
            }
        ],
    }
    return Formulation.model_validate(spec)


@pytest.mark.parametrize(
    ("comparator", "expected"),
    [("ge", 6.0), ("le", 5.0)],  # sum max(target,0) / sum max(-target,0)
)
def test_abs_term_is_lifted_exactly(comparator, expected):
    """``|t_i|`` aggregates over the free index like ``\\sum`` and hits the
    hand-computed L1 optimum, so the epigraph auxiliaries are pinned down."""
    inst = Instance(cardinalities={"I": 3}, parameters={"target": [2.0, -5.0, 4.0]})
    res = solve(_abs_probe(comparator=comparator), inst)
    assert res.status == "optimal"
    assert math.isclose(res.objective, expected, abs_tol=1e-6)


@pytest.mark.parametrize(("sense", "sign"), [("max", 1), ("min", -1)])
def test_abs_lifting_refused_where_inexact(sense, sign):
    """A maximized (or negatively signed) magnitude would let the auxiliary
    float free of ``|e|``; the grounder must refuse, not solve a laxer model."""
    from lp2graph.solve import UnsupportedModel

    inst = Instance(cardinalities={"I": 3}, parameters={"target": [2.0, -5.0, 4.0]})
    with pytest.raises(UnsupportedModel, match="sign"):
        solve(_abs_probe(sense=sense, sign=sign), inst)


def test_abs_in_equality_refused():
    from lp2graph.core.model import Formulation
    from lp2graph.solve import UnsupportedModel

    spec = json.loads(json.dumps(_ABS_PROBE))
    spec["constraints"][0]["comparator"] = "eq"
    spec["constraints"][0]["lhs"][0]["operator"] = "abs"
    spec["objective"] = {"sense": "min", "terms": []}
    inst = Instance(cardinalities={"I": 2}, parameters={"target": [1.0, 1.0]})
    with pytest.raises(UnsupportedModel, match="no exact linearization"):
        solve(Formulation.model_validate(spec), inst)


# --------------------------------------------------------------------------- #
# lexicographic objectives (staged solve)
# --------------------------------------------------------------------------- #


def _lex_model(order):
    """``c_i + t_i >= 1``, both non-negative, priorities in ``order``.

    Whichever family is optimized first is driven to 0 and the other
    absorbs the whole requirement, so the two orders give (0, n) and
    (0, n) on *different* terms: the result discriminates the ordering.
    """
    from lp2graph.core.model import Formulation

    terms = {
        name: {
            "ref": name,
            "ref_kind": "variable",
            "bindings": [{"index": "I", "expr": "i"}],
            "operator": "sum",
            "operator_over": ["I"],
            "role": "objective",
        }
        for name in ("c", "t")
    }
    return Formulation.model_validate(
        {
            "schema_version": "0.1.0",
            "id": "lex_probe",
            "name": "lex probe",
            "family": "lp",
            "indices": [{"name": "I"}],
            "variables": [
                {"name": "c", "shape": ["I"], "domain": "non_negative"},
                {"name": "t", "shape": ["I"], "domain": "non_negative"},
            ],
            "constraints": [
                {
                    "name": "cover",
                    "kind": "linear",
                    "quantifiers": [{"index": "i", "over": "I"}],
                    "comparator": "ge",
                    "lhs": [
                        {
                            "ref": n,
                            "ref_kind": "variable",
                            "bindings": [{"index": "I", "expr": "i"}],
                            "role": "lhs",
                        }
                        for n in ("c", "t")
                    ],
                    "rhs": [{"constant": 1, "role": "rhs"}],
                }
            ],
            "objective": {
                "sense": "min",
                "name": "lex",
                "combination": "lexicographic",
                "terms": [terms[n] for n in order],
            },
        }
    )


def test_lexicographic_respects_priority_order():
    from lp2graph.solve import solve_lexicographic

    inst = Instance(cardinalities={"I": 4}, parameters={})
    first = solve_lexicographic(_lex_model(("c", "t")), inst, solver="cbc")
    assert first.status == "optimal"
    # top priority sum(c) driven to 0; sum(t) then must cover all four rows
    assert first.objectives == pytest.approx((0.0, 4.0))
    # the achieved top-priority value is genuinely held (up to the fix tolerance),
    # not silently re-optimized away by the second stage
    assert sum(v for k, v in first.variables.items() if k.startswith("c_")) == pytest.approx(
        0.0, abs=1e-6
    )

    swapped = solve_lexicographic(_lex_model(("t", "c")), inst, solver="cbc")
    assert swapped.objectives == pytest.approx((0.0, 4.0))
    assert sum(v for k, v in swapped.variables.items() if k.startswith("t_")) == pytest.approx(
        0.0, abs=1e-6
    )


def test_lexicographic_rejects_non_lexicographic_objective(instance_files):
    from lp2graph.solve import UnsupportedModel, solve_lexicographic

    f, inst, _ = _spec(next(p for p in instance_files if p.stem == "assignment_4x4"))
    with pytest.raises(UnsupportedModel, match="lexicographic"):
        solve_lexicographic(f, inst)


def test_solve_still_refuses_lexicographic_and_points_at_the_staged_entry_point():
    from lp2graph.solve import UnsupportedModel

    with pytest.raises(UnsupportedModel, match="solve_lexicographic"):
        solve(_lex_model(("c", "t")), Instance(cardinalities={"I": 2}, parameters={}))


def test_solve_path_is_pulp4_clean(instance_files):
    """The grounder must not trip any PuLP-4.0 DeprecationWarning so the
    solve path survives the PuLP 4.0 upgrade (deprecated ``LpVariable(...)``
    constructor, ``PULP_CBC_CMD``, and ``LpProblem.constraints`` mapping)."""
    import warnings

    f, inst, _ = _spec(next(p for p in instance_files if p.stem == "assignment_4x4"))
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=DeprecationWarning, module=r"pulp.*")
        res = solve(f, inst)
    assert res.objective is not None
    assert res.n_vars > 0 and res.n_constraints > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
