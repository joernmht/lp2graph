"""Frozen report types for the end-to-end validation pipeline.

The pipeline never raises on bad input; every observation — a stripped
markdown fence, a failed parse attempt, a solver status — becomes a
:class:`Check` on the :class:`ValidationReport`. The report is the whole
contract: a caller (human, script, or LLM) reads the ``verdict`` and the
non-``ok`` checks and knows exactly what to fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lp2graph.core.model import Formulation

#: Stamped into every report so downstream records can tell which
#: detector/rule set produced them (same convention as mining/versions.py).
PIPELINE_VERSION = "validate-2026.07.0"

CheckLevel = Literal["ok", "warn", "error", "skip"]
CheckStage = Literal["decode", "detect", "parse", "semantics", "structure", "solve"]

Verdict = Literal["valid", "valid_with_warnings", "invalid"]


@dataclass(frozen=True, slots=True)
class Check:
    """One observation made by one pipeline stage.

    ``code`` is a stable machine-readable identifier (e.g.
    ``"markdown-fences"``, ``"parse-failed"``); ``message`` is the
    human-readable line; ``detail`` carries optional context (a rejected
    parser's error text, a list of unused symbols) as a plain string.
    """

    stage: CheckStage
    level: CheckLevel
    code: str
    message: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        d = {
            "stage": self.stage,
            "level": self.level,
            "code": self.code,
            "message": self.message,
        }
        if self.detail:
            d["detail"] = self.detail
        return d


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The outcome of validating one artifact.

    ``formulation`` is the parsed canonical model when the artifact got
    that far, else ``None`` — a report with ``formulation is None`` is
    always ``invalid``. ``solve`` summarizes the optional grounding
    smoke-check (status, objective, sizes) when it ran.
    """

    source: str
    fmt: str | None
    checks: tuple[Check, ...]
    formulation: Formulation | None = None
    solve: dict[str, object] | None = None
    pipeline_version: str = field(default=PIPELINE_VERSION)

    @property
    def errors(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.level == "error")

    @property
    def warnings(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.level == "warn")

    @property
    def verdict(self) -> Verdict:
        if self.errors or self.formulation is None:
            return "invalid"
        if self.warnings:
            return "valid_with_warnings"
        return "valid"

    def to_dict(self) -> dict[str, object]:
        """A JSON-ready dict. The formulation is summarized, not embedded."""
        f = self.formulation
        return {
            "pipeline_version": self.pipeline_version,
            "source": self.source,
            "fmt": self.fmt,
            "verdict": self.verdict,
            "formulation": None if f is None else {"id": f.id, "name": f.name, "family": f.family},
            "counts": {
                "ok": sum(1 for c in self.checks if c.level == "ok"),
                "warn": len(self.warnings),
                "error": len(self.errors),
                "skip": sum(1 for c in self.checks if c.level == "skip"),
            },
            "checks": [c.to_dict() for c in self.checks],
            "solve": self.solve,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        """Human-readable multi-line summary (what the CLI prints)."""
        lines: list[str] = []
        f = self.formulation
        if self.verdict != "invalid" and f is not None:
            lines.append(f"OK: {f.id} ({f.family})")
        else:
            lines.append(f"INVALID: {self.source}")
        for c in self.checks:
            if c.level in ("warn", "error", "skip"):
                tag = {"warn": "WARN", "error": "ERROR", "skip": "SKIP"}[c.level]
                lines.append(f"  {tag} [{c.stage}] {c.code}: {c.message}")
                if c.detail:
                    lines.append(f"        {c.detail}")
        if self.solve is not None:
            obj = self.solve.get("objective")
            lines.append(
                f"  solve: {self.solve.get('status')}"
                f" objective={obj}"
                f" vars={self.solve.get('n_vars')}"
                f" constraints={self.solve.get('n_constraints')}"
                f" solver={self.solve.get('solver')}"
            )
        lines.append(f"verdict: {self.verdict}")
        return "\n".join(lines)


__all__ = ["PIPELINE_VERSION", "Check", "CheckLevel", "CheckStage", "ValidationReport", "Verdict"]
