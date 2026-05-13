from pathlib import Path

import pytest

from core.scanners.art_scanner import ArtScanner
from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken, CancelledError

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


def test_normal_folder_uses_filename_glob(tmp_path: Path) -> None:
    """N normal PDFs in 7.-ART/ → no OCR, filename_glob direct."""
    art_folder = tmp_path / "7.-ART"
    art_folder.mkdir()
    # Three trivially-named singletons; one page each.
    for empresa in ("TITAN", "KOHLER", "ARAYA"):
        (art_folder / f"2026-04-15_art_{empresa}.pdf").write_bytes(_one_page_pdf_bytes())

    scanner = ArtScanner()
    result = scanner.count_ocr(art_folder, cancel=CancellationToken())

    assert result.method == "filename_glob"
    assert result.count == 3
    assert "ocr_failed" not in result.flags
    assert result.confidence == ConfidenceLevel.HIGH


@pytest.mark.slow
def test_compilation_pdf_uses_corner_count() -> None:
    """1 PDF flagged compilation_suspect → corner_count primary."""
    fixture = FIXTURE_ROOT / "art_multidoc"  # pinned in Chunk 2 Task 6
    scanner = ArtScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "corner_count"
    assert result.count >= 2  # multi-doc compilation
    assert result.confidence == ConfidenceLevel.HIGH


def test_empty_folder_returns_filename_glob_zero(tmp_path: Path) -> None:
    empty = tmp_path / "7.-ART"
    empty.mkdir()
    scanner = ArtScanner()
    result = scanner.count_ocr(empty, cancel=CancellationToken())

    assert result.count == 0
    assert result.method == "filename_glob"


def test_precancelled_token_raises_before_work(tmp_path: Path) -> None:
    folder = tmp_path / "7.-ART"
    folder.mkdir()
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        ArtScanner().count_ocr(folder, cancel=token)


def _one_page_pdf_bytes() -> bytes:
    """Minimal 1-page PDF — generated via PyMuPDF helper used in Chunk 2."""
    import fitz

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf
