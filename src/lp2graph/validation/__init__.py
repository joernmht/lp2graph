"""End-to-end validation of (LLM-)generated LP/MILP artifacts.

Where :func:`lp2graph.validate` checks the cross-reference invariants of
an already-parsed canonical model, this package answers the broader
question an LLM (or its harness) asks about its *own output*: "is the
model I just generated well-formed, complete, and solvable?" — for raw
text in any supported format, with detectors and repairs for the usual
faults of generated output (markdown fences, unicode look-alikes,
truncation), parse fallbacks across formats, and a solver smoke check.
Every entry point returns a :class:`ValidationReport`; nothing raises on
bad input.

    from lp2graph.validation import validate_text
    report = validate_text(llm_output)
    print(report.summary())          # or report.to_json()
    assert report.verdict != "invalid"

The same pipeline is exposed on the command line as ``lp2graph validate``.
"""

from __future__ import annotations

from lp2graph.validation.detect import EXT_FMT, FMT_ALIASES, FORMATS, sniff_format
from lp2graph.validation.pipeline import (
    validate_formulation,
    validate_path,
    validate_text,
)
from lp2graph.validation.report import (
    PIPELINE_VERSION,
    Check,
    CheckLevel,
    CheckStage,
    ValidationReport,
    Verdict,
)

__all__ = [
    "EXT_FMT",
    "FMT_ALIASES",
    "FORMATS",
    "PIPELINE_VERSION",
    "Check",
    "CheckLevel",
    "CheckStage",
    "ValidationReport",
    "Verdict",
    "sniff_format",
    "validate_formulation",
    "validate_path",
    "validate_text",
]
