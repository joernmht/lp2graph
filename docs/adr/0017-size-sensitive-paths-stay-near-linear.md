# ADR-0017: Size-sensitive paths stay near-linear, measured by a benchmark rather than by timing tests

- **Status:** accepted
- **Date:** 2026-10-19

## Context

Two input sizes grow without a bound the library controls. One is a **ground
view**, which has a node per variable or constraint instance, so a 40×40
assignment model is already 1.7k nodes. The other is a **flat import** (LP,
MPS, PuLP), which declares one template per scalar column, so a MIPLIB-size
file brings tens of thousands of templates. Most code was written for
template-scale graphs of 10–50 nodes. The first performance-efficiency pass
(2026-10-19) measured the size-sensitive paths and found four quadratic or
worse costs, none of them visible at template scale:

| path | cost | measured before → after |
|---|---|---|
| `metrics.structural.graph_diameter` | BFS from every node, O(V·(V+E)) | 36 s → 0.35 s (4k-node `mip_2_1_big_m` ground view) |
| `interop.mps.from_mps_string` | each row collected by scanning every column, O(R·C) | 1.86 s → 0.37 s (2,000 rows) |
| `core.validate.validate` | shape maps rebuilt per constraint, O(C·(V+P)) | dominant cost of every flat import |
| `validation.pipeline` duplicate-name check | `list.count` per name, O(N²) | O(N) |

The same pass found that `graph_diameter` also broke ADR-0006. Its BFS walked
`set[str]` neighbour sets, so the path it reported changed with
`PYTHONHASHSEED`.

No test caught any of this. The suite runs on template-scale inputs, and a
wall-clock assertion would not help: CI runners vary by several times, so a
timing threshold either flakes or sits too loose to catch a quadratic.

## Decision

1. **Size-sensitive paths stay near-linear in model size.** These are views,
   structural metrics, the grounder, the `interop` readers and writers, and
   `validate`/`validate_text`. In practice that rules out:
   - rebuilding a model-wide map inside a per-element loop. This means
     `Formulation.index_map()` / `parameter_map()` / `variable_map()`, which
     build a fresh dict on every call. Build the map once and pass it down, as
     `views/ground.py` does and `solve/grounder.py` now does through `_Ctx`.
   - `list.count`, `list.index` or `x in list` over model-sized lists inside
     loops;
   - collecting one axis of a sparse matrix by scanning the other.
2. **Metrics stay exact, not approximate.** A faster algorithm has to return
   the same value. `graph_diameter` uses exact eccentricity bounding (Takes &
   Kosters 2011), checked against brute force on 400 seeded random graphs and
   three ground views (`tests/test_metrics.py`).
3. **Speed never costs determinism.** Graph traversals iterate
   insertion-ordered lists, never sets, and ties break on node id. A
   subprocess test runs the reported diameter path under four hash seeds.
4. **Cost is measured by `benchmarks/scaling.py`, not asserted in CI.** The
   script generates seeded inputs at doubling sizes and prints wall-clock per
   path. A change to a size-sensitive path should be run through it before and
   after, and the growth between rows compared. CI keeps asserting
   *behaviour*: exactness, determinism, identical output.

## Consequences

- Flat imports and ground-view metrics are usable at MIPLIB and ground scale.
  Outputs are unchanged, except that `graph_diameter`'s `data["path"]` is now
  fixed and so may differ from what earlier releases reported.
- A regression back to quadratic is still not caught automatically. It shows
  up only when someone runs the benchmark. This is accepted: the alternative
  is flaky CI.
- **Costs knowingly left in place** (re-assess when the Paper-1 corpus exists;
  today it is unstarted, so n is small):
  - JSON Schema validation in `loads()` (ADR-0013) dominates small-document
    load time, at about 3 ms per document on this machine with the system
    `jsonschema`. ADR-0013 still governs it; the remedy it names, an opt-out
    for internally produced files, is not needed yet.
  - M3 clustering. `mining/cluster/agglomerative.py` recomputes average
    linkage per merge, about O(n³). `select_k` re-clusters per k, and
    `stability_report` runs about 35 full clusterings. A Lance–Williams update
    would fix this; it is queued in the quality backlog.
  - `mining/ingest/latex_normalizer.py` match callbacks re-count the prefix
    of the body per match. This is quadratic in body length, which matters
    only for very long MathML-derived bodies.

## Alternatives considered

- **Timing assertions in pytest** (for example "diameter of a 4k-node graph
  under 1 s"). Rejected: runner variance makes the threshold either flaky or
  meaningless.
- **An approximate diameter** (two-sweep BFS), as M3's taxonomy only buckets
  the value. Rejected: `graph_diameter` is a public metric that downstream
  datasets record as a number (raiLPminerExperimentation's `dataset.py`).
  Approximation would silently change those numbers, and the exact bounding
  algorithm is already fast enough.
- **Caching `Formulation.*_map()`** on the frozen model with
  `functools.cached_property`. This would fix every caller at once. Deferred:
  the pydantic frozen model with `extra="forbid"` needs a private-attribute
  cache, which touches the canonical model that ADR-0006 and ADR-0013 guard.
  Hoisting at the few hot call sites is the smaller change.
