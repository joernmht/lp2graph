# ADR-0004: Schema versioning policy

- **Status:** proposed
- **Date:** 2026-05-03

## Context

The canonical schema declares `schema_version`. Formulation files
include the version string. We need a policy that:

1. Lets us evolve the schema without silently breaking catalogs.
2. Lets users pin a known-good version.
3. Tells library code which version of the parser to apply.

This ADR is proposed (not accepted) because the v0.1 schema is
expected to change as the catalog grows; the policy will be ratified
when the schema is stable enough to commit to.

## Options

### A. Strict semantic versioning, additive-only minor changes

`MAJOR.MINOR.PATCH`. PATCH is bug-fixes (no schema change). MINOR
adds optional fields and new enum values. MAJOR is breaking. Loader
accepts any version with the same MAJOR.

### B. Single canonical version per release; no version migration

Each release declares one schema version. Files with older versions
are rejected; an external migration tool handles upgrades.

### C. Polymorphic loader

Loader inspects `schema_version` and dispatches to a versioned
sub-parser. Supports many versions in a single library version.

## Recommendation (proposed)

**Option A**, with the loader rejecting unknown MAJOR versions and
emitting a deprecation warning for files that use a MINOR older than
the current one (so contributors know to upgrade).

## Consequences

- New optional fields are MINOR. Removing or renaming a field is
  MAJOR.
- Adding a new enum value is MINOR if and only if existing files do
  not need to change.
- A migration tool (`lp2graph migrate <file>`) lands when the first
  MAJOR change is needed.

## Open question

What about *constraints* on existing fields tightening (e.g. a field
that was `string` becomes `pattern`)? Today's loader would reject
previously-valid files. We classify this as MAJOR by default; the
discussion belongs in the relevant `open-question` issue.
