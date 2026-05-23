"""Smoke tests for the Charla anchor pattern (Task 4.3).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.

The charla fixture (f_rch_p1.pdf) is a 3-page compilation: P1 and P3 are
both session covers, P2 is the attendance/continuation sheet of the first
session.  Expected cover count = 2.
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

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "charla"
_PDF = _FIXTURE_DIR / "f_rch_p1.pdf"
_GT = _FIXTURE_DIR / "ground_truth.json"


def _load_gt() -> dict:
    return json.loads(_GT.read_text())


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
    if not _PDF.exists():
        pytest.skip("Charla fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = AnchorsScanner(sigla="charla")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

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
    """per_file entry for the charla fixture PDF shows count=2."""
    if not _PDF.exists():
        pytest.skip("Charla fixture PDF not present (gitignored)")

    gt = _load_gt()
    scanner = AnchorsScanner(sigla="charla")
    result = scanner.count_ocr(_FIXTURE_DIR, cancel=CancellationToken())

    assert _PDF.name in result.per_file, (
        f"Expected '{_PDF.name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[_PDF.name] == gt["covers_expected"]
