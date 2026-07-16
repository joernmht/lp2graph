"""Detector unit tests: decoding, fence extraction, unicode repair, sniffing."""

from __future__ import annotations

from lp2graph.validation.detect import (
    decode_bytes,
    extract_fenced,
    normalize_unicode,
    resolve_fmt,
    sniff_format,
    truncation_checks,
)

LP_TEXT = "Minimize\n obj: 3 x + 5 y\nSubject To\n c1: x + y >= 2\nEnd\n"


def test_decode_utf8_clean():
    checks = []
    assert decode_bytes(b"min x", checks=checks) == "min x"
    assert checks == []


def test_decode_latin1_fallback_and_nul():
    checks = []
    text = decode_bytes(b"min \xe9\x00x", checks=checks)
    assert "\x00" not in text
    codes = {c.code for c in checks}
    assert codes == {"not-utf8", "nul-bytes"}


def test_extract_fenced_with_tag_hint():
    checks = []
    text, hint = extract_fenced(f"Here you go:\n\n```lp\n{LP_TEXT}```\nDone.", checks=checks)
    assert hint == "lp"
    assert text.startswith("Minimize")
    assert [c.code for c in checks] == ["markdown-fences"]


def test_extract_unterminated_fence_flags_truncation():
    checks = []
    text, _ = extract_fenced("```lp\nMinimize\n obj: x\n```\n```lp\nSubject To", checks=checks)
    assert "Subject To" in text
    assert {c.code for c in checks} == {"unterminated-fence", "markdown-fences"}


def test_no_fences_passthrough():
    checks = []
    text, hint = extract_fenced(LP_TEXT, checks=checks)
    assert text == LP_TEXT
    assert hint is None
    assert checks == []


def test_normalize_unicode_lookalikes():
    checks = []
    out = normalize_unicode("3 x \u2212 5 y \u2264 7", "lp", checks=checks)
    assert out == "3 x - 5 y <= 7"
    assert checks[0].code == "unicode-normalized"


def test_normalize_unicode_latex_keeps_relations():
    checks = []
    out = normalize_unicode("x \u2212 y \u2264 7", "latex", checks=checks)
    assert out == "x - y \u2264 7"  # relations are TeX's business; only the minus is repaired


def test_truncation_dangling_tail_and_braces():
    checks = []
    truncation_checks("\\begin{align} x_{i} +", "latex", checks=checks)
    codes = {c.code for c in checks}
    assert "dangling-tail" in codes
    assert "unbalanced-environments" in codes


def test_truncation_mps_endata():
    checks = []
    truncation_checks("NAME m\nROWS\nCOLUMNS\n", "mps", checks=checks)
    assert {c.code for c in checks} == {"mps-no-endata"}


def test_sniff_lp_beats_others():
    assert sniff_format(LP_TEXT)[0][0] == "lp"


def test_sniff_json_latex_python():
    assert sniff_format('{"id": "m", "family": "lp"}')[0][0] == "json"
    assert sniff_format("\\begin{align}\\min \\sum_i x_i\\end{align}")[0][0] == "latex"
    assert sniff_format("import pulp\nprob = pulp.LpProblem()")[0][0] == "python"


def test_sniff_garbage_scores_nothing():
    assert sniff_format("The optimal answer is train 5.") == []


def test_resolve_fmt_aliases():
    assert resolve_fmt("tex") == "latex"
    assert resolve_fmt(".gms") == "gams"
    assert resolve_fmt(None) is None
    assert resolve_fmt("LP") == "lp"
