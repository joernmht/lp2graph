# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-05-20

### Changed

- **BREAKING:** the import package is renamed `optgraph` → `lp2graph`, so it
  now matches the distribution name. Update imports
  (`from optgraph import …` → `from lp2graph import …`) and the console
  script (`optgraph …` → `lp2graph …`). No behaviour changed; this is a
  pure rename. The canonical `schema_version` is unaffected (still `0.1.0`).

## [0.1.0] - 2026-05-03

### Added

- Canonical JSON schema (`schema/canonical.schema.json`) with index
  families, parameters, variable templates, constraint templates,
  first-class objectives, and term-level refs/bindings/role/sign
  semantics.
- Pydantic v2 model (`lp2graph.core.model`) mirroring the schema.
- Two-phase validator (JSON Schema + semantic invariants).
- Three view derivations: `lp2graph.views.schema`, `.hybrid`, `.ground`.
- Internal typed graph (`lp2graph.core.graph`) — library-agnostic.
- Structural metrics: `node_counts_by_class`, `edge_density`,
  `constraint_variable_ratio`, `minimal_size`, `model_coherence`,
  `graph_diameter`.
- Presence flags: `has_big_m`, `has_integer_vars`,
  `has_modulo_offset`, `has_soft_slack`,
  `has_aggregation_operator`.
- Constraint classification (heuristic, regex-based; ported from the
  source repo with attribution).
- SVG renderer with the design-context palette and typography.
- Static interactive viewer (`viewer/index.html`).
- Export adapters: NetworkX (full), PyG (HeteroData), DGL, LaTeX,
  Pyomo (skeleton; bodies are stubs in v0.1).
- CLI: `lp2graph validate | view | render | metrics | export`.
- Initial catalog: 5 constraint-focused and 3 objective-focused
  formulations across LP and MILP families.
- 36 tests covering schema validation, view derivations, metrics,
  rendering, and exports.
- CI for Linux + macOS, Python 3.11/3.12/3.13.
- Docs: data-model, views, metrics, add-a-formulation, design context,
  extraction report; ADRs 0001-0005.

### Origin

Bootstrapped from
[`joernmht/raiLPminerExperimentation`](https://github.com/joernmht/raiLPminerExperimentation)
(MIT). See `docs/extraction-report.md` for the manifest.
