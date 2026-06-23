"""Tests for PaginationScanner — counts documents via the pagination engine.

``count_documents_by_pagination`` is monkeypatched so these tests never run
real OCR; the real engine is exercised by the insgral/altura smoke tests
(``test_pattern_insgral.py`` / ``test_pattern_altura.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken, CancelledError
from core.scanners.pagination_scanner import PaginationScanner
from core.scanners.utils.pagination_count import PaginationCountResult


def _pag(
    count: int,
    *,
    pages: int = 4,
    direct: int | None = None,
    recovered: int = 0,
    failed: int = 0,
    cover_code_recovery: bool = False,
) -> PaginationCountResult:
    """Build a PaginationCountResult with sensible defaults for unit tests."""
    if direct is None:
        direct = pages - recovered - failed
    return PaginationCountResult(
        count=count,
        pages_total=pages,
        direct_reads=direct,
        recovered_reads=recovered,
        failed_reads=failed,
        dominant_total=pages if pages else None,
        codes={},
        cover_code_recovery=cover_code_recovery,
    )


def test_pagination_scanner_pase1_is_filename_glob(tmp_path: Path):
    (tmp_path / "2026-04-15_insgral_eqf.pdf").write_bytes(b"%PDF-1.4\n")
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count(tmp_path)
    assert r.method == "filename_glob"


def test_pagination_scanner_invokes_engine(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(4, pages=12, direct=12),
    )
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 12)

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4
    assert r.method == "pagination"
    assert r.confidence == ConfidenceLevel.HIGH
    assert r.per_file[pdf.name] == 4


def test_espacios_pagination_counts_compilation(tmp_path: Path, monkeypatch):
    """Incr B: espacios is a pagination sigla — a single PDF that compiles two
    2-page "Página N de 2" F-PETS-CRS-08-01 inspections counts as 2 documents."""
    pdf = tmp_path / "2026-05_espacios.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(2, pages=4, direct=4),
    )
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 4)

    scanner = PaginationScanner(sigla="espacios")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 2
    assert r.method == "pagination"
    assert r.confidence == ConfidenceLevel.HIGH
    assert r.per_file[pdf.name] == 2


def test_pagination_scanner_a7_one_page_pdfs(tmp_path: Path, monkeypatch):
    """A7: 1-page PDFs counted trivially (no engine call)."""
    one = tmp_path / "2026-04-01_insgral_x.pdf"
    multi = tmp_path / "2026-04_insgral.pdf"
    for p in (one, multi):
        p.write_bytes(b"%PDF-1.4\n")

    def fake_page_count(path):
        return 1 if "2026-04-0" in path.name else 7

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", fake_page_count)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(3, pages=7, direct=7),
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4  # 1 (A7) + 3 (pagination)
    assert "a7_one_page_locked" in r.flags


def test_pagination_scanner_low_confidence_when_recovery_heavy(tmp_path: Path, monkeypatch):
    """Heavy recovery (>30% of pages) downgrades cell to LOW."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 10)
    # 4/10 = 40% recovered — above RECOVERY_LOW_CONF_RATIO (0.30)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(5, pages=10, direct=6, recovered=4),
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 5
    assert r.confidence == ConfidenceLevel.LOW
    assert "pagination_low_confidence" in r.flags


def test_pagination_scanner_low_confidence_when_failed_reads(tmp_path: Path, monkeypatch):
    """Any failed read (unresolvable gap) downgrades to LOW."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 6)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(3, pages=6, direct=4, recovered=1, failed=1),
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.confidence == ConfidenceLevel.LOW
    assert "pagination_low_confidence" in r.flags


def test_pagination_scanner_low_confidence_cover_code_recovery(tmp_path: Path, monkeypatch):
    """cover_code_recovery=True forces LOW even when recovery ratio is low."""
    pdf = tmp_path / "2026-04_irl.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 8)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(2, pages=8, direct=6, recovered=1, cover_code_recovery=True),
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.confidence == ConfidenceLevel.LOW
    assert "pagination_low_confidence" in r.flags


def test_pagination_scanner_engine_failure_falls_back(tmp_path: Path, monkeypatch):
    """A RuntimeError from the engine falls back to count=1 and downgrades confidence."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def _boom(*a, **k):
        raise RuntimeError("engine_failed")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 9)
    monkeypatch.setattr("core.scanners.pagination_scanner.count_documents_by_pagination", _boom)

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 1
    assert r.confidence == ConfidenceLevel.LOW
    assert r.errors


