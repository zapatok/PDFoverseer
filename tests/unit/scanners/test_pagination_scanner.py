"""Tests for PaginationScanner — counts documents via the V4 pipeline.

``count_documents_v4`` is monkeypatched so these tests never spawn the real
V4 process pool; the real pipeline is exercised by the insgral/altura smoke
tests (``test_pattern_insgral.py`` / ``test_pattern_altura.py``).
"""

from __future__ import annotations

from pathlib import Path

from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken
from core.scanners.pagination_scanner import PaginationScanner
from core.scanners.utils.v4_count import V4CountResult


def _v4(count: int, *, direct: int, inferred: int = 0, failed: int = 0) -> V4CountResult:
    """Build a V4CountResult with the given count and read-method tallies."""
    return V4CountResult(
        count=count,
        pages_total=direct + inferred + failed,
        direct_reads=direct,
        inferred_reads=inferred,
        failed_reads=failed,
    )


def test_pagination_scanner_pase1_is_filename_glob(tmp_path: Path):
    (tmp_path / "2026-04-15_insgral_eqf.pdf").write_bytes(b"%PDF-1.4\n")
    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count(tmp_path)
    assert r.method == "filename_glob"


def test_pagination_scanner_invokes_v4(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_v4",
        lambda *a, **k: _v4(4, direct=12),
    )
    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 12)

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4
    assert r.method == "v4"
    assert r.confidence == ConfidenceLevel.HIGH
    assert r.per_file[pdf.name] == 4


def test_pagination_scanner_a7_one_page_pdfs(tmp_path: Path, monkeypatch):
    """A7: 1-page PDFs counted trivially (no V4 call)."""
    one = tmp_path / "2026-04-01_insgral_x.pdf"
    multi = tmp_path / "2026-04_insgral.pdf"
    for p in (one, multi):
        p.write_bytes(b"%PDF-1.4\n")

    def fake_page_count(path):
        return 1 if "2026-04-0" in path.name else 7

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", fake_page_count)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_v4",
        lambda *a, **k: _v4(3, direct=7),
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 4  # 1 (A7) + 3 (V4)
    assert "a7_one_page_locked" in r.flags


def test_pagination_scanner_low_confidence_when_v4_guesses(tmp_path: Path, monkeypatch):
    """A count built entirely from inferred reads downgrades the cell to LOW."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 9)
    monkeypatch.setattr(
        "core.scanners.pagination_scanner.count_documents_v4",
        lambda *a, **k: _v4(5, direct=0, inferred=9),
    )

    scanner = PaginationScanner(sigla="insgral")
    r = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert r.count == 5
    assert r.confidence == ConfidenceLevel.LOW
    assert "v4_low_confidence" in r.flags


def test_pagination_scanner_v4_failure_falls_back(tmp_path: Path, monkeypatch):
    """A V4 RuntimeError falls back to count=1 and downgrades confidence."""
    pdf = tmp_path / "2026-04_insgral.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    def _boom(*a, **k):
        raise RuntimeError("v4_returned_no_reads")

    monkeypatch.setattr("core.scanners.pagination_scanner.get_page_count", lambda _: 9)
    monkeypatch.setattr("core.scanners.pagination_scanner.count_documents_v4", _boom)

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
