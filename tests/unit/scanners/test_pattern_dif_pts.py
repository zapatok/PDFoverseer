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

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken
from tests.unit.scanners.fixture_gt import fixture_dir, load_gt, skip_unless_present

_RCH = "dif_pts/f_rch"
_RCH_PDF = fixture_dir(_RCH) / "f_rch_p1_standalone.pdf"

_CH_CRS_01 = "dif_pts/f_ch_crs_01"
_CH_CRS_01_PDF = fixture_dir(_CH_CRS_01) / "f_ch_crs_01_2p_cover_shadow.pdf"

_AGUASAN = "dif_pts/f_aguasan"
_AGUASAN_PDF = fixture_dir(_AGUASAN) / "f_aguasan_p1_extintor.pdf"


# ---------------------------------------------------------------------------
# f_rch flavor
# ---------------------------------------------------------------------------


def test_dif_pts_rch_smoke():
    """AnchorsScanner detects 1 cover in the standalone RCH dif_pts fixture."""
    skip_unless_present(_RCH_PDF, "dif_pts RCH")

    gt = load_gt(_RCH)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(fixture_dir(_RCH), cancel=CancellationToken())

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
    skip_unless_present(_RCH_PDF, "dif_pts RCH")

    gt = load_gt(_RCH)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(fixture_dir(_RCH), cancel=CancellationToken())

    assert _RCH_PDF.name in result.per_file
    assert result.per_file[_RCH_PDF.name] == gt["covers_expected"]


# ---------------------------------------------------------------------------
# f_ch_crs_01 flavor — real cover + shadow anti-anchor test
# ---------------------------------------------------------------------------


def test_dif_pts_ch_crs_01_smoke():
    """AnchorsScanner detects exactly 1 cover in the 2-page cover+shadow fixture.

    Page 0 is a real charla cover; page 1 is a 'test de comprension' shadow page.
    The shadow must be rejected by anti_anchors so the count is 1, not 2.
    """
    skip_unless_present(_CH_CRS_01_PDF, "dif_pts f_ch_crs_01")

    gt = load_gt(_CH_CRS_01)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(fixture_dir(_CH_CRS_01), cancel=CancellationToken())

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
    """The 2-page fixture returns exactly the GT count — shadow page is anti-anchor blocked."""
    skip_unless_present(_CH_CRS_01_PDF, "dif_pts f_ch_crs_01")

    gt = load_gt(_CH_CRS_01)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(fixture_dir(_CH_CRS_01), cancel=CancellationToken())

    # The fixture has 2 pages; only the real cover should be counted.
    assert result.per_file.get(_CH_CRS_01_PDF.name, -1) == gt["covers_expected"], (
        f"Shadow page must be rejected; expected per_file count="
        f"{gt['covers_expected']}, got {result.per_file!r}"
    )


def test_dif_pts_ch_crs_01_per_file():
    """per_file breakdown is correct for the f_ch_crs_01 fixture."""
    skip_unless_present(_CH_CRS_01_PDF, "dif_pts f_ch_crs_01")

    gt = load_gt(_CH_CRS_01)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(fixture_dir(_CH_CRS_01), cancel=CancellationToken())

    assert _CH_CRS_01_PDF.name in result.per_file
    assert result.per_file[_CH_CRS_01_PDF.name] == gt["covers_expected"]


# ---------------------------------------------------------------------------
# f_aguasan flavor
# ---------------------------------------------------------------------------


def test_dif_pts_aguasan_smoke():
    """AnchorsScanner detects 1 cover in the AGUASAN dif_pts fixture."""
    skip_unless_present(_AGUASAN_PDF, "dif_pts AGUASAN")

    gt = load_gt(_AGUASAN)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(fixture_dir(_AGUASAN), cancel=CancellationToken())

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
    skip_unless_present(_AGUASAN_PDF, "dif_pts AGUASAN")

    gt = load_gt(_AGUASAN)
    scanner = AnchorsScanner(sigla="dif_pts")
    result = scanner.count_ocr(fixture_dir(_AGUASAN), cancel=CancellationToken())

    assert _AGUASAN_PDF.name in result.per_file
    assert result.per_file[_AGUASAN_PDF.name] == gt["covers_expected"]
