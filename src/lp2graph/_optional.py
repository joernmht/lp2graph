"""Uniform loading of optional dependencies (ADR-0007, clause 3).

ADR-0007 requires that a missing optional dependency raise "a clear
``ImportError`` naming the extra to install — it must not surface as an
opaque ``ModuleNotFoundError`` mid-call". The ``export/`` package has done
that from the start with hand-written ``try``/``except`` blocks; newer code
(``interop/``, parts of ``mining/``) grew bare ``import`` statements that
let ``ModuleNotFoundError: No module named 'gurobipy'`` escape to the
caller with no hint that ``pip install "lp2graph[gurobi]"`` is the fix.

:func:`require` makes the compliant path the short one, so the convention
is enforced by construction rather than by review. It performs the same
lazy, inside-the-function import ADR-0007 mandates — importing this module
never imports any optional dependency.
"""

from __future__ import annotations

import importlib
from types import ModuleType

#: Import name -> the extra that provides it, for the error message.
#: Mirrors ``[project.optional-dependencies]`` in ``pyproject.toml``.
_EXTRA_FOR: dict[str, str] = {
    "networkx": "networkx",
    "torch": "pyg",
    "torch_geometric": "pyg",
    "dgl": "dgl",
    "pyomo": "pyomo",
    "pulp": "solver",
    "highspy": "solver",
    "gurobipy": "gurobi",
    "nltk": "mining",
    "hdbscan": "mining",
}


def require(module: str, *, feature: str) -> ModuleType:
    """Import and return optional dependency ``module``.

    Args:
        module: The top-level import name (e.g. ``"gurobipy"``).
        feature: What the caller was trying to do, named the way a user
            would recognize it (e.g. ``"to_gurobipy"``); it leads the
            error message.

    Returns:
        The imported module.

    Raises:
        ImportError: If the dependency is absent — with a message naming
            both the dependency and the extra that installs it.
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        extra = _EXTRA_FOR.get(module)
        hint = (
            f"install with 'pip install lp2graph[{extra}]'"
            if extra
            else f"install {module!r} to use it"
        )
        raise ImportError(f"{feature} requires {module}; {hint}") from exc


__all__ = ["require"]
