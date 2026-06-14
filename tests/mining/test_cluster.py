"""Tests for M3 — cluster-and-name operator + taxonomy induction."""

from __future__ import annotations

from pathlib import Path

from lp2graph import load
from lp2graph.mining.cluster import (
    CN,
    UNASSIGNED,
    ClusterConfig,
    adjusted_rand_index,
    cosine_distance,
    induce,
    silhouette_score,
    stability_report,
)
from lp2graph.mining.cluster.agglomerative import agglomerative
from lp2graph.mining.homologize import (
    ConceptVectorizer,
    build_vocabulary,
    concept_bag,
)

ROOT = Path(__file__).resolve().parents[2]
FORMULATIONS = ROOT / "formulations"


def _all_formulations() -> list:
    return [load(p) for p in sorted(FORMULATIONS.rglob("*.json"))]


def _vectors(texts: list[str]):
    docs = [concept_bag(t) for t in texts]
    vocab = build_vocabulary(docs)
    _vec, vectors = ConceptVectorizer.fit_transform(docs, vocabulary=vocab)
    return vocab, vectors


# --- distance + agglomerative core -----------------------------------------


def test_cosine_distance_extremes() -> None:
    assert cosine_distance([1.0, 0.0], [1.0, 0.0]) == 0.0
    assert cosine_distance([1.0, 0.0], [0.0, 1.0]) == 1.0


def test_agglomerative_requires_one_stopping_rule() -> None:
    dist = [[0.0, 1.0], [1.0, 0.0]]
    import pytest

    with pytest.raises(ValueError):
        agglomerative(dist, distance_threshold=0.5, k=2)


def test_agglomerative_fixed_k_partitions() -> None:
    # Two tight pairs far apart → 2 clusters.
    dist = [
        [0.0, 0.1, 0.9, 0.9],
        [0.1, 0.0, 0.9, 0.9],
        [0.9, 0.9, 0.0, 0.1],
        [0.9, 0.9, 0.1, 0.0],
    ]
    labels = agglomerative(dist, distance_threshold=None, k=2)
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert labels[0] != labels[2]


# --- CN operator -----------------------------------------------------------


def test_cn_separates_topics_and_names_them() -> None:
    texts = [
        "minimum headway separation between trains",
        "headway spacing conflict on the track",
        "rolling stock assignment to services",
        "fleet allocation and rolling stock matching",
    ]
    vocab, vectors = _vectors(texts)
    cfg = ClusterConfig(distance_threshold=0.8)
    result = CN(list(range(len(texts))), vectors, vocab, cfg)
    # The two headway texts share a cluster; the two rolling-stock texts share
    # a different cluster.
    assert result.labels[0] == result.labels[1]
    assert result.labels[2] == result.labels[3]
    assert result.labels[0] != result.labels[2]
    # Names come from aggregated TF-IDF weight: the headway cluster is named
    # after its dominant concept, and the two clusters get distinct names.
    assert result.name_of(0) == "headway"
    assert result.name_of(2) in {"rolling_stock", "assignment"}
    assert result.name_of(0) != result.name_of(2)


def test_cn_routes_empty_text_to_unassigned() -> None:
    texts = ["headway separation", "rolling stock fleet", "xyzzy qux"]
    # Third doc has no in-vocabulary concept relative to a vocab built from the
    # first two — emulate by building vocab from only the first two.
    docs = [concept_bag(t) for t in texts]
    vocab = build_vocabulary(docs[:2])
    vec = ConceptVectorizer.fit(docs[:2], vocabulary=vocab)
    vectors = [vec.transform(d) for d in docs]
    result = CN(list(range(3)), vectors, vocab, ClusterConfig())
    assert result.labels[2] == UNASSIGNED
    assert "unassigned" in result.names.values()


def test_cn_is_deterministic() -> None:
    texts = [
        "headway separation between trains",
        "track capacity at a block section",
        "rolling stock circulation",
        "headway conflict spacing",
    ]
    vocab, vectors = _vectors(texts)
    a = CN(list(range(len(texts))), vectors, vocab, ClusterConfig())
    b = CN(list(range(len(texts))), vectors, vocab, ClusterConfig())
    assert a.labels == b.labels
    assert a.names == b.names
    assert a.members == b.members


