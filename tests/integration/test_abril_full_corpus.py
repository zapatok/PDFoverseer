"""Integration: scan the real ABRIL corpus and assert known counts/flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.orchestrator import enumerate_month, scan_month
from core.scanners.base import ConfidenceLevel

ABRIL = Path("A:/informe mensual/ABRIL")


@pytest.mark.slow
def test_abril_full_corpus_yields_54_cells():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    assert len(results) == 54


@pytest.mark.slow
def test_abril_hpv_art_high_count():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    r = results[("HPV", "art")]
    # 2026-05-11 corpus snapshot has ~767; bound liberally
    assert 700 <= r.count <= 900
    assert r.confidence == ConfidenceLevel.HIGH


@pytest.mark.slow
def test_abril_known_compilations_flagged():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    assert "compilation_suspect" in results[("HRB", "odi")].flags
    assert "compilation_suspect" in results[("HLU", "odi")].flags


@pytest.mark.slow
def test_abril_empty_categories_return_zero():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # 18.-CHPS for HRB and HLU is empty in 2026-05-11 snapshot
    assert results[("HRB", "chps")].count == 0
    assert results[("HLU", "chps")].count == 0
