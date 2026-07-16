"""Pipeline tests: parse fallbacks, structural detectors, solve smoke check.

Structure-stage tests run with ``solve_check=False`` so they stay
solver-free; the solve-stage tests gate on pulp like ``tests/test_solve.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lp2graph import load
from lp2graph.core.model import Parameter, VariableTemplate
from lp2graph.validation import validate_formulation, validate_path, validate_text

ASSIGNMENT = "formulations/constraints/assignment.json"

LP_TEXT = (
    "Minimize\n obj: 3 x + 5 y\nSubject To\n c1: x + y >= 2\nBounds\n x <= 10\n y <= 10\nEnd\n"
)


def _codes(report):
    return {c.code for c in report.checks}


# ---------------------------------------------------------------------------
# End-to-end happy paths
# ---------------------------------------------------------------------------


def test_canonical_json_path_is_valid():
    report = validate_path(ASSIGNMENT, solve_check=False)
    assert report.verdict == "valid"
    assert report.fmt == "json"
    assert report.formulation is not None
    assert report.summary().startswith("OK: assignment")


def test_lp_text_sniffed_and_valid():
    report = validate_text(LP_TEXT, solve_check=False)
    assert report.verdict == "valid"
    assert report.fmt == "lp"


def test_fenced_llm_answer_recovers_model():
    answer = f"Sure! Here is the model:\n\n```lp\n{LP_TEXT}```\n\nLet me know if it helps."
    report = validate_text(answer, solve_check=False)
    assert report.verdict == "valid_with_warnings"
    assert "markdown-fences" in _codes(report)
    assert report.formulation is not None


def test_unicode_lookalikes_are_repaired():
    report = validate_text(
        "Minimize\n obj: 3 x \u2212 5 y\nSubject To\n c1: x + y \u2265 2\nEnd\n", solve_check=False
    )
    assert report.formulation is not None
    assert "unicode-normalized" in _codes(report)


def test_report_json_is_deterministic():
    a = validate_text(LP_TEXT, solve_check=False).to_json()
    b = validate_text(LP_TEXT, solve_check=False).to_json()
    assert a == b
    payload = json.loads(a)
    assert payload["verdict"] == "valid"
    assert payload["pipeline_version"].startswith("validate-")


# ---------------------------------------------------------------------------
# Faulty input: detectors and fallbacks
# ---------------------------------------------------------------------------


def test_empty_input_is_invalid():
    report = validate_text("   \n")
    assert report.verdict == "invalid"
    assert "empty-input" in _codes(report)


def test_prose_only_reports_format_undetected():
    report = validate_text("The optimal answer is to reschedule train 5.")
    assert report.verdict == "invalid"
    assert "format-undetected" in _codes(report)


def test_explicit_wrong_format_fails_without_fallback():
    report = validate_text(LP_TEXT, fmt="latex", solve_check=False)
    assert report.verdict == "invalid"
    assert "parse-failed" in _codes(report)
    assert "all-parsers-failed" in _codes(report)


def test_unknown_format_name_is_reported():
    report = validate_text(LP_TEXT, fmt="excel")
    assert report.verdict == "invalid"
    assert "unknown-format" in _codes(report)


def test_python_source_is_recognized_but_not_executed():
    report = validate_text("import pulp\nprob = pulp.LpProblem('m', pulp.LpMinimize)\n")
    assert report.verdict == "invalid"
    failed = [c for c in report.checks if c.code == "parse-failed"]
    assert failed and "from_pulp" in failed[0].detail


def test_truncated_latex_flags_truncation():
    report = validate_text("\\begin{align}\n\\min \\sum_{i} c_i x_{i} \\\\\nx_i +")
    assert report.verdict == "invalid"
    assert "dangling-tail" in _codes(report)
    assert "unbalanced-environments" in _codes(report)


def test_semantic_error_in_canonical_json_is_terminal():
    doc = json.loads(Path(ASSIGNMENT).read_text(encoding="utf-8"))
    doc["variables"][0]["shape"] = ["NOPE"]
    report = validate_text(json.dumps(doc), fmt="json", solve_check=False)
    assert report.verdict == "invalid"
    semantic = [c for c in report.checks if c.code == "semantic"]
    assert semantic and "NOPE" in semantic[0].message


def test_missing_file_is_reported_not_raised():
    report = validate_path("does/not/exist.lp")
    assert report.verdict == "invalid"
    assert "unreadable" in _codes(report)


# ---------------------------------------------------------------------------
# Structure detectors
# ---------------------------------------------------------------------------


def test_incomplete_model_is_an_error():
    doc = json.loads(Path(ASSIGNMENT).read_text(encoding="utf-8"))
    doc["constraints"] = []
    report = validate_text(json.dumps(doc), fmt="json", solve_check=False)
    assert report.verdict == "invalid"
    incomplete = [c for c in report.checks if c.code == "incomplete"]
    assert incomplete and "constraints" in incomplete[0].message


def test_unused_symbol_warning():
    f = load(ASSIGNMENT)
    f = f.model_copy(update={"parameters": (*f.parameters, Parameter(name="ghost"))})
    report = validate_formulation(f, solve_check=False)
    assert report.verdict == "valid_with_warnings"
    unused = [c for c in report.checks if c.code == "unused-symbol"]
    assert unused and "ghost" in unused[0].message


def test_bound_conflict_is_an_error():
    f = load(ASSIGNMENT)
    bad = VariableTemplate(name="z", domain="continuous", lower=5.0, upper=1.0)
    f = f.model_copy(update={"variables": (*f.variables, bad)})
    report = validate_formulation(f, solve_check=False)
    assert report.verdict == "invalid"
    assert "bound-conflict" in _codes(report)


def test_duplicate_names_are_an_error():
    f = load(ASSIGNMENT)
    dupe = Parameter(name=f.variables[0].name)
    f = f.model_copy(update={"parameters": (*f.parameters, dupe)})
    report = validate_formulation(f, solve_check=False)
    assert report.verdict == "invalid"
    assert "duplicate-names" in _codes(report)


def test_validate_formulation_runs_semantics():
    f = load(ASSIGNMENT)
    report = validate_formulation(f, solve_check=False)
    assert "semantics-ok" in _codes(report)
    assert report.verdict == "valid"


# ---------------------------------------------------------------------------
# Solve smoke check (gated on pulp, like tests/test_solve.py)
# ---------------------------------------------------------------------------


def test_solve_smoke_on_template_model():
    pytest.importorskip("pulp")
    report = validate_path(ASSIGNMENT)
    assert report.verdict == "valid"
    assert report.solve is not None
    assert report.solve["status"] == "optimal"
    assert report.solve["instance_synthesized"] is True


def test_flat_unbounded_model_is_an_error():
    pytest.importorskip("pulp")
    report = validate_text("Minimize\n obj: 3 x - 5 y\nSubject To\n c1: x + y >= 2\nEnd\n")
    assert report.verdict == "invalid"
    assert "unbounded" in _codes(report)


def test_flat_infeasible_model_is_an_error():
    pytest.importorskip("pulp")
    report = validate_text("Minimize\n obj: x\nSubject To\n c1: x >= 2\n c2: x <= 1\nEnd\n")
    assert report.verdict == "invalid"
    assert "infeasible" in _codes(report)


def test_solve_disabled_records_skip():
    report = validate_path(ASSIGNMENT, solve_check=False)
    assert any(c.code == "solve-disabled" and c.level == "skip" for c in report.checks)
