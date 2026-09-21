# ADR-0013: Ship the canonical schema, and enforce it at the interchange boundary

- **Status:** accepted
- **Date:** 2026-09-21

## Context

`schema/canonical.schema.json` is the *published contract* of the canonical
formulation format. It carries a stable `$id`
(`https://github.com/joernmht/lp2graph/schema/canonical.schema.json`),
`docs/data-model.md` and `README.md` point readers at it, and third parties are
expected to validate their artifacts against it. ADR-0011 makes the canonical
`Formulation` the interchange pivot for every other format; this schema is how
that pivot is described to anyone outside this repository.

Three facts about it were all true at the same time, and together they made the
contract decorative:

1. **It was not in the wheel.** `[tool.hatch.build.targets.wheel]` lists
   `packages = ["src/lp2graph"]`, and the schema lives at the repo *root*, so it
   was included in the sdist and dropped from every wheel. Verified against the
   published artifact: `lp2graph-0.3.0-py3-none-any.whl` contains **zero** JSON
   files. Since v0.3.0 (PyPI, 2026-07-11) the normal way to obtain lp2graph has
   been `pip install`, which therefore delivered the reader but not the
   specification, and offered no API to reach it.

2. **`jsonschema` was a mandatory dependency that nothing imported.**
   `dependencies = ["pydantic>=2.0", "jsonschema>=4.0"]` — but `grep -r
   jsonschema src/` returned nothing. It was used only by `tests/`. Every
   installed user paid for a validator the library never ran, against a schema
   the library did not ship.

3. **The library and the schema disagreed, and nothing could notice.**
   `core/loader.py`'s own module docstring claimed "Schema validation against
   the JSON Schema runs first to give clear, spec-grounded error messages" —
   it did not run at all. With only pydantic enforcing the format, the model's
   ergonomic defaults leaked to the document boundary:

   | Document | Published schema | Library (before) |
   |---|---|---|
   | no `schema_version` | reject | **accept** (defaults to `0.1.0`) |
   | no `constraints` | reject | **accept** (defaults to `()`) |

   Both are silent-corruption paths for the mining corpus. An unversioned file
   silently *becomes* a `0.1.0` file, permanently defeating the only
   forward-compatibility mechanism the format has (ADR-0004). A constraint-less
   "formulation" is an extraction failure that loads clean and reads, to a
   human at a review gate, as a formulation with nothing in it.

Note that the reverse direction was already sound: `Term.constant` appears in
the schema but not in `Formulation.model_fields`, and a naive field-set
comparison flags it — but a `model_validator(mode="before")` normalizes it, and
the document is accepted. The conformance check therefore had to be
*behavioural* (accept/reject agreement), not structural.

## Decision

**The schema travels with the package, is reachable through a public accessor,
and is enforced on every document that enters the library.**

1. `[tool.hatch.build.targets.wheel.force-include]` maps
   `schema/canonical.schema.json` to `lp2graph/schema/canonical.schema.json`.
   The repo-root copy stays the single source of truth so the public `$id` URL
   does not move; there is exactly one copy in the source tree.
2. `lp2graph.schema` exposes `canonical_schema()` (parsed, `lru_cache`d) and
   `canonical_schema_path()`, both re-exported from `lp2graph`. They prefer the
   packaged copy and fall back to the repo-root copy so a `PYTHONPATH=src`
   source checkout — the documented dev setup — also resolves.
3. `core/loader.loads()` validates against the JSON Schema **before** pydantic,
   making the docstring true and giving `jsonschema` a reason to be a core
   dependency. Documents get the strict published contract; in-Python
   construction of `Formulation(...)` keeps its defaults untouched.
4. Model-invariant failures (cross-field rules the schema cannot express) are
   anchored to the artifact with `Exception.add_note` rather than by wrapping,
   so the exception type callers already catch — `pydantic.ValidationError` —
   is unchanged. This is a diagnosability gain with no API break.

## Consequences

- `pip install lp2graph` now delivers the specification, and
  `lp2graph.canonical_schema()` is the supported way to reach it. Verified
  against a built wheel installed into a clean prefix.
- The two accept/reject disagreements above are closed. `tests/
  test_interchange_contract.py` asserts agreement in *both* directions over a
  battery of mutations, and was confirmed to fail on the pre-decision loader.
- **`loads()` got ~14x slower**: measured per call on
  `formulations/constraints/lp_1_1_fixed_sequence.json`, JSON Schema costs
  **1.80 ms** against **0.14 ms** for `json.loads` + pydantic + semantic
  validation combined (~1.97 ms total, from ~0.14 ms). Absolute cost is small
  and the validator is compiled once (`lru_cache`), but bulk mining ingests
  pay it per file — ~1.8 s per thousand formulations. Accepted for now:
  correctness at the interchange boundary outweighs it, and no current path
  loads at a scale where it matters. If it ever does, the fix is a documented
  opt-out for *internally produced* files, never for external input.
- A CI `wheel` job builds a real wheel, asserts the schema is inside, installs
  it and calls the accessor. The packaging config is the only thing keeping the
  file in, and config regressions are invisible until a release.
- ADR-0004 (schema versioning) is still **proposed**, and this decision does not
  ratify it. It does make the version field load-bearing in practice: a
  document must now carry one. The unresolved part of ADR-0004 — accepting any
  matching MAJOR and warning on an older MINOR — remains unimplemented; a
  future `0.2.0` document is still rejected by a `Literal` type error rather
  than by a policy-aware message.

## Alternatives considered

- **Drop `jsonschema` from core deps** and let pydantic be the only validator.
  Cheaper and faster, but it makes the published `$id`-ed schema advisory
  documentation that nothing checks, and leaves both disagreements open. The
  schema is the artifact third parties integrate against; the library should be
  the reference implementation of it, not an approximation of it.
- **Tighten the pydantic model** (make `schema_version`/`constraints` required).
  Rejected: it would break every in-Python `Formulation(...)` construction in
  the library and tests for a problem that only exists at the document
  boundary.
- **Generate the JSON Schema from the pydantic model.** Attractive — one source
  of truth — but pydantic's emitted schema is shaped by pydantic (`$defs`
  naming, `anyOf` for optionals) and would churn the public `$id`-ed contract
  on every pydantic upgrade. The behavioural conformance test buys the same
  protection without surrendering control of the published document.
