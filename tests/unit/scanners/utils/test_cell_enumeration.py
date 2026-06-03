"""Tests for the shared cell-PDF enumeration helper.

The helper is the single source of truth for "which PDFs belong to a cell".
Both the OCR scanners and the progress pre-count rely on it returning exactly
the set the scanners iterate, so the progress bar's total never diverges from
the work actually done.
"""

from pathlib import Path

from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs


def _touch(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")


def test_includes_subfolders_recursively(tmp_path):
    # The real corpus nests PDFs in per-contractor subfolders (art, charla, …);
    # enumeration must recurse, matching count_pdfs_by_sigla (pase 1).
    _touch(tmp_path / "a.pdf")
    _touch(tmp_path / "EMPRESA" / "b.pdf")
    _touch(tmp_path / "EMPRESA" / "SUB" / "c.pdf")
    names = sorted(p.name for p in enumerate_cell_pdfs(tmp_path))
    assert names == ["a.pdf", "b.pdf", "c.pdf"]


def test_only_pdfs(tmp_path):
    _touch(tmp_path / "a.pdf")
    (tmp_path / "notes.txt").write_text("x")
    assert [p.name for p in enumerate_cell_pdfs(tmp_path)] == ["a.pdf"]


def test_missing_folder_returns_empty(tmp_path):
    assert enumerate_cell_pdfs(tmp_path / "nope") == []


def test_matches_scanner_iteration_set(tmp_path):
    # Contract: the helper returns EXACTLY what the scanners iterate
    # (sorted(folder.rglob("*.pdf"))), so progress total == iteration set.
    _touch(tmp_path / "a.pdf")
    _touch(tmp_path / "sub" / "b.pdf")
    assert enumerate_cell_pdfs(tmp_path) == sorted(tmp_path.rglob("*.pdf"))
