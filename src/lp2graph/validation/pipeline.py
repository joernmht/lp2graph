"""End-to-end validation pipeline for (LLM-)generated LP/MILP artifacts.

The three entry points never raise on bad input; they always return a
:class:`~lp2graph.validation.report.ValidationReport`:

- :func:`validate_text` — raw text or bytes in any supported format
  (canonical JSON, LaTeX, LP, MPS, GAMS, AMPL, JuMP). The format is
  sniffed when not given, and a failed parse falls back to the other
  plausible formats before giving up.
- :func:`validate_path` — the same, reading a file (format defaults to
  the extension).
- :func:`validate_formulation` — an already-parsed canonical model
  (e.g. from ``lp2graph.interop.from_pulp``); runs the semantic,
  structural, and solve stages only.

Stages: decode -> detect (fence/unicode/truncation repair, format
sniffing) -> parse (with fallback) -> semantics (cross-reference
invariants) -> structure (completeness, coherence, unused symbols,
degenerate constraints) -> solve (optional CBC/HiGHS/Gurobi smoke
check on a synthesized all-ones instance, skipped gracefully when no
solver is installed).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lp2graph.core.model import Formulation
from lp2graph.core.validate import ValidationError, validate
from lp2graph.metrics.structural import model_coherence, model_completeness
from lp2graph.validation.detect import (
    EXT_FMT,
    FORMATS,
    decode_bytes,
    extract_fenced,
    normalize_unicode,
    resolve_fmt,
    sniff_format,
    truncation_checks,
)
from lp2graph.validation.report import Check, ValidationReport

if TYPE_CHECKING:
    from lp2graph.core.model import Term
    from lp2graph.solve.instance import Instance

#: Upper bound on parse-fallback attempts (keeps a pathological input cheap).
_MAX_PARSE_ATTEMPTS = 4

#: Smoke-instance defaults: every index family gets this cardinality and
#: every parameter this value (big-M parameters get a larger constant so
#: indicator constructions stay non-binding).
_SMOKE_CARD = 3
_SMOKE_VALUE = 1.0
_SMOKE_BIG_M = 100.0


def validate_text(
    text: str | bytes,
    *,
    fmt: str | None = None,
    source: str = "<text>",
    solve_check: bool = True,
    instance: Instance | None = None,
    solver: str = "cbc",
    time_limit: float = 20.0,
) -> ValidationReport:
    """Validate a model given as raw text (or bytes) in any supported format."""
    checks: list[Check] = []

    if isinstance(text, bytes):
        text = decode_bytes(text, checks=checks)

    fmt = resolve_fmt(fmt)
    if fmt is not None and fmt not in FORMATS:
        checks.append(
            Check(
                stage="detect",
                level="error",
                code="unknown-format",
                message=f"unknown format {fmt!r}; supported: {', '.join(FORMATS)}.",
            )
        )
        return ValidationReport(source=source, fmt=None, checks=tuple(checks))

    if not text.strip():
        checks.append(
            Check(stage="decode", level="error", code="empty-input", message="input is empty.")
        )
        return ValidationReport(source=source, fmt=fmt, checks=tuple(checks))

    text, hint = extract_fenced(text, checks=checks)
    if not text.strip():
        checks.append(
            Check(
                stage="detect",
                level="error",
                code="empty-input",
                message="nothing left after removing markdown fences.",
            )
        )
        return ValidationReport(source=source, fmt=fmt, checks=tuple(checks))

    if fmt is not None:
        candidates = [fmt]
    else:
        ranked = sniff_format(text)
        candidates = [] if hint is None else [hint]
        candidates += [name for name, _ in ranked if name not in candidates]
        if not candidates:
            checks.append(
                Check(
                    stage="detect",
                    level="error",
                    code="format-undetected",
                    message="could not determine the input format; pass fmt= explicitly "
                    f"(one of: {', '.join(FORMATS)}).",
                )
            )
            return ValidationReport(source=source, fmt=None, checks=tuple(checks))
        checks.append(
            Check(
                stage="detect",
                level="ok",
                code="format-detected",
                message=f"detected format {candidates[0]!r}.",
                detail="candidates: " + ", ".join(f"{n}={s}" for n, s in ranked),
            )
        )

    text = normalize_unicode(text, candidates[0], checks=checks)
    truncation_checks(text, candidates[0], checks=checks)

    formulation, used_fmt = _parse_with_fallback(text, candidates, source, checks)
    if formulation is None:
        return ValidationReport(source=source, fmt=used_fmt, checks=tuple(checks))

    return _finish(
        formulation,
        source=source,
        fmt=used_fmt,
        checks=checks,
        run_semantics=False,  # every successful parse path above validated already
        solve_check=solve_check,
        instance=instance,
        solver=solver,
        time_limit=time_limit,
    )


def validate_path(
    path: str | Path,
    *,
    fmt: str | None = None,
    solve_check: bool = True,
    instance: Instance | None = None,
    solver: str = "cbc",
    time_limit: float = 20.0,
) -> ValidationReport:
    """Validate a model file; the format defaults to the file extension."""
    p = Path(path)
    checks: list[Check] = []
    try:
        data = p.read_bytes()
    except OSError as exc:
        checks.append(
            Check(
                stage="decode",
                level="error",
                code="unreadable",
                message=f"cannot read {p}: {exc}.",
            )
        )
        return ValidationReport(source=str(p), fmt=resolve_fmt(fmt), checks=tuple(checks))
    if fmt is None:
        fmt = EXT_FMT.get(p.suffix.lower())
    return validate_text(
        data,
        fmt=fmt,
        source=str(p),
        solve_check=solve_check,
        instance=instance,
        solver=solver,
        time_limit=time_limit,
    )


def validate_formulation(
    f: Formulation,
    *,
    source: str = "<formulation>",
    solve_check: bool = True,
    instance: Instance | None = None,
    solver: str = "cbc",
    time_limit: float = 20.0,
) -> ValidationReport:
    """Validate an already-parsed canonical model (semantics + structure + solve)."""
    return _finish(
        f,
        source=source,
        fmt="formulation",
        checks=[],
        run_semantics=True,
        solve_check=solve_check,
        instance=instance,
        solver=solver,
        time_limit=time_limit,
    )


# ---------------------------------------------------------------------------
# Parse stage
# ---------------------------------------------------------------------------


def _parse_with_fallback(
    text: str,
    candidates: list[str],
    source: str,
    checks: list[Check],
) -> tuple[Formulation | None, str | None]:
    """Try each candidate format in order; earlier failures become warnings
    when a later one succeeds, errors when nothing does.

    A *semantic* failure (the text parsed in some format but the model's
    cross-references are broken) is terminal: falling back to another
    format at that point would misdiagnose a genuinely-parsed model.
    """
    from lp2graph.mining.ingest import ingest

    attempts: list[Check] = []
    for fmt in candidates[:_MAX_PARSE_ATTEMPTS]:
        if fmt == "json":
            import json

            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                attempts.append(_attempt_failure("json", f"invalid JSON: {exc}"))
                continue
            try:
                f = Formulation.model_validate(data)
            except Exception as exc:  # pydantic.ValidationError
                attempts.append(_attempt_failure("json", f"not a canonical formulation: {exc}"))
                continue
            try:
                validate(f)
            except ValidationError as exc:
                _flush_attempts(attempts, checks, succeeded=True)
                checks.append(_parse_ok("json"))
                for err in exc.errors or [str(exc)]:
                    checks.append(
                        Check(stage="semantics", level="error", code="semantic", message=err)
                    )
                return f, "json"
            _flush_attempts(attempts, checks, succeeded=True)
            checks.append(_parse_ok("json"))
            checks.append(_semantics_ok())
            return f, "json"

        result = ingest(text, fmt=fmt)
        if result.formulation is not None:
            _flush_attempts(attempts, checks, succeeded=True)
            checks.append(_parse_ok(fmt))
            checks.append(_semantics_ok())
            return result.formulation, fmt

        semantic = [fl for fl in result.failures if fl.stage == "validate"]
        if semantic:
            _flush_attempts(attempts, checks, succeeded=True)
            checks.append(_parse_ok(fmt))
            for fl in semantic:
                checks.append(
                    Check(
                        stage="semantics",
                        level="error",
                        code="semantic",
                        message=fl.message,
                        detail=fl.detail,
                    )
                )
            return None, fmt

        detail = "; ".join(
            f"[{fl.stage}] {fl.message}" + (f" ({fl.detail})" if fl.detail else "")
            for fl in result.failures
        )
        attempts.append(_attempt_failure(fmt, detail))

    _flush_attempts(attempts, checks, succeeded=False)
    checks.append(
        Check(
            stage="parse",
            level="error",
            code="all-parsers-failed",
            message="no supported parser accepted the input "
            f"(tried: {', '.join(candidates[:_MAX_PARSE_ATTEMPTS])}).",
        )
    )
    return None, None


def _attempt_failure(fmt: str, detail: str) -> Check:
    return Check(
        stage="parse",
        level="error",
        code="parse-failed",
        message=f"not parseable as {fmt}.",
        detail=detail,
    )


def _flush_attempts(attempts: list[Check], checks: list[Check], *, succeeded: bool) -> None:
    """Record earlier attempts: warnings if a later parse won, errors if not."""
    for a in attempts:
        if succeeded:
            checks.append(
                Check(
                    stage="parse",
                    level="warn",
                    code="parse-fallback",
                    message=a.message + " (fell back to another format)",
                    detail=a.detail,
                )
            )
        else:
            checks.append(a)


def _parse_ok(fmt: str) -> Check:
    return Check(stage="parse", level="ok", code="parse-ok", message=f"parsed as {fmt}.")


def _semantics_ok() -> Check:
    return Check(
        stage="semantics",
        level="ok",
        code="semantics-ok",
        message="cross-reference invariants hold.",
    )


# ---------------------------------------------------------------------------
# Structure + solve stages
# ---------------------------------------------------------------------------


def _finish(
    f: Formulation,
    *,
    source: str,
    fmt: str | None,
    checks: list[Check],
    run_semantics: bool,
    solve_check: bool,
    instance: Instance | None,
    solver: str,
    time_limit: float,
) -> ValidationReport:
    if run_semantics:
        try:
            validate(f)
            checks.append(_semantics_ok())
        except ValidationError as exc:
            for err in exc.errors or [str(exc)]:
                checks.append(Check(stage="semantics", level="error", code="semantic", message=err))

    # A model with broken cross-references cannot be viewed or grounded;
    # downstream stages would only crash on the same defects.
    semantics_broken = any(c.stage == "semantics" and c.level == "error" for c in checks)
    if semantics_broken:
        checks.append(
            Check(
                stage="structure",
                level="skip",
                code="skipped-after-semantics",
                message="structure and solve checks skipped: fix the semantic errors first.",
            )
        )
        return ValidationReport(source=source, fmt=fmt, checks=tuple(checks), formulation=f)

    try:
        checks.extend(_structure_checks(f))
    except Exception as exc:  # the report contract: never raise on bad input
        checks.append(
            Check(
                stage="structure",
                level="error",
                code="structure-crashed",
                message=f"structural analysis raised {type(exc).__name__}: {exc}",
            )
        )

    solve_info: dict[str, object] | None = None
    if solve_check:
        solve_checks, solve_info = _solve_checks(
            f, instance=instance, solver=solver, time_limit=time_limit
        )
        checks.extend(solve_checks)
    else:
        checks.append(
            Check(
                stage="solve",
                level="skip",
                code="solve-disabled",
                message="solve check disabled by caller.",
            )
        )

    return ValidationReport(
        source=source, fmt=fmt, checks=tuple(checks), formulation=f, solve=solve_info
    )


def _structure_checks(f: Formulation) -> list[Check]:
    checks: list[Check] = []

    missing = []
    if f.objective is None:
        missing.append("objective")
    if not f.variables:
        missing.append("variables")
    if not f.constraints:
        missing.append("constraints")
    if model_completeness(f).value == 0:
        checks.append(
            Check(
                stage="structure",
                level="error",
                code="incomplete",
                message="not a complete model: missing " + ", ".join(missing) + ".",
            )
        )
    else:
        checks.append(
            Check(
                stage="structure",
                level="ok",
                code="complete",
                message="objective, >=1 variable, and >=1 constraint present.",
            )
        )

    from lp2graph.views.schema import schema

    if model_coherence(schema(f)).value == 0:
        checks.append(
            Check(
                stage="structure",
                level="warn",
                code="incoherent",
                message="schema graph is disconnected: some entities are not "
                "coupled to the rest of the model.",
            )
        )

    declared = (
        [("index", i.name) for i in f.indices]
        + [("parameter", p.name) for p in f.parameters]
        + [("variable", v.name) for v in f.variables]
    )
    names = [n for _, n in declared]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        checks.append(
            Check(
                stage="structure",
                level="error",
                code="duplicate-names",
                message="duplicate declaration names: " + ", ".join(dupes) + ".",
            )
        )

    used_vars, used_params, used_indices = _collect_references(f)
    for v in f.variables:
        used_indices.update(v.shape)
    for p in f.parameters:
        used_indices.update(p.shape)

    unused_vars = sorted({v.name for v in f.variables} - used_vars)
    unused_params = sorted({p.name for p in f.parameters} - used_params)
    unused_indices = sorted({i.name for i in f.indices} - used_indices)
    for kind, unused in (
        ("variable", unused_vars),
        ("parameter", unused_params),
        ("index", unused_indices),
    ):
        if unused:
            checks.append(
                Check(
                    stage="structure",
                    level="warn",
                    code="unused-symbol",
                    message=f"declared but never referenced {kind}(s): " + ", ".join(unused) + ".",
                )
            )

    for c in f.constraints:
        if not any(t.ref_kind == "variable" for t in (*c.lhs, *c.rhs)):
            checks.append(
                Check(
                    stage="structure",
                    level="warn",
                    code="constant-constraint",
                    message=f"constraint {c.name!r} references no decision variable.",
                )
            )
    if f.objective is not None and not any(t.ref_kind == "variable" for t in f.objective.terms):
        checks.append(
            Check(
                stage="structure",
                level="warn",
                code="constant-objective",
                message="objective references no decision variable.",
            )
        )

    for v in f.variables:
        if v.lower is not None and v.upper is not None and v.lower > v.upper:
            checks.append(
                Check(
                    stage="structure",
                    level="error",
                    code="bound-conflict",
                    message=f"variable {v.name!r} has lower bound {v.lower} > "
                    f"upper bound {v.upper}.",
                )
            )

    checks.append(
        Check(
            stage="structure",
            level="ok",
            code="counts",
            message=f"{len(f.variables)} variable(s), {len(f.constraints)} constraint(s), "
            f"{len(f.parameters)} parameter(s), {len(f.indices)} index famil(ies).",
        )
    )
    return checks


def _collect_references(f: Formulation) -> tuple[set[str], set[str], set[str]]:
    """Names of variables / parameters / indices actually referenced."""
    used_vars: set[str] = set()
    used_params: set[str] = set()
    used_indices: set[str] = set()

    def scan(terms: tuple[Term, ...]) -> None:
        for t in terms:
            if t.ref_kind == "variable":
                used_vars.add(t.ref)
            elif t.ref_kind == "parameter":
                used_params.add(t.ref)
            if isinstance(t.coefficient, str):
                used_params.add(t.coefficient)
            for b in t.bindings:
                if b.modulo is not None:
                    used_indices.add(b.modulo)
            used_indices.update(t.operator_over)

    for c in f.constraints:
        scan(c.lhs)
        scan(c.rhs)
        for q in c.quantifiers:
            used_indices.add(q.over)
            if q.where is not None:
                used_params.add(q.where.parameter)
    if f.objective is not None:
        scan(f.objective.terms)
    return used_vars, used_params, used_indices


def _solve_checks(
    f: Formulation,
    *,
    instance: Instance | None,
    solver: str,
    time_limit: float,
) -> tuple[list[Check], dict[str, object] | None]:
    checks: list[Check] = []

    import importlib.util

    if importlib.util.find_spec("pulp") is None:
        checks.append(
            Check(
                stage="solve",
                level="skip",
                code="solver-missing",
                message="pulp is not installed; solve check skipped "
                '(pip install "lp2graph[solver]").',
            )
        )
        return checks, None

    from lp2graph.solve import Instance as _Instance
    from lp2graph.solve import make_solver
    from lp2graph.solve.grounder import UnsupportedModel
    from lp2graph.solve.grounder import solve as _solve

    synthesized = instance is None
    # A synthesized instance only excuses infeasibility when it actually
    # invents data; a flat model (no indices, no parameters) carries its
    # real coefficients, so a bad status there is a genuine finding.
    placeholder_data = synthesized and bool(f.indices or f.parameters)
    if instance is None:
        instance = _smoke_instance(f, _Instance)
        if placeholder_data:
            checks.append(
                Check(
                    stage="solve",
                    level="ok",
                    code="smoke-instance",
                    message=f"no instance given: synthesized cardinalities={_SMOKE_CARD}, "
                    f"parameters={_SMOKE_VALUE} (big-M={_SMOKE_BIG_M}).",
                )
            )

    try:
        backend = make_solver(solver, time_limit=max(1.0, time_limit))
    except ValueError as exc:
        checks.append(Check(stage="solve", level="error", code="unknown-solver", message=str(exc)))
        return checks, None

    try:
        result = _solve(f, instance, solver=backend)
    except UnsupportedModel as exc:
        checks.append(
            Check(
                stage="solve",
                level="skip",
                code="grounder-unsupported",
                message=f"grounder cannot solve this model: {exc}; structural checks still apply.",
            )
        )
        return checks, None
    except Exception as exc:  # grounding must never crash the report
        checks.append(
            Check(
                stage="solve",
                level="error",
                code="grounding-failed",
                message=f"grounding/solving raised {type(exc).__name__}: {exc}",
            )
        )
        return checks, None

    info: dict[str, object] = {
        "status": result.status,
        "objective": result.objective,
        "n_vars": result.n_vars,
        "n_constraints": result.n_constraints,
        "solver": result.solver,
        "instance_synthesized": synthesized,
    }
    if result.status == "optimal":
        checks.append(
            Check(
                stage="solve",
                level="ok",
                code="solve-optimal",
                message=f"solved to optimality; objective = {result.objective}.",
            )
        )
    elif result.status == "infeasible":
        checks.append(
            Check(
                stage="solve",
                level="warn" if placeholder_data else "error",
                code="infeasible",
                message="model is infeasible on the synthesized smoke instance "
                "(may be the placeholder data, may be a modeling error)."
                if placeholder_data
                else "model is infeasible.",
            )
        )
    elif result.status == "unbounded":
        checks.append(
            Check(
                stage="solve",
                level="warn" if placeholder_data else "error",
                code="unbounded",
                message="objective is unbounded: a constraint or bound is likely "
                "missing, or the optimization sense is wrong.",
            )
        )
    else:
        checks.append(
            Check(
                stage="solve",
                level="warn",
                code="solver-status",
                message=f"solver finished with status {result.status!r} "
                f"(time limit {time_limit}s?).",
            )
        )
    return checks, info


def _smoke_instance(f: Formulation, instance_cls: type[Instance]) -> Instance:
    """All-ones placeholder data: enough to ground and smoke-solve a template."""
    cards = {i.name: _SMOKE_CARD for i in f.indices}
    params: dict[str, object] = {}
    for p in f.parameters:
        value = _SMOKE_BIG_M if p.kind == "big_m" else _SMOKE_VALUE
        params[p.name] = _nested(value, [cards.get(s, _SMOKE_CARD) for s in p.shape])
    return instance_cls(cardinalities=cards, parameters=params)


def _nested(value: float, dims: list[int]) -> object:
    if not dims:
        return value
    return [_nested(value, dims[1:]) for _ in range(dims[0])]


__all__ = ["validate_formulation", "validate_path", "validate_text"]
