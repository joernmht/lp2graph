# ADR-0012: One format registry, static and non-pluggable

- **Status:** accepted
- **Date:** 2026-08-26

## Context

Three layers independently answered "what format is this file?", each from its
own private extension table:

| Layer | Table | Extensions |
|---|---|---|
| `validation/detect.py` | `EXT_FMT` | `.json .tex .lp .mps .gms .mod .jl .py` |
| `mining/ingest/dispatch.py` | `_EXT_FMT` | `.tex .lp .mps .gms .mod .jl .py .pdf` |
| `cli.py` | `_read_model` / `_write_model` | `.json .tex .lp .mps .gms .mod .jl (.py out)` |

They had already drifted. `validation/detect.py` described its own table as
"superset of mining.ingest's table: adds .json" — the duplication was known,
documented in a comment, and unenforceable. The consequence was not cosmetic:
**`mining.ingest.ingest()` could not ingest lp2graph's own canonical `.json`**,
so the M1 corpus front-end was unable to re-ingest formulations an earlier
pass had already canonicalized — the exact operation corpus assembly needs.

`mining/ingest/dispatch.py` additionally re-implemented, as an eight-branch
`if/elif` chain, a dispatch that `code_importers.CODE_IMPORTERS` already
expressed as a table.

## Decision

**`lp2graph.formats` is the single source of truth for format identity.** It
owns `FORMATS`, `EXT_FMT`, `FMT_ALIASES` and the sniffable subsets; every
other layer imports from it and adds no table of its own.

Dispatch goes through the importer registry (`CODE_IMPORTERS`) rather than a
branch chain, so registering an importer is what makes a format reachable.

The tables are **plain module-level constants, not a mutable plug-in
registry**. Third-party code cannot register a format at runtime.

## Rationale

- Adding a format is one edit in one file, and every layer picks it up.
- Divergence becomes impossible to express rather than merely discouraged.
- **Determinism (ADR-0006) forbids a mutable registry.** If plug-ins could
  register formats at import time, the format a given file resolves to would
  depend on which packages happened to be imported, and in what order — so
  ingestion results would stop being reproducible from the inputs alone. A
  static table keeps routing a pure function of the source tree.

## Consequences

- Extending lp2graph to a new format requires editing the package (a source
  change and a release), not just installing a plug-in. Accepted: this is a
  determinism-critical library, and reproducibility outranks extensibility
  here.
- `validation.detect.FORMATS` / `EXT_FMT` / `FMT_ALIASES` remain importable at
  their old names as re-exports, so existing callers do not break.
- `mining.ingest` gained `.json` as a side effect of unification, which is the
  behaviour change corpus work needed.
- `pdf` stays a recognized-but-refused format so a PDF is reported, never
  silently mis-sniffed as text.

## Alternatives considered

- *An entry-point-based plug-in registry:* rejected — see the determinism
  argument above; it would make ingestion depend on the installed environment.
- *Keeping per-layer tables and adding a consistency test:* rejected — a test
  detects drift after it is written; a shared constant prevents it.
