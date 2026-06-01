"""AnchorsScanner.count_ocr emits per-PDF progress via the optional on_pdf
callback, and uses the shared cell enumeration. The callback must fire once per
PDF on every completion path (A7, OCR, handled error) so the progress bar's
``done`` matches the pre-counted ``total``.
"""

import pytest

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.cancellation import CancellationToken, CancelledError


def test_count_ocr_invokes_on_pdf_per_file(tmp_path, monkeypatch):
    # Two 1-page PDFs (A7 path — no real OCR needed) under an anchors sigla.
    for name in ("x.pdf", "y.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-1.4\n%%EOF\n")

    # get_page_count -> 1 so both take the A7 branch (no Tesseract).
    monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count", lambda p: 1)

    seen: list[str] = []
    AnchorsScanner(sigla="odi").count_ocr(
        tmp_path, cancel=CancellationToken(), on_pdf=lambda name: seen.append(name)
    )
    assert sorted(seen) == ["x.pdf", "y.pdf"]


def test_count_ocr_on_pdf_optional(tmp_path, monkeypatch):
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count", lambda p: 1)
    # No on_pdf -> must not raise.
    AnchorsScanner(sigla="odi").count_ocr(tmp_path, cancel=CancellationToken())


def test_count_ocr_cancel_before_loop_emits_nothing(tmp_path, monkeypatch):
    # A token already cancelled raises at the top guard, before any PDF is
    # processed -> on_pdf must never fire for a PDF that wasn't scanned.
    (tmp_path / "x.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    monkeypatch.setattr("core.scanners.anchors_scanner.get_page_count", lambda p: 1)
    tok = CancellationToken()
    tok.cancel()
    seen: list[str] = []
    with pytest.raises(CancelledError):
        AnchorsScanner(sigla="odi").count_ocr(tmp_path, cancel=tok, on_pdf=seen.append)
    assert seen == []
