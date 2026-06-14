# LP mining extensions (`lp2graph.mining`)

The `lp2graph.mining` subpackage implements the modules the **LP Mining with
LP2Graph** method needs on top of the deterministic core library. Each module
maps to a tracked issue (M1–M6). Everything is deterministic: every frozen
resource is versioned in `lp2graph.mining.versions` and the version strings are
stamped into the records the pipeline emits, so two runs over the same inputs
produce byte-identical artifacts and any resource change is a readable diff.

The optional heavy dependencies (`networkx`, `pyomo`, `nltk`/WordNet,
`hdbscan`) are all imported lazily; the package imports and the core paths run
on the standard install.

## M1 — Heterogeneous ingestion front-end (`mining.ingest`)

Turns idiosyncratic source artifacts into validated `Formulation`s, never
silently dropping a failure.

- **Solver-code importers.** `from_pyomo(model)` builds a canonical
  `Formulation` from a Pyomo `ConcreteModel`/`AbstractModel` (structural,
  best-effort). `.gms` / `.mod` / `.jl` route through a registry that returns
  honest, structured failures rather than swallowing the input.
- **Non-canonical LaTeX normalizer.** `normalize_latex` applies a *versioned*
  rewrite-rule table (unicode/ascii operators → canonical macros, `*` →
  `\cdot`, set wrappers, …), logging every rewrite with a `SourceSpan` into the
  original text, then `ingest_latex` parses the canonical result via the codec
  and runs the two-phase validator.
- `ingest(path_or_text, fmt=...)` dispatches by extension and always returns an
  `IngestionResult` whose `failures` are reported, never raised away.

## M2 — Lexical homologizer & concept vectorizer (`mining.homologize`)

Reduces names and descriptions to comparable concepts and emits frozen TF-IDF
concept vectors.

- `tokenize` / `lemmatize` with a versioned stop-list; `concept_bag` maps tokens
  to concepts through a frozen domain thesaurus (greedy multi-word match) with
  an optional WordNet backend.
- `ConceptVectorizer` over a sorted, diffable `Vocabulary` produces
  L2-normalized TF-IDF vectors that are stable across runs.
- `TypeSignature` exposes the structural signature `τ(s)` (domain/role/kind/
  shape/quantifier structure) read straight from the canonical model, and
  `Entity` / `corpus_entities` give the levels V/C/M their mineable units.

## M3 — Cluster-and-name operator + taxonomy (`mining.cluster`)

- `CN(entities, vectors, vocab, config)` clusters in cosine-distance space
  (deterministic average-linkage default; `fixed_k` with silhouette selection;
  optional HDBSCAN) and names each part by aggregated TF-IDF weight. Every
  entity lands in exactly one part, including an explicit `unassigned`.
- `induce(formulations)` runs the bottom-up passes — Level V (variables/params)
  → Level C (constraints/objective, *conditioned on Level-V membership*) →
  Level M (family/type histograms + flags + bucketed structural metrics) — plus
  the text-only `domain` and `solution_approach` clusterings.
- `stability_report` emits silhouette, bootstrap ARI, and sensitivity to the
  algorithm and `|C|`.

## M4 — Labeling service with closed-loop store (`mining.label`)

Two-stage labeling with a versioned, self-growing store.

- Controlled vocabularies per `(level, dimension)` seeded from M3.
- Stage 1 `RuleLayer` over flags / type-signatures / seed lexicon (label or
  abstain); Stage 2 calibrated one-vs-rest `LinearSVM`.
- The closed `LabelingService` loop gates on `theta_low` / `theta_high` +
  rule-consistency into auto-accept / human-adjudicate / defer, writes back to a
  versioned `LabelStore`, promotes confirmed `concept → label` rules, and
  retrains. Guardrails re-score a held-out gold set each loop, track drift and
  Cohen's κ, and raise a rollback flag if precision drops. The loop is
  replayable from the decision log.

## M5 — Corpus & provenance manager (`mining.corpusmgr`)

- `ProvenanceRecord` per formulation (source, venue + quality tier, year,
  citation count @ freeze date, domain shell, activity, priority cell P1–P5).
- `CorpusManifest` (frozen search date + query strings) makes a corpus
  regenerable. `deduplicate` groups by canonical schema-graph hash **or**
  bibliographic key (transitive); `select_representatives` picks the
  highest-citation member per cluster with documented fallbacks.

## M6 — Intra-cluster schema-graph isomorphism (`mining.isomorphism`)

`isomorphism_report(clusters)` computes, per cluster, the schema-graph
isomorphism rate (pairwise and whole-cluster), via the existing NetworkX export,
so a reader can judge how representative a validated anchor is.
