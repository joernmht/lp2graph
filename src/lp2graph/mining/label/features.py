"""Feature extraction for labeling (M4).

Both stages of the labeling service consume the same feature view of an
entity: its structural type-signature facets (``role:``, ``kind:``,
``domain:``, ``arity:``, ``over:``, ``quant:``) and its lexical concepts
(``concept:``). The rule layer reads individual feature tokens; the classifier
vectorizes the whole feature dict. Keeping one extractor means the two stages
never disagree about what an entity *is*.
"""

from __future__ import annotations

from lp2graph.mining.homologize.concept import concept_bag
from lp2graph.mining.homologize.entity import Entity


def entity_features(entity: Entity) -> dict[str, float]:
    """Return the namespaced feature dict for ``entity`` (deterministic)."""
    feats: dict[str, float] = {}
    sig = entity.signature
    if sig.domain:
        feats[f"domain:{sig.domain}"] = 1.0
    feats[f"role:{sig.role}"] = 1.0
    feats[f"kind:{sig.kind}"] = 1.0
    feats[f"arity:{sig.arity}"] = 1.0
    for s in sig.shape:
        feats[f"over:{s}"] = 1.0
    for q in sig.quantifiers:
        feats[f"quant:{q}"] = 1.0
    for concept, count in concept_bag(entity.text).items():
        feats[f"concept:{concept}"] = float(count)
    return feats


__all__ = ["entity_features"]
