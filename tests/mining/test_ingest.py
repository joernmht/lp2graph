"""Tests for M1 -- the heterogeneous ingestion front-end.

Covers the M1b non-canonical LaTeX normalizer (held-out reference
round-trip, failure reporting, determinism), the dispatcher's routing of
unsupported formats, and the M1a Pyomo importer (skipped where pyomo is
absent).
"""

# Greek/look-alike codepoints are the subject under test here, not a typo.
# ruff: noqa: RUF001

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


def test_non_utf8_source_reported(tmp_path):
    # Third-party corpus files are not guaranteed UTF-8; a lone latin-1 byte
    # must be reported as a read-stage failure, never raised (M1 invariant).
    p = tmp_path / "model.tex"
    p.write_bytes(b"\\begin{align}\n x \\le 5 \\quad \xe9\n\\end{align}\n")
    result = ingest(p)
    assert result.ok is False
    assert result.failures[0].stage == "read"
    assert "UTF-8" in result.failures[0].message


def test_python_source_reports_unsupported(tmp_path):
    # Executing arbitrary .py source stays out of scope by design.
    p = tmp_path / "m.py"
    p.write_text("import gurobipy", encoding="utf-8")
    result = ingest(p)
    assert result.ok is False
    assert result.failures[0].stage == "unsupported"


def test_code_formats_report_parse_failures(tmp_path):
    # Unparseable solver-language sources fail at the parse stage --
    # reported, never swallowed (the importers are real now).
    for ext in (".gms", ".mod", ".jl", ".lp", ".mps"):
        p = tmp_path / f"m{ext}"
        p.write_text("@@ not a model @@", encoding="utf-8")
        result = ingest(p)
        assert result.ok is False
        assert result.failures[0].stage == "parse"


def test_gams_file_ingests_to_validated_formulation(tmp_path):
    p = tmp_path / "knap.gms"
    p.write_text(
        "Binary Variables a, b, c;\n"
        "Variables profit;\n"
        "Equations obj, cap;\n"
        "obj .. profit =e= 60*a + 100*b + 120*c;\n"
        "cap .. 10*a + 20*b + 30*c =l= 50;\n"
        "Model knap / all /;\n"
        "Solve knap using mip maximizing profit;\n",
        encoding="utf-8",
    )
    result = ingest(p)
    assert result.ok is True
    assert result.formulation.id == "knap"
    assert len(result.formulation.variables) == 3
    assert result.formulation.objective.sense == "max"


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


def test_underset_bigop_rewritten_to_subscript_form():
    text, prov = normalize_latex(
        r"\underset{s_{i} \in \mathcal{S}}{\sum} t_{s_{i}}", source="d.tex"
    )
    assert text == r"\sum_{s_{i} \in \mathcal{S}} t_{s_{i}}"
    assert "underset_bigop" in {r.rule for r in prov.rewrites}


def test_underset_bigop_all_operators():
    for op in (r"\sum", r"\prod", r"\min", r"\max", r"\int", r"\bigcup", r"\bigcap"):
        text, _ = normalize_latex(r"\underset{i \in \mathcal{N}}{" + op + "} x_i", source="d.tex")
        assert text.startswith(op + r"_{i \in \mathcal{N}}"), text


def test_mathop_overset_underbrace_unwrapped():
    text, prov = normalize_latex(r"\mathop{\sum}_{i} x_i", source="d.tex")
    assert text == r"\sum_{i} x_i"
    text2, prov2 = normalize_latex(
        r"\overset{\text{def}}{\mathrm{Z}} + \underbrace{c x}", source="d.tex"
    )
    assert r"\overset" not in text2 and r"\underbrace" not in text2
    fired = {r.rule for r in prov.rewrites} | {r.rule for r in prov2.rewrites}
    assert {"mathop_unwrap", "overset_base", "underbrace_unwrap"} <= fired


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


def test_greek_command_identifiers_become_mathit_names():
    text, prov = normalize_latex(r"\min \lambda \cdot x_{i} + \pi_{i} + \tau", source="d.tex")
    assert text == r"\min \mathit{lambda} \cdot x_{i} + \mathit{pi}_{i} + \mathit{tau}"
    assert "greek_ident" in {r.rule for r in prov.rewrites}


