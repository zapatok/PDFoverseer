"""Smoke tests for the chps anchor pattern (Task 5.13).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.

Fixture: f_ar_01_p1_acta_reunion.pdf — HPV 3-page CHPS acta de reunion.
Single meeting-minutes document (F-CRS-AR-01): p1=cover with attendee table,
p2-p3=continuation (acuerdos).  Expected cover count = 1.
"""

from __future__ import annotations

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken
from tests.unit.scanners.fixture_gt import (
    fixture_dir,
    fixture_pdf,
    load_gt,
    skip_unless_present,
)

_SIGLA = "chps"


def test_chps_count_ocr_smoke():
    """AnchorsScanner returns 1 cover for the 3-page CHPS acta de reunion fixture.

    The fixture contains a single meeting-minutes document (F-CRS-AR-01).
    p1 matches 5 anchors (cover: 'lista de convocados', 'hospital de',
    'lugar de la reunion' + running header 'acta de reunion' + 'f-crs-ar-01').
    p2/p3 match only 2 anchors (running header only), falling below min_match=3.
    """
    skip_unless_present(fixture_pdf(_SIGLA), "CHPS")

    gt = load_gt(_SIGLA)
    scanner = AnchorsScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"CHPS cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high", f"Expected HIGH confidence, got {result.confidence}"


def test_chps_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF with the GT count."""
    skip_unless_present(fixture_pdf(_SIGLA), "CHPS")

    gt = load_gt(_SIGLA)
    scanner = AnchorsScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file, (
        f"Expected '{name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[name] == gt["covers_expected"]
