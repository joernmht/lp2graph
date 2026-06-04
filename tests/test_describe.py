"""Tests for the deterministic graph -> natural-language describer."""

from __future__ import annotations

import pytest

from lp2graph import describe, load


def test_describe_is_deterministic(formulation_files):
    for fp in formulation_files:
        f = load(fp)
        assert describe(f) == describe(f)


def test_describe_well_formed(formulation_files):
    """Structural/grammatical sanity: titled, references only declared
    symbols, no stray ``None``/``{}`` template leakage."""
    for fp in formulation_files:
        f = load(fp)
        text = describe(f)
        assert text.startswith("# ")
        assert "None" not in text
        # No unfilled format placeholders leaking from the generators.
        for leak in ("{a}", "{b}", "{}", "{0}", "{1}"):
            assert leak not in text, (fp.name, leak)
        assert "## Decision variables" in text
        if f.objective is not None:
            assert "## Objective" in text


def test_describe_mentions_every_constraint(formulation_files):
    for fp in formulation_files:
        f = load(fp)
        text = describe(f)
        for c in f.constraints:
            assert c.name in text, (fp.name, c.name)


def test_describe_renders_data_tables():
    from lp2graph.solve import Instance

    f = load("formulations/constraints/assignment.json")
    inst = Instance(
        cardinalities={"W": 3, "J": 3},
        parameters={"c": [[4, 1, 3], [2, 0, 5], [3, 2, 2]]},
    )
    text = describe(f, inst)
    assert "### Data values" in text
    assert "| **0** |" in text  # a markdown data-table row


def test_objective_no_double_verb():
    f = load("formulations/constraints/assignment.json")
    text = describe(f)
    assert "Minimize Minimize" not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
