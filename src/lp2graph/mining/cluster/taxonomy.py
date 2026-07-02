"""Bottom-up multi-level taxonomy induction (M3).

Runs the ``CN`` operator at each level of the method's bottom-up taxonomy:

- **Level V** — decision variables and parameters, clustered on lexical
  concepts + their type signatures.
- **Level C** — constraints and the objective, clustered on lexical concepts
  + type signatures *conditioned on Level-V membership*: each constraint's
  referenced variables contribute a ``vcluster:<name>`` feature, so two
  constraints that bind structurally-similar variable families are pulled
  together.
- **Level M** — whole models, clustered on family/type histograms, presence
  flags, and bucketed structural metrics.

Plus two text-only one-dimensional clusterings — **domain** and **solution
approach** — over the model-level free text.

The whole induction is deterministic given the versioned
:class:`~lp2graph.mining.cluster.operator.ClusterConfig`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from lp2graph.core.model import ConstraintTemplate, Formulation
from lp2graph.metrics.flags import presence_flags
from lp2graph.metrics.structural import model_completeness, structural_summary
from lp2graph.mining.cluster.operator import CN, ClusterConfig, NamedClustering
from lp2graph.mining.homologize.concept import concept_bag
from lp2graph.mining.homologize.entity import (
    Entity,
    corpus_entities,
    signature_documents,
    text_dimension,
)
from lp2graph.mining.homologize.vectorize import (
    ConceptVectorizer,
    Vocabulary,
    build_vocabulary,
)
from lp2graph.views.schema import schema


@dataclass(frozen=True, slots=True)
class LevelResult:
    """One level's entities, vocabulary, and named clustering."""

    level: str
    entities: tuple[Entity, ...]
    vocabulary: Vocabulary
    clustering: NamedClustering

    def named_partition(self) -> dict[str, tuple[str, ...]]:
        """Map cluster name → the entity ids it contains (for reporting)."""
        out: dict[str, tuple[str, ...]] = {}
        for cid, idxs in self.clustering.members.items():
            name = self.clustering.names[cid]
            out[name] = tuple(self.entities[i].id for i in idxs)
        return out


@dataclass(frozen=True, slots=True)
class Taxonomy:
    """The full multi-level taxonomy over a corpus."""

    level_v: LevelResult
    level_c: LevelResult
    level_m: LevelResult
    domain: LevelResult
    solution_approach: LevelResult

    def summary(self) -> dict[str, int]:
        """Cluster counts per level (a compact, diffable digest)."""
        return {
            "V": self.level_v.clustering.n_clusters,
            "C": self.level_c.clustering.n_clusters,
            "M": self.level_m.clustering.n_clusters,
            "domain": self.domain.clustering.n_clusters,
            "solution_approach": self.solution_approach.clustering.n_clusters,
        }


def _merge(*docs: dict[str, int]) -> dict[str, int]:
    merged: Counter[str] = Counter()
    for d in docs:
        merged.update(d)
    return dict(merged)


def _run_pass(
    level: str,
    entities: Sequence[Entity],
    documents: Sequence[dict[str, int]],
    config: ClusterConfig,
) -> LevelResult:
    vocab = build_vocabulary(documents)
    _vectorizer, vectors = ConceptVectorizer.fit_transform(documents, vocabulary=vocab)
    clustering = CN(entities, vectors, vocab, config)
    return LevelResult(
        level=level,
        entities=tuple(entities),
        vocabulary=vocab,
        clustering=clustering,
    )


def _referenced_variable_ids(f: Formulation) -> dict[str, list[str]]:
    """Map each Level-C entity id of ``f`` to the variable entity ids it uses."""
    out: dict[str, list[str]] = {}
    for c in f.constraints:
        cid = f"{f.id}::constraint::{c.name}"
        refs = sorted({t.ref for t in (*c.lhs, *c.rhs) if t.ref_kind == "variable"})
        out[cid] = [f"{f.id}::variable::{r}" for r in refs]
    if f.objective is not None:
        oid = f"{f.id}::objective::{f.objective.name}"
        refs = sorted({t.ref for t in f.objective.terms if t.ref_kind == "variable"})
        out[oid] = [f"{f.id}::variable::{r}" for r in refs]
    return out


_DENSITY_EDGES = (0.05, 0.15, 0.30)
_CVR_EDGES = (0.75, 1.25, 2.0)


def _bucket(value: float, edges: Sequence[float]) -> int:
    for i, e in enumerate(edges):
        if value < e:
            return i
    return len(edges)


_SIZE_EDGES = (10.0, 50.0, 200.0, 1000.0)
_DIAMETER_CAP = 12


