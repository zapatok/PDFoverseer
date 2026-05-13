from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.odi_scanner import OdiScanner

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


def test_normal_folder_uses_filename_glob(tmp_path: Path) -> None:
    """N normal PDFs in 3.-ODI Visitas/ → no OCR, filename_glob direct."""
    odi_folder = tmp_path / "3.-ODI Visitas"
    odi_folder.mkdir()
    for empresa in ("AGUASAN", "TITAN"):
        (odi_folder / f"2026-04-10_odi_{empresa}.pdf").write_bytes(_one_page_pdf_bytes())

    scanner = OdiScanner()
    result = scanner.count_ocr(odi_folder, cancel=CancellationToken())

    assert result.method == "filename_glob"
    assert result.count == 2
    assert "ocr_failed" not in result.flags
    assert result.confidence == ConfidenceLevel.HIGH


@pytest.mark.slow
def test_compilation_pdf_uses_header_detect() -> None:
    """1 PDF flagged compilation_suspect → header_detect on F-CRS-ODI/NN."""
    fixture = FIXTURE_ROOT / "odi_compilation"
    scanner = OdiScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "header_detect"
    assert result.count >= 2
    assert result.confidence == ConfidenceLevel.HIGH


def test_empty_folder_zero(tmp_path: Path) -> None:
    empty = tmp_path / "3.-ODI Visitas"
    empty.mkdir()
    scanner = OdiScanner()
    result = scanner.count_ocr(empty, cancel=CancellationToken())

    assert result.count == 0
    assert result.method == "filename_glob"


def test_precancelled_token_raises_before_work(tmp_path: Path) -> None:
    folder = tmp_path / "3.-ODI Visitas"
    folder.mkdir()
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Exception):  # CancelledError
        OdiScanner().count_ocr(folder, cancel=token)


def _one_page_pdf_bytes() -> bytes:
    """Minimal 1-page PDF — generated via PyMuPDF helper used in Chunk 2."""
    import fitz

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf
