"""Tests for M5: corpus & provenance manager."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from lp2graph import load
from lp2graph.core.model import Formulation
from lp2graph.mining.corpusmgr import (
    CorpusManager,
    CorpusManifest,
    ProvenanceRecord,
    bibliographic_key,
    deduplicate,
    manifest_from_dict,
    schema_graph_hash,
    select_representatives,
)

ROOT = Path(__file__).resolve().parents[2]
FORMULATIONS = ROOT / "formulations"


def _load(name: str) -> Formulation:
    matches = sorted(FORMULATIONS.rglob(name))
    assert matches, f"fixture {name} not found"
    return load(matches[0])


def _rename(f: Formulation, new_id: str) -> Formulation:
    """Copy a formulation changing only its id/name/description (cosmetics)."""
    with warnings.catch_warnings():
        # The coefficient field is a float|str|None union; pydantic emits a
        # benign serializer warning when dumping a numeric literal. The value
        # round-trips correctly, so silence the noise.
        warnings.simplefilter("ignore", UserWarning)
        data = f.model_dump(round_trip=True)
    data["id"] = new_id
    data["name"] = "Renamed " + new_id
    data["description"] = "totally different prose " + new_id
    return Formulation.model_validate(data)


def _record(
    source_id: str,
    *,
    venue: str = "JOC",
    tier: str = "A",
    year: int | None = 2024,
    citations: int = 0,
    cell: str = "P1",
) -> ProvenanceRecord:
    return ProvenanceRecord(
        source_id=source_id,
        venue=venue,
        quality_tier=tier,  # type: ignore[arg-type]
        year=year,
        citation_count=citations,
        domain_shell="railway",
        activity="rescheduling",
        priority_cell=cell,  # type: ignore[arg-type]
    )


# --- record validation ------------------------------------------------------


def test_record_rejects_bad_priority_cell() -> None:
    with pytest.raises(ValueError):
        _record("x", cell="P9")


def test_record_rejects_bad_tier() -> None:
    with pytest.raises(ValueError):
        _record("x", tier="A++")


# --- schema_graph_hash ------------------------------------------------------


def test_schema_graph_hash_is_stable_across_calls() -> None:
    f = _load("assignment.json")
    assert schema_graph_hash(f) == schema_graph_hash(f)


def test_schema_graph_hash_ignores_cosmetic_naming() -> None:
    f = _load("assignment.json")
    g = _rename(f, "assignment_copy")
    assert f.id != g.id
    assert schema_graph_hash(f) == schema_graph_hash(g)


def test_schema_graph_hash_differs_for_structurally_different() -> None:
    a = _load("assignment.json")
    b = _load("lp_1_1_fixed_sequence.json")
    assert schema_graph_hash(a) != schema_graph_hash(b)


# --- bibliographic_key ------------------------------------------------------


def test_bibliographic_key_normalizes() -> None:
    r1 = _record("Some-Repo", venue="INFORMS J. on Computing", year=2023)
    r2 = _record("some  repo", venue="informs j on computing", year=2023)
    assert bibliographic_key(r1) == bibliographic_key(r2)


# --- deduplicate ------------------------------------------------------------


def test_deduplicate_groups_by_structure_and_bib_transitively() -> None:
    a = _load("assignment.json")
    a_copy = _rename(a, "assignment_copy")  # structural dup of a
    other = _load("lp_1_1_fixed_sequence.json")
    other_bibdup = _load("lp_1_1_fixed_sequence.json")  # same bib as `other`

    items = [
        (a, _record("a", citations=5)),
        (a_copy, _record("a_copy", citations=9)),  # structural match -> a
        (other, _record("paper", venue="V", year=2020, citations=3)),
        (other_bibdup, _record("paper", venue="V", year=2020, citations=1)),
    ]
    res = deduplicate(items)

    # Two groups: {0,1} (structural) and {2,3} (bibliographic).
    assert res.groups == ((0, 1), (2, 3))
    # group 0 representative: highest citation -> index 1 (9 cites)
    # group 1 representative: highest citation -> index 2 (3 cites)
    assert res.representatives == (1, 2)


def test_deduplicate_transitive_chain() -> None:
    a = _load("assignment.json")
    a_copy = _rename(a, "assignment_copy")
    # a and a_copy share structure; a_copy and third share bib key.
    items = [
        (a, _record("rA", venue="V1", year=2001, citations=2)),
        (a_copy, _record("shared", venue="V2", year=2002, citations=4)),
        (
            _load("lp_1_1_fixed_sequence.json"),
            _record("shared", venue="V2", year=2002, citations=1),
        ),
    ]
    res = deduplicate(items)
    # 0-1 by structure, 1-2 by bib -> one transitive group.
    assert res.groups == ((0, 1, 2),)
    assert res.representatives == (1,)  # highest citation = index 1 (4)


def test_deduplicate_tiebreak_quality_then_index() -> None:
    a = _load("assignment.json")
    a2 = _rename(a, "a2")
    a3 = _rename(a, "a3")
    items = [
        (a, _record("a", tier="B", citations=5)),
        (a2, _record("a2", tier="A_star", citations=5)),  # same cites, better tier
        (a3, _record("a3", tier="A_star", citations=5)),  # tie -> lower index wins
    ]
    res = deduplicate(items)
    assert res.groups == ((0, 1, 2),)
    assert res.representatives == (1,)


# --- select_representatives -------------------------------------------------


def test_select_highest_citation() -> None:
    records = [
        _record("a", citations=3),
        _record("b", citations=10),
        _record("c", citations=7),
    ]
    out = select_representatives({"cl": [0, 1, 2]}, records)
    assert out["cl"].chosen_index == 1
    assert out["cl"].reason == "highest_citation"
    assert out["cl"].ranked_candidates == (1, 2, 0)


def test_select_all_zero_falls_back() -> None:
    records = [_record("a", citations=0), _record("b", citations=0)]
    out = select_representatives({"cl": [0, 1]}, records, benchmark_fallback={"cl": 1})
    assert out["cl"].chosen_index == 1
    assert out["cl"].reason == "benchmark_fallback"


def test_select_empty_cluster_uses_benchmark() -> None:
    out = select_representatives({"cl": []}, [], benchmark_fallback={"cl": 42})
    assert out["cl"].chosen_index == 42
    assert out["cl"].reason == "benchmark_fallback"


def test_select_all_zero_no_fallback() -> None:
    records = [_record("a", citations=0), _record("b", tier="A_star", citations=0)]
    out = select_representatives({"cl": [0, 1]}, records)
    # best tier wins the ranking; reason is the fallback flavor.
    assert out["cl"].chosen_index == 1
    assert out["cl"].reason == "next_highest_fallback"


# --- manifest round-trip ----------------------------------------------------


def test_manifest_round_trips() -> None:
    m = CorpusManifest(
        frozen_search_date="2026-06-01",
        queries=("railway rescheduling milp", "pesp timetabling"),
        notes="freeze for thesis ch. 5",
    )
    again = manifest_from_dict(m.to_dict())
    assert again == m


def test_manifest_rejects_empty_date() -> None:
    with pytest.raises(ValueError):
        CorpusManifest(frozen_search_date="")


# --- manager facade ---------------------------------------------------------


def test_manager_round_trip_and_ops() -> None:
    a = _load("assignment.json")
    a_copy = _rename(a, "a_copy")
    mgr = CorpusManager.build(
        CorpusManifest(frozen_search_date="2026-06-01", queries=("q1",)),
        [
            (a, _record("a", citations=2)),
            (a_copy, _record("a_copy", citations=8)),
        ],
    )
    res = mgr.deduplicate()
    assert res.groups == ((0, 1),)
    assert res.representatives == (1,)

    reps = mgr.representatives({"all": [0, 1]})
    assert reps["all"].chosen_index == 1

    rebuilt = CorpusManager.from_manifest_dict(mgr.to_manifest_dict())
    assert rebuilt.manifest == mgr.manifest


# --- determinism ------------------------------------------------------------


def test_dedup_and_selection_are_deterministic() -> None:
    a = _load("assignment.json")
    a2 = _rename(a, "a2")
    b = _load("lp_1_1_fixed_sequence.json")
    items = [
        (a, _record("a", venue="V", year=2020, citations=4)),
        (a2, _record("a2", venue="W", year=2021, citations=4)),
        (b, _record("b", venue="X", year=2019, citations=9)),
    ]
    r1 = deduplicate(items)
    r2 = deduplicate(items)
    assert r1 == r2

    records = [r for _, r in items]
    clusters = {"c": [0, 1, 2]}
    s1 = select_representatives(clusters, records)
    s2 = select_representatives(clusters, records)
    assert s1 == s2
