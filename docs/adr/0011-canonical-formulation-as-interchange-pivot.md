# ADR-0011: The canonical `Formulation` is the interchange pivot

- **Status:** accepted
- **Date:** 2026-08-26

## Context

`lp2graph.interop` (≈2650 LOC, the largest subpackage after `mining`) reads
and writes seven textual modelling formats — canonical JSON, canonical LaTeX,
CPLEX/Gurobi LP, MPS, GAMS, AMPL, JuMP — plus three live solver object APIs
(gurobipy, PuLP, Pyomo). The `lp2graph convert` subcommand exposes this as
"code ⇄ graph ⇄ code between modeling languages".

Ten formats that could each convert to the others directly would need up to
90 pairwise converters, every one of them a place for coefficient drift to
creep in. The package instead routes **everything through the canonical
pydantic `Formulation`**: each format has exactly one reader and one writer,
and conversion is always `read → Formulation → write`.

This is the decision the whole `interop` surface rests on, and it was
recorded only implicitly — in the shape of the code and a line of CLI help
text. It is also what makes ADR-0006 (determinism) hold across formats: the
pivot is frozen, schema-validated and insertion-order deterministic, so a
round trip cannot smuggle in ordering or precision differences.

## Decision

**No format converts directly to another. Every importer produces a validated
`Formulation`; every exporter consumes one.**

1. An importer is `text -> Formulation` and raises `InteropError` on anything
   it cannot represent faithfully — it never returns a partial model.
2. An exporter is `(Formulation, Instance | None) -> text`.
3. Formats that are scalar/flat (LP, MPS, and the live solver APIs) go through
   the shared `GroundedModel` intermediate in `interop/_grounded.py`, which is
   still derived from the pivot rather than from another format.
4. Adding format *F* costs one reader and one writer (2 units of work), not
   one converter per existing format.
5. The pivot is the schema-validated `Formulation` — not a looser dict — so
   every conversion is validated at the waist.

## Rationale

- **Replaceability.** A user can adopt lp2graph as a drop-in for a
  format-specific tool and keep their existing pipeline: the round trip
  through the pivot is lossless for anything the schema can express, and
  loudly lossy (an `InteropError`) for anything it cannot.
- **Linear extension cost.** N+M adapters instead of N×M converters.
- **One place to enforce determinism and validation** (ADR-0006), rather than
  once per format pair.
- **Fidelity is testable.** Because every path crosses the pivot, round-trip
  equivalence can be asserted as canonical-normal-form equality (ADR-0010)
  rather than per-pair byte comparison.

## Consequences

- A format's expressiveness is capped by the canonical schema. Features no
  format-pair pivot can carry (e.g. solver-specific hints) are dropped, and
  must surface as a reported failure rather than a silent omission.
- Two "flat" formats (LP → MPS) pay a template-level detour they do not
  strictly need. Accepted: the uniformity is worth more than the shortcut.
- Exporting a *template-level* formulation needs an `Instance` to ground it;
  the CLI therefore requires `--instance` for those targets.
- Each new format must be registered in `lp2graph.formats` (ADR-0012), not in
  a private table belonging to the new reader.

## Alternatives considered

- *Direct pairwise converters:* rejected — quadratic growth, and each pair
  becomes an independent opportunity for coefficient drift.
- *A looser dict/AST as the pivot:* rejected — it would move validation out of
  the waist and weaken the determinism guarantee that ADR-0006 makes global.
