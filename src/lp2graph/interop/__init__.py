"""Code ⇄ graph interoperability: solver and modeling-language interfaces.

Every interface converts between its language and the canonical
:class:`~lp2graph.core.model.Formulation` (the typed graph's single
source of truth), so any importer composes with any exporter —
``code -> graph -> code`` without LaTeX in between:

======================  =========================  ==========================
Language                code -> graph              graph -> code
======================  =========================  ==========================
Gurobi (gurobipy)       :func:`from_gurobipy`      :func:`to_gurobipy`,
                                                   :func:`to_gurobipy_code`
PuLP                    :func:`from_pulp`          :func:`to_pulp`,
                                                   :func:`to_pulp_code`
Pyomo                   :func:`from_pyomo`         :func:`to_pyomo`,
                                                   :func:`to_pyomo_code`
CPLEX/Gurobi LP file    :func:`from_lp_string`     :func:`to_lp_string`
MPS file                :func:`from_mps_string`    :func:`to_mps_string`
GAMS (scalar)           :func:`from_gams`          :func:`to_gams`
AMPL (scalar)           :func:`from_ampl`          :func:`to_ampl`
JuMP (scalar)           :func:`from_jump`          :func:`to_jump`
======================  =========================  ==========================

Importers return flat, coefficient-faithful formulations that solve
directly (``lp2graph.solve``). Exporters accept flat formulations
as-is and template-level formulations together with an
:class:`~lp2graph.solve.instance.Instance`. Unsupported constructs
raise :class:`InteropError`; nothing is silently dropped. All emitters
are deterministic. ``gurobipy`` / ``pulp`` / ``pyomo`` are optional and
imported lazily inside the functions that need them; the five text
formats are dependency-free for flat models.
"""

from __future__ import annotations

from lp2graph.interop._grounded import (
    GroundedConstraint,
    GroundedModel,
    GroundedVar,
    InteropError,
    ground,
    to_formulation,
)
from lp2graph.interop.ampl import from_ampl, to_ampl
from lp2graph.interop.gams import from_gams, to_gams
from lp2graph.interop.gurobi import from_gurobipy, to_gurobipy, to_gurobipy_code
from lp2graph.interop.jump import from_jump, to_jump
from lp2graph.interop.lp_format import from_lp_string, to_lp_string
from lp2graph.interop.mps import from_mps_string, to_mps_string
from lp2graph.interop.pulp_io import from_pulp, to_pulp, to_pulp_code
from lp2graph.interop.pyomo_io import from_pyomo, to_pyomo, to_pyomo_code

__all__ = [
    "GroundedConstraint",
    "GroundedModel",
    "GroundedVar",
    "InteropError",
    "from_ampl",
    "from_gams",
    "from_gurobipy",
    "from_jump",
    "from_lp_string",
    "from_mps_string",
    "from_pulp",
    "from_pyomo",
    "ground",
    "to_ampl",
    "to_formulation",
    "to_gams",
    "to_gurobipy",
    "to_gurobipy_code",
    "to_jump",
    "to_lp_string",
    "to_mps_string",
    "to_pulp",
    "to_pulp_code",
    "to_pyomo",
    "to_pyomo_code",
]
