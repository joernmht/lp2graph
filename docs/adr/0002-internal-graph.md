# ADR-0002: Internal graph — library-agnostic typed structure

- **Status:** accepted
- **Date:** 2026-05-03

## Context

View derivations produce graphs. Renderers, metrics, and exporters
consume them. The candidates for the internal graph type:

1. NetworkX `MultiDiGraph` (the source repo's choice).
2. PyG `HeteroData`.
3. A dedicated typed structure inside `optgraph`.

## Decision

**Use a small, dedicated typed structure** in
`optgraph.core.graph` (`Graph`, `Node`, `Edge` dataclasses). NetworkX,
PyG, and DGL are *export targets*, not internal representations.

## Rationale

- The core library must be importable without NetworkX, PyG, or DGL.
  An internal NetworkX type would force `networkx` into hard
  dependencies.
- Determinism is a load-bearing property. NetworkX's iteration order
  is dict-stable but the API surface (especially for multigraphs) is
  large enough that subtle non-determinism is hard to rule out.
- A small typed structure is straightforward to test and serialize.
- Renderers and metrics can rely on stable `cls`, `subtype`, `role`,
  and `data` shapes without spelunking through framework conventions.

## Consequences

- Adapters in `optgraph.export.*` perform the conversion. Each adapter
  has a dedicated round-trip test.
- The internal type's API is small by design. If we need shortest-path
  utilities for a metric, we either implement them in the metric
  module or convert to NetworkX inside that metric.
- Insertion order of nodes and edges is preserved; `Graph.__eq__`
  compares ordered sequences. Snapshot tests rely on this.

## Alternatives considered

- NetworkX as the internal type: forces `networkx` into core; loses
  type guarantees.
- PyG as the internal type: forces a heavyweight dependency; couples
  the library to a single GNN framework; PyG's HeteroData is geared
  toward training, not toward symbolic introspection.
