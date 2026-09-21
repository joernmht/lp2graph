# Software stack — lp2graph

Reference for the languages, runtimes, libraries, entry points, and
build/test/CI commands of `lp2graph`. Maintained by the nightly quality pass;
update when reality drifts. Last reviewed: 2026-09-21.

## Language & runtime

- **Python** — `requires-python = ">=3.11"`; CI matrix tests 3.11, 3.12, 3.13.
  Dev/CI on this machine runs CPython 3.12.
- Every module starts with `from __future__ import annotations`.
- Determinism is a hard requirement (see ADR 0006): frozen models, insertion-
  order graphs, seeded RNGs, sorted output, snapshot tests.

## Core dependencies (always installed)

| Library | Constraint | Role |
|---|---|---|
| `pydantic` | `>=2.0` | Canonical frozen `Formulation` model (`core/model.py`); single source of truth |
| `jsonschema` | `>=4.0` | Validates every loaded document against `schema/canonical.schema.json`, in `core/loader.py` (ADR-0013). Declared but **never imported** before 2026-09-21. |

## Optional dependencies (lazy-imported — see ADR 0007)

Imported *inside* the function that needs them so the package imports with only
the two core deps. Tests gate these paths with `pytest.importorskip("<dep>")`,
and each is listed in `[[tool.mypy.overrides]]` `ignore_missing_imports`.

Load them through **`lp2graph._optional.require(module, feature=...)`**, which
raises the `ImportError` naming the extra that ADR-0007 clause 3 requires.
`_optional._EXTRA_FOR` maps import name → extra and is asserted against
`pyproject.toml` by `tests/test_optional_deps.py`, so an extra can never be
named in an error message without being installable.

`all` must install on every environment `requires-python` claims (ADR-0014), so
it excludes both `gurobi` (commercial and licence-gated — it must not fail for a
user without a licence) and `dgl` (no Python 3.13 wheel and no sdist). pip
resolves an extra atomically, so one unresolvable member makes the whole extra —
and every unrelated backend in it — uninstallable. Re-check the extras against
PyPI whenever the CI matrix gains a Python version.

| Extra | Libraries | Enables |
|---|---|---|
| `networkx` | `networkx>=3.0` | `export/networkx_adapter.py`, M6 isomorphism |
| `pyg` | `torch>=2.0`, `torch_geometric>=2.4` | `export/pyg.py` |
| `dgl` | `dgl>=2.0; python_version < "3.13"`, `torch>=2.0` | `export/dgl.py`. Marked: DGL ships no cp313 wheel and no sdist (ADR-0014). |
| `pyomo` | `pyomo>=6.7` | `export/pyomo_stub.py`, M1 Pyomo import |
| `solver` | `pulp>=2.8`, `highspy>=1.7` | `solve/` grounding back-end, `interop` PuLP I/O |
| `gurobi` | `gurobipy>=11.0` | `interop.from_gurobipy` / `to_gurobipy` (commercial, licence-gated) |
| `mining` | `networkx`, `pyomo`, `nltk>=3.8`, `hdbscan>=0.8` | M1–M6 extension backends |
| `all` | every *unmarked* non-commercial extra above | everything except `gurobi` (commercial) and `dgl` (no cp313 wheel — ADR-0014) |
| `dev` | `pytest`, `pytest-cov`, `ruff>=0.15.12,<0.16`, `mypy>=1.10`, `pre-commit` | development |
| `docs` | `mkdocs-material`, `mkdocstrings[python]` | docs site |

> **PuLP 4.0 compatibility (migrated 2026-06-26, ADR-0008):** the `solve/`
> path no longer uses any API deprecated for PuLP 4.0. It builds variables via
> `prob.add_variable(...)`, counts constraints via `prob.numConstraints()`, and
> defaults to `COIN_CMD` through `solve.default_solver()` (with a bundled-CBC
> path fallback for PuLP 3.x). `tests/test_solve.py::test_solve_path_is_pulp4_clean`
> fails if any PuLP `DeprecationWarning` reappears. Floor stays `pulp>=2.8`;
> the migrated code runs on both 3.x and the forthcoming 4.0.

