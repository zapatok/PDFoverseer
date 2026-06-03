"""Pase-1 confidence/count rule (2026-06-02 conteo-confiable spec, Tema A1).

The honest "ready" model: a pase-1 (filename) cell is HIGH confidence (green)
only when its count is verifiable without OCR — either every matched PDF is a
single page (1 page = 1 document, trivially) or the sigla is a fixed-page sigla
(pages = documents). A multi-page file of a variable sigla is unverified and
reports LOW (amber) so the operator scans or confirms it.
"""

from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from core.scanners.base import ConfidenceLevel
from core.scanners.simple_factory import make_simple_scanner


def _pdf(path: Path, pages: int) -> None:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()


def _folder(tmp_path: Path, sigla: str, files: dict[str, int]) -> Path:
    """Create <tmp>/<sigla>/ with canonical filenames of the given page counts."""
    folder = tmp_path / sigla
    folder.mkdir()
    for name, pages in files.items():
        _pdf(folder / name, pages)
    return folder


def test_fixed_page_sigla_counts_pages_high(tmp_path: Path):
    # bodega: each page is a chequeo -> count = sum of pages.
    folder = _folder(
        tmp_path,
        "bodega",
        {
            "2026-04-01_bodega_a.pdf": 1,
            "2026-04-02_bodega_b.pdf": 4,
        },
    )
    r = make_simple_scanner("bodega").count(folder)
    assert r.count == 5
    assert r.per_file == {"2026-04-01_bodega_a.pdf": 1, "2026-04-02_bodega_b.pdf": 4}
    assert r.method == "page_count_pure"
    assert r.confidence == ConfidenceLevel.HIGH
    assert "fixed_pages_inferred" not in r.flags  # bodega is solid


def test_inferred_fixed_page_sigla_flags_verificar(tmp_path: Path):
    folder = _folder(tmp_path, "exc", {"2026-04-01_exc_a.pdf": 2})
    r = make_simple_scanner("exc").count(folder)
    assert r.count == 2
    assert "fixed_pages_inferred" in r.flags
    assert r.confidence == ConfidenceLevel.HIGH


def test_normal_sigla_all_one_page_high(tmp_path: Path):
    # charla, all single-page files -> trivially 1 doc each -> HIGH.
    folder = _folder(
        tmp_path,
        "charla",
        {
            "2026-04-01_charla_a.pdf": 1,
            "2026-04-02_charla_b.pdf": 1,
        },
    )
    r = make_simple_scanner("charla").count(folder)
    assert r.count == 2
    assert r.per_file == {"2026-04-01_charla_a.pdf": 1, "2026-04-02_charla_b.pdf": 1}
    assert r.confidence == ConfidenceLevel.HIGH
    assert r.method == "filename_glob"


def test_normal_sigla_with_multipage_low(tmp_path: Path):
    # A multi-page file of a variable sigla -> unverified -> LOW (amber).
    folder = _folder(
        tmp_path,
        "charla",
        {
            "2026-04-01_charla_a.pdf": 1,
            "2026-04-02_charla_b.pdf": 28,
        },
    )
    r = make_simple_scanner("charla").count(folder)
    assert r.count == 2  # still file count (1 doc per file, unverified)
    assert r.confidence == ConfidenceLevel.LOW


def test_empty_existing_folder_high_zero(tmp_path: Path):
    # Folder exists but has no matching PDFs -> count 0 is a certain zero
    # ("cero seguro"), so it reports HIGH (green), not amber.
    folder = tmp_path / "charla"
    folder.mkdir()
    r = make_simple_scanner("charla").count(folder)
    assert r.count == 0
    assert r.confidence == ConfidenceLevel.HIGH


def test_missing_folder_high_zero(tmp_path: Path):
    r = make_simple_scanner("bodega").count(tmp_path / "nope")
    assert r.count == 0
    assert r.confidence == ConfidenceLevel.HIGH
    assert "folder_missing" in r.flags
