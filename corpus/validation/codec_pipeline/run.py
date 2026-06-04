#!/usr/bin/env python3
r"""End-to-end validation of the deterministic text <-> graph <-> MILP pipeline.

For every instance in ``instances/`` this runner executes the *full loop*:

    formulation JSON  (the graph / canonical model)
        |  to_canonical_latex            -> paper-style LaTeX (the text)
        v
    LaTeX document
        |  from_canonical_latex          -> reconstructed canonical model
        v
    canonical model
        |  solve.grounder + instance data -> concrete MILP
        v
    optimal objective value

and checks four things:

  1. **Codec round-trip** — the reconstructed model has the same canonical
     normal form as the original (text is a faithful, reversible view).
  2. **Pipeline solve == direct solve** — solving the model reconstructed
     *from LaTeX* gives the same objective as solving the original JSON.
  3. **Cross-solver agreement** — CBC, HiGHS (and Gurobi if licensed) all
     return the same objective on the grounded model (determinism, not a
     solver artifact).
  4. **Known optimum** — the objective equals an independently established
     reference value (closed-form, brute force, or a published number).

It also records the *paper-anchored* reference optima already proven by the
sibling ``run_experiments.py`` harness (timtab1 = 764772, a published
MIPLIB cyclic-timetabling/PESP optimum of exactly the class the pipeline
handles; marcotallone = 3913.47).

Deterministic: single thread, no heuristic seeds. Writes
``results/codec_pipeline_results.json``.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
VAL = HERE.parent
REPO = VAL.parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(VAL / ".deps"))
os.environ.setdefault("GRB_LICENSE_FILE", str(REPO.parent / "gurobi.lic"))

import pulp  # noqa: E402

from lp2graph import load  # noqa: E402
from lp2graph.codec import (  # noqa: E402
    canonical_normal_form,
    from_canonical_latex,
    to_canonical_latex,
)
from lp2graph.solve import Instance, solve  # noqa: E402

RESULTS = HERE / "results"
RTOL, ATOL = 1e-6, 1e-4


def _solvers():
    out = [("cbc", pulp.PULP_CBC_CMD(msg=0, threads=1))]
    try:
        out.append(("highs", pulp.HiGHS(msg=False)))
    except Exception:  # noqa: BLE001
        pass
    try:
        g = pulp.GUROBI(msg=0)
        if g.available():
            out.append(("gurobi", g))
    except Exception:  # noqa: BLE001
        pass
    return out


def _close(a, b):
    return a is not None and b is not None and math.isclose(a, b, rel_tol=RTOL, abs_tol=ATOL)


def run_case(spec_path: pathlib.Path) -> dict:
    spec = json.loads(spec_path.read_text())
    f = load(REPO / spec["formulation"])
    inst = Instance(cardinalities=spec["cardinalities"], parameters=spec["parameters"])
    expected = spec["expected_optimum"]

    # 1. codec round-trip
    latex = to_canonical_latex(f)
    g = from_canonical_latex(latex)
    roundtrip_ok = canonical_normal_form(f) == canonical_normal_form(g)
    idempotent = to_canonical_latex(g) == latex

    # 2/3. direct vs pipeline, cross-solver
    direct = {name: solve(f, inst, solver=s).objective for name, s in _solvers()}
    pipeline = {name: solve(g, inst, solver=s).objective for name, s in _solvers()}

    objs = [v for v in list(direct.values()) + list(pipeline.values()) if v is not None]
    cross_solver_ok = all(_close(v, objs[0]) for v in objs) if objs else False
    pipeline_eq_direct = _close(direct["cbc"], pipeline["cbc"])
    matches_expected = _close(direct["cbc"], float(expected))

    return {
        "case": spec_path.stem,
        "formulation": spec["formulation"],
        "cardinalities": spec["cardinalities"],
        "expected_optimum": expected,
        "optimum_source": spec["optimum_source"],
        "codec_roundtrip_ok": roundtrip_ok,
        "codec_idempotent": idempotent,
        "direct_objective": direct,
        "pipeline_objective": pipeline,
        "cross_solver_agree": cross_solver_ok,
        "pipeline_equals_direct": pipeline_eq_direct,
        "matches_known_optimum": matches_expected,
        "passed": bool(
            roundtrip_ok
            and idempotent
            and cross_solver_ok
            and pipeline_eq_direct
            and matches_expected
        ),
    }


PAPER_ANCHORS = {
    "description": (
        "Published / benchmark optima proven by the sibling run_experiments.py "
        "harness for corpus models whose structure the canonical pipeline covers."
    ),
    "timtab1_cyclic_timetabling_pesp_milp": {
        "optimum": 764772.0,
        "source": "IBM/CPLEX timtab1 (MIPLIB cyclic timetabling / PESP); cross-solver proven",
        "pipeline_class": "PESP modulo — same structure as formulations/constraints/pesp_solvable.json",
    },
    "marcotallone_maintenance_scheduling_milp": {
        "optimum": 3913.47,
        "source": "marcotallone/railway-scheduling, Gurobi/HiGHS/CBC agreement at tight tolerance",
        "pipeline_class": "big-M time-indexed scheduling — same structure as mip_2_1_big_m / mip_2_4",
    },
}


def main() -> int:
    cases = sorted((HERE / "instances").glob("*.json"))
    results = [run_case(c) for c in cases]
    solvers = [n for n, _ in _solvers()]
    report = {
        "meta": {
            "solvers": solvers,
            "determinism": "single-thread; codec is model-free and deterministic",
            "n_cases": len(results),
            "n_passed": sum(r["passed"] for r in results),
        },
        "paper_anchors": PAPER_ANCHORS,
        "cases": results,
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / "codec_pipeline_results.json"
    out.write_text(json.dumps(report, indent=2))

    print(f"solvers: {solvers}")
    hdr = f"{'case':22s} {'expected':>10s} {'direct':>10s} {'pipeline':>10s}  rt  idem  xsolv  pass"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        print(f"{r['case']:22s} {str(r['expected_optimum']):>10s} "
              f"{str(r['direct_objective']['cbc']):>10s} "
              f"{str(r['pipeline_objective']['cbc']):>10s}  "
              f"{_y(r['codec_roundtrip_ok'])}   {_y(r['codec_idempotent'])}   "
              f"{_y(r['cross_solver_agree'])}    {_y(r['passed'])}")
    print(f"\n{report['meta']['n_passed']}/{report['meta']['n_cases']} cases passed")
    print(f"wrote {out}")
    return 0 if report["meta"]["n_passed"] == report["meta"]["n_cases"] else 1


def _y(b: bool) -> str:
    return " ok" if b else "NO!"


if __name__ == "__main__":
    sys.exit(main())
