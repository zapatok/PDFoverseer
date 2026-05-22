"""Smoke tests for the ART anchor pattern (Task 4.1).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.
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

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "art"
_PDF = _FIXTURE_DIR / "f_art_01_p1_crs_andamios.pdf"
_GT = _FIXTURE_DIR / "ground_truth.json"


def _load_gt() -> dict:
    return json.loads(_GT.read_text())


def test_art_count_ocr_smoke():
    """AnchorsScanner returns the expected cover count for the ART fixture."""
    if not _PDF.exists():
        pytest.skip("ART fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = AnchorsScanner(sigla="art")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"ART cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high", f"Expected HIGH confidence, got {result.confidence}"


def test_art_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF."""
    if not _PDF.exists():
        pytest.skip("ART fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="art")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert _PDF.name in result.per_file, (
        f"Expected '{_PDF.name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[_PDF.name] == 1
