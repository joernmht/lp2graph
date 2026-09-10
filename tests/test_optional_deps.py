"""Optional dependencies fail with a message naming their extra (ADR-0007).

Clause 3 of ADR-0007 requires a *clear* ``ImportError`` naming the extra to
install, "not an opaque ``ModuleNotFoundError`` mid-call". ``export/`` always
complied; the newer ``interop/`` and parts of ``mining/`` grew bare imports
that leaked ``No module named 'gurobipy'`` to callers. These tests pin the
contract so it cannot regress again.
"""

from __future__ import annotations

import importlib
import re
import sys

import pytest

from lp2graph._optional import _EXTRA_FOR, require


def _flat() -> object:
    """A tiny flat formulation the exporters can be handed."""
    from lp2graph import load

    return load("formulations/constraints/lp_1_1_fixed_sequence.json")


def _hide(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Make importing ``name`` fail as if the package were not installed.

    Setting the entry to ``None`` is the documented way to make
    ``importlib.import_module`` raise ``ImportError`` for a module that *is*
    installed here (pulp, networkx, pyomo all are), so the test measures the
    error contract rather than the local environment.
    """
    monkeypatch.setitem(sys.modules, name, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("module", sorted(_EXTRA_FOR))
def test_require_names_the_extra(monkeypatch: pytest.MonkeyPatch, module: str) -> None:
    _hide(monkeypatch, module)
    with pytest.raises(ImportError) as exc:
        require(module, feature="some_feature")
    msg = str(exc.value)
    assert "some_feature" in msg
    assert module in msg
    assert f"lp2graph[{_EXTRA_FOR[module]}]" in msg


def test_require_returns_the_module() -> None:
    assert require("json", feature="t").dumps({"a": 1}) == '{"a": 1}'


def test_unknown_module_still_gets_a_useful_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _hide(monkeypatch, "not_a_real_dep")
    with pytest.raises(ImportError, match="install 'not_a_real_dep' to use it"):
        require("not_a_real_dep", feature="t")


def test_extras_map_matches_pyproject() -> None:
    """Every extra named in an error message must actually be installable."""
    tomllib = pytest.importorskip("tomllib")
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text())
    declared = set(data["project"]["optional-dependencies"])
    assert set(_EXTRA_FOR.values()) <= declared


#: (dependency, module path, entry point, "needs a formulation argument?").
#: Every public interop entry point that drives an optional backend.
_INTEROP_ENTRYPOINTS = [
    ("gurobipy", "lp2graph.interop.gurobi", "from_gurobipy", False),
    ("gurobipy", "lp2graph.interop.gurobi", "to_gurobipy", True),
    ("pulp", "lp2graph.interop.pulp_io", "from_pulp", False),
    ("pulp", "lp2graph.interop.pulp_io", "to_pulp", True),
    ("pyomo", "lp2graph.interop.pyomo_io", "from_pyomo", False),
    ("pyomo", "lp2graph.interop.pyomo_io", "to_pyomo", True),
]


@pytest.mark.parametrize(
    ("module", "path", "func", "needs_formulation"),
    _INTEROP_ENTRYPOINTS,
    ids=[e[2] for e in _INTEROP_ENTRYPOINTS],
)
def test_interop_entrypoints_name_their_extra(
    monkeypatch: pytest.MonkeyPatch,
    module: str,
    path: str,
    func: str,
    needs_formulation: bool,
) -> None:
    """No interop entry point may leak a bare ModuleNotFoundError."""
    arg = _flat() if needs_formulation else object()
    entry = getattr(importlib.import_module(path), func)
    _hide(monkeypatch, module)
    with pytest.raises(ImportError) as exc:
        entry(arg)
    message = str(exc.value)
    assert re.search(rf"lp2graph\[{_EXTRA_FOR[module]}\]", message), message
    assert func in message
