"""Tests for the generic AnchorsScanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scanners.anchors_scanner import AnchorsScanner
from core.scanners.base import ConfidenceLevel
from core.scanners.cancellation import CancellationToken, CancelledError


def test_anchors_scanner_falls_through_to_filename_glob_for_pase1(tmp_path: Path):
    """Pase 1 (count) is always filename_glob — uniform across all scanners."""
    (tmp_path / "2026-04-15_andamios_chequeo.pdf").write_bytes(b"%PDF-1.4\n")
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count(tmp_path)
    assert result.method == "filename_glob"
    assert result.count == 1


def test_anchors_scanner_count_ocr_returns_base_for_unknown_sigla(tmp_path: Path, monkeypatch):
    """A sigla absent from PATTERNS has no flavors, so count_ocr returns the
    filename_glob base result unchanged (defensive early return).

    All 18 SIGLAS are now populated in PATTERNS, so the test removes one
    entry to exercise the fallback path. This does NOT reach the A7 one-page
    branch — the function returns as soon as it finds no pattern.
    """
    from core.scanners.patterns import PATTERNS

    monkeypatch.delitem(PATTERNS, "andamios", raising=False)
    pdf = tmp_path / "2026-04-15_andamios_chequeo.pdf"
    pdf.write_bytes(_one_page_pdf())
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.method == "filename_glob"  # no pattern → base returned


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


def test_anchors_scanner_zero_covers_multipage_is_low_trust(tmp_path: Path, monkeypatch):
    """F8: a multi-page PDF with 0 covers from the anchors engine is honest-low-trust
    (not a silent 'listo' 0) — the count stays 0 (an honest number), but confidence
    drops to LOW with the anchors_low_confidence flag so the operator reviews it
    (live case: senal 0/18)."""
    pdf = tmp_path / "2026-04_andamios.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"%fake-multipage\n")

    import core.scanners.anchors_scanner as _mod
    from core.scanners.utils import header_band_anchors as hba

    fake_result = hba.AnchorCountResult(
        count=0,
        pages_total=18,
        matches_per_flavor={},
        near_matches=[],
    )

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 18)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *args, **kw: fake_result,
    )

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.count == 0
    assert result.confidence == ConfidenceLevel.LOW
    assert "anchors_low_confidence" in result.flags


def test_anchors_scanner_nonzero_covers_multipage_stays_high(tmp_path: Path, monkeypatch):
    """Boundary companion to the zero-covers test above: covers > 0 on a
    multi-page PDF stays HIGH (absent other low-trust conditions)."""
    pdf = tmp_path / "2026-04_andamios.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"%fake-multipage\n")

    import core.scanners.anchors_scanner as _mod
    from core.scanners.utils import header_band_anchors as hba

    fake_result = hba.AnchorCountResult(
        count=3,
        pages_total=18,
        matches_per_flavor={"f_lch_05": 3},
        near_matches=[],
    )

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 18)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *args, **kw: fake_result,
    )

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(tmp_path, cancel=CancellationToken())
    assert result.count == 3
    assert result.confidence == ConfidenceLevel.HIGH
    assert "anchors_low_confidence" not in result.flags


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


def test_anchors_scanner_count_ocr_only_and_on_page(tmp_path: Path, monkeypatch):
    """rev-2 #1: `only=` scopes the scan to one PDF; `on_page` fires per page.

    Runs the real count_covers_by_anchors loop (render + OCR stubbed) so the
    per-page callback is genuinely exercised.
    """
    from PIL import Image

    pdf_a = tmp_path / "2026-04-01_andamios_a.pdf"
    pdf_b = tmp_path / "2026-04-02_andamios_b.pdf"
    for p in (pdf_a, pdf_b):
        p.write_bytes(b"%PDF-1.4\n")

    import core.scanners.anchors_scanner as _mod
    from core.scanners.utils import header_band_anchors as hba

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 2)  # force the OCR path
    # Stub render + OCR so the real loop runs without I/O and finds no anchors.
    monkeypatch.setattr(hba, "get_page_count", lambda _: 2)
    monkeypatch.setattr(hba, "render_page_region", lambda *a, **k: Image.new("RGB", (1, 1)))
    monkeypatch.setattr(hba.pytesseract, "image_to_string", lambda *a, **k: "")

    pages_seen: list[tuple[int, int]] = []

    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(
        tmp_path,
        cancel=CancellationToken(),
        only="2026-04-01_andamios_a.pdf",
        on_page=lambda i, n: pages_seen.append((i, n)),
    )

    # Only a.pdf was scanned; b.pdf is absent from per_file.
    assert set(result.per_file) == {"2026-04-01_andamios_a.pdf"}
    assert result.per_file["2026-04-01_andamios_a.pdf"] == 0  # no anchors matched
    assert result.files_scanned == 1
    # on_page fired once per page of the single file.
    assert pages_seen == [(0, 2), (1, 2)]


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


def test_count_ocr_skips_files_in_skip_set(tmp_path: Path, monkeypatch):
    """Incr. 1A: `skip` excluye archivos del escaneo — no entran a per_file
    ni al callback de progreso (los ya confiables: R1/manual/OCR previo)."""
    keep = tmp_path / "2026-04_andamios_keep.pdf"
    skip_pdf = tmp_path / "2026-04_andamios_skip.pdf"
    for p in (keep, skip_pdf):
        p.write_bytes(b"%PDF-1.4\n")

    import core.scanners.anchors_scanner as _mod
    from core.scanners.utils import header_band_anchors as hba

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 5)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *a, **k: hba.AnchorCountResult(
            count=5, pages_total=5, matches_per_flavor={}, near_matches=[]
        ),
    )

    seen: list[str] = []
    scanner = AnchorsScanner(sigla="andamios")
    result = scanner.count_ocr(
        tmp_path,
        cancel=CancellationToken(),
        on_pdf=lambda name, count, method, nm: seen.append(name),
        skip={"2026-04_andamios_skip.pdf"},
    )
    assert "2026-04_andamios_skip.pdf" not in seen
    assert "2026-04_andamios_skip.pdf" not in (result.per_file or {})
    assert "2026-04_andamios_keep.pdf" in (result.per_file or {})


def test_count_ocr_enriched_callback_carries_count_method_nm(tmp_path: Path, monkeypatch):
    """Incr. 1A: on_pdf recibe (name, count, method, near_matches) por archivo.
    Multipágina → header_band_anchors; 1 página (A7) → filename_glob (chip R1)."""
    multi = tmp_path / "2026-04_andamios_multi.pdf"
    one = tmp_path / "2026-04-01_andamios_one.pdf"
    for p in (multi, one):
        p.write_bytes(b"%PDF-1.4\n")

    import core.scanners.anchors_scanner as _mod
    from core.scanners.utils import header_band_anchors as hba

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda p: 1 if "one" in p.name else 4)
    monkeypatch.setattr(
        "core.scanners.anchors_scanner.count_covers_by_anchors",
        lambda *a, **k: hba.AnchorCountResult(
            count=4, pages_total=4, matches_per_flavor={}, near_matches=[]
        ),
    )

    rows: list[tuple] = []
    scanner = AnchorsScanner(sigla="andamios")
    scanner.count_ocr(
        tmp_path,
        cancel=CancellationToken(),
        on_pdf=lambda name, count, method, nm: rows.append((name, count, method, nm)),
    )
    by_name = {r[0]: r for r in rows}
    assert by_name["2026-04_andamios_multi.pdf"][1] == 4
    assert by_name["2026-04_andamios_multi.pdf"][2] == "header_band_anchors"
    assert by_name["2026-04-01_andamios_one.pdf"][1] == 1
    assert by_name["2026-04-01_andamios_one.pdf"][2] == "filename_glob"
    # near_matches siempre lista serializable (dicts), nunca NearMatchEntry.
    assert all(isinstance(r[3], list) for r in rows)


def test_anchors_count_ocr_cancel_mid_pdf_no_tick(tmp_path: Path, monkeypatch):
    """A cancel raised mid-PDF (inside the engine) propagates as CancelledError and
    the cancelled PDF is NOT ticked via on_pdf (emit=False).

    Pins the cancel contract across the engine boundary — load-bearing for the
    OcrScannerBase split, which moves the engine call into _count_one_pdf.
    """
    pdf = tmp_path / "2026-04_andamios_multi.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    import core.scanners.anchors_scanner as _mod

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 5)  # >1 → reach the engine

    def _raise_cancel(*a, **k):
        raise CancelledError()

    monkeypatch.setattr("core.scanners.anchors_scanner.count_covers_by_anchors", _raise_cancel)

    ticks: list = []
    scanner = AnchorsScanner(sigla="andamios")
    with pytest.raises(CancelledError):
        scanner.count_ocr(tmp_path, cancel=CancellationToken(), on_pdf=lambda *a: ticks.append(a))
    assert ticks == [], "a mid-PDF-cancelled file must not be ticked via on_pdf"


def test_anchors_count_ocr_pre_cancelled_token_no_tick(tmp_path: Path, monkeypatch):
    """A token already cancelled raises CancelledError and never ticks on_pdf."""
    pdf = tmp_path / "2026-04_andamios_multi.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    import core.scanners.anchors_scanner as _mod

    monkeypatch.setattr(_mod, "PATTERNS", {"andamios": _FAKE_PATTERN})
    monkeypatch.setattr(_mod, "get_page_count", lambda _: 5)

    token = CancellationToken()
    token.cancel()
    ticks: list = []
    scanner = AnchorsScanner(sigla="andamios")
    with pytest.raises(CancelledError):
        scanner.count_ocr(tmp_path, cancel=token, on_pdf=lambda *a: ticks.append(a))
    assert ticks == []
