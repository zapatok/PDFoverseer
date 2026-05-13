from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.charla_scanner import CharlaScanner

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "scanners_ocr"


def test_normal_folder_uses_filename_glob(tmp_path: Path) -> None:
    """N normal PDFs in charla folder → no OCR, filename_glob direct."""
    folder = tmp_path / "charla"
    folder.mkdir()
    for empresa in ("TITAN", "KOHLER"):
        (folder / f"2026-04-10_charla_{empresa}.pdf").write_bytes(_one_page_pdf())
    result = CharlaScanner().count_ocr(folder, cancel=CancellationToken())
    assert result.method == "filename_glob"
    assert result.count == 2


@pytest.mark.slow
def test_compilation_uses_page_count_pure() -> None:
    """1 PDF flagged compilation → page_count_pure (1pp = 1 charla)."""
    fixture = FIXTURE_ROOT / "charla_compilation"
    scanner = CharlaScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "page_count_pure"
    assert result.count >= 2
    assert result.confidence == ConfidenceLevel.HIGH


def test_empty_folder_returns_filename_glob_zero(tmp_path: Path) -> None:
    empty = tmp_path / "charla"
    empty.mkdir()
    scanner = CharlaScanner()
    result = scanner.count_ocr(empty, cancel=CancellationToken())

    assert result.count == 0
    assert result.method == "filename_glob"


def _one_page_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf
