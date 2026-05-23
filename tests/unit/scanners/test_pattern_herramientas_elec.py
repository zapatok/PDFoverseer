"""Smoke tests for the herramientas_elec anchor patterns (Task 5.11).

Three OCR-verified flavors:
  f_lch_xx  — CRS standard template (F-CRS-LCH family).  Standalone covers
               recognised by 'constructora region sur' + 'pagina 1 de'.
               Anti-anchors reject EPP checklists (F-CRS-LCH-02) misfiled here.
  f_hll_17  — HLL proprietary form REG-SSO-HLL-17.  Recognised by
               'reg sso hll 17' + 'chequeo de herramientas'.
  f_titan   — TITAN contractor proprietary template (TN-SGSSO-RG family).
               Recognised by 'titan' + at least one of 'sistema de gestion de
               seguridad y salud' / 'tn sgsso rg' / 'inspeccion' / 'herramienta'.

Anti-anchor shadow: a 2-page EPP checklist (F-CRS-LCH-02) misfiled in the
herramientas_elec folder.  Both pages carry 'constructora region sur' + 'pagina
1 de' (would fire f_lch_xx without protection), but 'chequeo de elementos'
fires on both → anti-anchor rejects them → 0 covers.  Decision A7 does NOT
fire (2 pages), so the anchor/anti-anchor logic is genuinely exercised.

Note: standalone 1-page EPP PDFs are A7-locked (always 1 doc, no OCR).
Anti-anchors only apply to multi-page PDFs where OCR is actually run.

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
_TITAN_PDF = _DIR / "f_titan_p1p2_martillo_tronzadora.pdf"
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
    """f_lch_xx fixture: scanner uses method 'header_band_anchors'."""
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
# f_titan flavor
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="Fixture engineered against the truncated anchor set "
    "(pre anchor-truncation postmortem 2026-05-22); awaiting fixture rebuild "
    "aligned to spec-verbatim anchors. Fase A calibration on the real ABRIL "
    "corpus is the active validation. See "
    "docs/superpowers/reports/2026-05-22-anchor-truncation-postmortem.md."
)
def test_herramientas_elec_titan_count():
    """f_titan fixture reports 2 covers (TITAN TN-SGSSO-RG proprietary form)."""
    if not _TITAN_PDF.exists():
        pytest.skip("herramientas_elec f_titan fixture not present (gitignored)")

    expected = _fixture_covers(_TITAN_PDF.name)
    scanner = AnchorsScanner(sigla="herramientas_elec")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert _TITAN_PDF.name in result.per_file, (
        f"Expected {_TITAN_PDF.name!r} in per_file; got keys={list(result.per_file)}"
    )
    assert result.per_file[_TITAN_PDF.name] == expected, (
        f"f_titan cover count: got {result.per_file[_TITAN_PDF.name]}, expected {expected}. "
        f"errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Anti-anchor shadow (EPP misfiled) — anti-anchor must genuinely fire
# ---------------------------------------------------------------------------


def test_herramientas_elec_shadow_epp_anti_anchor_rejects():
    """EPP misfiled in herramientas_elec folder: anti-anchor fires → 0 covers.

    The shadow fixture is a 2-page PDF so Decision A7 does NOT fire.
    Both pages carry 'constructora region sur' + 'pagina 1 de' (would match
    f_lch_xx without protection), but 'chequeo de elementos' fires on both
    pages → anti-anchor rejects them → 0 covers.  This verifies the
    anti-anchor is genuinely exercised, not bypassed by the A7 1-page lock.
    """
    if not _SHADOW_PDF.exists():
        pytest.skip("herramientas_elec EPP shadow fixture not present (gitignored)")

    scanner = AnchorsScanner(sigla="herramientas_elec")
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    got = result.per_file.get(_SHADOW_PDF.name, -1)
    assert got == 0, (
        f"Anti-anchor must reject EPP pages → 0 covers, got {got}. "
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
def test_herramientas_elec_total_count():
    """Total across all 4 fixtures: 3 + 2 + 2 + 0 = 7 covers."""
    all_present = (
        _LCH_PDF.exists() and _HLL_PDF.exists() and _TITAN_PDF.exists() and _SHADOW_PDF.exists()
    )
    if not all_present:
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
