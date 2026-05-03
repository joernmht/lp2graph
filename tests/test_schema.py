"""Schema validation: every catalog formulation passes JSON Schema and pydantic."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from optgraph import load


def test_schema_is_valid_jsonschema(schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)


def test_pydantic_loads_every_catalog_file(formulation_files: list[Path]) -> None:
    assert formulation_files, "no formulation files found in catalog"
    for p in formulation_files:
        f = load(p)
        assert f.id, f"empty id in {p}"
        assert f.name, f"empty name in {p}"


def test_jsonschema_validates_every_catalog_file(
    formulation_files: list[Path], schema_path: Path
) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for p in formulation_files:
        data = json.loads(p.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        assert not errors, f"{p}: {[e.message for e in errors]}"


def test_validation_catches_undeclared_variable_reference(tmp_path: Path) -> None:
    bad = {
        "schema_version": "0.1.0",
        "id": "bad_ref",
        "name": "Bad reference",
        "family": "lp",
        "indices": [{"name": "I"}],
        "variables": [
            {"name": "x", "shape": ["I"], "domain": "non_negative"}
        ],
        "constraints": [
            {
                "name": "c1",
                "comparator": "le",
                "lhs": [
                    {
                        "ref": "y",  # not declared
                        "ref_kind": "variable",
                        "bindings": [{"index": "I", "expr": "i", "offset": 0}],
                        "role": "lhs",
                    }
                ],
                "rhs": [{"ref": "one", "ref_kind": "literal", "coefficient": 1, "role": "rhs"}],
                "quantifiers": [{"index": "i", "over": "I"}],
            }
        ],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    from optgraph.core.validate import ValidationError

    with pytest.raises(ValidationError) as e:
        load(p)
    assert any("unknown variable 'y'" in m for m in e.value.errors)


def test_validation_catches_lp_with_integer_var(tmp_path: Path) -> None:
    bad = {
        "schema_version": "0.1.0",
        "id": "bad_lp",
        "name": "LP with integer var",
        "family": "lp",
        "indices": [],
        "variables": [{"name": "x", "domain": "binary"}],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    from optgraph.core.validate import ValidationError

    with pytest.raises(ValidationError):
        load(p)


def test_milp_must_have_an_integer_variable(tmp_path: Path) -> None:
    bad = {
        "schema_version": "0.1.0",
        "id": "bad_milp",
        "name": "MILP without integer",
        "family": "milp",
        "indices": [],
        "variables": [{"name": "x", "domain": "non_negative"}],
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    from optgraph.core.validate import ValidationError

    with pytest.raises(ValidationError):
        load(p)
