---
name: lp2graph-dev
description: >-
  Build, test, lint, and type-check the lp2graph library, and add modules the
  right way. Use whenever running pytest/ruff/mypy in this repo, debugging an
  import error like "ModuleNotFoundError: lp2graph", or adding code (especially
  under src/lp2graph/mining). Encodes the PYTHONPATH=src workflow and the
  determinism / optional-dependency / frozen-model conventions this repo
  enforces in CI.
---

# lp2graph developer workflow

## TL;DR — the one thing that trips everyone up

The package is **not pip-installed** in this environment (PEP 668 /
externally-managed Python). `pip install -e .` fails and bare `pytest` raises
`ModuleNotFoundError: No module named 'lp2graph'`. **Always run tooling with
`PYTHONPATH=src`.**

```bash
PYTHONPATH=src python3 -m pytest -q                  # full suite
PYTHONPATH=src python3 -m pytest tests/mining -q      # one area
PYTHONPATH=src python3 -m pytest tests/test_codec.py::test_x  # one test
PYTHONPATH=src python3 -m ruff check src tests        # lint
PYTHONPATH=src python3 -m ruff format src tests        # format (pre-commit hook)
PYTHONPATH=src python3 -m mypy                         # mypy --strict (targets src/lp2graph)
```

Run all four (ruff check, ruff format --check, mypy, pytest) before declaring
work done — CI runs them on Python 3.11–3.13, Linux + macOS.

If you need a runtime dep for verification (e.g. networkx), install it with
`pip install --break-system-packages networkx numpy` — but keep it OPTIONAL in
code (lazy import) and `pytest.importorskip(...)` in tests.

## Architecture (one-screen mental model)

`src/lp2graph/core/model.py` defines the canonical pydantic `Formulation` —
the **single source of truth**, mirroring `schema/canonical.schema.json`.
Everything is derived from it on demand:

- `core/graph.py` — internal insertion-order-deterministic typed multigraph.
- `views/` — `schema`, `hybrid`, `ground`.
- `metrics/` — `flags`, `structural`, `classification`.
- `codec/` — deterministic LaTeX ⇄ model (no LLM): `to_canonical_latex` /
  `from_canonical_latex`.
- `solve/` — grounding + `pulp`/HiGHS back-end.
- `export/` — `networkx`, `pyg`, `dgl`, `pyomo_stub`.
- `render/`, `nl/`.
- `mining/` — LP-mining extensions M1–M6 (see `docs/mining.md`).

## Hard rules

1. **Determinism.** Frozen models, insertion-order graphs, snapshot tests.
   Sort before emitting anything order-sensitive; seed every RNG
   (`random.Random(seed)`); never rely on `set` iteration order in output. The
   `mining` package versions every frozen resource in `mining/versions.py` and
   stamps the version into emitted records.
2. **Optional deps are lazy.** Core install is `pydantic` + `jsonschema` only.
   Import `networkx`/`pyomo`/`pulp`/`torch`/`nltk`/`hdbscan` *inside* the
   function that uses them; gate tests with `pytest.importorskip`. Add new
   optional modules to `[[tool.mypy.overrides]]` `ignore_missing_imports`.
3. **Style.** `from __future__ import annotations`; frozen dataclasses / pydantic;
   explicit `__all__`; line-length 100; module docstrings say *why*; no `Any`
   in public APIs. Tests go in `tests/` with **no `__init__.py`**.
4. **Scope.** Don't fix pre-existing lint debt in `examples/` or the untracked
   `ui/` as a side effect; keep `src/` and `tests/` clean.

## Adding a module (checklist)

- New code under `src/lp2graph/<area>/`; tests under `tests/<area>/`.
- If it's a mining module, version any frozen resource in `mining/versions.py`
  and stamp it into outputs.
- Run: `ruff format` → `ruff check` → `mypy` → `pytest` (all with
  `PYTHONPATH=src`).
- Update `CHANGELOG.md` under `[Unreleased]`; if user-facing, add/extend a page
  in `docs/` and wire it into `mkdocs.yml` nav (the mkdocs build is `--strict`,
  so an un-navigated page breaks it).
