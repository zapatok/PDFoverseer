"""Smoke tests for the maquinaria anchor pattern (Task 5.5).

These tests run Tesseract against real fixture PDFs.  When the fixture is
absent (gitignored), the test is skipped — not failed.  This keeps CI green.
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

_SIGLA = "maquinaria"


@pytest.mark.skip(
    reason="Fixture engineered against the truncated anchor set "
    "(pre anchor-truncation postmortem 2026-05-22); awaiting fixture rebuild "
    "aligned to spec-verbatim anchors. Fase A calibration on the real ABRIL "
    "corpus is the active validation. See "
    "docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md."
)
def test_maquinaria_count_ocr_smoke():
    """AnchorsScanner returns the expected cover count for the maquinaria fixture."""
    skip_unless_present(fixture_pdf(_SIGLA), _SIGLA)

    gt = load_gt(_SIGLA)
    scanner = AnchorsScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"maquinaria cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )


@pytest.mark.skip(
    reason="Fixture engineered against the truncated anchor set "
    "(pre anchor-truncation postmortem 2026-05-22); awaiting fixture rebuild "
    "aligned to spec-verbatim anchors. Fase A calibration on the real ABRIL "
    "corpus is the active validation. See "
    "docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md."
)
def test_maquinaria_count_ocr_per_file_breakdown():
    """per_file entry exists for the fixture PDF and carries the GT count."""
    skip_unless_present(fixture_pdf(_SIGLA), _SIGLA)

    gt = load_gt(_SIGLA)
    scanner = AnchorsScanner(sigla=_SIGLA)
    result = scanner.count_ocr(fixture_dir(_SIGLA), cancel=CancellationToken())

    name = gt["fixture"]
    assert name in result.per_file, (
        f"Expected '{name}' in per_file, got keys: {list(result.per_file)}"
    )
    assert result.per_file[name] == gt["covers_expected"]