def model_feature_document(f: Formulation) -> dict[str, int]:
    """Level-M structural feature document.

    Covers the model-level channel of the paper's Level M: the presence-flag
    vector ``φ`` and the structural metrics of Sec.~lp2graph — minimal size
    ``S_min``, constraint/variable ratio ``R_C/V``, graph diameter ``D_G``,
    edge density, and the two well-formedness indicators (coherence and
    completeness) — each bucketed (or flagged) so it joins the
    TF-IDF feature space. The raw declarative kind histograms are retained as
    supplementary signal; the *induced* Level-V/Level-C cluster histograms are
    added on top in :func:`induce` (they need the lower passes' output).
    """
    doc: Counter[str] = Counter()
    doc[f"family:{f.family}"] += 1
    for c in f.constraints:
        doc[f"ckind:{c.kind}"] += 1
        if c.domain_class:
            doc[f"cdom:{c.domain_class}"] += 1
    for v in f.variables:
        doc[f"vdom:{v.domain}"] += 1
        if v.domain_role:
            doc[f"vrole:{v.domain_role}"] += 1
    for name, result in presence_flags(f).items():
        if bool(result.value):
            doc[f"flag:{name}"] += 1
    g = schema(f)
    metrics = structural_summary(g)
    density = float(metrics["edge_density"].value)
    cvr = float(metrics["constraint_variable_ratio"].value)
    size = float(metrics["minimal_size"].value)
    diameter = int(metrics["graph_diameter"].value)
    coherent = int(metrics["model_coherence"].value)
    complete = int(model_completeness(f).value)
    doc[f"density_bin:{_bucket(density, _DENSITY_EDGES)}"] += 1
    doc[f"cvr_bin:{_bucket(cvr, _CVR_EDGES)}"] += 1
    doc[f"size_bin:{_bucket(size, _SIZE_EDGES)}"] += 1
    doc[f"diam:{min(diameter, _DIAMETER_CAP)}"] += 1
    doc[f"coherent:{coherent}"] += 1
    doc[f"complete:{complete}"] += 1
    return dict(doc)


def induce(formulations: Sequence[Formulation], config: ClusterConfig | None = None) -> Taxonomy:
    """Induce the full multi-level taxonomy over ``formulations``."""
    cfg = config or ClusterConfig()

    # Level V -------------------------------------------------------------
    v_entities = corpus_entities(formulations, "V")
    v_sig = signature_documents(v_entities)
    v_docs = [_merge(concept_bag(e.text), v_sig[i]) for i, e in enumerate(v_entities)]
    level_v = _run_pass("V", v_entities, v_docs, cfg)
    v_label_by_id = {e.id: level_v.clustering.name_of(i) for i, e in enumerate(v_entities)}

    # Level C (conditioned on Level-V membership) -------------------------
    c_entities = corpus_entities(formulations, "C")
    c_sig = signature_documents(c_entities)
    ref_map: dict[str, list[str]] = {}
    con_by_id: dict[str, ConstraintTemplate] = {}
    for f in formulations:
        ref_map.update(_referenced_variable_ids(f))
        for c in f.constraints:
            con_by_id[f"{f.id}::constraint::{c.name}"] = c
    c_docs: list[dict[str, int]] = []
    for i, e in enumerate(c_entities):
        cond: Counter[str] = Counter()
        # Histogram of Level-V cluster membership over the coupled variables.
        for vid in ref_map.get(e.id, []):
            name = v_label_by_id.get(vid)
            if name is not None:
                cond[f"vcluster:{name}"] += 1
        # Relevant per-constraint presence flags (paper Level C: big-M,
        # aggregation). Comparator + quantifier/restriction pattern + referent
        # multiset already arrive via the signature document (c_sig).
        con = con_by_id.get(e.id)
        if con is not None:
            if con.kind == "big_m" or con.indicator is not None:
                cond["cflag:big_m"] += 1
            if any(t.operator != "none" for t in (*con.lhs, *con.rhs)):
                cond["cflag:aggregation"] += 1
        c_docs.append(_merge(concept_bag(e.text), c_sig[i], dict(cond)))
    level_c = _run_pass("C", c_entities, c_docs, cfg)
    c_label_by_id = {e.id: level_c.clustering.name_of(i) for i, e in enumerate(c_entities)}

    # Level M (conditioned on the induced Level-V/Level-C partitions) ------
    m_entities = corpus_entities(formulations, "M")
    m_docs: list[dict[str, int]] = []
    for f in formulations:
        induced: Counter[str] = Counter()
        # Histogram of induced Level-C families present in the model.
        for c in f.constraints:
            fam = c_label_by_id.get(f"{f.id}::constraint::{c.name}")
            if fam is not None:
                induced[f"cfamily:{fam}"] += 1
        if f.objective is not None:
            fam = c_label_by_id.get(f"{f.id}::objective::{f.objective.name}")
            if fam is not None:
                induced[f"cfamily:{fam}"] += 1
        # Histogram of induced Level-V types (variables and parameters).
        for v in f.variables:
            vtype = v_label_by_id.get(f"{f.id}::variable::{v.name}")
            if vtype is not None:
                induced[f"vtype:{vtype}"] += 1
        for p in f.parameters:
            vtype = v_label_by_id.get(f"{f.id}::parameter::{p.name}")
            if vtype is not None:
                induced[f"vtype:{vtype}"] += 1
        m_docs.append(_merge(model_feature_document(f), dict(induced)))
    level_m = _run_pass("M", m_entities, m_docs, cfg)

    # Text-only one-dimensional clusterings -------------------------------
    domain_docs = [concept_bag(text_dimension(e, "domain")) for e in m_entities]
    domain = _run_pass("domain", m_entities, [dict(d) for d in domain_docs], cfg)
    sol_docs = [concept_bag(text_dimension(e, "solution_approach")) for e in m_entities]
    solution = _run_pass("solution_approach", m_entities, [dict(d) for d in sol_docs], cfg)

    return Taxonomy(
        level_v=level_v,
        level_c=level_c,
        level_m=level_m,
        domain=domain,
        solution_approach=solution,
    )


__all__ = [
    "LevelResult",
    "Taxonomy",
    "induce",
    "model_feature_document",
]
