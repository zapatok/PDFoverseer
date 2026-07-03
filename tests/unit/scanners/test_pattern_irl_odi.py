"""Smoke tests for the IRL and ODI pagination patterns (Task 4.2; migrated
from AnchorsScanner in Fase 7 test hardening — E8/E9).

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

_IRL_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "irl"
_IRL_PDF = _IRL_DIR / "f_irl_01_p1.pdf"
_IRL_GT = _IRL_DIR / "ground_truth.json"

_ODI_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "odi"
_ODI_PDF = _ODI_DIR / "f_odi_01_p1.pdf"
_ODI_GT = _ODI_DIR / "ground_truth.json"


def _load_gt(path: Path) -> dict:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# IRL
# ---------------------------------------------------------------------------


def test_irl_count_ocr_smoke():
    """PaginationScanner returns 1 cover for the 54-page IRL booklet fixture.

    The booklet embeds many sub-forms, each with its own 'pagina N de M'
    header.  IRL's patterns.py entry sets cover_code='F-CRS-ODI-01', so the
    engine only counts a document start where curr==1 AND the page's form
    code matches — the embedded sub-forms' own page-1s (pages 33+) are
    appendix material, not IRL covers, so they must not inflate the count.
    """
    if not _IRL_PDF.exists():
        pytest.skip("IRL fixture PDF not present (gitignored)")

    gt = _load_gt(_IRL_GT)
    scanner = PaginationScanner(sigla="irl")
    result = scanner.count_ocr(_IRL_DIR, cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"IRL cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_irl_count_ocr_per_file_breakdown():
    """per_file entry exists for the IRL fixture PDF."""
    if not _IRL_PDF.exists():
        pytest.skip("IRL fixture PDF not present (gitignored)")

    scanner = PaginationScanner(sigla="irl")
    result = scanner.count_ocr(_IRL_DIR, cancel=CancellationToken())

    assert _IRL_PDF.name in result.per_file
    assert result.per_file[_IRL_PDF.name] == 1


# ---------------------------------------------------------------------------
# ODI
# ---------------------------------------------------------------------------


def test_odi_count_ocr_smoke():
    """PaginationScanner returns 1 cover for the 2-page ODI visita fixture.

    Both pages belong to a single document: P1 reads 'pagina 1 de 2' (the
    cover) and P2 'pagina 2 de 2' (the continuation page with 'induccion
    inicial' content) — the engine counts one document start (curr==1 once).
    """
    if not _ODI_PDF.exists():
        pytest.skip("ODI fixture PDF not present (gitignored)")

    gt = _load_gt(_ODI_GT)
    scanner = PaginationScanner(sigla="odi")
    result = scanner.count_ocr(_ODI_DIR, cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"ODI cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_odi_count_ocr_per_file_breakdown():
    """per_file entry exists for the ODI fixture PDF."""
    if not _ODI_PDF.exists():
        pytest.skip("ODI fixture PDF not present (gitignored)")

    scanner = PaginationScanner(sigla="odi")
    result = scanner.count_ocr(_ODI_DIR, cancel=CancellationToken())

    assert _ODI_PDF.name in result.per_file
    assert result.per_file[_ODI_PDF.name] == 1
