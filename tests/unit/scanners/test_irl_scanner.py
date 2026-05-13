from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.irl_scanner import IrlScanner

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


def test_normal_folder_uses_filename_glob(tmp_path: Path) -> None:
    """N normal PDFs in irl folder → no OCR, filename_glob direct."""
    irl_folder = tmp_path / "irl"
    irl_folder.mkdir()
    for empresa in ("FIRM1", "FIRM2"):
        (irl_folder / f"2026-04-10_irl_{empresa}.pdf").write_bytes(_one_page_pdf_bytes())

    scanner = IrlScanner()
    result = scanner.count_ocr(irl_folder, cancel=CancellationToken())

    assert result.method == "filename_glob"
    assert result.count == 2
    assert "ocr_failed" not in result.flags
    assert result.confidence == ConfidenceLevel.HIGH


@pytest.mark.slow
def test_compilation_pdf_uses_header_detect() -> None:
    """1 PDF flagged compilation_suspect → header_detect on F-CRS-IRL/NN."""
    fixture = FIXTURE_ROOT / "irl_compilation"
    scanner = IrlScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "header_detect"
    assert result.count >= 1
    assert result.confidence == ConfidenceLevel.HIGH


def test_empty_folder_zero(tmp_path: Path) -> None:
    empty = tmp_path / "irl"
    empty.mkdir()
    scanner = IrlScanner()
    result = scanner.count_ocr(empty, cancel=CancellationToken())

    assert result.count == 0
    assert result.method == "filename_glob"


def test_precancelled_token_raises_before_work(tmp_path: Path) -> None:
    folder = tmp_path / "irl"
    folder.mkdir()
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Exception):  # CancelledError
        IrlScanner().count_ocr(folder, cancel=token)


def _one_page_pdf_bytes() -> bytes:
    """Minimal 1-page PDF — generated via PyMuPDF helper used in Chunk 2."""
    import fitz

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf
