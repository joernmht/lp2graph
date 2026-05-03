# ADR-0001: Build tool — `hatchling`

- **Status:** accepted
- **Date:** 2026-05-03
- **Deciders:** bootstrap

## Context

We need a Python build backend that supports modern PEP 621 metadata,
extras, and editable installs. Candidates: `setuptools`, `hatchling`,
`flit-core`, `poetry-core`, `pdm-backend`, `uv`'s `uv-build`.

## Decision

**Use `hatchling`** as the build backend, declared in
`pyproject.toml`'s `[build-system]`. Developers can use `pip`, `uv`, or
`hatch` interchangeably for installs.

## Consequences

- Modern, PEP 621-native, no `setup.py`. Sdist and wheel both built
  via `python -m build`.
- Editable installs via `pip install -e .` work without configuration.
- `hatch` is *not* required for development; we do not adopt
  `hatch`-managed environments. Contributors use whatever virtualenv
  manager they like.
- License-files declared via `license = { text = "Apache-2.0" }` /
  `license-files = ["LICENSE"]` (PEP 639), supported by hatchling
  ≥ 1.21.

## Alternatives considered

- `setuptools`: works, but PEP 621 support feels grafted on; we want
  the modern path.
- `poetry-core`: requires Poetry for development; we do not want to
  impose a manager.
- `flit-core`: minimal, but does not handle our license-files block
  cleanly.

## Revisit

Re-evaluate if hatchling's release cadence falls behind, or if a
better-supported PEP 639 implementation appears.
