# ADR-0003: License — Apache 2.0

- **Status:** accepted
- **Date:** 2026-05-03

## Context

The source repository
([`joernmht/raiLPminerExperimentation`](https://github.com/joernmht/raiLPminerExperimentation))
is MIT-licensed. The new repo can choose any license at least as
permissive that satisfies our goals.

## Decision

**Apache 2.0.** Source repository attribution is preserved in
`docs/extraction-report.md` and in per-file headers where code is
extracted or refactored.

## Rationale

- Apache 2.0 has an explicit patent grant. MIT does not. For a library
  used in research and industry alike, the patent grant matters.
- Apache 2.0 is OSI-approved, FSF-approved, and broadly compatible
  with downstream consumers.
- Compatible with the source repo's MIT (we may incorporate MIT code
  with attribution into an Apache-licensed work).

## Consequences

- Every file extracted or refactored from the source repo carries a
  header crediting the origin and noting the original MIT license.
- `LICENSE` is the Apache 2.0 text; an `appendix` notes the partial
  MIT derivation.
- Contributors agree to license their contributions under Apache 2.0
  (the standard implicit DCO is sufficient; we do not require a CLA at
  v0.1).

## Alternatives considered

- MIT (matching the source): no patent grant.
- BSD-3-Clause: similar to MIT, no patent grant.
- LGPL: incompatible with our use cases (proprietary downstream
  embedding).
- MPL-2.0: file-level copyleft is unusual for a Python library; would
  surprise contributors.
