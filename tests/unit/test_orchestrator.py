from pathlib import Path

from core.orchestrator import enumerate_month

ABRIL = Path("A:/informe mensual/ABRIL")


def test_enumerate_month_returns_4_hospitals():
    inv = enumerate_month(ABRIL)
    assert sorted(inv.hospitals_present) == ["HLU", "HPV", "HRB"]  # HLL not normalized
    assert "HLL" in inv.hospitals_missing


def test_enumerate_month_populates_18_categories_per_hospital():
    inv = enumerate_month(ABRIL)
    for hosp in ("HPV", "HRB", "HLU"):
        assert len(inv.cells[hosp]) == 18


def test_enumerate_month_returns_zero_for_missing_category(tmp_path):
    (tmp_path / "HPV").mkdir()  # empty hospital folder
    inv = enumerate_month(tmp_path)
    assert "HPV" in inv.hospitals_present
    # all 18 categories should be present (as missing folders)
    assert len(inv.cells["HPV"]) == 18
