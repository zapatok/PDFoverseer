"""Single source of truth for enumerating the PDFs that belong to a cell.

The OCR scanners (pase 2) and the pre-scan PDF count must agree on which files
belong to a cell — otherwise the progress bar's ``done`` (driven by the scanner
iterating each PDF) and ``total`` (the pre-count) diverge (audit finding #1).

Both passes count **recursively**: ``count_pdfs_by_sigla`` (pase 1) and
``AnchorsScanner`` / ``PaginationScanner.count_ocr`` (pase 2) all use
``folder.rglob("*.pdf")`` unconditionally. The real corpus nests several siglas
(art, charla, …) in per-contractor subfolders, and ``rglob`` is a safe superset
of ``glob`` for the flat ones (diff=0 across all hospitals — Fase B audit
2026-05-22). The ``recursive_glob`` field in ``patterns.py`` is informational
only; no counting path branches on it (audit finding #3 — both passes already
agree, so this helper preserves, rather than changes, behavior).
"""

from __future__ import annotations

from pathlib import Path


def enumerate_cell_pdfs(folder: Path) -> list[Path]:
    """Return the sorted list of PDFs for a cell, recursively.

    Mirrors exactly what the OCR scanners iterate
    (``sorted(folder.rglob("*.pdf"))``) so the progress bar's total equals the
    number of PDFs that will actually be scanned.

    Args:
        folder: The cell's category folder.

    Returns:
        Sorted list of PDF paths under ``folder`` (recursively), or an empty
        list if the folder does not exist.
    """
    if not folder.exists():
        return []
    return sorted(folder.rglob("*.pdf"))
