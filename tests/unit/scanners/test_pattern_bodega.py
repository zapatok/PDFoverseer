"""Smoke tests for the bodega pagination pattern (Task 5.4; migrated from
AnchorsScanner in Fase 7 test hardening — E8/E9).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.

Fixture: f_pets_07_03_p1_chequeo.pdf — HPV 4-page bodega compilation.
Each of the 4 pages is a separate Chequeo Bodega SUSPEL/RESPEL document
(F-PETS-CRS-07-03, Pagina 1 de 1).  Expected cover count = 4.
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

_SIGLA = "bodega"


def test_bodega_count_ocr_smoke():
    """PaginationScanner returns 4 covers for the 4-page bodega compilation fixture.

    Each page of the fixture is a separate 1-page Chequeo Bodega document,
    each reading 'Pagina 1 de 1' in the top-right corner.
    """
    skip_unless_present(fixture_pdf(_SIGLA), "Bodega")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"Bodega cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high", f"Expected HIGH confidence, got {result.confidence}"


def test_bodega_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF with the GT count."""
    skip_unless_present(fixture_pdf(_SIGLA), "Bodega")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file, (
        f"Expected '{name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[name] == gt["covers_expected"]