def test_greek_rewrite_never_touches_non_greek_commands():
    for untouched in (r"a \le b", r"x \neq y", r"\forall i \in \mathcal{I}", r"\left( x \right)"):
        text, _ = normalize_latex(untouched, source="d.tex")
        assert "mathit" not in text, text


def test_ell_command_and_le_are_distinguished():
    text, _ = normalize_latex(r"\ell \le \ell_{max}", source="d.tex")
    # ``_{max}`` is a label subscript (no binder binds it), so it folds into
    # the plain name; the \ell / \le distinction is what this test guards.
    assert text == r"\mathit{ell} \le ell_max"


def test_unicode_greek_identifiers_become_mathit_names():
    text, prov = normalize_latex("λ_{j} + Δ + ς + ℓ", source="d.tex")
    assert text == r"\mathit{lambda}_{j} + \mathit{Delta} + \mathit{sigma} + \mathit{ell}"
    assert "greek_unicode_ident" in {r.rule for r in prov.rewrites}


def test_greek_rewrite_is_deterministic():
    src = r"\min \varepsilon + λ \cdot x"
    assert normalize_latex(src, source="d.tex")[0] == normalize_latex(src, source="d.tex")[0]


# ---------------------------------------------------------------------------
# M1b rule batch rewrite-2026.08.1: \times, sum_merge, accents, primes
# (lp2graph issues #52-#57; corpus evidence in the 2026-08 sprint)
# ---------------------------------------------------------------------------


def test_times_command_becomes_cdot():
    text, prov = normalize_latex(r"w_{1} \times f_{1} + a \times b", source="d.tex")
    # Without a declared shape a numeric subscript is a label: a weighted
    # objective names distinct scalars w_1, w_2 (declaration-driven rules).
    assert text == r"w_1 \cdot f_1 + a \cdot b"
    assert "times_cdot" in {r.rule for r in prov.rewrites}


def test_consecutive_sums_merge_into_one_multi_binder():
    text, prov = normalize_latex(
        r"\sum_{a \in \mathcal{A}} \sum_{b \in \mathcal{B}} x_{a,b}", source="d.tex"
    )
    assert text == r"\sum_{a \in \mathcal{A}, b \in \mathcal{B}} x_{a,b}"
    assert "sum_merge" in {r.rule for r in prov.rewrites}


def test_triple_sum_merges_in_one_firing_preserving_order():
    text, prov = normalize_latex(
        r"\sum_{j \in T} \sum_{a \in A_{j}} \sum_{k \in K} x", source="d.tex"
    )
    assert text == r"\sum_{j \in T, a \in A_{j}, k \in K} x"
    assert sum(1 for r in prov.rewrites if r.rule == "sum_merge") == 1


def test_underset_sums_merge_after_bigop_rewrite():
    text, _ = normalize_latex(
        r"\underset{a \in A}{\sum} \underset{b \in B}{\sum} x_{a,b}", source="d.tex"
    )
    assert text == r"\sum_{a \in A, b \in B} x_{a,b}"


def test_separated_sums_do_not_merge():
    src = r"\sum_{a \in \mathcal{A}} x_{a} + \sum_{b \in \mathcal{B}} y_{b}"
    text, prov = normalize_latex(src, source="d.tex")
    assert "sum_merge" not in {r.rule for r in prov.rewrites}
    assert text == src


def test_accented_identifiers_become_plain_suffixed_names():
    text, prov = normalize_latex(r"\hat{tc}_{e} + \bar{h w}_{i} + \bar t", source="d.tex")
    assert text == r"tc_hat_{e} + hw_bar_{i} + t_bar"
    assert "accent_ident" in {r.rule for r in prov.rewrites}


def test_accent_over_greek_composes_via_mathit_unwrap():
    text, _ = normalize_latex(r"\tilde{\beta} + \hat{\lambda}_{k}", source="d.tex")
    assert text == r"beta_tilde + lambda_hat_{k}"


def test_overset_accent_wins_over_overset_base():
    text, prov = normalize_latex(r"\overset{~}{\beta}_{k} + \overset{def}{=}", source="d.tex")
    assert text == r"beta_tilde_{k} + {=}"
    fired = {r.rule for r in prov.rewrites}
    assert {"overset_accent", "overset_base"} <= fired


