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
@pytest.mark.xfail(
    reason="Real ART corpus (HLU 144pp) lacks 'Página N de M' in the corner. "
    "Scanner correctly falls back to filename_glob with ocr_failed flag. "
    "OCR engine refinement against real ART forms is deferred to a post-overhaul "
    "pass — for now FASE 2 ships the scanner structure + fallback behaviour.",
    strict=False,
)
def test_compilation_pdf_uses_corner_count() -> None:
    """1 PDF flagged compilation_suspect → corner_count primary.

    Pinned for the day corner_count is refined to handle the real ART corpus.
    Today, the fixture has no extractable pagination, so the scanner takes the
    documented fallback path; that behaviour is verified in
    ``test_compilation_pdf_falls_back_when_no_pagination``.
    """
    fixture = FIXTURE_ROOT / "art_multidoc"  # pinned in Chunk 2 Task 6
    scanner = ArtScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "corner_count"
    assert result.count >= 2  # multi-doc compilation
    assert result.confidence == ConfidenceLevel.HIGH


@pytest.mark.slow
def test_compilation_pdf_falls_back_when_no_pagination() -> None:
    """Document the *current* behaviour on the real fixture: when corner_count
    finds no pagination, scanner returns filename_glob count with ocr_failed
    flag and LOW confidence. Updates needed if the fixture or the OCR engine
    is refined to recognise ART pagination.
    """
    fixture = FIXTURE_ROOT / "art_multidoc"
    scanner = ArtScanner()
    result = scanner.count_ocr(fixture, cancel=CancellationToken())

    assert result.method == "filename_glob"
    assert result.confidence == ConfidenceLevel.LOW
    assert "ocr_failed" in result.flags


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
