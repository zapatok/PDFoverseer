"""Tests for the generic AnchorsScanner."""

from __future__ import annotations

from pathlib import Path

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken


def test_anchors_scanner_falls_through_to_filename_glob_for_pase1(tmp_path: Path):
    """Pase 1 (count) is always filename_glob — uniform across all scanners."""
    (tmp_path / "2026-04-15_andamios_chequeo.pdf").write_bytes(b"%PDF-1.4\n")
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count(tmp_path)
    assert result.method == "filename_glob"
    assert result.count == 1


def test_anchors_scanner_count_ocr_returns_base_for_unknown_sigla(tmp_path: Path):
    """A sigla absent from PATTERNS has no flavors, so count_ocr returns the
    filename_glob base result unchanged (early return on empty flavors).

    Note: this does NOT exercise the A7 one-page path — the function returns
    before reaching that branch because 'andamios' is not in PATTERNS.
    """
    pdf = tmp_path / "2026-04-15_andamios_chequeo.pdf"
    pdf.write_bytes(_one_page_pdf())
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.method == "filename_glob"  # unknown sigla → no flavors → base returned


def test_anchors_scanner_a7_only_one_page_pdfs(tmp_path: Path, monkeypatch):
    """A7 path: a folder containing only 1-page PDFs is handled without OCR.

    With a known sigla (PATTERNS monkeypatched to have a flavor), every PDF
    has page_count == 1, so each is counted trivially. count_covers_by_anchors
    must NOT be called.
    """
    pdf_a = tmp_path / "2026-04-01_andamios_a.pdf"
    pdf_b = tmp_path / "2026-04-02_andamios_b.pdf"
    pdf_c = tmp_path / "2026-04-03_andamios_c.pdf"
    for p in (pdf_a, pdf_b, pdf_c):
        p.write_bytes(_one_page_pdf())

    import core.scanners.anchors_scanner as _mod

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 1)

    ocr_called = []

    def _must_not_be_called(*args, **kw):
        ocr_called.append(True)
        raise AssertionError("count_covers_by_anchors must not be called when all PDFs are 1-page")

    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        _must_not_be_called,
    )

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())

    assert result.method == "header_band_anchors"
    assert "a7_one_page_locked" in result.flags
    assert result.count == 3  # one trivial doc per 1-page PDF
    assert not ocr_called, "count_covers_by_anchors was invoked unexpectedly"


def _one_page_pdf() -> bytes:
    """Return the bytes of a minimal valid 1-page PDF for tests."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000053 00000 n \n0000000095 00000 n \ntrailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n141\n%%EOF\n"
    )


_FAKE_FLAVOR = {"name": "f_andamios_test", "anchors": ["andamios"], "min_match": 1}
_FAKE_PATTERN = {
    "filename_glob": r"^.*andamios.*\.pdf$",
    "scan_strategy": "anchors",
    "cover_flavors": [_FAKE_FLAVOR],
}


def test_anchors_scanner_count_ocr_invokes_count_covers(tmp_path: Path, monkeypatch):
    """When a multi-page PDF is present, OCR is invoked."""
    pdf = tmp_path / "2026-04_andamios.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"%fake-multipage\n")

    import core.scanners.anchors_scanner as _mod
    from core.scanners.utils import header_band_anchors as hba

    fake_result = hba.AnchorCountResult(
        count=29,
        pages_total=29,
        matches_per_flavor={"f_lch_05": 29},
        near_matches=[],
    )

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 29)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *args, **kw: fake_result,
    )

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.method == "header_band_anchors"
    assert result.count == 29
    assert result.confidence == ConfidenceLevel.HIGH


def test_anchors_scanner_a7_one_page_pdfs_counted_as_one(tmp_path: Path, monkeypatch):
    """A7: PDFs of 1 page contribute count=1 without OCR (locked at R1)."""
    one_pager_a = tmp_path / "2026-04-01_andamios_aguasan.pdf"
    one_pager_b = tmp_path / "2026-04-02_andamios_aguasan.pdf"
    multi = tmp_path / "2026-04_andamios.pdf"
    for p in (one_pager_a, one_pager_b, multi):
        p.write_bytes(b"%PDF-1.4\n")

    # Stub page counts: two 1-page + one 5-page
    def fake_page_count(path):
        return 1 if path.name.startswith("2026-04-0") else 5

    import core.scanners.anchors_scanner as _mod
    from core.scanners.utils import header_band_anchors as hba

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", fake_page_count)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *args, **kw: hba.AnchorCountResult(
            count=5,
            pages_total=5,
            matches_per_flavor={"f_lch_05": 5},
            near_matches=[],
        ),
    )

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    # 1-pagers: 2 docs counted trivially; multi-page: 5 covers from OCR → 7 total
    assert result.count == 7
    assert "a7_one_page_locked" in result.flags


def test_anchors_scanner_carpeta_inexistente(tmp_path: Path):
    """A8: missing folder → count=0, confidence=HIGH, flag folder_missing."""
    missing = tmp_path / "DOES_NOT_EXIST"
    scanner = AnchorsScanner(sigla="andamios")
    r1 = scanner.count(missing)
    assert r1.count == 0
    assert r1.confidence == ConfidenceLevel.HIGH
    assert "folder_missing" in r1.flags

    r2 = scanner.count_ocr(missing, cancel=CancellationToken())
    assert r2.count == 0
    assert "folder_missing" in r2.flags
