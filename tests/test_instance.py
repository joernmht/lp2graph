"""Tests for instance data access (``lp2graph.solve.instance``)."""

from __future__ import annotations

import pytest

from lp2graph.solve.instance import Instance, lookup


def test_lookup_reads_json_style_string_keys() -> None:
    # An instance file's mappings arrive with string keys; a stray ``list(key)``
    # candidate (unhashable) used to raise TypeError before they were tried.
    inst = Instance.from_dict({"cardinalities": {"I": 2}, "parameters": {"c": {"0,1": 3.0}}})
    assert lookup(inst.parameters["c"], (0, 1)) == 3.0
    assert lookup({"1": 2.5}, (1,)) == 2.5


def test_lookup_still_prefers_tuple_and_bare_keys() -> None:
    assert lookup({(0, 1): 4.0}, (0, 1)) == 4.0
    assert lookup({0: 5.0}, (0,)) == 5.0


def test_lookup_reports_a_missing_key() -> None:
    with pytest.raises(KeyError):
        lookup({"0,0": 1.0}, (0, 1))
