# Validating generated models

`lp2graph.validation` answers the question an LLM (or its harness) asks
about its own output: **"is the LP/MILP I just generated well-formed,
complete, and solvable?"** It accepts raw text in any supported format,
detects and repairs the usual faults of generated output, and returns a
structured report. It never raises on bad input.

Where [`lp2graph.validate`](data-model.md) checks the cross-reference
invariants of an already-parsed canonical model, this pipeline covers the
whole journey from untrusted text to a solver verdict.

## Quick start

Command line (exit code 0 unless the verdict is `invalid`):

```bash
lp2graph validate model.lp                  # any of .json/.tex/.lp/.mps/.gms/.mod/.jl
lp2graph validate answer.txt --json         # unknown extension: format is sniffed
lp2graph validate model.tex --no-solve      # structural checks only
lp2graph validate model.json --instance data.json --solver highs
```

Python:

```python
from lp2graph.validation import validate_text

report = validate_text(llm_output)          # bytes or str; format sniffed
print(report.summary())                     # human-readable
report.to_json()                            # machine-readable
assert report.verdict != "invalid"          # "valid" | "valid_with_warnings" | "invalid"
```

For a model that only exists as a live solver object (the deterministic
core never executes generated code), go through
[interop](interop.md) first:

```python
from lp2graph.interop import from_pulp
from lp2graph.validation import validate_formulation

report = validate_formulation(from_pulp(prob))
```

## Pipeline stages

Every observation is a `Check(stage, level, code, message, detail)` with
level `ok`, `warn`, `error`, or `skip`. Any `error` makes the verdict
`invalid`.

1. **decode** — bytes to text: UTF-8 with latin-1 fallback, BOM and NUL
   stripping (`not-utf8`, `bom-stripped`, `nul-bytes`).
2. **detect** — repairs and diagnostics for generated output:
   - markdown code fences are extracted, surrounding prose discarded
     (`markdown-fences`); a fence language tag becomes a format hint; an
     unterminated final fence is flagged as truncation
     (`unterminated-fence`);
   - unicode look-alikes (U+2212 minus, `≤`/`≥`, no-break space, smart
     quotes) are replaced with ASCII (`unicode-normalized`) — LaTeX input
     only gets the sign/space subset;
   - truncation heuristics: input ending mid-expression
     (`dangling-tail`), unbalanced braces or `\begin`/`\end`
     environments, MPS without `ENDATA`;
   - format sniffing over content indicators when no format is given
     (`format-detected` / `format-undetected`).
3. **parse** — routes to the deterministic parsers (canonical JSON, the
   [M1b LaTeX normalizer](mining.md), and the LP/MPS/GAMS/AMPL/JuMP
   readers from [interop](interop.md)). If the sniffed format fails, the
   other plausible formats are tried before giving up; superseded
   attempts are downgraded to warnings (`parse-fallback`). Python source
   is recognized but *not executed*: the report points to
   `interop.from_pulp` / `from_gurobipy` / `from_pyomo`.
4. **semantics** — the cross-reference invariants of
   `lp2graph.validate` (undefined entities, mismatched bindings, unknown
   quantifier indices). Semantic failures are terminal: downstream
   stages are skipped rather than crashed.
5. **structure** — model-level detectors: completeness (objective + ≥1
   variable + ≥1 constraint; `incomplete` is an error), schema-graph
   coherence (`incoherent`), duplicate declaration names, declared-but-
   unreferenced symbols (`unused-symbol`), constraints or objectives
   that reference no decision variable, conflicting variable bounds.
6. **solve** — an optional grounding smoke check (CBC by default, HiGHS
   or Gurobi by name). A template model without instance data gets a
   synthesized all-ones instance (cardinality 3 per index family,
   parameters 1.0, big-M 100.0); a bad status on placeholder data is a
   warning, while a flat model (real coefficients from LP/MPS/code) that
   is infeasible or unbounded is an error. Skipped gracefully when pulp
   is not installed or the grounder does not support a feature.

## Reading the report

```json
{
  "pipeline_version": "validate-2026.07.0",
  "source": "model.lp",
  "fmt": "lp",
  "verdict": "valid_with_warnings",
  "formulation": {"id": "lp_model", "name": "lp_model", "family": "lp"},
  "counts": {"ok": 5, "warn": 1, "error": 0, "skip": 0},
  "checks": [{"stage": "detect", "level": "warn", "code": "markdown-fences", "...": "..."}],
  "solve": {"status": "optimal", "objective": 6.0, "n_vars": 2,
            "n_constraints": 1, "solver": "PULP_CBC_CMD",
            "instance_synthesized": true}
}
```

`report.formulation` holds the parsed canonical
`Formulation` when the artifact got that far — ready for views, metrics,
exports, or the codec.

Determinism holds throughout: fixed detector tables, fixed sniffing
tie-breaks, and a `pipeline_version` stamp on every report.
