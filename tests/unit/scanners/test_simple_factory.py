from pathlib import Path

import pytest

from core.domain import SIGLAS
from core.scanners import all_siglas, get
from core.scanners.base import ConfidenceLevel
from core.scanners.simple_factory import make_simple_scanner

ABRIL = Path("A:/informe mensual/ABRIL")


def test_all_siglas_registered():
    registered = set(all_siglas())
    assert set(SIGLAS) <= registered


@pytest.mark.corpus
def test_simple_scanner_counts_correctly_in_hpv_art():
    scanner = get("art")
    result = scanner.count(ABRIL / "HPV" / "7.-ART")
    assert result.count > 0
    # ART forms are multi-page (multi-worker sheets) and ART is NOT a fixed-page
    # sigla, so the honest pase-1 rule reports LOW — the filename count is a
    # guess until OCR/confirm verifies it (conteo-confiable spec, Tema A1).
    assert result.confidence == ConfidenceLevel.LOW
    assert result.method == "filename_glob"


def test_simple_scanner_handles_missing_folder(tmp_path):
    scanner = get("reunion")
    result = scanner.count(tmp_path / "does_not_exist")
    assert result.count == 0
    assert "folder_missing" in result.flags


@pytest.mark.corpus
def test_simple_scanner_flags_compilation_in_hrb_odi():
    scanner = get("odi")
    result = scanner.count(ABRIL / "HRB" / "3.-ODI Visitas")
    # Count is 1 (the compilation PDF) but flag must be set
    assert "compilation_suspect" in result.flags


def test_factory_builds_independently():
    scanner = make_simple_scanner("art")
    assert scanner.sigla == "art"


def test_simple_scanner_chps_folder_scope(tmp_path):
    """F14 — chps's SimpleFilenameScanner resolves per-file paths for every
    PDF in the folder (folder count_scope), not just token-matching ones."""
    (tmp_path / "crs.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "titan.pdf").write_bytes(b"%PDF\n%%EOF")

    scanner = get("chps")
    result = scanner.count(tmp_path)

    assert result.count == 2
    assert set(result.per_file) == {"crs.pdf", "titan.pdf"}


# F10 — duplicate-basename detection.
def test_simple_scanner_flags_duplicate_basenames(tmp_path):
    (tmp_path / "AGUASAN").mkdir()
    (tmp_path / "AGUASAN" / "2026-04-15_art_x.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "TITAN").mkdir()
    (tmp_path / "TITAN" / "2026-04-15_art_x.pdf").write_bytes(b"%PDF\n%%EOF")

    scanner = get("art")
    result = scanner.count(tmp_path)

    assert "duplicate_basenames" in result.flags


def test_simple_scanner_no_duplicate_flag_in_flat_folder(tmp_path):
    (tmp_path / "2026-04-15_art_a.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-04-15_art_b.pdf").write_bytes(b"%PDF\n%%EOF")

    scanner = get("art")
    result = scanner.count(tmp_path)

    assert "duplicate_basenames" not in result.flags


def test_pase1_telemetry_carries_filename_suspects(tmp_path):
    """Anti-colados V1: a foreign-named file in the folder surfaces as a
    telemetry suspect; present_files carries every PDF (for downstream eviction).
    Detection never changes the count (host art: only the art file counts)."""
    (tmp_path / "2026-05-04_art_a.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "2026-05-04_odi_b.pdf").write_bytes(b"%PDF\n%%EOF")
    (tmp_path / "crs.pdf").write_bytes(b"%PDF\n%%EOF")  # suggests nothing → silence

    scanner = get("art")
    result = scanner.count(tmp_path)

    assert result.telemetry is not None
    suspects = result.telemetry.colado_suspects
    assert len(suspects) == 1
    assert suspects[0]["file"] == "2026-05-04_odi_b.pdf"
    assert suspects[0]["suggested_sigla"] == "odi"
    assert suspects[0]["kind"] == "filename"
    assert set(result.telemetry.present_files) == {
        "2026-05-04_art_a.pdf",
        "2026-05-04_odi_b.pdf",
        "crs.pdf",
    }
    # The count is unaffected by detection: only the art file matches host art.
    assert result.count == 1


def test_pase1_telemetry_empty_on_missing_folder(tmp_path):
    """folder_missing → telemetry present but empty (evicts everything downstream)."""
    scanner = get("art")
    result = scanner.count(tmp_path / "nope")
    assert result.telemetry is not None
    assert result.telemetry.colado_suspects == []
    assert result.telemetry.present_files == []


def _make_pdf(path, n_pages):
    """Real n-page PDF (same fabrication pattern as test_compute_settled)."""
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def test_duplicate_basenames_corrupt_fixed_page_count(tmp_path):
    """F10 blast radius on a FIXED_PAGE_SIGLA (bodega): count = sum of the
    basename-keyed `pages` dict, so two same-named PDFs collapse to ONE entry
    and the HEADLINE count is corrupted — 3pp A/x + 5pp B/x yields count=5
    (the last rglob'd path wins the dict), not the true 8. THIS undercount is
    exactly what the duplicate_basenames flag warns about; flag-only (no
    auto-correction) is the accepted design, and this pin makes the blast
    radius visible to whoever touches the name-keyed model next. (On a
    variable sigla like art, only the per_file display loses an entry — the
    headline count stays len(matched); fixed-page is the worst case.)"""
    _make_pdf(tmp_path / "A" / "2026-04_bodega_chequeo.pdf", 3)
    _make_pdf(tmp_path / "B" / "2026-04_bodega_chequeo.pdf", 5)

    scanner = get("bodega")
    result = scanner.count(tmp_path)

    assert "duplicate_basenames" in result.flags
    assert result.files_scanned == 2
    # Pinned CORRUPTED value (true total is 8): the pages dict holds one
    # entry per basename, and B/'s 5-page file overwrote A/'s 3-page one.
    assert result.count == 5
    assert result.per_file == {"2026-04_bodega_chequeo.pdf": 5}
