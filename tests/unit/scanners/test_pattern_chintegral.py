"""Smoke tests for the chintegral anchor patterns (Task 5.1).

Three flavors:
- f_rch: standard RCH template ("registro de charla" + "nombre de la charla")
- f_japa: JAPA contractor variant ("registro capacitacion" + "sociedad de proyectos de ingenieria")
- f_previene: PREVIENE programme ("programa previene" + "lista de asistencia")

Each flavor has its own fixture sub-directory containing one PDF.  When the
fixture PDF is absent (gitignored), the test is skipped — not failed.  This
keeps CI green.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytesseract
import pytest

pytesseract.pytesseract.tesseract_cmd = os.getenv(
    "TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

from core.scanners.anchors_scanner import AnchorsScanner  # noqa: E402
from core.scanners.cancellation import CancellationToken  # noqa: E402

_BASE = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "chintegral"

_RCH_DIR = _BASE / "f_rch"
_RCH_PDF = _RCH_DIR / "f_rch_p1_crs.pdf"

_JAPA_DIR = _BASE / "f_japa"
_JAPA_PDF = _JAPA_DIR / "f_japa_p1_reinstruccion.pdf"

_PREVIENE_DIR = _BASE / "f_previene"
_PREVIENE_PDF = _PREVIENE_DIR / "f_previene_p1_hll.pdf"


def _gt(subdir: Path) -> dict:
    return json.loads((subdir / "ground_truth.json").read_text())


# ---------------------------------------------------------------------------
# f_rch flavor
# ---------------------------------------------------------------------------


def test_chintegral_rch_smoke():
    """AnchorsScanner detects 1 cover in the RCH chintegral fixture."""
    if not _RCH_PDF.exists():
        pytest.skip("chintegral RCH fixture PDF not present (gitignored)")

    gt = _gt(_RCH_DIR)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(_RCH_DIR, cancel=CancellationToken())

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
    if not _RCH_PDF.exists():
        pytest.skip("chintegral RCH fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(_RCH_DIR, cancel=CancellationToken())

    assert _RCH_PDF.name in result.per_file
    assert result.per_file[_RCH_PDF.name] == 1


# ---------------------------------------------------------------------------
# f_japa flavor
# ---------------------------------------------------------------------------


def test_chintegral_japa_smoke():
    """AnchorsScanner detects 1 cover in the JAPA chintegral fixture."""
    if not _JAPA_PDF.exists():
        pytest.skip("chintegral JAPA fixture PDF not present (gitignored)")

    gt = _gt(_JAPA_DIR)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(_JAPA_DIR, cancel=CancellationToken())

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
    if not _JAPA_PDF.exists():
        pytest.skip("chintegral JAPA fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(_JAPA_DIR, cancel=CancellationToken())

    assert _JAPA_PDF.name in result.per_file
    assert result.per_file[_JAPA_PDF.name] == 1


# ---------------------------------------------------------------------------
# f_previene flavor
# ---------------------------------------------------------------------------


def test_chintegral_previene_smoke():
    """AnchorsScanner detects 1 cover in the PREVIENE chintegral fixture."""
    if not _PREVIENE_PDF.exists():
        pytest.skip("chintegral PREVIENE fixture PDF not present (gitignored)")

    gt = _gt(_PREVIENE_DIR)
    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(_PREVIENE_DIR, cancel=CancellationToken())

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
    if not _PREVIENE_PDF.exists():
        pytest.skip("chintegral PREVIENE fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="chintegral")
    result = scanner.count_ocr(_PREVIENE_DIR, cancel=CancellationToken())

    assert _PREVIENE_PDF.name in result.per_file
    assert result.per_file[_PREVIENE_PDF.name] == 1