def test_underset_accent_collapses_to_underline_name():
    text, _ = normalize_latex(r"\underset{\underline}{h w}_{i}", source="d.tex")
    assert text == r"hw_underline_{i}"


def test_accent_rewrite_never_touches_lookalikes():
    for untouched in (r"\barwedge x", r"\bar{x + y}", r"\dotsc", r"\left| x \right|"):
        text, _ = normalize_latex(untouched, source="d.tex")
        assert text == untouched, text


def test_primed_identifiers_get_p_suffix():
    text, prov = normalize_latex(
        r"t' + k^{'} + l^{\prime\prime} + x_{t'} \forall t' \in \mathcal{T}", source="d.tex"
    )
    # The renamed letter stays bound (the quantifier renames with it), so
    # x_{tp} keeps its index; an unbound two-letter word would be a label.
    assert text == r"tp + kp + lpp + x_{tp} \forall tp \in \mathcal{T}"
    assert "prime_ident" in {r.rule for r in prov.rewrites}


def test_decorated_rewrites_are_deterministic():
    src = r"\hat{tc}' + \overset{~}{\beta} + \sum_{a \in A} \sum_{b \in B} x"
    a1, p1 = normalize_latex(src, source="d.tex")
    a2, p2 = normalize_latex(src, source="d.tex")
    assert a1 == a2
    assert p1.rewrites == p2.rewrites


# ---------------------------------------------------------------------------
# Grammar extensions (codec parser through ingest_latex): comparators,
# chained relations, subscripted coefficients, \frac, residue guard
# ---------------------------------------------------------------------------

_PROBE_HEADER = """%@ meta id=probe family=lp schema=0.1.0
%@ name :: Probe
%@ index E ordered=0 cyclic=0 :: Edges.
%@ index J ordered=0 cyclic=0 :: Jobs.
%@ param w shape=E kind=vector domain=- :: Weight.
%@ param a shape=J,E kind=matrix domain=- :: Matrix.
%@ param c shape=E kind=vector domain=- :: Cost.
%@ param l shape=- kind=scalar domain=- :: Low.
%@ param u shape=- kind=scalar domain=- :: Up.
%@ param b shape=J kind=vector domain=- :: Bound.
%@ var x shape=E domain=non_negative role=primary drole=- lo=- hi=- :: Flow.
%@ obj sense=min name=cost combination=sum :: Minimize.
%@ con cap kind=capacity domain=- indicator=- :: Capacity.
"""

_PROBE_OBJ = "  \\min\\quad & \\sum_{e \\in \\mathcal{E}} c \\cdot x_{e} \\tag{cost} \\\\"


def _probe(*rows: str) -> IngestionResult:
    doc = _PROBE_HEADER + "\\begin{align}\n" + "\n".join(rows) + "\n\\end{align}\n"
    return ingest_latex(doc, source="probe.tex")


def test_subscripted_coefficient_resolves_via_binder_index():
    # Issue #52 acceptance probe: the binder carries the index, so w_{e}
    # resolves to the bare parameter w.
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} w_{e} \cdot x_{e} \tag{cost} \\")
    assert r.ok, r.failures
    (term,) = r.formulation.objective.terms
    assert term.coefficient == "w"
    assert term.ref == "x"


def test_subscripted_coefficient_resolves_via_quantifier_index():
    # The standard LP row: a_{j,e} x_e <= b_j forall j.
    r = _probe(
        _PROBE_OBJ,
        r"  & \sum_{e \in \mathcal{E}} a_{j,e} \cdot x_{e} \le b_{j}"
        r" \qquad \forall j \in \mathcal{J} \tag{cap} \\",
    )
    assert r.ok, r.failures
    (cap,) = r.formulation.constraints
    assert cap.lhs[0].coefficient == "a"


def test_subscripted_coefficient_with_foreign_index_is_refused_by_name():
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} b_{e} \cdot x_{e} \tag{cost} \\")
    assert not r.ok
    assert r.failures[0].stage == "parse"
    assert "subscripted coefficient" in r.failures[0].message


def test_leq_and_geq_are_row_comparators_not_le_plus_junk():
    r = _probe(_PROBE_OBJ, r"  & x_{e} \leq u \qquad \forall e \in \mathcal{E} \tag{cap} \\")
    assert r.ok, r.failures
    assert r.formulation.constraints[0].comparator == "le"
    r = _probe(_PROBE_OBJ, r"  & x_{e} \geq l \qquad \forall e \in \mathcal{E} \tag{cap} \\")
    assert r.ok, r.failures
    assert r.formulation.constraints[0].comparator == "ge"


