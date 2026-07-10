"""Smoke tests for the IRL and ODI pagination patterns (Task 4.2; migrated
from AnchorsScanner in Fase 7 test hardening — E8/E9).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.
"""

from __future__ import annotations

from core.scanners.cancellation import CancellationToken
from core.scanners.pagination_scanner import PaginationScanner
from tests.unit.scanners.fixture_gt import (
    fixture_dir,
    fixture_pdf,
    load_gt,
    skip_unless_present,
)

# ---------------------------------------------------------------------------
# IRL
# ---------------------------------------------------------------------------


def test_irl_count_ocr_smoke():
    """PaginationScanner returns 1 cover for the 54-page IRL booklet fixture.

    The booklet embeds many sub-forms, each with its own 'pagina N de M'
    header.  IRL's patterns.py entry sets cover_code='F-CRS-IRL-01', so the
    engine only counts a document start where curr==1 AND the page's form
    code matches — the embedded sub-forms' own page-1s (pages 33+) are
    appendix material, not IRL covers, so they must not inflate the count.
    """
    skip_unless_present(fixture_pdf("irl"), "IRL")

    gt = load_gt("irl")
    scanner = PaginationScanner(sigla="irl")
    result = scanner.count_ocr(fixture_dir("irl"), cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"IRL cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_irl_count_ocr_per_file_breakdown():
    """per_file entry exists for the IRL fixture PDF and carries the GT count."""
    skip_unless_present(fixture_pdf("irl"), "IRL")

    gt = load_gt("irl")
    scanner = PaginationScanner(sigla="irl")
    result = scanner.count_ocr(fixture_dir("irl"), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file
    assert result.per_file[name] == gt["covers_expected"]


# ---------------------------------------------------------------------------
# ODI
# ---------------------------------------------------------------------------


def test_odi_count_ocr_smoke():
    """PaginationScanner returns 1 cover for the 2-page ODI visita fixture.

    Both pages belong to a single document: P1 reads 'pagina 1 de 2' (the
    cover) and P2 'pagina 2 de 2' (the continuation page with 'induccion
    inicial' content) — the engine counts one document start (curr==1 once).
    """
    skip_unless_present(fixture_pdf("odi"), "ODI")

    gt = load_gt("odi")
    scanner = PaginationScanner(sigla="odi")
    result = scanner.count_ocr(fixture_dir("odi"), cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"ODI cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_odi_count_ocr_per_file_breakdown():
    """per_file entry exists for the ODI fixture PDF and carries the GT count."""
    skip_unless_present(fixture_pdf("odi"), "ODI")

    gt = load_gt("odi")
    scanner = PaginationScanner(sigla="odi")
    result = scanner.count_ocr(fixture_dir("odi"), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file
    assert result.per_file[name] == gt["covers_expected"]
