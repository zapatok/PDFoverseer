"""PaginationScanner.count_ocr emits per-PDF progress via the optional on_pdf
callback (same contract as AnchorsScanner) and uses the shared enumeration.
"""

import pytest

from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.pagination_scanner import PaginationScanner


def test_pagination_count_ocr_invokes_on_pdf(tmp_path, monkeypatch):
    for name in ("a.pdf", "b.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-1.4\n%%EOF\n")
    # get_page_count -> 1 forces the A7 path (no V4 pipeline runs).
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda p: 1)
    seen: list[str] = []
    PaginationScanner(sigla="insgral").count_ocr(
        tmp_path, cancel=CancellationToken(), on_pdf=lambda n: seen.append(n)
    )
    assert sorted(seen) == ["a.pdf", "b.pdf"]


def test_pagination_count_ocr_on_pdf_optional(tmp_path, monkeypatch):
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda p: 1)
    PaginationScanner(sigla="insgral").count_ocr(tmp_path, cancel=CancellationToken())


def test_pagination_count_ocr_cancel_before_loop_emits_nothing(tmp_path, monkeypatch):
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda p: 1)
    tok = CancellationToken()
    tok.cancel()
    seen: list[str] = []
    with pytest.raises(CancelledError):
        PaginationScanner(sigla="insgral").count_ocr(tmp_path, cancel=tok, on_pdf=seen.append)
    assert seen == []
