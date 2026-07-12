"""Smoke tests for the Charla pattern — migrated anchors → pagination (Track
D / D2, 2026-07-12 benchmark; see docs/research/2026-07-12-rch-pagination-decision.md).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.

The charla fixture (f_rch_p1.pdf) is a 3-page compilation: P1 and P3 are
both session covers, P2 is the attendance/continuation sheet of the first
session.  Expected cover count = 2.

These were `@pytest.mark.skip`'d pending a fixture rebuild against the
spec-verbatim anchor set (pre anchor-truncation postmortem 2026-05-22,
docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md); that
concern is anchors-specific and no longer applies to the migrated
PaginationScanner path (the fixture PDF still is not present on this
machine — `skip_unless_present` continues to gate these on presence, not an
unconditional skip).
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

_SIGLA = "charla"


def test_charla_count_ocr_smoke():
    """PaginationScanner returns 2 covers for the 3-page charla compilation fixture.

    The fixture contains two separate charla session covers (P1 and P3), each
    reading "Página 1 de N"; P2 is the continuation of the first session.
    """
    skip_unless_present(fixture_pdf(_SIGLA), "Charla")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"
    assert result.count == gt["covers_expected"], (
        f"Charla cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_charla_count_ocr_per_file_breakdown():
    """per_file entry for the charla fixture PDF carries the GT count."""
    skip_unless_present(fixture_pdf(_SIGLA), "Charla")

    gt = load_gt(_SIGLA)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file, (
        f"Expected '{name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[name] == gt["covers_expected"]
