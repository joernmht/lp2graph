"""Source-span provenance shared by the ingestion and labeling layers.

Mining real formulations means transforming idiosyncratic source artifacts
(solver code, paper LaTeX) into the canonical model. Every such transform
must be auditable: a reader has to be able to point at a canonical field
and ask "where did this come from, and what rewrite produced it?". These
small, frozen records answer that question.

They are intentionally dependency-free dataclasses (not pydantic models):
they describe *how* a ``Formulation`` was obtained, not the formulation
itself, so they live beside the canonical model rather than inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """A half-open character/line span in a named source artifact.

    ``source`` is a stable identifier for the artifact (a path, a URL, or
    a logical id). ``start``/``end`` are 0-based character offsets into the
    artifact text; ``line`` is the 1-based line of ``start`` when known.
    A span with ``start == end == 0`` and ``line is None`` denotes "whole
    artifact / location unknown".
    """

    source: str
    start: int = 0
    end: int = 0
    line: int | None = None

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError("SourceSpan offsets must be non-negative")
        if self.end < self.start:
            raise ValueError("SourceSpan end must be >= start")

    @property
    def is_whole(self) -> bool:
        """True if this span denotes the whole artifact / unknown location."""
        return self.start == 0 and self.end == 0 and self.line is None


@dataclass(frozen=True, slots=True)
class Rewrite:
    """A single recorded normalization step.

    ``rule`` is the identifier of the rewrite rule that fired (so the set
    of rules that touched a document is recoverable). ``before``/``after``
    are the literal text fragments. ``span`` anchors the rewrite back to
    the *original* source. The pair ``(rules_version, rule)`` makes a
    rewrite reproducible: same input + same versioned rule table → same
    rewrite.
    """

    rule: str
    before: str
    after: str
    span: SourceSpan
    rules_version: str = ""


@dataclass(frozen=True, slots=True)
class ProvenanceMap:
    """The audit trail attached to one ingested formulation.

    ``rewrites`` is the ordered list of normalizations applied (M1b).
    ``field_spans`` maps a dotted canonical field path (e.g.
    ``"variables.x"`` or ``"constraints.headway"``) to the source span it
    was recovered from, so a downstream tool can highlight provenance in
    the original artifact. Both are append-only build artifacts.
    """

    source: str
    rewrites: tuple[Rewrite, ...] = ()
    field_spans: dict[str, SourceSpan] = field(default_factory=dict)

    def with_rewrite(self, rewrite: Rewrite) -> ProvenanceMap:
        """Return a copy with ``rewrite`` appended (immutable update)."""
        return ProvenanceMap(
            source=self.source,
            rewrites=(*self.rewrites, rewrite),
            field_spans=dict(self.field_spans),
        )


__all__ = ["ProvenanceMap", "Rewrite", "SourceSpan"]
