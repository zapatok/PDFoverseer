"""Tests for PaginationScanner — reuses corner_count.count_paginations."""

from __future__ import annotations

from pathlib import Path

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.pagination_scanner import PaginationScanner


def _one_page_pdf() -> bytes:
    """Minimal valid 1-page PDF for A7 tests."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000053 00000 n \n0000000095 00000 n \ntrailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n141\n%%EOF\n"
    )


def test_pagination_scanner_pase1_is_filename_glob(tmp_path: Path):
    (tmp_path / "2026-04-15_insgral_eqf.pdf").write_bytes(b"%PDF-1.4\n")
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count(tmp_path)
    assert r.method == "filename_glob"


def test_pagination_scanner_invokes_corner_count(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    from core.scanners.utils import corner_count as cc

    def fake_count_paginations(pdf_path, *, dpi=200, cancel=None):
        return cc.CornerCountResult(
            count=4,
            transitions=[(1, 3), (2, 3), (3, 3), (1, 5), (2, 5), (1, 2), (2, 2), (1, 4)],
            pages_total=12,
        )

    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_paginations",
        fake_count_paginations,
    )
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 12)

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4
    assert r.method == "pagination"
    assert r.confidence == ConfidenceLevel.HIGH


def test_pagination_scanner_a7_one_page_pdfs(tmp_path: Path, monkeypatch):
    """A7: 1-page PDFs counted trivially (no corner_count call)."""
    one = tmp_path / "2026-04-01_insgral_x.pdf"
    multi = tmp_path / "2026-04_insgral.pdf"
    for p in (one, multi):
        p.write_bytes(b"%PDF-1.4\n")

    def fake_page_count(path):
        return 1 if "2026-04-0" in path.name else 7

    from core.scanners.utils import corner_count as cc

    def fake_count(pdf_path, *, dpi=200, cancel=None):
        return cc.CornerCountResult(count=3, transitions=[], pages_total=7)

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", fake_page_count)
    monkeypatch.setattr("core.scanners.pagination_scanner.count_paginations", fake_count)

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4  # 1 (A7) + 3 (corner_count)
    assert "a7_one_page_locked" in r.flags


def test_pagination_scanner_carpeta_inexistente(tmp_path: Path):
    """A8: missing folder → count=0 with flag."""
    missing = tmp_path / "DOES_NOT_EXIST"
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(missing, cancel=CancellationToken())
    assert r.count == 0
    assert "folder_missing" in r.flags
