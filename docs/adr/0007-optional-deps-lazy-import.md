# ADR-0007: Optional dependencies are lazily imported

- **Status:** accepted
- **Date:** 2026-06-14

## Context

`lp2graph` derives many artefacts from the canonical `Formulation`: NetworkX /
PyG / DGL exports, a PuLP/HiGHS solver back-end, Pyomo import, and the mining
extensions (NLTK/WordNet, HDBSCAN, scikit-learn, NetworkX isomorphism). Most of
those libraries are heavyweight (`torch`, `dgl`), platform-sensitive, or rarely
needed by a given user. If they were hard dependencies, `import lp2graph` would
require the whole stack, the install would be slow and fragile, and CI on the
core path would be coupled to GPU/ML wheels.

The codebase already follows a lazy-import convention, but it was only recorded
as a coding note in `CLAUDE.md`, not as an architectural decision with rationale
and consequences.

## Decision

**Core install is `pydantic` + `jsonschema` only. Everything heavier is an
optional extra, imported *inside* the function that uses it.** Specifically:

1. Optional libraries are declared as `[project.optional-dependencies]` extras
   (`networkx`, `pyg`, `dgl`, `pyomo`, `solver`, `mining`, `all`).
2. The import statement lives inside the function/method that needs the library,
   not at module top level, so `import lp2graph` and unrelated modules work with
   only the core deps installed.
3. A missing optional dep raises a clear `ImportError` naming the extra to
   install — it must not surface as an opaque `ModuleNotFoundError` mid-call.
4. Tests for optional-dep paths are gated with
   `pytest.importorskip("<dep>")`.
5. Each optional library is listed in `[[tool.mypy.overrides]]`
   `ignore_missing_imports` so `mypy --strict` passes without it installed.

## Rationale

- Keeps the core importable and the canonical model usable with a tiny,
  reproducible dependency footprint.
- Decouples the determinism-critical core from large ML/solver toolchains.
- Lets CI exercise the core path on all Python versions without installing
  `torch`/`dgl` everywhere.

## Consequences

- Adding a new optional backend is a four-step checklist: (a) add an extra in
  `pyproject.toml`, (b) lazy-import it inside its function with a helpful
  `ImportError`, (c) gate its tests with `pytest.importorskip`, (d) add it to
  the mypy `ignore_missing_imports` list. STACK.md tracks the current set.
- A small runtime cost on first use (the import happens on the call path); this
  is negligible relative to the work those functions do.
- Module-level type hints referring to optional types rely on
  `from __future__ import annotations` (already mandatory) so they are not
  evaluated at import time.

## Alternatives considered

- *Everything as hard deps:* rejected — heavy, fragile install; couples the core
  to ML/solver wheels.
- *A single `extras` bucket:* rejected — users installing only the solver should
  not pull `torch`; granular extras keep installs minimal.
- *Try/except top-level import with a sentinel `None`:* rejected in favour of
  in-function imports, which keep failure local to the feature being used and
  avoid module-load-order surprises.
</content>