def test_abs_on_constraint_lhs_is_not_mistaken_for_le():
    r = _probe(
        _PROBE_OBJ,
        r"  & \left| x_{e} \right| \le u \qquad \forall e \in \mathcal{E} \tag{cap} \\",
    )
    assert r.ok, r.failures
    (cap,) = r.formulation.constraints
    assert cap.lhs[0].operator == "abs"


def test_chained_relation_splits_into_lo_and_up_rows():
    r = _probe(
        _PROBE_OBJ,
        r"  & l \leq x_{e} \leq u \qquad \forall e \in \mathcal{E} \tag{cap} \\",
    )
    assert r.ok, r.failures
    lo, up = r.formulation.constraints
    assert (lo.name, up.name) == ("cap_lo", "cap_up")
    assert lo.comparator == up.comparator == "le"
    # Both halves inherit the row's quantifier tail.
    assert [q.index for q in lo.quantifiers] == [q.index for q in up.quantifiers] == ["e"]
    # Shared con metadata reaches both halves.
    assert lo.kind == up.kind == "capacity"


def test_ge_chain_names_upper_bound_first():
    r = _probe(_PROBE_OBJ, r"  & u \ge x_{e} \ge l \qquad \forall e \in \mathcal{E} \tag{cap} \\")
    assert r.ok, r.failures
    assert [c.name for c in r.formulation.constraints] == ["cap_up", "cap_lo"]


def test_mixed_direction_chain_is_refused_by_name():
    r = _probe(_PROBE_OBJ, r"  & l \le x_{e} \ge u \qquad \forall e \in \mathcal{E} \tag{cap} \\")
    assert not r.ok
    assert "chained relation" in r.failures[0].message or "mixed" in r.failures[0].message


def test_binder_range_chain_is_not_split():
    # A comparator chain INSIDE a binder subscript is a range, not a row
    # relation (corpusbuilder.split refuses the same look-alike).
    r = _probe(
        _PROBE_OBJ,
        r"  & \sum_{t \leq t + T} x_{e} \le u \qquad \forall e \in \mathcal{E} \tag{cap} \\",
    )
    assert len(r.formulation.constraints if r.ok else ()) <= 1


def test_numeric_frac_folds_into_the_coefficient():
    r = _probe(r"  \min\quad & \frac{1}{2} \sum_{e \in \mathcal{E}} x_{e} \tag{cost} \\")
    assert r.ok, r.failures
    assert r.formulation.objective.terms[0].coefficient == 0.5
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} \frac{3}{4} \cdot x_{e} \tag{cost} \\")
    assert r.ok, r.failures
    assert r.formulation.objective.terms[0].coefficient == 0.75


def test_bare_numeric_frac_is_a_literal():
    r = _probe(
        _PROBE_OBJ, r"  & x_{e} \le \frac{1}{2} \qquad \forall e \in \mathcal{E} \tag{cap} \\"
    )
    assert r.ok, r.failures
    rhs = r.formulation.constraints[0].rhs[0]
    assert rhs.ref_kind == "literal" and rhs.coefficient == 0.5


def test_nonterminating_frac_is_refused_by_name():
    r = _probe(r"  \min\quad & \frac{1}{3} \sum_{e \in \mathcal{E}} x_{e} \tag{cost} \\")
    assert not r.ok
    assert "terminating" in r.failures[0].message


def test_symbolic_frac_is_refused_by_name():
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} \frac{u}{l} \cdot x_{e} \tag{cost} \\")
    assert not r.ok
    assert "frac" in r.failures[0].message


def test_trailing_superscript_is_refused_not_dropped():
    r = _probe(_PROBE_OBJ, r"  & x_{e}^{k} \le u \qquad \forall e \in \mathcal{E} \tag{cap} \\")
    assert not r.ok
    # ``k`` is bound nowhere, so the script rules read it as a label and the
    # row names the undeclared symbol x_k; still refused by name, not dropped.
    assert "x_k" in r.failures[0].message
    assert "not a declared" in r.failures[0].message


