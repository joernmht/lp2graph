"""Graph visualization for LP models (circular, tree, diameter highlighting)."""

import os
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd
from matplotlib.lines import Line2D


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def setup_graphviz():
    """Check if Graphviz ``dot`` is available on PATH."""
    try:
        subprocess.run(['dot', '-V'], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def create_manual_tree_layout(G):
    """Manual tree layout: objective top, variables middle, constraints bottom."""
    pos = {}
    levels = {'objective': [], 'constraint': [], 'variable': []}

    for node_id in G.nodes():
        node_type = G.nodes[node_id]['type']
        levels[node_type].append(node_id)

    if levels['objective']:
        pos[levels['objective'][0]] = (0, 4)

    variable_count = len(levels['variable'])
    constraint_count = len(levels['constraint'])

    for i, node in enumerate(levels['constraint']):
        x = -15 + (30 * i / (constraint_count - 1)) if constraint_count > 1 else 0
        pos[node] = (x, 0)

    for i, node in enumerate(levels['variable']):
        x = -15 + (30 * i / (variable_count - 1)) if variable_count > 1 else 0
        pos[node] = (x, 2)

    return pos


def _build_nx_graph(nodes, connections):
    """Build a NetworkX graph from nodes and connections."""
    G = nx.Graph()
    for node in nodes:
        G.add_node(
            node['id'], type=node['type'],
            name=node['name'], number=node['number'],
        )

    for conn in connections:
        eq_num, var_num = conn
        eq_node = var_node = None
        for node in nodes:
            if node['type'] in ['objective', 'constraint'] and node['number'] == eq_num:
                eq_node = node['id']
            elif node['type'] == 'variable' and node['number'] == var_num:
                var_node = node['id']
        if eq_node and var_node:
            G.add_edge(eq_node, var_node)

    return G


def _classify_nodes(G):
    """Classify graph nodes into variable/objective/constraint lists and labels."""
    variable_nodes, objective_nodes, constraint_nodes = [], [], []
    node_labels = {}
    for node_id in G.nodes():
        nd = G.nodes[node_id]
        if nd['type'] == 'variable':
            variable_nodes.append(node_id)
            node_labels[node_id] = f"V{nd['number']}"
        elif nd['type'] == 'objective':
            objective_nodes.append(node_id)
            node_labels[node_id] = "OBJ"
        else:
            constraint_nodes.append(node_id)
            node_labels[node_id] = f"C{nd['number']}"
    return variable_nodes, objective_nodes, constraint_nodes, node_labels


# ---------------------------------------------------------------------------
# Circular layout
# ---------------------------------------------------------------------------

def visualize_circular_graph(
    nodes: List[Dict],
    connections: List[List],
    title: str = "LP Model Graph",
    figsize: Tuple[int, int] = (10, 8),
):
    """Visualize the graph in a circular layout."""
    if not nodes:
        print("No nodes to visualize")
        return

    G = _build_nx_graph(nodes, connections)
    pos = nx.circular_layout(G)
    variable_nodes, objective_nodes, constraint_nodes, node_labels = _classify_nodes(G)

    fig, ax = plt.subplots(figsize=figsize)
    nx.draw_networkx_edges(G, pos, edge_color='gray', alpha=0.8, ax=ax)

    if variable_nodes:
        nx.draw_networkx_nodes(
            G, pos, nodelist=variable_nodes, node_color='lightblue',
            node_shape='o', node_size=1200, alpha=0.8, ax=ax,
        )
    if objective_nodes:
        nx.draw_networkx_nodes(
            G, pos, nodelist=objective_nodes, node_color='lightgreen',
            node_shape='s', node_size=1200, alpha=0.8, ax=ax,
        )
    if constraint_nodes:
        nx.draw_networkx_nodes(
            G, pos, nodelist=constraint_nodes, node_color='lightcoral',
            node_shape='D', node_size=1200, alpha=0.8, ax=ax,
        )

    nx.draw_networkx_labels(
        G, pos, labels=node_labels, font_size=9, font_weight='bold', ax=ax,
    )

    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='lightblue',
               markersize=10, label='Variables (Circle)'),
        Line2D([0], [0], marker='s', color='w', markerfacecolor='lightgreen',
               markersize=10, label='Objective (Square)'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor='lightcoral',
               markersize=10, label='Constraints (Diamond)'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.axis('off')
    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Tree layout
# ---------------------------------------------------------------------------

def visualize_tree_graph(
    nodes: List[Dict],
    connections: List[List],
    title: str = "LP Model Tree Graph",
    figsize: Tuple[int, int] = (12, 10),
):
    """Visualize the graph in a hierarchical tree layout."""
    if not nodes:
        print("No nodes to visualize")
        return

    graphviz_available = setup_graphviz()
    G = _build_nx_graph(nodes, connections)
    variable_nodes, objective_nodes, constraint_nodes, node_labels = _classify_nodes(G)

    root_node = None
    for node_id in G.nodes():
        if G.nodes[node_id]['type'] == 'objective':
            root_node = node_id
            break

    if graphviz_available:
        try:
            pos = nx.nx_pydot.graphviz_layout(G, prog='dot', root=root_node)
        except Exception:
            pos = create_manual_tree_layout(G)
    else:
        pos = create_manual_tree_layout(G)

    fig, ax = plt.subplots(figsize=figsize)
    nx.draw_networkx_edges(G, pos, edge_color='gray', alpha=0.6, ax=ax, width=2)

    if objective_nodes:
        nx.draw_networkx_nodes(
            G, pos, nodelist=objective_nodes, node_color='lightgreen',
            node_shape='s', node_size=1500, alpha=0.8, ax=ax,
        )
    if variable_nodes:
        nx.draw_networkx_nodes(
            G, pos, nodelist=variable_nodes, node_color='lightblue',
            node_shape='o', node_size=1200, alpha=0.8, ax=ax,
        )
    if constraint_nodes:
        nx.draw_networkx_nodes(
            G, pos, nodelist=constraint_nodes, node_color='lightcoral',
            node_shape='D', node_size=1200, alpha=0.8, ax=ax,
        )

    nx.draw_networkx_labels(
        G, pos, labels=node_labels, font_size=9, font_weight='bold', ax=ax,
    )

    legend_elements = [
        Line2D([0], [0], marker='s', color='w', markerfacecolor='lightgreen',
               markersize=12, label='Objective (Square)'),
        Line2D([0], [0], marker='D', color='w', markerfacecolor='lightcoral',
               markersize=10, label='Constraints (Diamond)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='lightblue',
               markersize=10, label='Variables (Circle)'),
    ]
    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))
    ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
    ax.axis('off')
    plt.tight_layout()
    plt.show()


