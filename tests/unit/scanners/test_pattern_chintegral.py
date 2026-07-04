"""Smoke tests for the chintegral anchor patterns (Task 5.1).

Three flavors:
- f_rch: standard RCH template ("registro de charla" + "nombre de la charla")
- f_japa: JAPA contractor variant ("registro capacitacion" + "sociedad de proyectos de ingenieria")
- f_previene: PREVIENE programme ("programa previene" + "lista de asistencia")

Each flavor has its own fixture sub-directory containing one PDF (flavor-dir
GT shape: the sub-directory's ground_truth.json carries covers_expected).
When the fixture PDF is absent (gitignored), the test is skipped — not
failed.  This keeps CI green.
"""

from __future__ import annotations

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken
from tests.unit.scanners.fixture_gt import fixture_dir, load_gt, skip_unless_present

_RCH = "chintegral/f_rch"
_RCH_PDF = fixture_dir(_RCH) / "f_rch_p1_crs.pdf"

_JAPA = "chintegral/f_japa"
_JAPA_PDF = fixture_dir(_JAPA) / "f_japa_p1_reinstruccion.pdf"

_PREVIENE = "chintegral/f_previene"
_PREVIENE_PDF = fixture_dir(_PREVIENE) / "f_previene_p1_hll.pdf"


# ---------------------------------------------------------------------------
# f_rch flavor
# ---------------------------------------------------------------------------


def test_chintegral_rch_smoke():
    """AnchorsScanner detects 1 cover in the RCH chintegral fixture."""
    skip_unless_present(_RCH_PDF, "chintegral RCH")

    gt = load_gt(_RCH)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(fixture_dir(_RCH), cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"RCH cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_chintegral_rch_per_file():
    """per_file breakdown is correct for the RCH fixture."""
    skip_unless_present(_RCH_PDF, "chintegral RCH")

    gt = load_gt(_RCH)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(fixture_dir(_RCH), cancel=CancellationToken())

    assert _RCH_PDF.name in result.per_file
    assert result.per_file[_RCH_PDF.name] == gt["covers_expected"]


# ---------------------------------------------------------------------------
# f_japa flavor
# ---------------------------------------------------------------------------


def test_chintegral_japa_smoke():
    """AnchorsScanner detects 1 cover in the JAPA chintegral fixture."""
    skip_unless_present(_JAPA_PDF, "chintegral JAPA")

    gt = load_gt(_JAPA)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(fixture_dir(_JAPA), cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"JAPA cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_chintegral_japa_per_file():
    """per_file breakdown is correct for the JAPA fixture."""
    skip_unless_present(_JAPA_PDF, "chintegral JAPA")

    gt = load_gt(_JAPA)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(fixture_dir(_JAPA), cancel=CancellationToken())

    assert _JAPA_PDF.name in result.per_file
    assert result.per_file[_JAPA_PDF.name] == gt["covers_expected"]


# ---------------------------------------------------------------------------
# f_previene flavor
# ---------------------------------------------------------------------------


def test_chintegral_previene_smoke():
    """AnchorsScanner detects 1 cover in the PREVIENE chintegral fixture."""
    skip_unless_present(_PREVIENE_PDF, "chintegral PREVIENE")

    gt = load_gt(_PREVIENE)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(fixture_dir(_PREVIENE), cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"PREVIENE cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_chintegral_previene_per_file():
    """per_file breakdown is correct for the PREVIENE fixture."""
    skip_unless_present(_PREVIENE_PDF, "chintegral PREVIENE")

    gt = load_gt(_PREVIENE)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(fixture_dir(_PREVIENE), cancel=CancellationToken())

    assert _PREVIENE_PDF.name in result.per_file
    assert result.per_file[_PREVIENE_PDF.name] == gt["covers_expected"]
