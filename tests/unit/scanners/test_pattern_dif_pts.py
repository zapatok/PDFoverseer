"""Smoke tests for the dif_pts anchor patterns (Task 5.2).

Three flavors, with anti-anchor support:
- f_rch: standalone RCH charla sheets ("f crs rch 01" + "pagina 1 de 1")
- f_ch_crs_01: HLL compilation format — real covers vs shadow "test de comprension"
  pages rejected via anti_anchors ("alternativa correcta", "test de comprension")
- f_aguasan: AGUASAN contractor variant ("tema tratado" + "seleccione")

top_fraction=1/3 is applied at the sigla level (dif_pts forms use the upper third).

The f_ch_crs_01 fixture is a 2-page PDF: page 0 is a real cover, page 1 is a
shadow test-de-comprension page.  The scanner must return count=1 (not 2).

When a fixture PDF is absent (gitignored), the test is skipped — not failed.
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

_BASE = Path(__file__).parent.parent.parent / "fixtures" / "scanners" / "dif_pts"

_RCH_DIR = _BASE / "f_rch"
_RCH_PDF = _RCH_DIR / "f_rch_p1_standalone.pdf"

_CH_CRS_01_DIR = _BASE / "f_ch_crs_01"
_CH_CRS_01_PDF = _CH_CRS_01_DIR / "f_ch_crs_01_2p_cover_shadow.pdf"

_AGUASAN_DIR = _BASE / "f_aguasan"
_AGUASAN_PDF = _AGUASAN_DIR / "f_aguasan_p1_extintor.pdf"


def _gt(subdir: Path) -> dict:
    return json.loads((subdir / "ground_truth.json").read_text())


# ---------------------------------------------------------------------------
# f_rch flavor
# ---------------------------------------------------------------------------


def test_dif_pts_rch_smoke():
    """AnchorsScanner detects 1 cover in the standalone RCH dif_pts fixture."""
    if not _RCH_PDF.exists():
        pytest.skip("dif_pts RCH fixture PDF not present (gitignored)")

    gt = _gt(_RCH_DIR)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(_RCH_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"RCH cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_dif_pts_rch_per_file():
    """per_file breakdown is correct for the RCH fixture."""
    if not _RCH_PDF.exists():
        pytest.skip("dif_pts RCH fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(_RCH_DIR, cancel=CancellationToken())

    assert _RCH_PDF.name in result.per_file
    assert result.per_file[_RCH_PDF.name] == 1


# ---------------------------------------------------------------------------
# f_ch_crs_01 flavor — real cover + shadow anti-anchor test
# ---------------------------------------------------------------------------


def test_dif_pts_ch_crs_01_smoke():
    """AnchorsScanner detects exactly 1 cover in the 2-page cover+shadow fixture.

    Page 0 is a real charla cover; page 1 is a 'test de comprension' shadow page.
    The shadow must be rejected by anti_anchors so the count is 1, not 2.
    """
    if not _CH_CRS_01_PDF.exists():
        pytest.skip("dif_pts f_ch_crs_01 fixture PDF not present (gitignored)")

    gt = _gt(_CH_CRS_01_DIR)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(_CH_CRS_01_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"f_ch_crs_01 cover count mismatch: got {result.count}, "
        f"expected {gt['covers_expected']} (shadow page must be rejected). "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_dif_pts_ch_crs_01_shadow_rejected():
    """The 2-page fixture returns exactly 1 — shadow page is anti-anchor blocked."""
    if not _CH_CRS_01_PDF.exists():
        pytest.skip("dif_pts f_ch_crs_01 fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(_CH_CRS_01_DIR, cancel=CancellationToken())

    # The fixture has 2 pages; only 1 should be counted as a cover.
    assert result.per_file.get(_CH_CRS_01_PDF.name, -1) == 1, (
        f"Shadow page must be rejected; expected per_file count=1, got {result.per_file!r}"
    )


def test_dif_pts_ch_crs_01_per_file():
    """per_file breakdown is correct for the f_ch_crs_01 fixture."""
    if not _CH_CRS_01_PDF.exists():
        pytest.skip("dif_pts f_ch_crs_01 fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(_CH_CRS_01_DIR, cancel=CancellationToken())

    assert _CH_CRS_01_PDF.name in result.per_file
    assert result.per_file[_CH_CRS_01_PDF.name] == 1


# ---------------------------------------------------------------------------
# f_aguasan flavor
# ---------------------------------------------------------------------------


def test_dif_pts_aguasan_smoke():
    """AnchorsScanner detects 1 cover in the AGUASAN dif_pts fixture."""
    if not _AGUASAN_PDF.exists():
        pytest.skip("dif_pts AGUASAN fixture PDF not present (gitignored)")

    gt = _gt(_AGUASAN_DIR)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(_AGUASAN_DIR, cancel=CancellationToken())

    assert result.method == "header_band_anchors", (
        f"Expected method 'header_band_anchors', got {result.method!r}"
    )
    assert result.count == gt["covers_expected"], (
        f"AGUASAN cover count mismatch: got {result.count}, expected {gt['covers_expected']}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"


def test_dif_pts_aguasan_per_file():
    """per_file breakdown is correct for the AGUASAN fixture."""
    if not _AGUASAN_PDF.exists():
        pytest.skip("dif_pts AGUASAN fixture PDF not present (gitignored)")

    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(_AGUASAN_DIR, cancel=CancellationToken())

    assert _AGUASAN_PDF.name in result.per_file
    assert result.per_file[_AGUASAN_PDF.name] == 1
