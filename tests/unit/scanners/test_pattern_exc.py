"""Smoke tests for the exc pagination pattern (Task 5.8; migrated from
AnchorsScanner in Fase 7 test hardening — E8/E9).

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

_SIGLA = "exc"


def test_exc_count_ocr_smoke():
    """PaginationScanner returns the expected cover count for the exc fixture."""
    skip_unless_present(fixture_pdf(_SIGLA), _SIGLA)

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"exc cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )


def test_exc_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF and carries the GT count."""
    skip_unless_present(fixture_pdf(_SIGLA), _SIGLA)

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file, (
        f"Expected '{name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[name] == gt["covers_expected"]
