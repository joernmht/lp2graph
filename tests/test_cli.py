"""Smoke tests for the ``lp2graph`` command-line entry point.

``cli.main`` is the console-script registered in ``pyproject.toml``
(``lp2graph = "lp2graph.cli:main"``) yet had no test coverage: this file
exercises every solver-free subcommand end-to-end through ``main(argv)``
(no subprocess), so a regression in argument wiring or a subcommand body is
caught by the suite rather than only in the field. The solver subcommand is
gated on ``pulp`` like the rest of ``tests/test_solve.py``.
"""

from __future__ import annotations

import json

import pytest

from lp2graph.cli import main

ASSIGNMENT = "formulations/constraints/assignment.json"
PESP = "formulations/constraints/mip_2_8_pesp.json"


def test_validate_ok(capsys):
    assert main(["validate", ASSIGNMENT]) == 0
    out = capsys.readouterr().out
    assert out.startswith("OK:")


@pytest.mark.parametrize("view", ["schema", "hybrid"])
def test_view_prints_counts(capsys, view):
    assert main(["view", ASSIGNMENT, "--view", view]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["view"] == view
    assert payload["nodes"] > 0
    assert payload["edges"] > 0


def test_view_ground_with_cardinalities(capsys):
    # ground view needs concrete set sizes; assignment uses sets W and J.
    assert main(["view", ASSIGNMENT, "--view", "ground", "--card", "W=4", "--card", "J=4"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["view"] == "ground"
    assert payload["nodes"] > 0


def test_metrics_is_json(capsys):
    assert main(["metrics", ASSIGNMENT]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    assert payload  # non-empty metric set


def test_latex_then_parse_roundtrip(tmp_path, capsys):
    """`latex` emits canonical LaTeX to a file; `parse` reads it back to JSON."""
    tex = tmp_path / "out.tex"
    assert main(["latex", ASSIGNMENT, "--output", str(tex)]) == 0
    capsys.readouterr()
    assert tex.exists()
    body = tex.read_text(encoding="utf-8")
    assert r"\begin{align}" in body

    assert main(["parse", str(tex)]) == 0
    parsed = json.loads(capsys.readouterr().out)
    # a parsed formulation carries an id and at least one constraint.
    assert parsed["id"]
    assert parsed["constraints"]


def test_describe_emits_text(capsys):
    assert main(["describe", PESP]) == 0
    out = capsys.readouterr().out
    assert len(out.strip()) > 0


@pytest.mark.parametrize("fmt", ["latex", "pyomo"])
def test_export_solverfree_formats(capsys, fmt):
    """latex/pyomo exports need no optional graph-ML deps."""
    assert main(["export", ASSIGNMENT, "--format", fmt]) == 0
    assert capsys.readouterr().out.strip()


def test_export_to_file(tmp_path, capsys):
    dest = tmp_path / "model.tex"
    assert main(["export", ASSIGNMENT, "--format", "latex", "--output", str(dest)]) == 0
    assert dest.exists() and dest.read_text(encoding="utf-8").strip()


def test_no_subcommand_errors():
    """argparse requires a subcommand; bare invocation exits non-zero."""
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_deterministic_metrics_output(capsys):
    """The metrics subcommand is a pure function of the input file."""
    assert main(["metrics", ASSIGNMENT]) == 0
    first = capsys.readouterr().out
    assert main(["metrics", ASSIGNMENT]) == 0
    second = capsys.readouterr().out
    assert first == second


def test_solve_matches_known_optimum(capsys):
    pytest.importorskip("pulp")
    inst = "corpus/validation/codec_pipeline/instances/assignment_4x4.json"
    import json as _json
    from pathlib import Path

    spec = _json.loads(Path(inst).read_text(encoding="utf-8"))
    # the CLI solve subcommand grounds `path` with `--instance` and solves.
    assert main(["solve", ASSIGNMENT, "--instance", inst, "--solver", "cbc"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["objective"] == pytest.approx(float(spec["expected_optimum"]), abs=1e-4)
