"""End-to-end tests for ``lp2graph convert`` (code -> graph -> code)."""

from __future__ import annotations

import _models
import pytest

from lp2graph.cli import main
from lp2graph.interop import from_lp_string, to_lp_string


def _default_solver():
    from lp2graph.solve import default_solver

    return default_solver()


GAMS_KNAPSACK = """\
Binary Variables a, b, c;
Variables profit;
Equations obj, cap;
obj .. profit =e= 60*a + 100*b + 120*c;
cap .. 10*a + 20*b + 30*c =l= 50;
Model knap / all /;
Solve knap using mip maximizing profit;
"""


def test_convert_gams_to_lp_solves(tmp_path, capsys):
    src = tmp_path / "knap.gms"
    src.write_text(GAMS_KNAPSACK, encoding="utf-8")
    dst = tmp_path / "knap.lp"
    assert main(["convert", str(src), str(dst)]) == 0
    assert "knap" in capsys.readouterr().out
    g = from_lp_string(dst.read_text(encoding="utf-8"))
    assert _models.solve_cbc(g) == pytest.approx(220.0)


@pytest.mark.parametrize("ext", [".mps", ".gms", ".mod", ".jl", ".json", ".tex"])
def test_convert_lp_to_every_text_target(tmp_path, ext):
    src = tmp_path / "m.lp"
    src.write_text(to_lp_string(_models.express_freight()), encoding="utf-8")
    dst = tmp_path / f"m{ext}"
    assert main(["convert", str(src), str(dst)]) == 0
    assert dst.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("api", ["gurobipy", "pulp", "pyomo"])
def test_convert_to_python_script_compiles(tmp_path, api):
    src = tmp_path / "m.lp"
    src.write_text(to_lp_string(_models.dantzig()), encoding="utf-8")
    dst = tmp_path / "m.py"
    assert main(["convert", str(src), str(dst), "--python-api", api]) == 0
    compile(dst.read_text(encoding="utf-8"), str(dst), "exec")


def test_convert_pulp_script_runs_to_optimum(tmp_path):
    pulp = pytest.importorskip("pulp")
    src = tmp_path / "m.mod"
    from lp2graph.interop import to_ampl

    src.write_text(to_ampl(_models.express_freight()), encoding="utf-8")
    dst = tmp_path / "m.py"
    assert main(["convert", str(src), str(dst)]) == 0
    ns: dict = {}
    exec(compile(dst.read_text(encoding="utf-8"), str(dst), "exec"), ns)
    prob = ns["build_problem"]()
    prob.solve(_default_solver())
    assert pulp.value(prob.objective) == pytest.approx(44.0)


def test_convert_unknown_extension_exits(tmp_path):
    src = tmp_path / "m.lp"
    src.write_text(to_lp_string(_models.dantzig()), encoding="utf-8")
    with pytest.raises(SystemExit, match="cannot write"):
        main(["convert", str(src), str(tmp_path / "m.xyz")])
