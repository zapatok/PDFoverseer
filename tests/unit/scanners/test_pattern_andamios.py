"""Smoke tests for the andamios anchor patterns (Task 5.12).

Two OCR-verified flavors:
  f_lch_xx   — CRS standard template (F-CRS-LCH-05).  Cover pages in a
                multi-form compilation recognised by 'lista de chequeo de
                andamios' + 'datos del andamio' + 'pagina 1 de' (min_match=2).
  f_ribeiro  — RIBEIRO SPA proprietary form.  Recognised by 'linea de
                negocio' + 'inspeccion de andamios' + 'ribeiro' (min_match=2).

Anti-anchor shadow: ART armado_titan misfiled in the andamios folder must
yield 0 covers (ART pages naturally fail andamios anchor matching).

Fixtures (gitignored): tests/fixtures/scanners/andamios/*.pdf
Ground truth (committed): tests/fixtures/scanners/andamios/ground_truth.json
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

_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "andamios"
_GT = _DIR / "ground_truth.json"

_LCH_PDF = _DIR / "f_lch_05_p2p5_chequeo_hrb.pdf"
_RIBEIRO_PDF = _DIR / "f_ribeiro_p1_andamios_hrb.pdf"
_SHADOW_PDF = _DIR / "f_lch_05_shadow_art.pdf"


def _load_gt() -> dict:
    return json.loads(_GT.read_text())


def _fixture_covers(filename: str) -> int:
    gt = _load_gt()
    for entry in gt["fixtures"]:
        if entry["file"] == filename:
            return entry["covers_expected"]
    raise KeyError(f"fixture not found in ground_truth.json: {filename!r}")


# ---------------------------------------------------------------------------
# f_lch_xx flavor
# ---------------------------------------------------------------------------


def test_andamios_lch_xx_smoke():
    """f_lch_xx fixture: AnchorsScanner uses header_band_anchors method."""
    if not _LCH_PDF.exists():
        pytest.skip("andamios f_lch_xx fixture not present (gitignored)")

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )


@pytest.mark.skip(
    reason="Fixture engineered against the truncated anchor set "
    "(pre anchor-truncation postmortem 2026-05-22); awaiting fixture rebuild "
    "aligned to spec-verbatim anchors. Fase A calibration on the real ABRIL "
    "corpus is the active validation. See "
    "docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md."
)
def test_andamios_lch_xx_count():
    """f_lch_xx fixture: 2 covers in a 4-page compilation (cover+cont+cover+cont)."""
    if not _LCH_PDF.exists():
        pytest.skip("andamios f_lch_xx fixture not present (gitignored)")

    expected = _fixture_covers(_LCH_PDF.name)
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert _LCH_PDF.name in result.per_file, (
        f"Expected {_LCH_PDF.name!r} in per_file; got keys={list(result.per_file)}"
    )
    assert result.per_file[_LCH_PDF.name] == expected, (
        f"f_lch_xx cover count: got {result.per_file[_LCH_PDF.name]}, expected {expected}. "
        f"errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# f_ribeiro flavor
# ---------------------------------------------------------------------------


def test_andamios_ribeiro_count():
    """f_ribeiro fixture: 1 cover (RIBEIRO SPA proprietary form)."""
    if not _RIBEIRO_PDF.exists():
        pytest.skip("andamios f_ribeiro fixture not present (gitignored)")

    expected = _fixture_covers(_RIBEIRO_PDF.name)
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert _RIBEIRO_PDF.name in result.per_file, (
        f"Expected {_RIBEIRO_PDF.name!r} in per_file; got keys={list(result.per_file)}"
    )
    assert result.per_file[_RIBEIRO_PDF.name] == expected, (
        f"f_ribeiro cover count: got {result.per_file[_RIBEIRO_PDF.name]}, expected {expected}. "
        f"errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Anti-anchor shadow (ART misfiled)
# ---------------------------------------------------------------------------


def test_andamios_shadow_art_yields_zero():
    """ART armado_titan misfiled in andamios folder must yield 0 covers."""
    if not _SHADOW_PDF.exists():
        pytest.skip("andamios ART shadow fixture not present (gitignored)")

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    got = result.per_file.get(_SHADOW_PDF.name, 0)
    assert got == 0, (
        f"ART shadow must yield 0 covers, got {got}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="Fixture engineered against the truncated anchor set "
    "(pre anchor-truncation postmortem 2026-05-22); awaiting fixture rebuild "
    "aligned to spec-verbatim anchors. Fase A calibration on the real ABRIL "
    "corpus is the active validation. See "
    "docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md."
)
def test_andamios_total_count():
    """Total across all 3 fixtures: 2 + 1 + 0 = 3 covers."""
    if not (_LCH_PDF.exists() and _RIBEIRO_PDF.exists() and _SHADOW_PDF.exists()):
        pytest.skip("one or more andamios fixtures not present (gitignored)")

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    gt = _load_gt()
    total_expected = sum(e["covers_expected"] for e in gt["fixtures"])
    assert result.count == total_expected, (
        f"Total cover count: got {result.count}, expected {total_expected}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"
