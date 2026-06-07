# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **LP mining extensions** (`lp2graph.mining`, issues #38–#43) — six
  deterministic modules implementing the *LP Mining with LP2Graph* method on
  top of the core library. Every frozen resource is versioned in
  `lp2graph.mining.versions` and stamped into emitted records.
  - **M1 `mining.ingest`** — heterogeneous ingestion front-end: a Pyomo
    importer (`from_pyomo`), a versioned non-canonical LaTeX normalizer with
    source-span provenance (`normalize_latex` / `ingest_latex`), and an
    extension dispatcher (`ingest`) that reports failures as structured
    `IngestionResult`s rather than dropping them.
  - **M2 `mining.homologize`** — lexical homologizer (tokenize / lemmatize /
    versioned stop-list / frozen domain thesaurus + optional WordNet) and a
    TF-IDF `ConceptVectorizer` over a sorted, diffable `Vocabulary`, plus the
    type signature `τ(s)` and the `Entity` model for levels V/C/M.
  - **M3 `mining.cluster`** — the cluster-and-name operator `CN` (deterministic
    average-linkage default, `fixed_k`+silhouette, optional HDBSCAN), the
    bottom-up Level V→C→M taxonomy `induce`, and `stability_report`
    (silhouette + bootstrap ARI + sensitivity).
  - **M4 `mining.label`** — two-stage labeling service: rule layer + calibrated
    one-vs-rest `LinearSVM`, a confidence-gated closed loop with a versioned,
    replayable `LabelStore`, rule promotion, retraining, and gold-set
    guardrails (drift, per-class P/R, Cohen's κ, rollback flag).
  - **M5 `mining.corpusmgr`** — provenance records, a regeneration `CorpusManifest`
    (frozen search date + queries), deterministic dedup (schema-graph hash or
    bibliographic key), and reproducible representative selection.
  - **M6 `mining.isomorphism`** — per-cluster schema-graph isomorphism rate via
    the NetworkX export (`isomorphism_report`).

## [0.3.0] - 2026-06-01

### Added

- **Deterministic LaTeX ⇄ graph codec** (`lp2graph.codec`): paper-style
  LaTeX (`\mathcal` index sets, `\sum`, `\forall`, big-M) round-trips with
  the canonical model with no LLM in the loop.
  `to_canonical_latex` / `from_canonical_latex`, plus
  `canonical_normal_form` for round-trip comparison. The LaTeX
  serialization is a tested fixed point (`to(from(to(f))) == to(f)`); the
  solvable content round-trips exactly.
- **Real grounding solver back-end** (`lp2graph.solve`): replaces the v0.1
  Pyomo stub. Grounds a formulation with an `Instance` (cardinalities +
  parameter values) into a concrete `pulp.LpProblem` and solves it
  (CBC / HiGHS / Gurobi). Covers the linear core including big-M and PESP
  modulo; boundary-degenerate constraint instances are correctly omitted.
- **Deterministic graph → natural-language describer** (`lp2graph.nl`):
  generates a Markdown problem description (sets, data, decisions,
  per-constraint sentences, objective) with parameter **data tables** when
  an instance is supplied.
- **End-to-end validation suite** (`corpus/validation/codec_pipeline/`):
  runs the full JSON→LaTeX→parse→ground→solve loop and checks codec
  round-trip, pipeline-vs-direct equality, cross-solver agreement, and
  match to independently established optima (assignment 13, big-M ordering
  30, fixed-sequence 18, PESP 1, time-indexed 4). Records paper anchors
  (timtab1 = 764772, marcotallone = 3913.47).
- New formulations: `assignment.json`, `pesp_solvable.json`.
- CLI: `lp2graph latex | parse | describe | solve`.
- New tests: `test_codec.py`, `test_solve.py`, `test_describe.py`.
- Optional `solver` extra (`pulp`, `highspy`).

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
