from pathlib import Path

from core.domain import SIGLAS
from core.scanners import all_siglas, get
from core.scanners.base import ConfidenceLevel
from core.scanners.simple_factory import make_simple_scanner

ABRIL = Path("A:/informe mensual/ABRIL")


def test_all_18_siglas_registered():
    registered = set(all_siglas())
    assert set(SIGLAS) <= registered


def test_simple_scanner_counts_correctly_in_hpv_art():
    scanner = get("art")
    result = scanner.count(ABRIL / "HPV" / "7.-ART")
    assert result.count > 0
    assert result.confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
    assert result.method == "filename_glob"


def test_simple_scanner_handles_missing_folder(tmp_path):
    scanner = get("reunion")
    result = scanner.count(tmp_path / "does_not_exist")
    assert result.count == 0
    assert "folder_missing" in result.flags


def test_simple_scanner_flags_compilation_in_hrb_odi():
    scanner = get("odi")
    result = scanner.count(ABRIL / "HRB" / "3.-ODI Visitas")
    # Count is 1 (the compilation PDF) but flag must be set
    assert "compilation_suspect" in result.flags


def test_factory_builds_independently():
    scanner = make_simple_scanner("art")
    assert scanner.sigla == "art"
