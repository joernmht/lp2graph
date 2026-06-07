"""Stage-1 rule layer (M4).

Deterministic, high-precision rules over the feature tokens: if an antecedent
feature (a type-signature facet such as ``domain:timing`` or a seed-lexicon
concept such as ``concept:headway``) is present, the rule proposes a label.
The rule layer is intentionally allowed to *abstain* — when no rule fires, or
when fired rules disagree — so that uncertain cases fall through to the
classifier and the closed loop rather than being forced.

The lexicon grows over the loop: confirmed ``concept → label`` associations are
promoted into new rules (see :mod:`lp2graph.mining.label.loop`), which is why
the rule set is versioned.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from lp2graph.mining.versions import LABEL_LEXICON_VERSION


@dataclass(frozen=True, slots=True)
class SeedRule:
    """If ``antecedent`` is present in an entity's features, propose ``label``.

    ``confidence`` reflects how much the loop trusts the rule (seed rules are
    near-certain; promoted rules inherit the confidence they earned).
    """

    antecedent: str
    label: str
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class RuleDecision:
    """Outcome of applying the rule layer to one entity."""

    label: str | None
    fired: tuple[str, ...]  # antecedents that fired
    confidence: float
    conflict: bool

    @property
    def abstained(self) -> bool:
        return self.label is None


@dataclass(frozen=True, slots=True)
class RuleLayer:
    """An ordered, versioned set of :class:`SeedRule`."""

    rules: tuple[SeedRule, ...]
    version: str = LABEL_LEXICON_VERSION

    def apply(self, features: Mapping[str, float]) -> RuleDecision:
        """Apply every rule whose antecedent is present.

        If the fired rules all agree on a label, return it (with the max
        confidence among them). If they disagree, abstain and flag a conflict.
        If none fire, abstain.
        """
        fired: list[SeedRule] = [r for r in self.rules if r.antecedent in features]
        if not fired:
            return RuleDecision(label=None, fired=(), confidence=0.0, conflict=False)
        labels = {r.label for r in fired}
        antecedents = tuple(r.antecedent for r in fired)
        if len(labels) > 1:
            return RuleDecision(label=None, fired=antecedents, confidence=0.0, conflict=True)
        label = next(iter(labels))
        confidence = max(r.confidence for r in fired)
        return RuleDecision(label=label, fired=antecedents, confidence=confidence, conflict=False)

    def with_rules(self, extra: Iterable[SeedRule], *, version: str) -> RuleLayer:
        """Return a new, re-versioned layer with ``extra`` rules appended.

        De-duplicates on ``(antecedent, label)`` keeping the first occurrence,
        so promotion is idempotent and order-stable.
        """
        seen: set[tuple[str, str]] = set()
        merged: list[SeedRule] = []
        for r in (*self.rules, *extra):
            key = (r.antecedent, r.label)
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
        return RuleLayer(rules=tuple(merged), version=version)


__all__ = ["RuleDecision", "RuleLayer", "SeedRule"]
