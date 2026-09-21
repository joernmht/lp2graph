# ADR-0015: Text I/O declares its encoding, and artifact writes pin the newline

- **Status:** accepted
- **Date:** 2026-09-21

## Context

Python's text I/O defaults follow the *locale*: `open()`, `Path.read_text()` and
`Path.write_text()` use `locale.getpreferredencoding(False)` when no `encoding`
is passed, and a text write with `newline=None` rewrites every `"\n"` as
`os.linesep`. On Linux both defaults are invisible — PEP 538/540 coerce the C
locale to UTF-8, and `os.linesep` is already LF — so an omission accumulates
silently and is felt only by someone running the code elsewhere.

lp2graph is the most exposed of these repos to that trap, for two reasons:

- It is a **library other people install** (PyPI since v0.3.0), so its callers'
  locales are not ours. Under a cp1252 default (the Windows norm) a read of a
  UTF-8 file does *not* raise — cp1252 maps almost every byte, so it silently
  mojibakes (`Bešinović` → `BeÅ¡inoviÄ‡`) — while a write of the same content
  raises `UnicodeEncodeError`. The canonical LaTeX codec emits mathematical
  operators and the formulation catalog carries non-ASCII prose, so both paths
  are live.
- **Determinism is a hard requirement here** (ADR-0006, CLAUDE.md): snapshot
  tests assert identical output across runs. CRLF output breaks a
  byte-identical-artifact claim on *every line*, for a reason invisible in a
  diff view — and it is the emitted artifacts, not in-process values, that the
  mining corpus and its hashes are built from.

Measured in this repo before the change: **1** text read in `src/` relied on the
locale encoding (`solve/grounder.py`, reading back the `.lp` file PuLP had just
written), and **all 4** artifact writes in `cli.py` — `render`, `export`,
`convert` and the shared `_emit` helper, i.e. every file the CLI produces —
relied on `os.linesep`. Two test helpers also read `pyproject.toml` and a JSON
spec with the locale encoding.

This is the shared convention from `~/.claude/quality/STYLE.md` §5, whose
reference implementation and rationale live in raiLPminerExperimentation
(its ADR-0016, 78 encoding + 55 newline call sites). lp2graph was named there as
the repo to do next, "which emits the canonical LaTeX/JSON these artifacts are
made of and is the most exposed".

## Decision

1. Every text-mode `open()`, `Path.read_text()` and `Path.write_text()` in `src/`
   and `tests/` passes **`encoding="utf-8"`**. Binary-mode calls are exempt.
2. Every text *write* in `src/` also passes **`newline="\n"`**. Tests are exempt
   from the newline rule: they compare in-process values, not bytes.
3. Reads keep universal-newline translation (`newline` unset on read), so CRLF
   input still parses — we are strict about what we emit, liberal about what we
   accept.
4. Enforced by an **AST test** (`tests/test_text_io_encoding.py`), not a lint
   rule: ruff's encoding rules (`PLW1514`, the `FURB` set) are preview-only and
   STYLE.md §1 pins ruff's stable `E/F/W/I/UP/B/SIM/RUF` selection. The test
   carries *planted-violation* cases, so a green run proves the guard can still
   fail rather than merely that it ran.
5. A CI `c-locale` job runs the suite under
   `PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 LC_ALL=C` (preferred encoding
   `ANSI_X3.4-1968`), so the failure mode is exercised rather than assumed away.

## Consequences

- Artifacts are LF and UTF-8 on every platform, which is what the determinism
  claim requires in order to mean anything off this machine.
- The guard is cheap to keep green and fails with the file:line to fix. It is
  the third repo to adopt the rule; railOperationKG and raiLParchitectCode
  remain.
- `Path.write_text(..., newline=...)` requires Python 3.10+; `requires-python`
  is already `>=3.11`.
- The rule is about *declaring* intent, not about changing behaviour on Linux:
  the suite passes identically before and after under a UTF-8 locale. The
  change is only observable where it was already broken.
