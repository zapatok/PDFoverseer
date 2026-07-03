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

from collections import Counter
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


def find_duplicate_basenames(folder: Path) -> dict[str, int]:
    """Return ``{basename: occurrence_count}`` for every basename that occurs
    more than once under ``folder`` (recursively) — e.g. the same filename
    reused across two contractor subfolders (F10).

    PDFoverseer's per-file models (``per_file``, ``per_file_method``,
    ``per_file_overrides``, near-match lookups) are keyed by basename, not
    full path, so two distinct PDFs that happen to share a name can silently
    collide in those dicts (the second one scanned overwrites the first's
    entry — an undercount that leaves no trace). This walks the SAME
    enumeration ``enumerate_cell_pdfs`` already provides (the single source
    of truth for "which PDFs belong to a cell"), so it never diverges from
    what the scanners actually see.

    Args:
        folder: The cell's category folder.

    Returns:
        Mapping of basename to how many times it occurs, restricted to
        basenames occurring 2+ times. Empty dict if there are no duplicates
        or the folder does not exist.
    """
    counts = Counter(p.name for p in enumerate_cell_pdfs(folder))
    return {name: n for name, n in counts.items() if n >= 2}
