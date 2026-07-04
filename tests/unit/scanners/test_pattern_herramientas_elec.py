"""Smoke tests for the herramientas_elec pagination patterns (Task 5.11;
migrated from AnchorsScanner in Fase 7 test hardening — E8/E9).

Three OCR-verified flavors:
  f_lch_xx  — CRS standard template (F-CRS-LCH family).  Standalone covers.
  f_hll_17  — HLL proprietary form REG-SSO-HLL-17.  Standalone covers.
  f_titan   — TITAN contractor proprietary template (TN-SGSSO-RG family).

Shadow-fixture caveat: f_lch_xx_shadow_epp is a 2-page EPP checklist
(F-CRS-LCH-02) misfiled in the herramientas_elec folder. Under AnchorsScanner
this yielded 0 covers because an anti-anchor ('chequeo de elementos')
rejected both pages. PaginationScanner has no anti-anchor / content-matching
mechanism — cover_code is its only sigla discriminator, and herramientas_elec
has no cover_code — so it counts purely from the pagination text in the page
corner, regardless of which sigla's folder the PDF sits in. If this fixture's
pages carry real 'Página N de M' markers, the migrated assertion below may
FAIL; that would be a genuine product finding (misfiled documents are no
longer rejected for pagination-migrated siglas), not a broken test — see the
Fase 7 plan's NUANCES for Task 7.1.

Fixtures (gitignored): tests/fixtures/scanners/herramientas_elec/*.pdf
Ground truth (committed): tests/fixtures/scanners/herramientas_elec/ground_truth.json
"""

from __future__ import annotations

import pytest

from core.scanners.cancellation import CancellationToken
from core.scanners.pagination_scanner import PaginationScanner
from tests.unit.scanners.fixture_gt import fixture_covers, fixture_dir, load_gt

_SIGLA = "herramientas_elec"
_DIR = fixture_dir(_SIGLA)

_LCH_PDF = _DIR / "f_lch_xx_p1p3_extensiones.pdf"
_HLL_PDF = _DIR / "f_hll_17_p1p2_herr_hll.pdf"
_TITAN_PDF = _DIR / "f_titan_p1p2_martillo_tronzadora.pdf"
_SHADOW_PDF = _DIR / "f_lch_xx_shadow_epp.pdf"


# ---------------------------------------------------------------------------
# f_lch_xx flavor
# ---------------------------------------------------------------------------


def test_herramientas_elec_lch_xx_smoke():
    """f_lch_xx fixture: scanner uses method 'pagination'."""
    if not _LCH_PDF.exists():
        pytest.skip("herramientas_elec f_lch_xx fixture not present (gitignored)")

    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"


def test_herramientas_elec_lch_xx_count():
    """f_lch_xx fixture reports 3 covers."""
    if not _LCH_PDF.exists():
        pytest.skip("herramientas_elec f_lch_xx fixture not present (gitignored)")

    expected = fixture_covers(_SIGLA, _LCH_PDF.name)
    scanner = PaginationScanner(sigla=_SIGLA)
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

    expected = fixture_covers(_SIGLA, _HLL_PDF.name)
    scanner = PaginationScanner(sigla=_SIGLA)
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


def test_herramientas_elec_titan_count():
    """f_titan fixture reports 2 covers (TITAN TN-SGSSO-RG proprietary form)."""
    if not _TITAN_PDF.exists():
        pytest.skip("herramientas_elec f_titan fixture not present (gitignored)")

    expected = fixture_covers(_SIGLA, _TITAN_PDF.name)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert _TITAN_PDF.name in result.per_file, (
        f"Expected {_TITAN_PDF.name!r} in per_file; got keys={list(result.per_file)}"
    )
    assert result.per_file[_TITAN_PDF.name] == expected, (
        f"f_titan cover count: got {result.per_file[_TITAN_PDF.name]}, expected {expected}. "
        f"errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Shadow fixture (EPP misfiled) — see module docstring caveat
# ---------------------------------------------------------------------------


def test_herramientas_elec_shadow_epp_anti_anchor_rejects():
    """EPP misfiled in herramientas_elec folder: GT says 0 covers.

    Under AnchorsScanner this was enforced by an anti-anchor. PaginationScanner
    has no equivalent mechanism (see module docstring) — a FAILURE here signals
    a real product gap, not a stale test.
    """
    if not _SHADOW_PDF.exists():
        pytest.skip("herramientas_elec EPP shadow fixture not present (gitignored)")

    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    got = result.per_file.get(_SHADOW_PDF.name, -1)
    assert got == 0, (
        f"Anti-anchor semantics must reject EPP pages → 0 covers, got {got}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def test_herramientas_elec_total_count():
    """Total across all 4 fixtures: 3 + 2 + 2 + 0 = 7 covers."""
    all_present = (
        _LCH_PDF.exists() and _HLL_PDF.exists() and _TITAN_PDF.exists() and _SHADOW_PDF.exists()
    )
    if not all_present:
        pytest.skip("one or more herramientas_elec fixtures not present (gitignored)")

    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    gt = load_gt(_SIGLA)
    total_expected = sum(e["covers_expected"] for e in gt["fixtures"])
    assert result.count == total_expected, (
        f"Total cover count: got {result.count}, expected {total_expected}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"
