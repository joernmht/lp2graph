# ADR-0006: Determinism as a hard, load-bearing requirement

- **Status:** accepted
- **Date:** 2026-06-14

## Context

`lp2graph` mines published LP/MILP formulations into a reproducible dataset and
taxonomy (Paper 1). Every artefact the library emits — graphs, LaTeX, metrics,
mining records — is downstream of research claims, so byte-for-byte
reproducibility across runs, machines, and Python versions is a correctness
property, not a nicety. Python has several common sources of run-to-run
variation: `set` / `frozenset` iteration order, hash randomisation, unseeded
RNGs, `dict` ordering assumptions over unsorted input, and wall-clock/`random`
calls embedded in output.

This expectation is enforced throughout the code (frozen models, insertion-order
graphs, snapshot tests, versioned mining resources) and stated in `CLAUDE.md`,
but had no ADR recording it as an architectural constraint.

## Decision

**Determinism is a hard requirement across the whole library.** Concretely:

1. The canonical `Formulation` and the typed `Graph`/`Node`/`Edge` are frozen
   (`extra="forbid"`); the internal graph preserves insertion order and
   `__eq__` compares ordered sequences (see ADR-0002).
2. Anything order-sensitive is **sorted before it is emitted**; output never
   depends on `set` iteration order or on `dict` ordering over unsorted data.
3. Every RNG is explicitly seeded (`random.Random(seed)`); no `Math.random`,
   no unseeded `numpy`/`random`, no wall-clock values in output.
4. The `mining` package versions every frozen resource in `mining/versions.py`
   and **stamps the version into emitted records** so a record names the exact
   resources that produced it.
5. **Snapshot tests** assert identical output across runs and guard against
   regressions.

## Rationale

- Research reproducibility: a reviewer or co-author must regenerate the exact
  dataset/taxonomy from the same inputs.
- Diffability: sorted, stable output makes review and version control tractable.
- Debuggability: a non-reproducible bug in a mining pipeline is far more
  expensive to chase than the discipline of sorting and seeding up front.

## Consequences

- New code must sort before emitting and thread an explicit `seed` through any
  stochastic step; reviewers reject `set`-iteration-in-output and unseeded RNGs.
- New frozen resources in `mining` must be added to `mining/versions.py` and
  stamped into outputs.
- Optional-dependency back-ends (NetworkX, HDBSCAN, scikit-learn, …) must be
  used in deterministic mode (seeded, sorted) or wrapped so their output is
  normalised before emission.
- The snapshot-test suite is part of the determinism contract; changing emitted
  output is an intentional, reviewed act (update the snapshot deliberately).

## Alternatives considered

- *"Deterministic enough" / best-effort:* rejected — partial determinism still
  yields irreproducible research artefacts and silent diffs.
- *Freeze only the mining outputs:* rejected — views, codec, and metrics feed
  the mining pipeline, so determinism must hold end-to-end to be meaningful.
</content>