# ---------------------------------------------------------------------------
# Diameter analysis
# ---------------------------------------------------------------------------

def find_graph_diameter_and_path(G):
    """Find the diameter and the path(s) that achieve it.

    Returns:
        Tuple of ``(diameter, diameter_edges, diameter_paths)``.
    """
    if len(G.nodes()) == 0:
        return 0, set(), []

    if not nx.is_connected(G):
        largest_component = max(nx.connected_components(G), key=len)
        G = G.subgraph(largest_component)

    all_shortest_paths = dict(nx.all_pairs_shortest_path_length(G))

    diameter = 0
    diameter_pairs = []

    for source in all_shortest_paths:
        for target, distance in all_shortest_paths[source].items():
            if distance > diameter:
                diameter = distance
                diameter_pairs = [(source, target)]
            elif distance == diameter and distance > 0:
                diameter_pairs.append((source, target))

    diameter_edges = set()
    diameter_paths = []

    for source, target in diameter_pairs:
        try:
            path = nx.shortest_path(G, source, target)
            diameter_paths.append(path)
            for i in range(len(path) - 1):
                edge = tuple(sorted([path[i], path[i + 1]]))
                diameter_edges.add(edge)
        except nx.NetworkXNoPath:
            continue

    return diameter, diameter_edges, diameter_paths
