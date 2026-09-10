# ADR-0010: Codec round-trip fidelity is canonical-normal-form equivalence, not byte-identity

- **Status:** accepted
- **Date:** 2026-07-15

## Context

Paper 1's central claim rests on the LaTeX codec being **reversible**: a
`Formulation` can be emitted to canonical, paper-style LaTeX with
`to_canonical_latex` and parsed back with `from_canonical_latex` (the
`text ⇄ graph` interface). "Reversible" needs a precise definition, because the
codec is *not* a byte-for-byte serialiser — it normalises the model on the way
through. The round-trip test (`tests/test_codec.py::test_roundtrip_normal_form`)
asserts

```python
canonical_normal_form(f) == canonical_normal_form(from_canonical_latex(to_canonical_latex(f)))
```

i.e. equivalence under `canonical_normal_form` (CNF), **not**
`f.model_dump() == g.model_dump()`. On the 10 curated formulations in
`formulations/`, the full-model round-trip diverges for 4 of them (constraints
only) while CNF is preserved for all 10. Two normalisations account for the
divergence, both intentional:

1. **Numeric coefficient widening** — a source coefficient written as the int
   `1` returns as the float `1.0` (`core/model.py:231`,
   `coefficient: float | str | None`). The two are numerically equal and CNF
   folds them together.
2. **Literal-name canonicalisation** — a named literal term (e.g. `ref: "one"`)
   returns as the generic `ref: "_const"` whose `coefficient` carries the value
   (`core/model.py:_normalize_constant`, lines ~237-259). The symbolic *name* of
   a constant is not recoverable from the emitted LaTeX; the value is.

Without an ADR, a future reader could (a) mistake CNF-equivalence for
byte-identity and "fix" the round-trip test to compare `model_dump`, breaking it
for no correctness gain, or (b) assume constant names survive the codec.

## Decision

**The codec's reversibility guarantee is CNF-equivalence, and CNF is the
fidelity oracle for the `text ⇄ graph` interface.** Concretely:

1. `from_canonical_latex(to_canonical_latex(f))` is guaranteed equal to `f`
   **under `canonical_normal_form`**, not under `model_dump`. CNF is the
   equivalence class the paper's "same formulation" claim ranges over.
2. `to_canonical_latex` is additionally an **exact fixed point**: `to(from(to(f)))
   == to(f)` byte-for-byte (`test_text_idempotence`). The LaTeX string, not the
   model dict, is the canonical serialised form.
3. Normalisations that CNF is allowed to fold: int↔float numeric coefficients,
   and the name of a literal/constant term (canonicalised to `_const`).
   Semantically load-bearing structure — variables, parameters, indices,
   quantifiers, comparators, coefficients-as-parameters, signs, operators — must
   survive the round-trip and is asserted by CNF equivalence.

## Rationale

- The paper reasons about formulations up to renaming and trivial numeric
  representation; CNF is exactly that equivalence, so it is the right oracle.
- A byte-identity oracle would force the codec to preserve incidental input
  spelling (int vs float, a constant's nickname) that carries no mathematical
  content, making the codec brittle without improving correctness.
- The LaTeX string *is* stable byte-for-byte (fixed point), so downstream
  diffing and reproducibility (ADR-0006) hold at the serialised-text layer.

## Consequences

- Do **not** rewrite the round-trip test to compare `model_dump`; compare CNF.
- Callers must not rely on a constant term's symbolic name surviving the codec,
  nor on int-vs-float coefficient spelling.
- The `coefficient: float | str | None` union accepts an `int` literal on input
  (the curated formulations use `1`), which triggers a pydantic
  `PydanticSerializationUnexpectedValue` *serialisation warning* — cosmetic, no
  wrong result, but a typing wart. A follow-up may either widen the annotation
  to include `int` or coerce int→float at validation time; either keeps CNF
  behaviour identical. Tracked in the quality backlog.
- CNF is a load-bearing correctness component; changes to `canonical_normal_form`
  must be reviewed as deliberately as snapshot updates (ADR-0006).

## Alternatives considered

- *Byte-identity round-trip (`model_dump` equality):* rejected — forces the
  codec to preserve mathematically irrelevant input spelling and constant
  nicknames; brittle, no correctness benefit.
- *Leave the contract implicit in the test:* rejected — the CNF-vs-dump
  distinction is subtle and easy to "fix" wrongly; recording it prevents a
  well-meaning regression.
