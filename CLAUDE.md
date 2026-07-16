# CLAUDE.md — lp2graph

Guidance for Claude Code working in this repository. These instructions
override default behavior; follow them exactly.

## What this is

`lp2graph` is a typed-graph representation of LP/MIP/MILP formulations. The
**canonical pydantic `Formulation`** (`src/lp2graph/core/model.py`) is the
*single source of truth*. Everything else is derived on demand from it:

```
Formulation (core/model.py, mirrors schema/canonical.schema.json)
  → typed Graph (core/graph.py)         insertion-order deterministic multigraph
  → views/        schema · hybrid · ground
  → metrics/      flags · structural · classification
  → codec/        deterministic LaTeX ⇄ model (no LLM)
  → solve/        grounding + pulp/HiGHS back-end
  → export/       networkx · pyg · dgl · pyomo_stub
  → render/ · nl/
  → mining/       LP-mining extensions M1–M6 (see below)
```

**Determinism is a hard requirement.** Models are frozen / `extra="forbid"`;
the internal graph preserves insertion order; snapshot tests assert identical
output across runs. Never introduce nondeterminism (`set` iteration order in
output, `dict` ordering assumptions on unsorted data, `Math.random`/`Date`,
unseeded RNG). Sort before emitting; seed every RNG.

## Running tests / lint / types in THIS environment

The package is **not** pip-installed here (PEP 668 / externally-managed
Python), so `pip install -e .` fails and bare `pytest` errors with
`ModuleNotFoundError: lp2graph`. **Always prefix with `PYTHONPATH=src`:**

```bash
PYTHONPATH=src python3 -m pytest -q                 # full suite
PYTHONPATH=src python3 -m pytest tests/mining -q     # one area
PYTHONPATH=src python3 -m ruff check src tests       # lint (line-length 100)
PYTHONPATH=src python3 -m ruff format src tests       # format (a pre-commit hook)
PYTHONPATH=src python3 -m mypy                        # mypy --strict, config targets src/lp2graph
```

`ruff format --check` is enforced by pre-commit — run `ruff format` on files
you add. `mypy` config is `files = ["src/lp2graph"]`, `strict = true`.

CI runs ruff + ruff-format + `mypy --strict src/lp2graph` + pytest on
Linux/macOS for Python 3.11–3.13. Keep all four green.

Pre-existing lint debt in `examples/` and the untracked `ui/` is **not**
yours — don't "fix" it in unrelated PRs; only keep `src/` and `tests/` clean.

## Releasing to PyPI

The package is on PyPI as `lp2graph` (first release v0.3.0, 2026-07-11) via
**trusted publishing** (OIDC — no tokens anywhere). `release.yml` publishes
whatever `main` is at the tag, and CI does **not** gate it, so only release
when CI on `main` is green:

1. Bump `version` in `pyproject.toml`, commit, push, wait for CI.
2. `git tag vX.Y.Z && git push origin vX.Y.Z` — the tag must match the
   pyproject version. `release.yml` builds sdist+wheel and publishes.
3. `gh release create vX.Y.Z --title ... --notes ...` (the workflow does not
   create the GitHub release entry).
4. Verify: `pip install --target /tmp/t lp2graph && PYTHONPATH=/tmp/t python3
   -c "import lp2graph; print(lp2graph.__version__)"`.

The PyPI side is a *pending publisher* config owned by Joern (project
`lp2graph`, repo `joernmht/lp2graph`, workflow `release.yml`, environment
`pypi`) — if publishing 403s, that config is the first thing to check.

## Optional dependencies

Core deps are only `pydantic` + `jsonschema`. Everything heavier is an
**optional extra, lazily imported inside the function that needs it**, so the
package imports without it: `networkx`, `pyomo`, `pulp`/`highspy`, `torch`/PyG/
DGL, and (for mining) `nltk`/WordNet, `hdbscan`. In tests, gate optional-dep
paths with `pytest.importorskip("<dep>")`. Mirror the existing
`mypy.overrides` `ignore_missing_imports` list when adding a new optional dep.

## Conventions (match the surrounding code)

- `from __future__ import annotations` at the top of every module.
- Frozen dataclasses / frozen pydantic models; explicit `__all__`.
- Module docstrings explain *why* the module exists; public functions have
  docstrings. No `Any` in public APIs.
- Tests live in `tests/` with **no `__init__.py`** (don't add one).
- Adapt-from-source files credit the origin in their docstring (see
  `metrics/classification.py`).

## The mining subpackage (`src/lp2graph/mining/`, issues #38–#43)

LP-mining extensions on top of the core. Every frozen resource is versioned in
`mining/versions.py` and **stamped into emitted records** for reproducibility.

| Pkg | Issue | Purpose |
|---|---|---|
| `mining.ingest` | M1 #38 | Pyomo importer + versioned non-canonical LaTeX normalizer (source-span provenance); failures returned as `IngestionResult`, never dropped |
| `mining.homologize` | M2 #39 | tokenize/lemmatize + stop-list, thesaurus(+WordNet) concept map, TF-IDF `ConceptVectorizer`, type signature `τ(s)`, `Entity`/levels V/C/M |
| `mining.cluster` | M3 #40 | `CN` operator, Level V→C→M `induce`, `stability_report` |
| `mining.label` | M4 #41 | rule layer + calibrated `LinearSVM`, closed loop, replayable versioned `LabelStore`, gold-set guardrails |
| `mining.corpusmgr` | M5 #42 | provenance records, `CorpusManifest`, dedup, representative selection |
| `mining.isomorphism` | M6 #43 | per-cluster schema-graph isomorphism rate (NetworkX) |

When extending mining: keep pure-Python/deterministic, version any new frozen
resource in `versions.py`, and add tests under `tests/mining/`. See
`docs/mining.md`.
