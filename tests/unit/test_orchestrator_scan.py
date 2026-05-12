"""Tests for scan_cell and scan_month orchestrator functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.orchestrator import enumerate_month, scan_cell, scan_month
from core.scanners.base import ConfidenceLevel  # noqa: F401 (used by callers)

ABRIL = Path("A:/informe mensual/ABRIL")


def test_scan_cell_hpv_art_returns_count():
    inv = enumerate_month(ABRIL)
    cell = next(c for c in inv.cells["HPV"] if c.sigla == "art")
    result = scan_cell(cell)
    assert result.count > 0
    assert result.method == "filename_glob"


def test_scan_month_returns_result_per_cell():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # 3 hospitals × 18 cats = 54 cells
    assert len(results) == 54
    # All have a count (possibly zero)
    for (hosp, sigla), r in results.items():
        assert r.count >= 0


def test_scan_month_flags_known_compilations():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # HRB ODI and HLU ODI are known compilations
    assert "compilation_suspect" in results[("HRB", "odi")].flags
    assert "compilation_suspect" in results[("HLU", "odi")].flags
