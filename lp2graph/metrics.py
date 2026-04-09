"""Complexity metrics calculation for LP model graphs."""

from typing import Dict, List

import networkx as nx
import pandas as pd


def calculate_complexity_metrics(
    nodes: List[Dict], connections: List[List],
) -> Dict[str, float]:
    """Calculate complexity metrics for an LP model.

    Returns:
        Dictionary with ``minimal_size``, ``graph_diameter``,
        ``constraint_variable_ratio``, ``model_coherence``,
        ``model_completeness``, ``constraint_count``, ``variable_count``.
    """
    n_variables = len([n for n in nodes if n['type'] == 'variable'])
    n_constraints = len([n for n in nodes if n['type'] == 'constraint'])
    n_objectives = len([n for n in nodes if n['type'] == 'objective'])

    G = nx.Graph()
    for node in nodes:
        G.add_node(node['id'])

    for conn in connections:
        eq_num, var_num = conn
        eq_node = None
        var_node = None
        for node in nodes:
            if node['type'] in ['objective', 'constraint'] and node['number'] == eq_num:
                eq_node = node['id']
            elif node['type'] == 'variable' and node['number'] == var_num:
                var_node = node['id']
        if eq_node and var_node:
            G.add_edge(eq_node, var_node)

    metrics = {}

    nV_min = n_variables if n_variables > 0 else 1
    nC_min = n_constraints if n_constraints > 0 else 1
    metrics['minimal_size'] = nV_min * nC_min
    metrics['constraint_count'] = n_constraints
    metrics['variable_count'] = n_variables

    if len(G.nodes()) <= 1:
        metrics['graph_diameter'] = 0
    elif nx.is_connected(G):
        metrics['graph_diameter'] = nx.diameter(G)
    else:
        components = list(nx.connected_components(G))
        if components:
            largest_component = max(components, key=len)
            subgraph = G.subgraph(largest_component)
            if len(subgraph.nodes()) > 1:
                metrics['graph_diameter'] = nx.diameter(subgraph)
            else:
                metrics['graph_diameter'] = 0
        else:
            metrics['graph_diameter'] = 0

    if n_variables > 0:
        metrics['constraint_variable_ratio'] = n_constraints / n_variables
    else:
        metrics['constraint_variable_ratio'] = (
            float('inf') if n_constraints > 0 else 0
        )

    metrics['model_coherence'] = (
        1 if (len(G.nodes()) <= 1 or nx.is_connected(G)) else 0
    )

    metrics['model_completeness'] = 1 if (
        n_objectives == 1
        and n_variables > 0
        and n_constraints > 0
        and all(
            len([c for c in connections if c[1] == var['number']]) >= 2
            for var in nodes
            if var['type'] == 'variable'
        )
    ) else 0

    return metrics


def add_complexity_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Add complexity metrics as separate columns to a DataFrame.

    Args:
        df: DataFrame with ``nodes`` and ``connections`` columns.

    Returns:
        DataFrame with added metric columns.
    """
    df_copy = df.copy()

    metric_names = [
        'minimal_size', 'graph_diameter', 'constraint_variable_ratio',
        'model_coherence', 'model_completeness', 'model_naivety',
    ]
    for metric in metric_names:
        df_copy[metric] = 0.0

    for idx in df_copy.index:
        nodes = df_copy.loc[idx, 'nodes']
        connections = df_copy.loc[idx, 'connections']

        if nodes and isinstance(nodes, list):
            try:
                metrics = calculate_complexity_metrics(nodes, connections)
                for metric_name, value in metrics.items():
                    df_copy.loc[idx, metric_name] = value
            except Exception as e:
                print(f"Error calculating metrics for row {idx}: {e}")
                for metric in metric_names:
                    df_copy.loc[idx, metric] = 0.0

    return df_copy
