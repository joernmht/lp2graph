"""Internal typed graph used by view derivations, metrics, render, and export.  # noqa: E501

This is *not* a NetworkX, PyG, or DGL graph. It is a small, library-agnostic
representation that downstream consumers translate into their own format.

A :class:`Graph` is a directed multigraph with typed nodes and typed edges.
Nodes carry a ``cls`` (class), ``subtype``, ``shape`` (the index families
they range over, in the schema view), and a free-form ``data`` dict for
view-specific metadata. Edges carry a ``type``, ``role``, optional
``label``, and ``data``.

Determinism: node and edge insertion order is preserved. Equality compares
nodes and edges as ordered sequences. This guarantees identical render and
export output across runs given identical inputs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

NodeClass = Literal[
    "variable",
    "constraint",
    "objective",
    "index",
    "parameter",
    "operator",
    "instance_variable",
    "instance_constraint",
]
"""High-level node category. Drives palette selection in the renderer."""


EdgeType = Literal[
    "var_in_constraint",
    "var_in_objective",
    "uses_index",
    "uses_parameter",
    "operator_input",
    "operator_output",
    "instance_of",
    "ground_var_in_constraint",
]
"""Edge category. Drives stroke/style in the renderer."""


@dataclass(frozen=True, slots=True)
class Node:
    """A node in the typed graph.

    ``id`` must be unique within the graph. Inserting a node with a
    duplicate id raises :class:`ValueError`. ``cls`` selects the visual
    class; ``subtype`` is a free string used by renderers (e.g.
    ``"binary"`` for a binary variable).
    """

    id: str
    cls: NodeClass
    subtype: str = ""
    label: str = ""
    shape: tuple[str, ...] = ()
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Edge:
    """A directed edge in the typed graph."""

    src: str
    dst: str
    type: EdgeType
    role: str = ""
    label: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


class Graph:
    """A directed multigraph with insertion-order determinism.

    Not thread-safe. Designed for single-pass construction inside a view
    derivation, then read-only consumption by metrics, renderers, and
    exporters.
    """

    __slots__ = ("_edges", "_nodes", "_view")

    def __init__(self, view: str = "") -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._view = view

    # -- accessors --------------------------------------------------------

    @property
    def view(self) -> str:
        """The view this graph was derived from (``"schema"``, etc.)."""
        return self._view

    @property
    def nodes(self) -> tuple[Node, ...]:
        return tuple(self._nodes.values())

    @property
    def edges(self) -> tuple[Edge, ...]:
        return tuple(self._edges)

    def node(self, node_id: str) -> Node:
        return self._nodes[node_id]

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def __len__(self) -> int:
        return len(self._nodes)

    # -- mutation ---------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        cls: NodeClass,
        *,
        subtype: str = "",
        label: str = "",
        shape: Iterable[str] = (),
        data: Mapping[str, Any] | None = None,
    ) -> Node:
        if node_id in self._nodes:
            raise ValueError(f"duplicate node id: {node_id!r}")
        node = Node(
            id=node_id,
            cls=cls,
            subtype=subtype,
            label=label or node_id,
            shape=tuple(shape),
            data=dict(data or {}),
        )
        self._nodes[node_id] = node
        return node

    def add_edge(
        self,
        src: str,
        dst: str,
        type: EdgeType,
        *,
        role: str = "",
        label: str = "",
        data: Mapping[str, Any] | None = None,
    ) -> Edge:
        if src not in self._nodes:
            raise KeyError(f"unknown source node: {src!r}")
        if dst not in self._nodes:
            raise KeyError(f"unknown destination node: {dst!r}")
        edge = Edge(
            src=src,
            dst=dst,
            type=type,
            role=role,
            label=label,
            data=dict(data or {}),
        )
        self._edges.append(edge)
        return edge

    # -- introspection ----------------------------------------------------

    def nodes_by_class(self, cls: NodeClass) -> tuple[Node, ...]:
        return tuple(n for n in self._nodes.values() if n.cls == cls)

    def edges_by_type(self, type: EdgeType) -> tuple[Edge, ...]:
        return tuple(e for e in self._edges if e.type == type)

    def out_edges(self, node_id: str) -> tuple[Edge, ...]:
        return tuple(e for e in self._edges if e.src == node_id)

    def in_edges(self, node_id: str) -> tuple[Edge, ...]:
        return tuple(e for e in self._edges if e.dst == node_id)


__all__ = ["Edge", "EdgeType", "Graph", "Node", "NodeClass"]