def test_juxtaposed_second_factor_is_refused_not_dropped():
    # Regression lock: p_{e} x_{e} used to parse "successfully" with the
    # second factor silently discarded (ADR-0015's silent-loss class).
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} w_{e} x_{e} \tag{cost} \\")
    assert not r.ok
    assert "trailing" in r.failures[0].message


def test_declared_constant_subscript_parses_as_element_reference():
    # Issue #54: with the family declared, t_{0}-style refs are legal
    # bindings (expr '0'); only undeclared symbols get the named error.
    r = _probe(_PROBE_OBJ, r"  & b_{0} \le u \tag{cap} \\")
    assert r.ok, r.failures
    assert r.formulation.constraints[0].lhs[0].bindings[0].expr == "0"


def test_undeclared_constant_subscript_gets_a_named_error():
    r = _probe(_PROBE_OBJ, r"  & z_{0} \le u \tag{cap} \\")
    assert not r.ok
    assert "declare" in r.failures[0].message


# ---------------------------------------------------------------------------
# M1b rule batch rewrite-2026.09.0: declaration-driven script resolution
# (issues #62 regression, #63; corpus evidence: 49 + 21 of 220 failing papers
# in the 2026-09 promote re-run stall on superscripts and label subscripts)
# ---------------------------------------------------------------------------

_CTX_HEADER = """%@ meta id=ctx family=lp schema=0.1.0
%@ name :: Context probe
%@ index I ordered=0 cyclic=0 :: Items.
%@ index T ordered=1 cyclic=0 :: Periods.
%@ param B shape=T kind=vector domain=- :: Demand.
%@ var w shape=T domain=continuous role=primary drole=- lo=- hi=- :: Waiting.
%@ var t shape=I domain=continuous role=primary drole=- lo=- hi=- :: Time.
%@ var x shape=I,T domain=continuous role=primary drole=- lo=- hi=- :: Flow.
%@ var Z_1 shape=- domain=continuous role=primary drole=- lo=- hi=- :: Component.
"""


def _norm(row: str) -> tuple[str, set[str]]:
    """Normalize one row under ``_CTX_HEADER``; return the row and the rules that fired."""
    doc = _CTX_HEADER + "\\begin{align}\n  & " + row + " \\tag{r} \\\\\n\\end{align}\n"
    text, prov = normalize_latex(doc, source="ctx.tex")
    body = text.split("\\begin{align}", 1)[1].split(" \\tag{r}", 1)[0]
    return body.strip(" &\n"), {r.rule for r in prov.rewrites}


def test_unbraced_scripts_brace_against_declarations():
    row, fired = _norm(
        r"\sum_{u \in \mathcal{T}} B_u \cdot w_u + Z_1 + x_i \forall i \in \mathcal{I}"
    )
    assert (
        row == r"\sum_{u \in \mathcal{T}} B_{u} \cdot w_{u} + Z_1 + x_{i} \forall i \in \mathcal{I}"
    )
    assert "bare_sub_brace" in fired


def test_unbraced_subscript_on_an_unknown_symbol_is_left_alone():
    # Neither ``q`` is shaped nor ``v`` bound: nothing to resolve against.
    row, fired = _norm(r"q_v + x_{i} \forall i \in \mathcal{I}")
    assert row.startswith("q_v")
    assert "bare_sub_brace" not in fired


def test_bound_superscripts_move_into_the_subscript():
    row, fired = _norm(
        r"x_{i}^{k} + p_{n}^{t + 1} + N_{b}^{i j} + \sum_{p = 1}^{f^{i}} y_{p}"
        r" \forall i \in \mathcal{I}, k \in \mathcal{K}, t \in \mathcal{T}, j \in \mathcal{J}"
    )
    assert row.startswith(r"x_{i, k} + p_{n, t + 1} + N_{b, i, j} + \sum_{p = 1}^{f_{i}} y_{p}")
    assert "superscript_index" in fired
    assert "superscript_label" not in fired