## Architecture (single source of truth → derived views)

```
core/model.py  Formulation (pydantic, frozen, extra="forbid")
core/graph.py  insertion-order-deterministic typed multigraph
  ├ views/     schema · hybrid · ground
  ├ metrics/   flags · structural · classification
  ├ codec/     deterministic LaTeX ⇄ model (no LLM)
  ├ solve/     grounding + pulp/HiGHS back-end
  ├ export/    networkx · pyg · dgl · pyomo_stub
  ├ render/ · nl/
  ├ interop/   7 text formats + 3 live solver APIs, all via the pivot (ADR-0011)
  ├ transform/ big-M rewriting
  ├ validation/ faulty-input detection + the end-to-end validate pipeline
  └ mining/    LP-mining extensions M1–M6 (versioned in mining/versions.py)

formats.py     the single format registry every layer routes by (ADR-0012)
_optional.py   require(): optional-dep loading with ADR-0007 error messages
```

`interop/`, `transform/` and `validation/` post-date the original diagram in
`CLAUDE.md`, which still lists only the core chain; treat this table as
current.

## Entry points

- **CLI:** `lp2graph = "lp2graph.cli:main"` (`[project.scripts]`); also
  `python -m lp2graph.cli`. Subcommands: `validate`, `view`, `render`,
  `metrics`, `export` (`networkx`/`pyg`/`dgl`/`latex`/`pyomo`), `latex`
  (graph→text), `parse` (text→graph), `describe` (NL), `solve` (ground +
  MILP). `main(argv)` returns an int exit code and is exercised in-process by
  `tests/test_cli.py`.
- **Library:** top-level `lp2graph` re-exports `Formulation`, `load`/`loads`,
  `validate`/`ValidationError`, `describe`, and the codec.
- **Docs site:** MkDocs (`mkdocs.yml`), built `--strict`.

## Build / test / lint / type commands

The package is **not** pip-installed in this environment (PEP 668), so prefix
local tooling with `PYTHONPATH=src`:

```bash
PYTHONPATH=src python3 -m pytest -q                 # full suite (445 tests, 12 skipped here)
PYTHONPATH=src python3 -m ruff check src tests      # lint (line-length 100)
PYTHONPATH=src python3 -m ruff format --check src tests   # format gate
PYTHONPATH=src python3 -m mypy                      # mypy --strict (src/lp2graph)
mkdocs build --strict                               # docs
# the ASCII-locale run CI's `c-locale` job does (ADR-0015):
PYTHONPATH=src PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 LC_ALL=C python3 -m pytest -q
```

## CI / pre-commit

- **CI** (`.github/workflows/ci.yml`) on push/PR to `main`, five independent
  jobs:

  | Job | What it gates |
  |---|---|
  | `lint` | `ruff check` → `ruff format --check` → `mypy src/lp2graph`, once on py3.12 |
  | `test` | `pytest --cov` + CLI schema validation, matrix {ubuntu, macos} × py{3.11, 3.12, 3.13} |
  | `wheel` | builds a real wheel, asserts `lp2graph/schema/canonical.schema.json` is inside, installs it, calls `canonical_schema()` (ADR-0013) |
  | `c-locale` | the suite under `PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 LC_ALL=C` (ADR-0015) |
  | `backends` | `[dev,solver,pyomo,mining]` on py3.12; fails if an optional backend still skips for a missing dep |

  **`lint` is deliberately its own job** (split 2026-09-21). As steps inside
  `test` they ran six times and, because a job fails fast, a one-file format
  drift hid every test result behind it — a red `Lint` meant there was *no*
  test signal rather than a passing one. That cost a sibling repo 3.5 weeks of
  unnoticed red (STYLE.md §6).

  `test` installs only `[dev]`, so the optional-backend paths skip there; that
  is what `backends` exists to cover. `backends` skips `[all]` on purpose
  (torch ≈ 2 GB), so the torch/dgl exporters remain the one backend family CI
  does not execute. `docs.yml` builds the site; `release.yml` publishes.
