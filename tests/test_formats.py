"""The format registry is the single source of truth (ADR-0012).

These tests exist to make the drift that motivated ADR-0012 unexpressible:
before it, `validation.detect` and `mining.ingest.dispatch` each carried a
private extension table, and `mining.ingest` had silently lost `.json`.
"""

from __future__ import annotations

import pytest

from lp2graph import formats
from lp2graph.mining.ingest.code_importers import CODE_IMPORTERS
from lp2graph.mining.ingest.dispatch import _EXT_FMT
from lp2graph.validation import detect

ASSIGNMENT = "formulations/objectives/objective_abs_deviation.json"


def test_detect_and_ingest_share_one_table() -> None:
    """The two layers that used to drift now read the same object."""
    assert _EXT_FMT is formats.EXT_FMT
    assert detect.EXT_FMT is formats.SNIFFABLE_EXT_FMT
    assert detect.FMT_ALIASES is formats.FMT_ALIASES


def test_sniffable_subset_is_the_registry_minus_pdf() -> None:
    """A PDF is binary; the text sniffer must never be offered one."""
    assert set(formats.SNIFFABLE_FORMATS) == set(formats.FORMATS) - {"pdf"}
    assert ".pdf" not in formats.SNIFFABLE_EXT_FMT


def test_every_extension_maps_to_a_declared_format() -> None:
    assert set(formats.EXT_FMT.values()) <= set(formats.FORMATS)


def test_every_alias_resolves_to_a_declared_format() -> None:
    assert set(formats.FMT_ALIASES.values()) <= set(formats.FORMATS)


def test_every_routable_format_has_an_importer_or_is_special_cased() -> None:
    """Nothing in FORMATS is reachable-but-unroutable."""
    special = {"latex", "pdf"}  # handled directly by the dispatcher
    assert set(formats.FORMATS) - special == set(CODE_IMPORTERS) - special


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [(".json", "json"), ("json", "json"), (".TeX", "latex"), (".mod", "ampl"), (".zzz", None)],
)
def test_format_for_extension(suffix: str, expected: str | None) -> None:
    assert formats.format_for_extension(suffix) == expected


@pytest.mark.parametrize(
    ("given", "expected"),
    [("latex", "latex"), ("tex", "latex"), ("GMS", "gams"), (".py", "python"), ("nope", None)],
)
def test_normalize_format_accepts_keys_and_aliases(given: str, expected: str | None) -> None:
    assert formats.normalize_format(given) == expected


def test_registry_is_not_mutated_by_use() -> None:
    """Routing must stay a pure function of the source tree (ADR-0012)."""
    before = dict(formats.EXT_FMT)
    formats.format_for_extension(".zzz")
    formats.normalize_format("nope")
    assert before == formats.EXT_FMT
