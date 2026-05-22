"""Smoke tests for the herramientas_elec anchor patterns (Task 5.11).

Two OCR-verified flavors:
  f_lch_xx  — CRS standard template (F-CRS-LCH family).  Standalone covers
               recognised by 'constructora region sur' + 'pagina 1 de'.
  f_hll_17  — HLL proprietary form REG-SSO-HLL-17.  Recognised by
               'reg sso hll 17' + 'chequeo de herramientas'.

A7-lock shadow: the EPP fixture is a 1-page PDF.  Decision A7 fires before
OCR: single-page PDFs are always counted as 1 document (trivial lock).
Anti-anchors only apply to multi-page PDFs where OCR is actually run.
The EPP fixture therefore counts as 1 cover — this is expected, correct
behavior, not a false positive.

Fixtures (gitignored): tests/fixtures/scanners/herramientas_elec/*.pdf
Ground truth (committed): tests/fixtures/scanners/herramientas_elec/ground_truth.json
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

_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "herramientas_elec"
_GT = _DIR / "ground_truth.json"

_LCH_PDF = _DIR / "f_lch_xx_p1p3_extensiones.pdf"
_HLL_PDF = _DIR / "f_hll_17_p1p2_herr_hll.pdf"
_SHADOW_PDF = _DIR / "f_lch_xx_shadow_epp.pdf"


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


def test_herramientas_elec_lch_xx_smoke():
    """f_lch_xx fixture: 3 standalone covers in a 3-page extensiones PDF."""
    if not _LCH_PDF.exists():
        pytest.skip("herramientas_elec f_lch_xx fixture not present (gitignored)")

    scanner = AnchorsScanner(sigla="herramientas_elec")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )


def test_herramientas_elec_lch_xx_count():
    """f_lch_xx fixture reports 3 covers."""
    if not _LCH_PDF.exists():
        pytest.skip("herramientas_elec f_lch_xx fixture not present (gitignored)")

    expected = _fixture_covers(_LCH_PDF.name)
    scanner = AnchorsScanner(sigla="herramientas_elec")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    # Verify per_file breakdown for this specific file
    assert _LCH_PDF.name in result.per_file, (
        f"Expected {_LCH_PDF.name!r} in per_file; got keys={list(result.per_file)}"
    )
    assert result.per_file[_LCH_PDF.name] == expected, (
        f"f_lch_xx cover count: got {result.per_file[_LCH_PDF.name]}, expected {expected}. "
        f"errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# f_hll_17 flavor
# ---------------------------------------------------------------------------


def test_herramientas_elec_hll17_count():
    """f_hll_17 fixture reports 2 covers (REG-SSO-HLL-17 proprietary form)."""
    if not _HLL_PDF.exists():
        pytest.skip("herramientas_elec f_hll_17 fixture not present (gitignored)")

    expected = _fixture_covers(_HLL_PDF.name)
    scanner = AnchorsScanner(sigla="herramientas_elec")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert _HLL_PDF.name in result.per_file, (
        f"Expected {_HLL_PDF.name!r} in per_file; got keys={list(result.per_file)}"
    )
    assert result.per_file[_HLL_PDF.name] == expected, (
        f"f_hll_17 cover count: got {result.per_file[_HLL_PDF.name]}, expected {expected}. "
        f"errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Anti-anchor shadow (EPP misfiled)
# ---------------------------------------------------------------------------


def test_herramientas_elec_shadow_epp_a7_counts_one():
    """EPP misfiled in herramientas_elec folder: A7 lock fires (1-page PDF → 1 doc).

    Anti-anchors only apply to multi-page PDFs where OCR is actually run.
    A 1-page PDF is always counted as 1 document by Decision A7, regardless
    of whether its content matches any anchor or anti-anchor pattern.
    """
    if not _SHADOW_PDF.exists():
        pytest.skip("herramientas_elec EPP shadow fixture not present (gitignored)")

    scanner = AnchorsScanner(sigla="herramientas_elec")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    got = result.per_file.get(_SHADOW_PDF.name, 0)
    assert got == 1, (
        f"A7 lock must count single-page EPP as 1 document, got {got}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def test_herramientas_elec_total_count():
    """Total across all 3 fixtures: 3 + 2 + 1 = 6 covers (EPP shadow counted by A7)."""
    if not (_LCH_PDF.exists() and _HLL_PDF.exists() and _SHADOW_PDF.exists()):
        pytest.skip("one or more herramientas_elec fixtures not present (gitignored)")

    scanner = AnchorsScanner(sigla="herramientas_elec")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    gt = _load_gt()
    total_expected = sum(e["covers_expected"] for e in gt["fixtures"])
    assert result.count == total_expected, (
        f"Total cover count: got {result.count}, expected {total_expected}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"
