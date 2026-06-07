"""Tests for M1 -- the heterogeneous ingestion front-end.

Covers the M1b non-canonical LaTeX normalizer (held-out reference
round-trip, failure reporting, determinism), the dispatcher's routing of
unsupported formats, and the M1a Pyomo importer (skipped where pyomo is
absent).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lp2graph import load
from lp2graph.codec import from_canonical_latex, to_canonical_latex
from lp2graph.mining.ingest import (
    IngestionResult,
    from_pyomo,
    ingest,
    ingest_latex,
    normalize_latex,
)

ROOT = Path(__file__).resolve().parents[2]


def _reference_canonical() -> str:
    """A canonical LaTeX string the codec is known to accept."""
    return to_canonical_latex(load(ROOT / "formulations/constraints/assignment.json"))


def _decanonicalize(canonical: str) -> str:
    """Deliberately de-canonicalize: unicode operators, ascii, '*', \\mathbb,
    and stray whitespace -- everything the normalizer must undo."""
    body_start = canonical.index(r"\begin{align}")
    head, body = canonical[:body_start], canonical[body_start:]
    body = (
        body.replace(r"\sum", "∑")
        .replace(r"\cdot", " * ")
        .replace(r"\forall", "∀")
        .replace(r"\in", "∈")
        .replace(r"\mathcal{W}", r"\mathbb{W}")
        .replace(r"\mathcal{J}", r"\mathbb{J}")
        .replace(" = 1", "  =  1")  # stray whitespace
    )
    return head + body


# ---------------------------------------------------------------------------
# M1b: held-out reference round-trip (the acceptance test)
# ---------------------------------------------------------------------------


def test_held_out_reference_roundtrip():
    reference = _reference_canonical()
    noncanonical = _decanonicalize(reference)
    assert noncanonical != reference  # we really de-canonicalized it

    result = ingest_latex(noncanonical, source="assignment.tex")
    assert result.ok, [f.message for f in result.failures]

    # The recovered formulation reproduces the canonical normal form.
    target = to_canonical_latex(from_canonical_latex(reference))
    assert to_canonical_latex(result.formulation) == target

    # Provenance: non-empty, every span indexes back into the ORIGINAL text.
    rewrites = result.provenance.rewrites
    assert rewrites
    for rw in rewrites:
        span = rw.span
        assert span.source == "assignment.tex"
        assert noncanonical[span.start : span.end] == rw.before
        assert rw.rules_version  # stamped with REWRITE_RULES_VERSION


def test_held_out_reference_via_dispatch(tmp_path):
    reference = _reference_canonical()
    noncanonical = _decanonicalize(reference)
    p = tmp_path / "author.tex"
    p.write_text(noncanonical, encoding="utf-8")

    result = ingest(p)
    assert result.ok
    target = to_canonical_latex(from_canonical_latex(reference))
    assert to_canonical_latex(result.formulation) == target


def test_inequality_reference_roundtrip():
    """A second held-out case exercising \\le/\\ge comparators."""
    reference = to_canonical_latex(load(ROOT / "formulations/constraints/mip_2_1_big_m.json"))
    noncanonical = (
        reference.replace(r"\le", "≤")
        .replace(r"\ge", "≥")
        .replace(r"\cdot", "*")
        .replace(r"\forall", "∀")
        .replace(r"\in", "∈")
    )
    result = ingest_latex(noncanonical, source="bigm.tex")
    assert result.ok
    target = to_canonical_latex(from_canonical_latex(reference))
    assert to_canonical_latex(result.formulation) == target
    assert result.provenance.rewrites


# ---------------------------------------------------------------------------
# Failure reporting: never an uncaught exception
# ---------------------------------------------------------------------------


def test_malformed_latex_is_reported():
    # Header present but a body that the canonical grammar cannot parse
    # (a comparison with no comparator).
    reference = _reference_canonical()
    header = reference[: reference.index(r"\begin{align}")]
    broken = header + "\\begin{align}\n  & x_{w,j} \\tag{oops} \\\\\n\\end{align}\n"
    result = ingest_latex(broken, source="broken.tex")
    assert result.ok is False
    assert result.failures
    assert result.failures[0].stage in {"parse", "validate"}


def test_unknown_extension_reported(tmp_path):
    p = tmp_path / "model.xyz"
    p.write_text("whatever", encoding="utf-8")
    result = ingest(p, fmt=None)
    assert result.ok is False
    assert result.failures[0].stage == "unsupported"


def test_pdf_reported_unsupported(tmp_path):
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.7 not real")
    result = ingest(p)
    assert result.ok is False
    assert result.failures[0].stage == "unsupported"
    assert "PDF" in result.failures[0].message


def test_missing_file_reported():
    result = ingest(Path("/no/such/file.tex"))
    assert result.ok is False
    assert result.failures[0].stage == "read"


def test_code_stubs_report_unsupported(tmp_path):
    for ext in (".gms", ".mod", ".jl", ".py"):
        p = tmp_path / f"m{ext}"
        p.write_text("source", encoding="utf-8")
        result = ingest(p)
        assert result.ok is False
        assert result.failures[0].stage == "unsupported"


def test_unwrap_raises_on_failure():
    from lp2graph.mining.ingest import IngestionError

    result = IngestionResult.single_failure(source="x", stage="unsupported", message="nope")
    with pytest.raises(IngestionError):
        result.unwrap()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_normalize_is_deterministic():
    noncanonical = _decanonicalize(_reference_canonical())
    text_a, prov_a = normalize_latex(noncanonical, source="d.tex")
    text_b, prov_b = normalize_latex(noncanonical, source="d.tex")
    assert text_a == text_b
    assert prov_a.rewrites == prov_b.rewrites


# ---------------------------------------------------------------------------
# M1a: Pyomo importer (skipped where pyomo is absent)
# ---------------------------------------------------------------------------


def test_from_pyomo_concrete_model():
    pyomo = pytest.importorskip("pyomo")  # noqa: F841
    from pyomo.environ import (
        Binary,
        ConcreteModel,
        Constraint,
        NonNegativeReals,
        Objective,
        Set,
        Var,
        minimize,
    )

    m = ConcreteModel(name="tiny")
    m.I = Set(initialize=[1, 2, 3])
    m.x = Var(m.I, domain=Binary)
    m.y = Var(domain=NonNegativeReals)
    m.obj = Objective(expr=m.y, sense=minimize)
    m.c = Constraint(m.I, rule=lambda mm, i: mm.x[i] <= 1)

    result = from_pyomo(m)
    assert result.ok, [f.message for f in result.failures]
    f = result.formulation
    assert {v.name for v in f.variables} == {"x", "y"}
    assert f.variable_map()["x"].domain == "binary"
    assert f.variable_map()["y"].domain == "non_negative"
    assert f.family == "milp"
    assert {c.name for c in f.constraints} == {"c"}


def test_from_pyomo_without_pyomo_is_reported(monkeypatch):
    """If pyomo cannot be imported, from_pyomo reports an 'import' failure
    instead of raising."""
    import builtins

    real_import = builtins.__import__

    def _fake(name, *args, **kwargs):
        if name.startswith("pyomo"):
            raise ImportError("simulated missing pyomo")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake)
    result = from_pyomo(object())
    assert result.ok is False
    assert result.failures[0].stage == "import"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
