# Data model

`lp2graph` represents an optimization formulation as a structured JSON
document validated against
[`schema/canonical.schema.json`](../schema/canonical.schema.json) and
mirrored by the pydantic types in
[`optgraph.core.model`](../src/optgraph/core/model.py).

## Top-level structure

```json
{
  "schema_version": "0.1.0",
  "id": "mip_2_1_big_m",
  "name": "2.1 Big-M ordering MIP",
  "family": "milp",
  "indices":    [...],
  "parameters": [...],
  "variables":  [...],
  "constraints":[...],
  "objective":  { "sense": "min", "terms": [...] }
}
```

`id` is a stable lowercase identifier. `family` is one of `lp`, `mip`,
`milp`. The semantic validator enforces family invariants — an `lp`
must not have integer or binary variables; a `milp` must have at least
one.

## Indices

```json
{ "name": "T", "ordered": true, "cyclic": false }
```

An *ordered* index admits offsets like `t-1`. A *cyclic* index wraps
modulo cardinality (PESP). Bindings can override the default by
declaring `modulo` explicitly.

## Parameters

```json
{ "name": "M", "kind": "big_m" }
{ "name": "r", "shape": ["I"], "kind": "vector" }
```

`kind` ∈ `{scalar, vector, matrix, big_m, tolerance}`. The `big_m` and
`tolerance` tags are not just decoration — they feed presence flags
(`has_big_m`) and surface in the renderer.

## Variable templates

```json
{ "name": "y", "shape": ["I", "I"], "domain": "binary", "role": "indicator" }
```

A *template* `y[I, I]` represents the family of `|I|^2` binary
variables. The schema view exposes the template; the ground view
exposes the instances. `role` distinguishes primary, auxiliary, slack,
and indicator variables.

## Constraint templates

```json
{
  "name": "order_a",
  "kind": "big_m",
  "quantifiers": [
    { "index": "i", "over": "I" },
    { "index": "j", "over": "I", "restriction": "ne_other", "restriction_other": "i" }
  ],
  "comparator": "ge",
  "lhs": [ ... terms ... ],
  "rhs": [ ... terms ... ]
}
```

The body is a comparison of two term lists. The semantic validator
enforces that every quantifier's `over` is a declared index family,
that `restriction_other` references another quantifier in the same
constraint, and that every term's `bindings` cover exactly the
referenced template's shape.

A quantifier may carry an attribute-based selection predicate:

```json
{ "index": "t", "over": "T", "where": { "parameter": "is_local", "equals": true } }
```

The named parameter must be shaped exactly over the quantifier's `over`
index. Schema and hybrid views surface the predicate as a label on the
quantifier; the ground view applies it as a filter at materialization
time, requiring the parameter's concrete values via the
`parameter_values` argument to `ground()`.

## Terms

The four-tuple `(ref, bindings, role, sign)` plus optional `operator`
and `operator_over` is what makes the schema/hybrid/ground views
derivable from a single source of truth.

```json
{
  "ref": "x",
  "ref_kind": "variable",
  "bindings": [
    { "index": "I", "expr": "i" },
    { "index": "T", "expr": "t-1", "offset": -1 }
  ],
  "coefficient": "M",
  "sign": -1,
  "role": "lhs",
  "operator": "sum",
  "operator_over": ["T"]
}
```

| Field | Purpose |
|---|---|
| `ref` | Name of a variable template, parameter, or `"one"` for literals. |
| `ref_kind` | `variable` / `parameter` / `literal`. |
| `constant` | Shorthand for a numeric constant term: `{ "constant": 3599, "role": "rhs" }`. Mutually exclusive with `ref`/`coefficient`; normalized at parse time to a literal term. |
| `bindings` | One per index slot of the referenced template. `expr` is in the constraint's quantifier scope; `offset` is the numeric offset extracted; `modulo` overrides the per-index cyclic flag. |
| `coefficient` | Number or parameter name. |
| `sign` | `+1` or `-1`; multiplied with the coefficient at evaluation time but kept separate so renderers show it explicitly. |
| `role` | Drives edge coloring: `lhs`, `rhs`, `objective`, `slack`, `aux`. |
| `operator` | Aggregation: `none`, `sum`, `max`, `min`, `abs`, `indicator`, `modulo`. |
| `operator_over` | Index families the operator aggregates over. |

## Objective

```json
{
  "sense": "min",
  "name": "weighted_sum",
  "combination": "weighted_sum",
  "terms": [ ... ]
}
```

Objectives are first-class. `combination` is `sum`, `lexicographic`,
or `weighted_sum`. Multiple terms with the same `ref` but different
operators or coefficients are permitted — they remain distinct edges
in the schema view.

## Validation

Two-phase: **JSON Schema** for the document shape (handled by
`jsonschema`), then **semantic validation** (handled by
`optgraph.core.validate`) for cross-cutting invariants:

- Every index, parameter, and variable name referenced is declared.
- Every binding covers exactly the referenced template's shape.
- Every quantifier `restriction_other` resolves to another quantifier
  on the same constraint.
- Family consistency: LP has no integer/binary; MILP has at least one.

Errors are aggregated into a single `ValidationError` so all problems
appear in one report rather than one fix at a time.