def test_every_entity_in_exactly_one_part() -> None:
    texts = ["headway", "capacity", "rolling stock", "delay penalty cost"]
    vocab, vectors = _vectors(texts)
    result = CN(list(range(len(texts))), vectors, vocab, ClusterConfig())
    covered = [i for idxs in result.members.values() for i in idxs]
    assert sorted(covered) == list(range(len(texts)))
    assert len(covered) == len(set(covered))  # disjoint


# --- adjusted rand index ---------------------------------------------------


def test_ari_identity_and_relabeling() -> None:
    assert adjusted_rand_index([0, 0, 1, 1], [0, 0, 1, 1]) == 1.0
    assert adjusted_rand_index([0, 0, 1, 1], [1, 1, 0, 0]) == 1.0  # relabel invariant


def test_silhouette_in_range() -> None:
    dist = [
        [0.0, 0.1, 0.9],
        [0.1, 0.0, 0.9],
        [0.9, 0.9, 0.0],
    ]
    s = silhouette_score(dist, [0, 0, 1])
    assert -1.0 <= s <= 1.0


# --- taxonomy induction over the real catalog ------------------------------


def test_induce_runs_on_catalog_and_is_reproducible() -> None:
    forms = _all_formulations()
    assert len(forms) >= 3
    tax_a = induce(forms)
    tax_b = induce(forms)
    # Re-run reproduces partitions and names at every level.
    for level in ("level_v", "level_c", "level_m", "domain", "solution_approach"):
        ra = getattr(tax_a, level)
        rb = getattr(tax_b, level)
        assert ra.clustering.labels == rb.clustering.labels
        assert ra.clustering.names == rb.clustering.names
    summary = tax_a.summary()
    assert set(summary) == {"V", "C", "M", "domain", "solution_approach"}
    # Level-C conditioning: at least one cluster vocab carries a vcluster token.
    assert any(c.startswith("vcluster:") for c in tax_a.level_c.vocabulary.concepts)


def test_level_features_match_paper_spec() -> None:
    forms = _all_formulations()
    tax = induce(forms)
    c_vocab = set(tax.level_c.vocabulary.concepts)
    # Level C carries the paper's constraint structural signature pieces.
    assert any(c.startswith("cmp:") for c in c_vocab)  # comparator
    assert any(c.startswith("ref:") for c in c_vocab)  # referent multiset
    assert any(c.startswith("vcluster:") for c in c_vocab)  # Level-V conditioning
    m_vocab = set(tax.level_m.vocabulary.concepts)
    # Level M is conditioned on the induced lower-level partitions and carries
    # the full structural-metric set.
    assert any(c.startswith("vtype:") for c in m_vocab)  # induced Level-V types
    assert any(c.startswith("cfamily:") for c in m_vocab)  # induced Level-C families
    assert any(c.startswith("size_bin:") for c in m_vocab)  # S_min
    assert any(c.startswith("diam:") for c in m_vocab)  # graph diameter D_G
    assert any(c.startswith("coherent:") for c in m_vocab)  # coherence


def test_stability_report_emitted() -> None:
    forms = _all_formulations()
    tax = induce(forms)
    lvl = tax.level_c
    docs = None
    # Rebuild vectors for the C level to feed the stability report.
    from lp2graph.mining.cluster.taxonomy import _referenced_variable_ids
    from lp2graph.mining.homologize.entity import signature_documents

    sig = signature_documents(lvl.entities)
    ref_map: dict[str, list[str]] = {}
    for f in forms:
        ref_map.update(_referenced_variable_ids(f))
    from collections import Counter

    docs = []
    v_label = {e.id: tax.level_v.clustering.name_of(i) for i, e in enumerate(tax.level_v.entities)}
    for i, e in enumerate(lvl.entities):
        cond: Counter[str] = Counter()
        for vid in ref_map.get(e.id, []):
            name = v_label.get(vid)
            if name:
                cond[f"vcluster:{name}"] += 1
        merged = Counter(concept_bag(e.text))
        merged.update(sig[i])
        merged.update(cond)
        docs.append(dict(merged))
    vec = ConceptVectorizer.fit(docs, vocabulary=lvl.vocabulary)
    vectors = [vec.transform(d) for d in docs]
    report = stability_report(
        vectors, lvl.vocabulary, lvl.clustering, lvl.clustering.config, n_bootstrap=10
    )
    assert -1.0 <= report.bootstrap_ari_mean <= 1.0
    assert report.bootstrap_ari_min <= report.bootstrap_ari_max
    assert report.config_version
    assert "algorithm=fixed_k" in report.sensitivity
