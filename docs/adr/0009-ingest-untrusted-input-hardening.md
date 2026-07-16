# ADR-0009: Ingestion hardens against untrusted third-party source input

- **Status:** accepted
- **Date:** 2026-07-02

## Context

The M1 ingestion front-end (`mining/ingest/dispatch.py`) is the boundary where
`lp2graph` consumes **untrusted, externally-authored source artifacts**: the
Paper-1 corpus is mined from third-party GitHub repositories, so the `.tex` /
`.py` / `.gms` / `.mod` / `.jl` files handed to `ingest()` are not written to
our conventions and may be malformed, oddly encoded, or hostile.

The module documents a hard invariant for this layer:

> Unknown extensions/formats produce a reported `IngestionFailure`, never an
> exception. … there is no input that silently drops.

`ingest()` upholds this well for routing and downstream parse/validate stages
(`latex_normalizer.ingest_latex` wraps every stage in try/except and returns an
`IngestionResult`). But the *file-read* step in `_resolve` only caught
`FileNotFoundError` and `OSError`. `Path.read_text(encoding="utf-8")` also
raises **`UnicodeDecodeError`**, which is a subclass of `ValueError` — **not**
`OSError` — so a single non-UTF-8 source file (a BOM, latin-1 comments, or a
binary blob mistaken for text — all common in real third-party repos) escaped
as an uncaught exception and **aborted the entire batch ingest**.

Confirmed reproduction (2026-07-02): a `.tex` file containing the lone byte
`0xE9` raised `UnicodeDecodeError` straight out of `ingest()`. This is both a
robustness defect and an availability/DoS concern for the corpus pipeline: one
bad-encoding file in a mined repo stops all subsequent files from being
processed, and the failure is an opaque traceback rather than an attributable,
per-source report.

## Decision

**Treat a decode failure as a reported read-stage `IngestionResult` failure,
not an exception.** `_resolve` gains an explicit `except UnicodeDecodeError`
arm (ordered before the `OSError` arm, since it is not an `OSError` subclass)
that returns `IngestionResult.single_failure(stage="read", …)` naming the
offending source and carrying `UnicodeDecodeError` as the detail.

Rejected alternative: decoding with `errors="replace"` and proceeding. That
would silently corrupt the algebra of the formulation and violate the M1
"never silently drop / never silently alter" principle — a *reported* failure
is strictly better than a *silently mangled* success for a dataset-building
tool that must be reproducible and auditable.

## Consequences

- The M1 "never an exception at the routing layer" invariant now actually holds
  for the encoding failure mode; a corpus batch survives an individual
  bad-encoding file and attributes the failure to its source.
- New offline regression test `test_non_utf8_source_reported` locks the
  behaviour (feeds a lone `0xE9` byte, asserts `stage == "read"` and a
  UTF-8 message). Full suite stays green; determinism paths untouched.
- Out of scope (documented as follow-ups, not fixed here):
  - **No input-size bound** before `read_text` — a multi-GB file in a mined
    repo would be read fully into memory (memory-exhaustion DoS). A size cap at
    the read boundary is the natural next hardening step.
  - The `_looks_like_path` heuristic treats any short single-line string ending
    in a known suffix as a filesystem path; raw text that happens to look like
    a path is read from disk. Low risk in the batch/offline threat model, but
    worth an explicit `fmt=`/`Path` contract if `ingest` is ever exposed to
    caller-controlled strings.

## Notes

No drift from accepted ADRs 0001–0008. Relates to the M1 ingestion invariant
(`mining/ingest/`, issue #38) and complements the reliability posture recorded
for the sibling repos (silent-drop elimination).
