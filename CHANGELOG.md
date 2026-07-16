# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **`lp2graph.validation`** — end-to-end validation of (LLM-)generated
  LP/MILP artifacts. `validate_text` / `validate_path` / `validate_formulation`
  accept raw text, bytes, files, or parsed models in any supported format
  (canonical JSON, LaTeX, LP, MPS, GAMS, AMPL, JuMP) and return a structured
  `ValidationReport` instead of raising: faulty-input detectors and repairs
  (markdown fences, unicode look-alikes, truncation, NUL/encoding damage),
  format sniffing with parse fallbacks, the semantic invariants, structural
  detectors (completeness, coherence, duplicate/unused symbols, constant
  constraints, bound conflicts), and an optional grounding smoke check on a
  synthesized all-ones instance (CBC/HiGHS/Gurobi; skipped gracefully without
  pulp). Reports are deterministic and stamped with a `pipeline_version`.
- **`lp2graph validate` CLI** upgraded to run that pipeline on any supported
  model file (previously canonical JSON only): `--fmt`, `--json`, `--no-solve`,
  `--instance`, `--solver`, `--time-limit`; exit code 0 unless the verdict is
  `invalid`. New docs page `docs/validation.md`.

- **M1b big-operator wrapper rules** (`mining.ingest.latex_normalizer`) — four
  new rewrite rules driven by Paper-1 corpus evidence (3,668 of 8,957 Tier-2
  MathML-derived formulas): `underset_bigop` (`\underset{X}{\sum}` →
  `\sum_{X}`, likewise `\prod`/`\min`/`\max`/`\int`/`\bigcup`/`\bigcap`),
  `mathop_unwrap`, `underbrace_unwrap`, and `overset_base`. Rule-table version
  bumped to `rewrite-2026.07.0`.
- **`lp2graph.interop`** — functional code ⇄ graph interfaces for the common
  modeling languages, replacing the historic stubs. Importers build
  coefficient-faithful flat `Formulation`s from **gurobipy** models
  (`from_gurobipy`), **PuLP** problems (`from_pulp`), **Pyomo** concrete
  models (`from_pyomo`, full linear term recovery via `standard_repn`;
  ranged constraints split), and **LP / MPS / GAMS / AMPL / JuMP** text
  (`from_lp_string` / `from_mps_string` / `from_gams` / `from_ampl` /
  `from_jump`). Exporters emit every one of those targets from any
  formulation (`to_gurobipy[_code]`, `to_pulp[_code]`, `to_pyomo[_code]`,
  `to_lp_string`, `to_mps_string`, `to_gams`, `to_ampl`, `to_jump`) — flat
  models directly, template-level models through the PuLP grounder with an
  `Instance`. All emitters are deterministic fixpoints; unsupported
  constructs raise `InteropError` instead of being dropped. Verified by a
  `code → graph → code` round-trip matrix (`tests/interop/`, 100 tests)
  that solves every path against hand-verified optima with CBC, HiGHS, and
  Gurobi, including cross-reads of Gurobi-written `.lp`/`.mps` files.
- **`lp2graph convert IN OUT`** — CLI conversion between modeling languages
  through the canonical graph, routed by file extension
  (`.json/.tex/.lp/.mps/.gms/.mod/.jl`, plus `.py` solver scripts via
  `--python-api {gurobipy,pulp,pyomo}`).
- **`mining.ingest`** now routes `.gms/.mod/.jl` to the real interop parsers
  (previously honest stubs) and gained `.lp`/`.mps` support (`import_lp`,
  `import_mps`); parse problems surface as structured `stage="parse"`
  failures.

- **`metrics.model_completeness`** — the second model-level well-formedness
  indicator described in *LP Mining with LP2Graph* (objective declared together
  with ≥1 variable and ≥1 constraint), companion to `model_coherence`. Now
  computed and wired into the Level-M structural feature document
  (`mining.cluster.taxonomy.model_feature_document`) as a `complete:{0,1}`
  feature, closing a paper↔code gap where the paper named both indicators but
  only coherence was implemented.
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

### Fixed

- **`interop.from_pulp` crashed on unnamed constraints** (`prob += expr <= rhs`
  without a name label): the constraint's ``name`` is ``None`` and the
  name-sanitizer raised ``TypeError``. Anonymous constraints now take the
  deterministic ``c1``/``c2``/... fallback names.

### Changed

- **PuLP 4.0 forward-compatibility** (`lp2graph.solve` + `lp2graph.interop`):
  migrated off the APIs PuLP 4.0 removes — variables are built with
  `prob.add_variable(...)`, constraints counted with `prob.numConstraints()`,
  and the default CBC solver is created by the new `solve.default_solver()`
  (`COIN_CMD` with a bundled-CBC fallback) instead of the deprecated
  `PULP_CBC_CMD`. `interop.grounded_from_pulp` lists constraints
  version-agnostically, `to_pulp_code` emits scripts using the sanctioned
  APIs, and the M1 ingest reader reports non-UTF-8 source files as
  structured read-stage failures (ADR-0009) instead of raising.

- **CI now gates formatting:** added a `ruff format --check src tests` step to
  `ci.yml` (previously only `ruff check` ran, so format drift could land
  undetected). Bumped the `ruff-pre-commit` pin v0.4.10 → v0.15.12 and the
  `dev` extra to `ruff>=0.15.12,<0.16` so local, pre-commit, and CI agree;
  reformatted 21 pre-existing files to the current ruff style.

### Docs

- Added `docs/STACK.md` (software-stack reference) and ADR-0006 (determinism as
  a hard requirement) and ADR-0007 (optional dependencies are lazily imported),
  wired into the MkDocs nav.

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
