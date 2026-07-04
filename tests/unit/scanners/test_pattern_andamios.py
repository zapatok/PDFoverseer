"""Smoke tests for the andamios pagination patterns (Task 5.12; migrated
from AnchorsScanner in Fase 7 test hardening — E8/E9).

Fixtures exercised:
  f_lch_xx   — CRS standard template (F-CRS-LCH-05), a 4-page slice of a
                9-page compilation with 2 standalone covers.
  f_ribeiro  — RIBEIRO SPA proprietary form, 1 standalone cover.
  f_lch_05_shadow_art — ART armado_titan misfiled in the andamios folder.

Shadow-fixture caveat: under AnchorsScanner this fixture yielded 0 covers
because an anti-anchor ('analisis de riesgos en el trabajo' / 'f crs art')
rejected the page. PaginationScanner has no anti-anchor / content-matching
mechanism — cover_code is its only sigla discriminator, and andamios has no
cover_code — so it counts purely from the pagination text in the page corner,
regardless of which sigla's folder the PDF sits in. If this fixture's pages
carry real 'Página N de M' markers, the migrated assertion below may FAIL;
that would be a genuine product finding (misfiled documents are no longer
rejected for pagination-migrated siglas), not a broken test — see the Fase 7
plan's NUANCES for Task 7.1.

Fixtures (gitignored): tests/fixtures/scanners/andamios/*.pdf
Ground truth (committed): tests/fixtures/scanners/andamios/ground_truth.json
"""

from __future__ import annotations

import pytest

from core.scanners.cancellation import CancellationToken
from core.scanners.pagination_scanner import PaginationScanner
from tests.unit.scanners.fixture_gt import fixture_covers, fixture_dir, load_gt

_SIGLA = "andamios"
_DIR = fixture_dir(_SIGLA)

_LCH_PDF = _DIR / "f_lch_05_p2p5_chequeo_hrb.pdf"
_RIBEIRO_PDF = _DIR / "f_ribeiro_p1_andamios_hrb.pdf"
_SHADOW_PDF = _DIR / "f_lch_05_shadow_art.pdf"


# ---------------------------------------------------------------------------
# f_lch_xx flavor
# ---------------------------------------------------------------------------


def test_andamios_lch_xx_smoke():
    """f_lch_xx fixture: PaginationScanner uses method 'pagination'."""
    if not _LCH_PDF.exists():
        pytest.skip("andamios f_lch_xx fixture not present (gitignored)")

    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert result.method == "pagination", f"Expected method 'pagination', got {result.method!r}"


def test_andamios_lch_xx_count():
    """f_lch_xx fixture: 2 covers in a 4-page compilation (cover+cont+cover+cont)."""
    if not _LCH_PDF.exists():
        pytest.skip("andamios f_lch_xx fixture not present (gitignored)")

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
# f_ribeiro flavor
# ---------------------------------------------------------------------------


def test_andamios_ribeiro_count():
    """f_ribeiro fixture: 1 cover (RIBEIRO SPA proprietary form)."""
    if not _RIBEIRO_PDF.exists():
        pytest.skip("andamios f_ribeiro fixture not present (gitignored)")

    expected = fixture_covers(_SIGLA, _RIBEIRO_PDF.name)
    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    assert _RIBEIRO_PDF.name in result.per_file, (
        f"Expected {_RIBEIRO_PDF.name!r} in per_file; got keys={list(result.per_file)}"
    )
    assert result.per_file[_RIBEIRO_PDF.name] == expected, (
        f"f_ribeiro cover count: got {result.per_file[_RIBEIRO_PDF.name]}, expected {expected}. "
        f"errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Shadow fixture (ART misfiled) — see module docstring caveat
# ---------------------------------------------------------------------------


def test_andamios_shadow_art_yields_zero():
    """ART armado_titan misfiled in andamios folder: GT says 0 covers.

    Under AnchorsScanner this was enforced by an anti-anchor. PaginationScanner
    has no equivalent mechanism (see module docstring) — a FAILURE here signals
    a real product gap, not a stale test.
    """
    if not _SHADOW_PDF.exists():
        pytest.skip("andamios ART shadow fixture not present (gitignored)")

    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    got = result.per_file.get(_SHADOW_PDF.name, 0)
    assert got == 0, (
        f"ART shadow must yield 0 covers, got {got}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def test_andamios_total_count():
    """Total across all 3 fixtures: 2 + 1 + 0 = 3 covers."""
    if not (_LCH_PDF.exists() and _RIBEIRO_PDF.exists() and _SHADOW_PDF.exists()):
        pytest.skip("one or more andamios fixtures not present (gitignored)")

    scanner = PaginationScanner(sigla=_SIGLA)
    result = scanner.count_ocr(_DIR, cancel=CancellationToken())

    gt = load_gt(_SIGLA)
    total_expected = sum(e["covers_expected"] for e in gt["fixtures"])
    assert result.count == total_expected, (
        f"Total cover count: got {result.count}, expected {total_expected}. "
        f"per_file={result.per_file!r}  errors={result.errors!r}"
    )
    assert result.confidence.value == "high"
