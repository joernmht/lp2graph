"""Frozen result types for the heterogeneous ingestion front-end.

The cardinal invariant of M1 is that an ingestion failure is *always
representable and reported, never silently dropped*. Every importer and
the dispatcher return an :class:`IngestionResult`, which is either a
success (a validated :class:`~lp2graph.core.model.Formulation` plus its
:class:`~lp2graph.mining.provenance.ProvenanceMap`) or a non-empty tuple
of structured :class:`IngestionFailure` records. A bare
``NotImplementedError`` swallowed deep in a call stack would violate this
contract; an :class:`IngestionFailure` naming the ``source`` and the
``stage`` it failed at does not.
"""

from __future__ import annotations

from dataclasses import dataclass

from lp2graph.core.model import Formulation
from lp2graph.mining.provenance import ProvenanceMap


class IngestionError(Exception):
    """Raised by :meth:`IngestionResult.unwrap` on a failed ingestion.

    Carries the failed result so callers can inspect every reported
    :class:`IngestionFailure` after catching it.
    """

    def __init__(self, result: IngestionResult) -> None:
        self.result = result
        joined = "; ".join(f"[{f.stage}] {f.message}" for f in result.failures)
        super().__init__(f"ingestion failed: {joined}")


@dataclass(frozen=True, slots=True)
class IngestionFailure:
    """A structured, never-swallowed ingestion failure.

    ``source`` is the artifact identifier (path / url / logical id);
    ``stage`` names the phase that failed (e.g. ``"normalize"``,
    ``"parse"``, ``"validate"``, ``"unsupported"``, ``"import"``);
    ``message`` is a human-readable summary; ``detail`` carries optional
    extra context (e.g. the list of semantic validation errors), kept as a
    plain string so the record stays hashable and dependency-free.
    """

    source: str
    stage: str
    message: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """The outcome of ingesting one source artifact.

    Exactly one of two states holds: a *success* carries a validated
    ``formulation`` and a ``provenance`` map with an empty ``failures``
    tuple; a *failure* carries ``formulation is None`` and a non-empty
    ``failures`` tuple. The constructors :meth:`success` and
    :meth:`failure` are the only sanctioned way to build instances and
    enforce that invariant.
    """

    source: str
    formulation: Formulation | None = None
    provenance: ProvenanceMap | None = None
    failures: tuple[IngestionFailure, ...] = ()

    def __post_init__(self) -> None:
        ok = self.formulation is not None
        if ok and self.failures:
            raise ValueError("IngestionResult cannot be both ok and carry failures")
        if not ok and not self.failures:
            raise ValueError("a failed IngestionResult must carry >=1 failure")
        if ok and self.provenance is None:
            raise ValueError("a successful IngestionResult must carry provenance")

    @classmethod
    def success(
        cls, *, source: str, formulation: Formulation, provenance: ProvenanceMap
    ) -> IngestionResult:
        """Build a successful result around a validated formulation."""
        return cls(source=source, formulation=formulation, provenance=provenance)

    @classmethod
    def failure(cls, *, source: str, failures: tuple[IngestionFailure, ...]) -> IngestionResult:
        """Build a failed result from a non-empty tuple of failures."""
        return cls(source=source, failures=failures)

    @classmethod
    def single_failure(
        cls, *, source: str, stage: str, message: str, detail: str = ""
    ) -> IngestionResult:
        """Convenience: a failed result carrying one failure."""
        return cls.failure(
            source=source,
            failures=(
                IngestionFailure(source=source, stage=stage, message=message, detail=detail),
            ),
        )

    @property
    def ok(self) -> bool:
        """True iff a validated formulation was produced."""
        return self.formulation is not None

    def unwrap(self) -> Formulation:
        """Return the validated formulation, or raise on failure.

        The escape hatch for callers that want exceptions: it never hides
        a failure (the raised :class:`IngestionError` carries every
        reported :class:`IngestionFailure`).
        """
        if self.formulation is None:
            raise IngestionError(self)
        return self.formulation


__all__ = [
    "IngestionError",
    "IngestionFailure",
    "IngestionResult",
]
