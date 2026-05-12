from pathlib import Path

from core.scanners.utils.filename_glob import count_pdfs_by_sigla, per_empresa_breakdown

# Real fixtures from ABRIL HPV
ABRIL_ROOT = Path("A:/informe mensual/ABRIL")


def test_count_art_in_hpv():
    folder = ABRIL_ROOT / "HPV" / "7.-ART"
    result = count_pdfs_by_sigla(folder, sigla="art")
    # HPV ART has ~767 PDFs across 13 empresa subfolders as of 2026-05-11 audit
    # We don't pin to 767 exactly (corpus may evolve); just bound it
    assert 700 <= result.count <= 900
    assert result.method == "filename_glob"


def test_count_zero_when_folder_empty(tmp_path):
    empty = tmp_path / "1.-Reunion Prevencion 0"
    empty.mkdir()
    result = count_pdfs_by_sigla(empty, sigla="reunion")
    assert result.count == 0


def test_count_zero_when_folder_missing(tmp_path):
    missing = tmp_path / "doesnotexist"
    result = count_pdfs_by_sigla(missing, sigla="reunion")
    assert result.count == 0
    assert "folder_missing" in result.flags


def test_per_empresa_breakdown_for_hpv_art():
    folder = ABRIL_ROOT / "HPV" / "7.-ART"
    breakdown = per_empresa_breakdown(folder)
    # 13 empresa subfolders exist (AGUASAN, ALUMINIO 2000, ARAYA, FLEISHMANN, HU,
    # JAPA, JJC, KOHLER, MMG, RACO, REALI, STI, TITAN).
    # CRS files live flat in the parent, not in a subfolder.
    assert len(breakdown) >= 5
    assert any("JJC" in name.upper() or "TITAN" in name.upper() for name in breakdown)