def test_label_superscripts_fold_into_plain_names():
    row, fired = _norm(
        r"t_{i}^{arr} + v_{i}^{c} + \mathit{tau}_{k}^{de} + x_{k}^{\text{end}}"
        r" + t_{i,s}^{d e p} + Y_{i,s}^{1} + q^{*} + r^* \forall i \in \mathcal{I}, k \in \mathcal{K}, s \in \mathcal{S}"
    )
    assert row.startswith(
        r"t_arr_{i} + v_c_{i} + tau_de_{k} + x_end_{k} + t_dep_{i,s} + Y_1_{i,s} + q_star + r_star"
    )
    assert {"superscript_label", "bare_sup_brace"} <= fired


def test_label_subscripts_fold_into_plain_names():
    row, fired = _norm(
        r"h_{min} + Z_{1} + z_{1} + t_{0} + x_{i, \mathit{dep}} + f_{cost}"
        r" \forall i \in \mathcal{I}"
    )
    # t is declared with a shape, so t_{0} is a fixed-element reference (#54)
    # and stays; Z_{1}/z_{1} have no shape and become plain names.
    assert row.startswith(r"h_min + Z_1 + z_1 + t_{0} + x_dep_{i} + f_cost")
    assert "label_subscript" in fired


def test_complex_scripts_are_left_for_the_parser_to_refuse():
    src = r"a_{k}^{v \left(u\right)} + a_{i}^{m_{d}} + x_{u \rightarrow v}^{e} \forall i \in \mathcal{I}, k \in \mathcal{K}"
    row, fired = _norm(src)
    # Nested or delimited superscripts stay as written; a label superscript
    # over an unresolvable subscript folds into the name and leaves the
    # subscript for the parser to refuse.
    assert row == (
        r"a_{k}^{v \left(u\right)} + a_{i}^{m_{d}} + x_e_{u \rightarrow v}"
        r" \forall i \in \mathcal{I}, k \in \mathcal{K}"
    )
    assert "superscript_index" not in fired
    r = _probe(
        r"  \min\quad & \sum_{e \in \mathcal{E}} c \cdot x_{e}^{k \left(e\right)} \tag{cost} \\"
    )
    assert not r.ok
    assert "trailing" in r.failures[0].message


def test_script_rules_never_touch_the_header_or_binders():
    doc = (
        _CTX_HEADER
        + "\\begin{align}\n  & \\sum_{i \\in \\mathcal{I}} t_{i}^{arr} \\tag{r} \\\\\n\\end{align}\n"
    )
    text, _ = normalize_latex(doc, source="ctx.tex")
    assert text.startswith(_CTX_HEADER)
    assert r"\sum_{i \in \mathcal{I}} t_arr_{i}" in text


def test_unbraced_subscript_regression_round_trips():
    # Issue #62: B_u \cdot w_u used to ingest as a literal term with a string
    # coefficient and not round-trip. Now the scripts brace against the
    # declarations and the row is the ordinary bound product.
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} w_e \cdot x_e \tag{cost} \\")
    assert r.ok, r.failures
    (term,) = r.formulation.objective.terms
    assert (term.ref, term.ref_kind, term.coefficient) == ("x", "variable", "w")
    assert [b.expr for b in term.bindings] == ["e"]
    again = from_canonical_latex(to_canonical_latex(r.formulation))
    assert again.model_dump() == r.formulation.model_dump()


def test_undeclared_referent_and_coefficient_are_refused_by_name():
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} c \cdot y_{e} \tag{cost} \\")
    assert not r.ok
    assert "not a declared variable or parameter" in r.failures[0].message
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} q \cdot x_{e} \tag{cost} \\")
    assert not r.ok
    assert "not a declared parameter" in r.failures[0].message
    r = _probe(r"  \min\quad & \sum_{e \in \mathcal{E}} x \cdot x_{e} \tag{cost} \\")
    assert not r.ok
    assert "nonlinear" in r.failures[0].message


def test_script_resolution_is_deterministic_and_versioned():
    src = r"t_{i}^{arr} + x_{i}^{k} + h_{min} + B_u \forall i \in \mathcal{I}, k \in \mathcal{K}, u \in \mathcal{T}"
    doc = _CTX_HEADER + "\\begin{align}\n  & " + src + " \\tag{r} \\\\\n\\end{align}\n"
    a1, p1 = normalize_latex(doc, source="ctx.tex")
    a2, p2 = normalize_latex(doc, source="ctx.tex")
    assert a1 == a2
    assert p1.rewrites == p2.rewrites
    assert {r.rules_version for r in p1.rewrites} == {"rewrite-2026.09.0"}
