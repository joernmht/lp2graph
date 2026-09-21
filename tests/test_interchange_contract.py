"""The published JSON Schema is shipped, reachable, and actually enforced.

Compatibility (ISO/IEC 25010 -> interoperability). ``canonical.schema.json``
is the contract third parties validate against: it carries a stable ``$id``
and ``docs/data-model.md`` points readers at it. Two things have to stay
true for that contract to mean anything, and neither was tested before
ADR-0013:

1. **It ships.** Until v0.3.1 the wheel contained no data files at all
   (verified against the published ``lp2graph-0.3.0-py3-none-any.whl``), so
   ``pip install lp2graph`` handed a user the reader but not the
   specification -- while still forcing them to install ``jsonschema``,
   which no module in ``src/`` imported.
2. **The library agrees with it.** A contract the implementation does not
   enforce drifts silently. The loader deliberately carries ergonomic
   defaults for in-Python construction, which on their own accepted an
   unversioned or constraint-less *document* that the schema rejects.
"""

from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from lp2graph import canonical_schema, canonical_schema_path, loads
from lp2graph.core.validate import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_accessor_returns_the_published_schema() -> None:
    schema = canonical_schema()
    assert schema["$id"].endswith("canonical.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)


def test_accessor_is_cached_and_matches_the_repo_copy() -> None:
    assert canonical_schema() is canonical_schema(), "schema should be read once"
    on_disk = json.loads(
        (REPO_ROOT / "schema" / "canonical.schema.json").read_text(encoding="utf-8")
    )
    assert canonical_schema() == on_disk
    assert canonical_schema_path().is_file()


def test_wheel_is_configured_to_ship_the_schema() -> None:
    """The force-include mapping is the only thing putting the schema in the wheel.

    ``[tool.hatch.build.targets.wheel] packages`` copies ``src/lp2graph``
    only, so without this mapping the data file is silently dropped from
    every wheel -- which is exactly what shipped in v0.3.0.
    """
    cfg = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]
    mapping = wheel.get("force-include", {})
    assert mapping.get("schema/canonical.schema.json") == (
        "lp2graph/schema/canonical.schema.json"
    ), "the wheel must force-include the canonical schema (ADR-0013)"


def _catalog_doc() -> dict[str, Any]:
    path = REPO_ROOT / "formulations" / "constraints" / "lp_1_1_fixed_sequence.json"
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _schema_accepts(doc: dict[str, Any]) -> bool:
    return jsonschema.Draft202012Validator(canonical_schema()).is_valid(doc)


def _library_accepts(doc: dict[str, Any]) -> bool:
    try:
        loads(json.dumps(doc))
    except Exception:
        return False
    return True


#: (label, mutation) pairs probing both directions of the contract.
_MUTATIONS: list[tuple[str, Any]] = [
    ("unchanged", lambda d: None),
    ("missing schema_version", lambda d: d.pop("schema_version")),
    ("missing constraints", lambda d: d.pop("constraints")),
    ("missing variables", lambda d: d.pop("variables")),
    ("missing id", lambda d: d.pop("id")),
    ("unknown top-level field", lambda d: d.update(provenance_note="x")),
    ("unknown nested field", lambda d: d["variables"][0].update(units="min")),
    ("future schema_version", lambda d: d.update(schema_version="0.2.0")),
    ("bad family", lambda d: d.update(family="quadratic")),
    ("empty variables", lambda d: d.update(variables=[])),
]


@pytest.mark.parametrize(("label", "mutate"), _MUTATIONS, ids=[m[0] for m in _MUTATIONS])
def test_library_and_schema_agree(label: str, mutate: Any) -> None:
    """Whatever the published schema accepts, the loader accepts -- and vice versa.

    A one-sided contract is the drift this guards: a document valid against
    the ``$id``-ed schema that the library refuses is a broken promise to a
    third party, and one the library accepts that the schema refuses means
    the spec no longer describes the implementation.
    """
    doc = _catalog_doc()
    mutate(doc)
    assert _schema_accepts(doc) == _library_accepts(doc), (
        f"{label}: schema={'accept' if _schema_accepts(doc) else 'reject'} "
        f"but library={'accept' if _library_accepts(doc) else 'reject'}"
    )


def test_schema_violation_names_the_source_and_the_rule() -> None:
    doc = _catalog_doc()
    del doc["schema_version"]
    with pytest.raises(ValidationError) as excinfo:
        loads(json.dumps(doc), source="corpus/f.json")
    assert "corpus/f.json" in str(excinfo.value)
    assert any("schema_version" in m for m in excinfo.value.errors)


def test_model_invariant_error_is_anchored_to_the_source() -> None:
    """Cross-field rules are pydantic's, not the schema's; they still name the file.

    The exception *type* stays ``pydantic.ValidationError`` (callers catch
    it today), so the source is attached as a note rather than by wrapping.
    """
    import pydantic

    doc = _catalog_doc()
    doc["constraints"][0]["rhs"] = [{"constant": 1, "ref": "one", "role": "rhs"}]
    with pytest.raises(pydantic.ValidationError) as excinfo:
        loads(json.dumps(doc), source="corpus/bad.json")
    assert any("corpus/bad.json" in n for n in getattr(excinfo.value, "__notes__", []))


def test_every_catalog_file_passes_the_enforced_loader(
    formulation_files: list[Path],
) -> None:
    """The repo's own catalog must satisfy the contract it publishes."""
    assert formulation_files
    for path in formulation_files:
        loads(path.read_text(encoding="utf-8"), source=str(path))


def test_jsonschema_is_a_used_core_dependency() -> None:
    """``jsonschema`` is declared a hard runtime dep; something must import it.

    It was declared, installed and never imported anywhere in ``src/`` --
    a mandatory dependency doing no work for any installed user.
    """
    hits = [
        p.relative_to(REPO_ROOT)
        for p in sorted((REPO_ROOT / "src").rglob("*.py"))
        if "jsonschema" in p.read_text(encoding="utf-8")
    ]
    assert hits, "jsonschema is a core dependency but src/ never imports it"


def test_unversioned_document_is_refused_rather_than_assumed() -> None:
    """The version field is the format's only forward-compat mechanism (ADR-0004).

    Defaulting it at the *document* boundary would make an unversioned file
    indistinguishable from a 0.1.0 one, permanently.
    """
    doc = copy.deepcopy(_catalog_doc())
    del doc["schema_version"]
    with pytest.raises(ValidationError):
        loads(json.dumps(doc))
