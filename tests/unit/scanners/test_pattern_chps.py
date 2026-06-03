"""Smoke tests for the chps anchor pattern (Task 5.13).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.

Fixture: f_ar_01_p1_acta_reunion.pdf — HPV 3-page CHPS acta de reunion.
Single meeting-minutes document (F-CRS-AR-01): p1=cover with attendee table,
p2-p3=continuation (acuerdos).  Expected cover count = 1.
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

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "chps"
_PDF = _FIXTURE_DIR / "f_ar_01_p1_acta_reunion.pdf"
_GT = _FIXTURE_DIR / "ground_truth.json"


def _load_gt() -> dict:
    return json.loads(_GT.read_text())


def test_chps_count_ocr_smoke():
    """AnchorsScanner returns 1 cover for the 3-page CHPS acta de reunion fixture.

    The fixture contains a single meeting-minutes document (F-CRS-AR-01).
    p1 matches 5 anchors (cover: 'lista de convocados', 'hospital de',
    'lugar de la reunion' + running header 'acta de reunion' + 'f-crs-ar-01').
    p2/p3 match only 2 anchors (running header only), falling below min_match=3.
    """
    if not _PDF.exists():
        pytest.skip("CHPS fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = AnchorsScanner(sigla="chps")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"CHPS cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high", f"Expected HIGH confidence, got {result.confidence}"


def test_chps_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF with count=1."""
    if not _PDF.exists():
        pytest.skip("CHPS fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = AnchorsScanner(sigla="chps")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert _PDF.name in result.per_file, (
        f"Expected '{_PDF.name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[_PDF.name] == gt["covers_expected"]
