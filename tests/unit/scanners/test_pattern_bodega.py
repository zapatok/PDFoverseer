"""Smoke tests for the bodega anchor pattern (Task 5.4).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.

Fixture: f_pets_07_03_p1_chequeo.pdf — HPV 4-page bodega compilation.
Each of the 4 pages is a separate Chequeo Bodega SUSPEL/RESPEL document
(F-PETS-CRS-07-03, Pagina 1 de 1).  Expected cover count = 4.
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

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "bodega"
_PDF = _FIXTURE_DIR / "f_pets_07_03_p1_chequeo.pdf"
_GT = _FIXTURE_DIR / "ground_truth.json"


def _load_gt() -> dict:
    return json.loads(_GT.read_text())


def test_bodega_count_ocr_smoke():
    """AnchorsScanner returns 4 covers for the 4-page bodega compilation fixture.

    Each page of the fixture is a separate 1-page Chequeo Bodega document.
    All 4 pages match min_match=3 anchors in the top band:
    'chequeo bodega' + 'f-pets-crs-07-03' + 'bodega suspel'.
    """
    if not _PDF.exists():
        pytest.skip("Bodega fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = AnchorsScanner(sigla="bodega")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"Bodega cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high", f"Expected HIGH confidence, got {result.confidence}"


def test_bodega_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF with count=4."""
    if not _PDF.exists():
        pytest.skip("Bodega fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = AnchorsScanner(sigla="bodega")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert _PDF.name in result.per_file, (
        f"Expected '{_PDF.name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[_PDF.name] == gt["covers_expected"]
