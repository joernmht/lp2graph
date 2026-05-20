# Adding a new formulation — worked example

This walkthrough adds a hypothetical *1.7 reduced-cyclic LP* —
a continuous LP variant of PESP without the integer wrap variables.

## 1. Pick the file location

```
formulations/constraints/lp_1_7_reduced_cyclic.json
```

`id` field inside the document must match the filename stem.

## 2. Sketch the algebraic form

```
min   sum_{(i,j)} (t_j - t_i - l_{ij})^2     (mocked as L1: |t_j - t_i - l_{ij}|)
s.t.  t_j - t_i  >= l_{ij} mod T_period      forall (i,j)
      0 <= t_i  <  T_period                  forall i
```

## 3. Encode as JSON

Mirror the existing `mip_2_8_pesp.json` but drop the integer `k`
variable and add `modulo` bindings on `t`:

```json
{
  "schema_version": "0.1.0",
  "id": "lp_1_7_reduced_cyclic",
  "name": "1.7 Reduced-cyclic LP",
  "family": "lp",
  "indices": [
    { "name": "E" },
    { "name": "T", "ordered": true, "cyclic": true }
  ],
  "parameters": [
    { "name": "l", "shape": ["E", "E"], "kind": "matrix" },
    { "name": "T_period", "kind": "scalar" }
  ],
  "variables": [
    { "name": "t", "shape": ["E"], "domain": "non_negative" }
  ],
  "constraints": [
    {
      "name": "cyclic_offset",
      "kind": "modulo",
      "quantifiers": [
        { "index": "i", "over": "E" },
        { "index": "j", "over": "E", "restriction": "ne_other", "restriction_other": "i" }
      ],
      "comparator": "ge",
      "lhs": [
        { "ref": "t", "ref_kind": "variable", "bindings": [{ "index": "E", "expr": "j", "modulo": "T" }], "role": "lhs" },
        { "ref": "t", "ref_kind": "variable", "bindings": [{ "index": "E", "expr": "i" }], "sign": -1, "role": "lhs" }
      ],
      "rhs": [
        { "ref": "l", "ref_kind": "parameter", "bindings": [{ "index": "E", "expr": "i" }, { "index": "E", "expr": "j" }], "role": "rhs" }
      ]
    }
  ],
  "objective": {
    "sense": "min",
    "name": "tension",
    "terms": [
      { "ref": "t", "ref_kind": "variable", "bindings": [{ "index": "E", "expr": "i" }], "operator": "sum", "operator_over": ["E"], "role": "objective" }
    ]
  }
}
```

## 4. Validate

```bash
lp2graph validate formulations/constraints/lp_1_7_reduced_cyclic.json
```

If validation fails, the error report lists every issue. Common
problems:

- Missing binding for one of a template's shape slots.
- Quantifier `over` referencing an undeclared index.
- `ref` pointing at a variable that does not exist.

## 5. Eyeball the rendering

```bash
lp2graph render formulations/constraints/lp_1_7_reduced_cyclic.json --view hybrid --output preview.svg
```

Open `preview.svg`. The hybrid view should clearly show the modulo
binding on the LHS edge.

## 6. Add to the catalog index and commit

Edit `docs/index.md` to add a row in the catalog table, then commit
using the conventional commit format:

```
feat(catalog): add 1.7 reduced-cyclic LP formulation

Closes #N
```
