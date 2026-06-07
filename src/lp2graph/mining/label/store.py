"""Versioned label database and decision log (M4).

The closed loop is auditable and replayable because every decision is logged
and every accepted label is a fully-stamped record. The store holds two
append-only logs:

- ``records`` — the label database: one :class:`LabelRecord` per accepted
  ``(entity, dimension)``, stamped with its source and the lexicon / classifier
  / corpus versions in force when it was written.
- ``decisions`` — the decision log: one :class:`Decision` per entity processed
  in a loop, capturing the rule and classifier proposals, the gate that fired,
  and the final value.

:meth:`LabelStore.replay` reconstructs the records purely from the decision
log, which is the acceptance guarantee: the loop is replayable from its log.
Both logs serialize to plain JSON-able dicts (the versioned DB on disk).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

Source = Literal["rule", "clf", "human"]
Gate = Literal["auto_accept", "adjudicate", "defer"]

STORE_SCHEMA_VERSION = "labelstore-1"


@dataclass(frozen=True, slots=True)
class LabelRecord:
    """One accepted label, fully stamped for reproducibility."""

    entity_id: str
    level: str
    dimension: str
    value: str
    source: Source
    confidence: float
    lexicon_version: str
    clf_version: str
    corpus_version: str
    loop: int


@dataclass(frozen=True, slots=True)
class Decision:
    """One decision-log entry: everything needed to replay an entity's label."""

    entity_id: str
    level: str
    dimension: str
    rule_label: str | None
    rule_confidence: float
    clf_label: str
    clf_confidence: float
    gate: Gate
    final_value: str | None
    source: Source | None
    loop: int
    lexicon_version: str
    clf_version: str
    corpus_version: str


@dataclass
class LabelStore:
    """The closed-loop store: a label DB + a decision log."""

    records: list[LabelRecord]
    decisions: list[Decision]

    @classmethod
    def empty(cls) -> LabelStore:
        return cls(records=[], decisions=[])

    def write(self, record: LabelRecord) -> None:
        self.records.append(record)

    def log(self, decision: Decision) -> None:
        self.decisions.append(decision)

    def extend_decisions(self, decisions: Iterable[Decision]) -> None:
        self.decisions.extend(decisions)

    def latest_labels(self, dimension: str) -> dict[str, LabelRecord]:
        """Latest accepted record per entity for ``dimension`` (last write wins)."""
        out: dict[str, LabelRecord] = {}
        for r in self.records:
            if r.dimension == dimension:
                out[r.entity_id] = r
        return out

    # -- replay ----------------------------------------------------------

    @staticmethod
    def replay(decisions: Iterable[Decision]) -> list[LabelRecord]:
        """Reconstruct the accepted records from a decision log.

        A decision contributes a record iff it was accepted (``gate`` other
        than ``defer`` and a ``final_value`` is present). The result is
        order-preserving and depends only on the log — the replay guarantee.
        """
        out: list[LabelRecord] = []
        for d in decisions:
            if d.gate == "defer" or d.final_value is None or d.source is None:
                continue
            if d.source == "human":
                confidence = 1.0
            elif d.source == "rule":
                confidence = d.rule_confidence
            else:
                confidence = d.clf_confidence
            out.append(
                LabelRecord(
                    entity_id=d.entity_id,
                    level=d.level,
                    dimension=d.dimension,
                    value=d.final_value,
                    source=d.source,
                    confidence=confidence,
                    lexicon_version=d.lexicon_version,
                    clf_version=d.clf_version,
                    corpus_version=d.corpus_version,
                    loop=d.loop,
                )
            )
        return out

    # -- serialization ---------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": STORE_SCHEMA_VERSION,
            "records": [asdict(r) for r in self.records],
            "decisions": [asdict(d) for d in self.decisions],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> LabelStore:
        raw_records = cast("list[dict[str, Any]]", data.get("records", []))
        raw_decisions = cast("list[dict[str, Any]]", data.get("decisions", []))
        records = [LabelRecord(**r) for r in raw_records]
        decisions = [Decision(**d) for d in raw_decisions]
        return cls(records=records, decisions=decisions)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> LabelStore:
        return cls.from_dict(json.loads(text))


__all__ = [
    "STORE_SCHEMA_VERSION",
    "Decision",
    "Gate",
    "LabelRecord",
    "LabelStore",
    "Source",
]