- **pre-commit** (`.pre-commit-config.yaml`): pre-commit-hooks v4.6.0,
  ruff-pre-commit **v0.15.12** (`ruff --fix` + `ruff-format`), mirrors-mypy
  v1.10.0. Keep the pre-commit ruff rev and the `dev` extra's `ruff` pin in
  lock-step so local, pre-commit, and CI agree on formatting.

## Validation harnesses (functional fidelity)

Two families of fidelity checks live under `corpus/validation/`. Both are
**standalone scripts**, not collected by pytest — run them by hand:

- **`codec_pipeline/run.py`** — end-to-end `formulation JSON → LaTeX → parse →
  ground+solve → objective` for the 5 specs in `codec_pipeline/instances/`,
  asserting (1) codec round-trip, (2) pipeline-solve == direct-solve, (3)
  cross-solver agreement CBC/HiGHS/Gurobi, (4) objective == known optimum.
  `python3 run.py` → `results/codec_pipeline_results.json`. **The known-optimum
  and round-trip parts are ALSO gated inside pytest** via `tests/test_solve.py`
  (which consumes the same `instance_files` fixture, `importorskip("pulp")`);
  the cross-solver combination is script-only.
- **`scripts/run_experiments.py`** — external published-optima fidelity:
  MIPLIB `timtab1` (optimum **764772.0**) and the `marcotallone` maintenance
  model (**3913.47**), cross-solved across Gurobi/HiGHS/CBC with round-trip
  re-emit. Script-only (no pytest coverage) — the published anchors are also
  recorded as `PAPER_ANCHORS` in `codec_pipeline/run.py`.

Gap: the cross-solver + external-anchor checks are not in CI, so a regression
there would only surface on a manual run. See the quality backlog (2026-07-15).

## Build backend & packaging

- `hatchling>=1.21`; wheel packages `src/lp2graph`. Version `0.3.0`
  (`Development Status :: 3 - Alpha`). License Apache-2.0.
- **Packaged data:** `schema/canonical.schema.json` is mapped into the wheel at
  `lp2graph/schema/canonical.schema.json` by
  `[tool.hatch.build.targets.wheel.force-include]`. `packages = ["src/lp2graph"]`
  alone silently drops it — the published v0.3.0 wheel contains **zero** JSON
  files — so reach it only through `lp2graph.canonical_schema()` /
  `canonical_schema_path()`, never by path arithmetic from `__file__`
  (ADR-0013). The repo-root copy remains the single source of truth because its
  `$id` URL is public; the accessor falls back to it for `PYTHONPATH=src`
  checkouts. The CI `wheel` job guards the mapping.

## Security notes (untrusted-input surfaces)

The library has **no `eval`/`exec`/`pickle`/`subprocess`/`os.system` paths** and
no network I/O; deserialization is `json.loads` -> pydantic `model_validate`
(frozen, `extra="forbid"`) -> in-memory semantic `validate()` -- structurally
safe (no `$ref`/SSRF resolver). The genuine attack surface is the ingestion
boundary, where the Paper-1 corpus is mined from **third-party GitHub repos**:

- **`mining/ingest/dispatch.py`** -- reads arbitrary source files. Hardened
  2026-07-02 (ADR-0009): non-UTF-8 files are reported as read-stage
  `IngestionResult` failures, not raised, so one bad-encoding file no longer
  aborts a batch. **Open follow-up:** no input-size bound before `read_text`
  (multi-GB file -> memory-exhaustion DoS); `_looks_like_path` treats short
  path-like strings as filesystem paths.
- **Regex-driven LaTeX parsing** (`codec/latex.py`,
  `mining/ingest/latex_normalizer.py`) -- reviewed for catastrophic backtracking
  (ReDoS); patterns are lazy (`.*?`) or non-nested, no `(a+)+`-class constructs
  found. `ingest_latex` swallows all parse exceptions, so a *hang* (not a crash)
  would be the failure mode of any future pathological pattern -- keep new
  ingest regexes linear.
