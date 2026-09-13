# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **M3 clustering 50x faster, bit-identical results.** `distance_matrix`
  reduces every pair to the non-zero coordinates of the row vector (a zero
  product adds exactly 0.0, so the dense sum is reproduced coordinate for
  coordinate), and `agglomerative` caches every group pair's average linkage
  by group id, recomputes only the merged group's distances with the exact
  member order of the from-scratch loop, and keeps each row's first-minimum
  column, so a merge costs O(g) instead of a full O(n^2 x members)
  rescan. Ties still resolve to the first pair in (row, column) order; a
  property test with forced ties locks the equivalence to the naive
  definition. One taxonomy induction over the lab corpus went from 84 s to
  1.5 s.

### Added

- **Binder letters, big-M products, set algebra in binders**
  (`rewrite-2026.09.4`): `bigop_lone_binder` gives `\\sum_{n}` the family the
  declared shapes assign to `n` in the row; `distribute_param` distributes a
  declared parameter over a parenthesised sum exactly (`M \\left(1 -
  x\\right)` -> `M - M \\cdot x`, numeric pieces become `2 \\cdot M`);
  `restricted_set_widen` handles set differences/intersections inside binder
  groups (brace-aware); `declared_product` and `distribute_param` never fire
  inside a quantifier tail.
- **Implicit structure the corpus leaves unsaid** (`rewrite-2026.09.3`,
  measured against the lab corpus after `rewrite-2026.09.2`): a row without
  any quantifier gets `\\forall` over the families the declared shapes give
  its free index letters (`implicit_quantifier`, recorded; a letter that would
  get two families leaves the row untouched); `\\forall f` / `\\forall i, j
  \\in J` resolve lone letters the same way (`forall_lone_letters`);
  memberships listed after the algebra without `\\forall` are the
  quantifier tail (codec); an equality chain `a = b = c` and a same-direction
  chain with three or more comparators split into consecutive rows, and an
  interval membership `t \\in [a, b]` into its two bounds (codec, exact);
  strict `<`/`>` in the algebra relax to `\\le`/`\\ge` as a recorded
  approximation (restrictions in a tail keep `<`); a parenthesised single
  symbol `(\\bar{a})_{ik}` is that symbol (`paren_symbol_unwrap`);
  `\\begin{matrix}`-style wrappers inside a row are dropped
  (`env_wrapper_strip`); `\\mathbf{\\mathcal{E}}` and `\\in \\mathbf{I}`
  are the set (`mathbf_set_unwrap`); `\\text{u}` naming a declared or bound
  symbol is the identifier (`text_ident_symbol`); `restricted_set_widen` also
  widens function-style sets `H(e)` and set differences/intersections
  (`S \\setminus T`, `S \\cap T`) to the base family, recorded; unions are
  refused.
- **Row conventions the corpus writes** (`rewrite-2026.09.2`, issue #64;
  lab measurement: 55 of 6,207 accepted rows parsed before this). Codec: the
  quantifier tail starts at `\qquad` OR the first top-level `\forall`
  (a dangling comma before it is dropped); trailing `,` `.` `;` `:` on a
  row, a term or a tail are typography; binder and quantifier clauses accept
  `i \in \mathcal{I}`, `i \in \mathit{I}`, `i \in I` and `i, j \in I`,
  and REFUSE by name what used to bind silently or vanish (a subscripted set,
  a tuple binder, a range, any clause that is neither a set membership, a
  where-clause nor a restriction). M1b: `text_ident_script` unwraps
  `\text{l}`/`\mathrm{l}` inside a script; `declared_product` inserts the
  `\cdot` between a declared parameter and a declared symbol written side by
  side (coefficient first, `x_{i} c_{i}` -> `c_{i} \cdot x_{i}`), leaving
  undeclared names for the parser to refuse. `restricted_set_widen` widens a
  binder or quantifier over a subscripted/superscripted set (`\\mathcal{S}_{i}`)
  to its base family and records the widening as a rewrite (the same recorded
  approximation the repository converter makes); Greek index letters
  (`\\mathit{delta} \\in T`) bind, and a `:` in a quantifier tail separates a
  restriction clause.