def test_pagination_scanner_carpeta_inexistente(tmp_path: Path):
    """A8: missing folder → count=0 with flag."""
    missing = tmp_path / "DOES_NOT_EXIST"
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(missing, cancel=CancellationToken())
    assert r.count == 0
    assert "folder_missing" in r.flags


# --- Write-path verification tests (new in Task 11) ---


def test_pagination_scanner_on_pdf_method_is_pagination(tmp_path: Path, monkeypatch):
    """on_pdf receives method='pagination' for multi-page PDFs."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 4)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(2, pages=4, direct=4),
    )

    methods_seen: list[str] = []
    PaginationScanner(sigla="insgral").count_ocr(
        tmp_path,
        cancel=CancellationToken(),
        on_pdf=lambda name, count, method, nm: methods_seen.append(method),
    )
    assert methods_seen == ["pagination"]


def test_pagination_scanner_recovery_heavy_sets_low_confidence_flag(tmp_path: Path, monkeypatch):
    """Exactly 31% recovered (just over threshold) → pagination_low_confidence flag set."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 100)
    # 31/100 = 0.31 > 0.30 threshold
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(8, pages=100, direct=69, recovered=31),
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert "pagination_low_confidence" in r.flags
    assert r.confidence == ConfidenceLevel.LOW


def test_pagination_scanner_on_page_forwarded_to_engine(tmp_path: Path, monkeypatch):
    """on_page callback is passed through to count_documents_by_pagination."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    captured_on_page = []

    def fake_engine(*a, on_page=None, **k):
        # Simulate the engine firing on_page for 3 pages
        if on_page is not None:
            for i in range(1, 4):
                on_page(i, 3)
                captured_on_page.append((i, 3))
        return _pag(2, pages=3, direct=3)

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 3)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination", fake_engine
    )

    seen_pages: list[tuple[int, int]] = []
    PaginationScanner(sigla="insgral").count_ocr(
        tmp_path,
        cancel=CancellationToken(),
        on_page=lambda done, total: seen_pages.append((done, total)),
    )
    # The engine received and fired on_page
    assert captured_on_page == [(1, 3), (2, 3), (3, 3)]
    # The outer seen_pages should also be populated (same callback passed through)
    assert seen_pages == [(1, 3), (2, 3), (3, 3)]


def test_pagination_count_ocr_cancel_mid_pdf_no_tick(tmp_path: Path, monkeypatch):
    """A cancel raised mid-PDF (inside the engine) propagates as CancelledError and
    the cancelled PDF is NOT ticked via on_pdf (emit=False).

    Pins the cancel contract across the engine boundary — load-bearing for the
    OcrScannerBase split, which moves the engine call into _count_one_pdf.
    """
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def _raise_cancel(*a, **k):
        raise CancelledError()

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 5)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination", _raise_cancel
    )

    ticks: list = []
    scanner = PaginationScanner(sigla="insgral")
    with pytest.raises(CancelledError):
        scanner.count_ocr(tmp_path, cancel=CancellationToken(), on_pdf=lambda *a: ticks.append(a))
    assert ticks == [], "a mid-PDF-cancelled file must not be ticked via on_pdf"


def test_pagination_count_ocr_pre_cancelled_token_no_tick(tmp_path: Path, monkeypatch):
    """A token already cancelled raises CancelledError and never ticks on_pdf."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 5)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_by_pagination",
        lambda *a, **k: _pag(2, pages=5, direct=5),
    )

    token = CancellationToken()
    token.cancel()
    ticks: list = []
    scanner = PaginationScanner(sigla="insgral")
    with pytest.raises(CancelledError):
        scanner.count_ocr(tmp_path, cancel=token, on_pdf=lambda *a: ticks.append(a))
    assert ticks == []
