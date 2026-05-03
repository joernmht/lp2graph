# Add a formulation

The catalog lives in [`formulations/`](../formulations/). Adding a new
formulation is the single most useful contribution.

## Checklist

1. Create a file `formulations/<group>/<id>.json` where `<group>` is
   `constraints/` or `objectives/` and `<id>` matches the `id` field
   inside the document.
2. Set `schema_version` to the current value (`"0.1.0"`).
3. Declare every index family before referencing it.
4. Declare parameters and variable templates with their full shape.
5. For each constraint:
    - quantifiers reference declared indices, with restrictions if needed
      (`ne_other`, `lt_other`, `ordered_pair`, …).
    - terms have one `binding` per shape slot of the referenced template.
    - `role` is set on every term (`lhs`, `rhs`, `objective`, `slack`,
      `aux`).
    - aggregations use `operator` and `operator_over`.
6. If the formulation has an objective, set `sense`, `name`, optionally
   `combination`, and a list of terms.
7. Run `optgraph validate formulations/.../<id>.json` — both the JSON
   Schema and semantic validators must pass.
8. Run `optgraph render formulations/.../<id>.json --view hybrid
   --output preview.svg` and look at the result. The structure should
   match what you intended.
9. Add the file to the catalog table in [`docs/index.md`](index.md).
10. Open a PR using the `new-formulation` template.

## What to avoid

- **Hidden indices.** If a constraint applies "for all i", that `i`
  must be a quantifier with an `over`. Never let an index be implicit
  in a string.
- **Embedded coefficients.** A term's coefficient lives in the
  `coefficient` field, not concatenated into the variable name.
- **Multi-purpose variables.** If `x[I]` means two different things in
  two different parts of the model, declare two templates.
- **Fragile references to `one`.** Use `{"ref": "one", "ref_kind":
  "literal", "coefficient": <number>, "role": "rhs"}` for constant
  RHS terms; `coefficient` is where the value goes.

## Example diff

```diff
+ formulations/constraints/lp_1_3_station_specific.json
+ docs/index.md     # add a row in the catalog table
```

## Tests

Schema validation runs over every file in the catalog automatically:
`pytest tests/test_schema.py`. View derivation and metrics tests are
parameterized over the catalog where it makes sense; if your new
formulation exercises a new schema feature, add a targeted test in
`tests/test_views.py` or `tests/test_metrics.py` to lock the behavior.
