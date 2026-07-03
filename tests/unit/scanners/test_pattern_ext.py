"""Smoke tests for the ext pagination pattern (Task 5.6; migrated from
AnchorsScanner in Fase 7 test hardening — E8/E9).

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

from core.scanners.cancellation import CancellationToken  # noqa: E402
from core.scanners.pagination_scanner import PaginationScanner  # noqa: E402

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "ext"
_PDF = _FIXTURE_DIR / "ext_chequeos.pdf"
_GT = _FIXTURE_DIR / "ground_truth.json"


def _load_gt() -> dict:
    return json.loads(_GT.read_text())


def test_ext_count_ocr_smoke():
    """PaginationScanner returns the expected cover count for the ext fixture."""
    if not _PDF.exists():
        pytest.skip("ext fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = PaginationScanner(sigla="ext")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"ext cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )


def test_ext_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF."""
    if not _PDF.exists():
        pytest.skip("ext fixture PDF not present (gitignored)")

    scanner = PaginationScanner(sigla="ext")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert _PDF.name in result.per_file, (
        f"Expected '{_PDF.name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[_PDF.name] == 15
