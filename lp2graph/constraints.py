"""Constraint type classification for railway rescheduling LP models."""

import ast
import re
from typing import Any, Dict, List

import pandas as pd


CONSTRAINT_TYPE_KEYWORDS = {
    'ordering': [
        r'\bprecedence\b', r'\border\b', r'\bordering\b',
        r'\bovertaking\b', r'\bovertake\b', r'\bre-?ordering\b',
    ],
    'routing': [
        r'\broute\s+selection\b', r'\brouting\b', r'\brerouting\b',
        r'\bre-?routing\b',
    ],
    'timing': [
        r'\bdepart(ure)?\b', r'\bdwell\b', r'\bdelay\b',
        r'\bscheduled\b', r'\brunning\s+time\b',
        r'\bminimum\s+duration\b', r'\bre-?timing\b',
    ],
    'cancellation': [
        r'\bcancel(l?ation|l?ed|l?ing)?\b',
        r'\btrain\s+service\s+balance\b',
        r'\bunbalanced\s+timetable\b',
    ],
    'headway': [
        r'\bheadway\b', r'\bconflict-free\b',
        r'\bincompatible\s+arc\b', r'\btrain\s+incompatibility\b',
    ],
    'capacity': [
        r'\binfrastructure\s+capacity\b', r'\btrack\s+capacity\b',
        r'\bstation\s+capacity\b', r'\bblock\s+section\b',
        r'\bsingle-?track\b', r'\bno-?store\b',
    ],
    'flow_balance': [
        r'\bflow\s+balance\b', r'\bflow\s+conservation\b',
    ],
    'big_m': [
        r'\blarge\s+constant\b', r'\bbig-?M\s+constraint\b',
        r'\bbig-?M\b',
    ],
    'passenger_connection': [
        r'\bminimum\s+transfer\s+time\b',
        r'\bpassenger\s+connection\b',
    ],
    'rolling_stock_connection': [
        r'\brolling\s+stock\s+connection\b',
    ],
}


def classify_constraint_types(nodes: List[Dict]) -> Dict[str, Any]:
    """Classify each constraint node by type using keyword matching.

    Returns:
        Dictionary with ``classification_matrix``, ``type_counts``,
        ``total_constraints``, ``classified_constraints``.
    """
    if isinstance(nodes, str):
        try:
            nodes = ast.literal_eval(nodes)
        except Exception:
            return {
                'classification_matrix': [],
                'type_counts': {},
                'total_constraints': 0,
                'classified_constraints': 0,
            }

    if not nodes:
        return {
            'classification_matrix': [],
            'type_counts': {},
            'total_constraints': 0,
            'classified_constraints': 0,
        }

    constraint_nodes = [n for n in nodes if n.get('type') == 'constraint']
    classification_matrix = []
    constraint_type_counts = {ctype: 0 for ctype in CONSTRAINT_TYPE_KEYWORDS}

    for constraint in constraint_nodes:
        search_text = (
            f"{constraint.get('name', '')} "
            f"{constraint.get('equation', '')} "
            f"{constraint.get('description', '')}"
        )

        matched_types = []
        type_match_dict = {}

        for ctype, keywords in CONSTRAINT_TYPE_KEYWORDS.items():
            pattern = '|'.join(keywords)
            if re.search(pattern, search_text, re.IGNORECASE):
                matched_types.append(ctype)
                type_match_dict[ctype] = 1
                constraint_type_counts[ctype] += 1
            else:
                type_match_dict[ctype] = 0

        classification_matrix.append({
            'constraint_number': constraint.get('number'),
            'constraint_name': constraint.get('name', ''),
            'matched_types': matched_types,
            'type_vector': type_match_dict,
            'is_classified': len(matched_types) > 0,
        })

    return {
        'classification_matrix': classification_matrix,
        'type_counts': constraint_type_counts,
        'total_constraints': len(constraint_nodes),
        'classified_constraints': sum(
            1 for c in classification_matrix if c['is_classified']
        ),
    }


def add_constraint_classification(df: pd.DataFrame) -> pd.DataFrame:
    """Add constraint type classification to a DataFrame.

    Args:
        df: DataFrame with ``nodes`` column.

    Returns:
        DataFrame with added ``constraint_classification`` and
        ``constraint_type_summary`` columns.
    """
    df_copy = df.copy()
    df_copy['constraint_classification'] = None
    df_copy['constraint_type_summary'] = None

    for idx in df_copy.index:
        nodes = df_copy.loc[idx, 'nodes']

        if isinstance(nodes, str):
            try:
                nodes = ast.literal_eval(nodes)
            except Exception:
                df_copy.at[idx, 'constraint_classification'] = []
                df_copy.at[idx, 'constraint_type_summary'] = {}
                continue

        if nodes and isinstance(nodes, list):
            try:
                classification = classify_constraint_types(nodes)
                df_copy.at[idx, 'constraint_classification'] = (
                    classification['classification_matrix']
                )
                df_copy.at[idx, 'constraint_type_summary'] = (
                    classification['type_counts']
                )
            except Exception as e:
                print(f"Error classifying constraints for row {idx}: {e}")
                df_copy.at[idx, 'constraint_classification'] = []
                df_copy.at[idx, 'constraint_type_summary'] = {}
        else:
            df_copy.at[idx, 'constraint_classification'] = []
            df_copy.at[idx, 'constraint_type_summary'] = {}

    return df_copy