- **M1b declaration-driven script resolution** (`rewrite-2026.09.1`,
  issue #63; corpus evidence: 49 + 21 of the 220 papers still failing the
  Paper-1 promotion after the #52–#57 batch stall on superscripts and
  label subscripts). The canonical grammar has no superscripts and every
  subscript position is an index, so the normalizer now decides what a
  script is from the document itself — the `%@` header (declared names,
  shapes) and the body's binders/quantifiers — and rewrites bijectively:
  `bare_sub_brace`/`bare_sup_brace` brace unbraced scripts against the
  declarations (`B_u \cdot w_u` -> `B_{u} \cdot w_{u}`, a declared plain
  name such as `Z_1` stays); `superscript_index` moves bound-letter
  superscripts into the subscript (`x_{i}^{k}` -> `x_{i, k}`,
  `p_{n}^{t + 1}` -> `p_{n, t + 1}`, MathML-spaced `^{i j}` -> two
  indices); `superscript_label` folds label superscripts into plain names
  (`t_{i}^{arr}` -> `t_arr_{i}`, `v_{i}^{c}` -> `v_c_{i}`,
  `\mathit{tau}_{k}^{de}` -> `tau_de_{k}`, `Y_{i,s}^{1}` -> `Y_1_{i,s}`,
  `q^{*}` -> `q_star`, `d^{+}`/`d^{-}` -> `d_plus`/`d_minus`); `label_subscript` folds label subscripts
  (`h_{min}` -> `h_min`, `Z_{1}` -> `Z_1` when `Z` has no declared shape;
  a numeric subscript on a shaped symbol stays a fixed-element reference).
  Nested or delimited scripts are left untouched for the parser to refuse
  by name, glued bound letters split into indices (`x_{ij}` -> `x_{i, j}`),
  and a document without any `%@` declaration is left untouched by all
  five rules (nothing to resolve against). `RewriteRule` gained `ctx_replacement` (rules that read a
  `DocContext`), and a rule that declines records no rewrite. The
  declaration sidecar must declare the folded spellings.

### Fixed

- **Codec accepted undeclared identifiers silently** (issue #62): an
  undeclared referent fell through `_SymTab.kind()` as a `literal` term
  and a bare coefficient name was returned without checking it is a
  declared parameter, so unbraced subscripts (`B_u \cdot w_u`) ingested
  `ok=True` with `ref="w_u"`, `coefficient="B_u"` and did not round-trip
  (surfaced by the lab's re-promoted `trc.2014.06.003`). Both paths now
  refuse by name, pointing at the declaration and the braced form.

- **Grammar holes #52–#57 closed deterministically** (issues filed from the
  Paper-1 corpus promotion sprint; every fix is exact-or-refused-by-name,
  nothing is dropped silently):
  - *Codec parser* (`codec.latex`): `\leq`/`\geq`/`\leqslant`/`\geqslant`
    accepted as row comparators with token guards (previously `\leq` was read
    as `\le` plus a stray `q`, and `\left|` on a constraint LHS was read as
    `\le` — both silently corrupted the relation split); chained
    same-direction inequality rows `l \le e \le u` split into two constraints
    `<name>_lo`/`<name>_up` inheriting the row's quantifiers (#53;
    mixed-direction, equality, and 3+-comparator chains refused by name);
    subscripted coefficients `w_{e} \cdot x_{e}` resolve to the bare
    parameter exactly when the written indices match what grounding uses —
    the referent's bindings, or the unique in-scope binder/quantifier index
    per declared shape slot (#52); numeric `\frac{a}{b}` with a terminating
    decimal folds into the numeric coefficient, every other `\frac` is
    refused by name (#57); constant subscripts (`t_{0}`) get a named
    diagnostic pointing at the missing shape declaration — with the family
    declared they were already legal element references (#54); trailing
    `^{...}` or juxtaposed factors after a referent's subscript are refused
    by name instead of being **silently dropped** (previously
    `p_{e} x_{e}` parsed with `x` discarded and `x_{e}^{k}` lost its
    superscript index).
  - *M1b normalizer* (`mining.ingest.latex_normalizer`): `sum_merge`
    (consecutive `\sum` operators merge into one multi-binder `\sum`,
    order-preserving, #56); `overset_accent`/`underset_accent` (accent-shaped
    `\overset`/`\underset` pairs collapse to the standard accent command
    before `overset_base` can drop the accent); `accent_ident` and
    `prime_ident` (decorated identifiers rename bijectively to plain `\w+`
    names — `\hat{tc}` → `tc_hat`, `t'`/`k^{'}` → `tp`/`kp` — valid in every
    grammar position, #55). Rule-table version bumped to `rewrite-2026.08.1`.

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
