"""Smoke tests for the insgral pagination pattern (Task 5.3).

These tests run against real fixture PDFs.  When a fixture PDF is absent
(gitignored), the test is skipped — not failed.  This keeps CI green.

Fixture: 4 HRB insgral PDFs, each 1 page.  Each is a separate inspection
checklist (LCH-series forms with diverse templates).  The PaginationScanner
applies the A7 lock: every single-page PDF counts as 1 document without OCR.
Expected cover count = 4.

Note: real corpus insgral PDFs use centered pagination stamps (not the
upper-right corner that corner_count OCRs), so corner_count returns 0 for
any multi-page compilation.  The A7 path is the operative one here.
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

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "insgral"
_GT = _FIXTURE_DIR / "ground_truth.json"


def _load_gt() -> dict:
    return json.loads(_GT.read_text())


def _any_fixture_pdf_present() -> bool:
    return any(_FIXTURE_DIR.glob("*.pdf"))


def test_insgral_count_ocr_smoke():
    """PaginationScanner returns 4 docs for the 4-file insgral fixture folder.

    Each PDF is 1 page, so the A7 lock fires (count=1 per file, no OCR needed).
    Total = 4.  Method must be 'pagination'.
    """
    if not _any_fixture_pdf_present():
        pytest.skip("Insgral fixture PDFs not present (gitignored)")

    gt = _load_gt()
    scanner = PaginationScanner(sigla="insgral")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"Insgral cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  flags={result.flags!r}  errors={result.errors!r}"
    )


def test_insgral_count_ocr_a7_lock_fires():
    """A7 flag is present — each 1-page PDF triggered the A7 lock."""
    if not _any_fixture_pdf_present():
        pytest.skip("Insgral fixture PDFs not present (gitignored)")

    scanner = PaginationScanner(sigla="insgral")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert "a7_one_page_locked" in result.flags, (
        f"Expected 'a7_one_page_locked' in flags, got: {result.flags!r}"
    )
