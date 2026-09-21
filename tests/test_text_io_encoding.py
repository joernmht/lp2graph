"""Guard: text I/O declares ``encoding="utf-8"``, and artifact writes pin ``newline="\\n"``.

Compatibility (ISO/IEC 25010 -> interoperability). ``open()``,
``Path.read_text()`` and ``Path.write_text()`` follow the *locale*
encoding. On Linux that is UTF-8 in practice (PEP 538/540 coerce the C
locale), so an omission is invisible here -- but lp2graph is a library
other people install, and it emits the canonical LaTeX/JSON that the
mining corpus is made of. Under a cp1252 default (the Windows norm) a
read silently *mojibakes* every non-ASCII string rather than raising,
while a write of the same content raises ``UnicodeEncodeError``. The
canonical LaTeX codec emits mathematical operators and the formulation
catalog carries non-ASCII prose, so both paths are live here.

The ``newline`` argument matters for the same reason and one more: a text
write with the default ``newline=None`` rewrites every ``"\\n"`` as
``os.linesep``, so on Windows every emitted artifact is CRLF. That breaks
this repo's *hard* determinism requirement (ADR-0006, CLAUDE.md) by every
single line -- snapshot comparisons and corpus hashes stop matching for a
reason no reader can see. Only the trees that emit artifacts are held to
the newline rule; tests compare in-process values, not bytes.

This is an AST check rather than a lint rule because ruff's encoding rules
(``PLW1514``, the ``FURB`` set) are preview-only, and the shared toolchain
pins ruff's stable ``E/F/W/I/UP/B/SIM/RUF`` selection
(``~/.claude/quality/STYLE.md`` §1). Ported from the reference
implementation in raiLPminerExperimentation (its ADR-0016); see ADR-0015.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Trees whose text I/O must declare an encoding.
CHECKED_TREES = ("src", "tests")

#: Trees that emit on-disk artifacts, so their writes must also pin the newline.
PRODUCER_TREES = ("src",)

#: ``pathlib`` text helpers; both take an ``encoding`` keyword.
_TEXT_METHODS = frozenset({"read_text", "write_text"})


def _mode_of(call: ast.Call) -> str:
    """The literal ``mode`` argument of an ``open()`` call, if it is a constant."""
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        return str(call.args[1].value)
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return ""


def offenders(source: str, label: str) -> list[str]:
    """Text-I/O calls in ``source`` that do not pass ``encoding=``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=label)):
        if not isinstance(node, ast.Call):
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        # `Path.read_text()` / `Path.write_text()` -- attribute form only.
        if isinstance(node.func, ast.Attribute) and node.func.attr in _TEXT_METHODS:
            found.append(f"{label}:{node.lineno} {node.func.attr}()")
        # Builtin `open()` -- the bare name only, so `tarfile.open` / `Image.open`
        # (different signatures, no `encoding`) are not swept up.
        elif (
            isinstance(node.func, ast.Name) and node.func.id == "open" and "b" not in _mode_of(node)
        ):
            found.append(f"{label}:{node.lineno} open()")
    return found


def newline_offenders(source: str, label: str) -> list[str]:
    """Text *writes* in ``source`` that do not pin ``newline="\\n"``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=label)):
        if not isinstance(node, ast.Call):
            continue
        if any(kw.arg == "newline" for kw in node.keywords):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr == "write_text":
            found.append(f"{label}:{node.lineno} write_text()")
        elif func.attr == "open":
            mode = (
                node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else ""
            )
            if isinstance(mode, str) and "b" not in mode and any(c in mode for c in "wax"):
                found.append(f"{label}:{node.lineno} open({mode!r})")
    return found


def _scan(trees: tuple[str, ...], check: object) -> list[str]:
    found: list[str] = []
    for tree in trees:
        for path in sorted((REPO_ROOT / tree).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT)
            found += check(path.read_text(encoding="utf-8"), str(rel))  # type: ignore[operator]
    return found


def test_every_text_io_call_declares_utf8() -> None:
    found = _scan(CHECKED_TREES, offenders)
    assert found == [], (
        "text I/O without an explicit encoding (see ADR-0015); "
        'add encoding="utf-8":\n  ' + "\n  ".join(found)
    )


def test_every_artifact_write_pins_lf() -> None:
    found = _scan(PRODUCER_TREES, newline_offenders)
    assert found == [], (
        "text write without an explicit newline (see ADR-0015); emitted artifacts "
        'would be CRLF on Windows, breaking determinism. Add newline="\\n":\n  '
        + "\n  ".join(found)
    )


def test_the_guard_sees_planted_violations() -> None:
    """A green run means something only if the check can still fail."""
    src = "from pathlib import Path\nPath('a').read_text()\nPath('b').write_text('x')\nopen('c')\n"
    assert len(offenders(src, "planted.py")) == 3
    assert len(newline_offenders(src, "planted.py")) == 1


def test_the_guard_accepts_compliant_calls() -> None:
    """...and only fails for the reason it claims to."""
    src = (
        "from pathlib import Path\n"
        "Path('a').read_text(encoding='utf-8')\n"
        "Path('b').write_text('x', encoding='utf-8', newline='\\n')\n"
        "open('c', encoding='utf-8')\n"
        "open('d', 'rb')\n"
    )
    assert offenders(src, "ok.py") == []
    assert newline_offenders(src, "ok.py") == []
