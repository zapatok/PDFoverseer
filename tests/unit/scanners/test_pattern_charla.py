"""Smoke tests for the Charla anchor pattern (Task 4.3).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.

The charla fixture (f_rch_p1.pdf) is a 3-page compilation: P1 and P3 are
both session covers, P2 is the attendance/continuation sheet of the first
session.  Expected cover count = 2.
"""

from __future__ import annotations

import pytest

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken
from tests.unit.scanners.fixture_gt import (
    fixture_dir,
    fixture_pdf,
    load_gt,
    skip_unless_present,
)

_SIGLA = "charla"


@pytest.mark.skip(
    reason="Fixture engineered against the truncated anchor set "
    "(pre anchor-truncation postmortem 2026-05-22); awaiting fixture rebuild "
    "aligned to spec-verbatim anchors. Fase A calibration on the real ABRIL "
    "corpus is the active validation. See "
    "docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md."
)
def test_charla_count_ocr_smoke():
    """AnchorsScanner returns 2 covers for the 3-page charla compilation fixture.

    The fixture contains two separate charla session covers (P1 and P3).
    P2 is a continuation page that shares the form header but lacks the
    'nombre de la charla' anchor — so min_match=2 fires only on covers.
    """
    skip_unless_present(fixture_pdf(_SIGLA), "Charla")

    gt = load_gt(_SIGLA)
    scanner = AnchorsScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"Charla cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


@pytest.mark.skip(
    reason="Fixture engineered against the truncated anchor set "
    "(pre anchor-truncation postmortem 2026-05-22); awaiting fixture rebuild "
    "aligned to spec-verbatim anchors. Fase A calibration on the real ABRIL "
    "corpus is the active validation. See "
    "docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md."
)
def test_charla_count_ocr_per_file_breakdown():
    """per_file entry for the charla fixture PDF carries the GT count."""
    skip_unless_present(fixture_pdf(_SIGLA), "Charla")

    gt = load_gt(_SIGLA)
    scanner = AnchorsScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file, (
        f"Expected '{name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[name] == gt["covers_expected"]
