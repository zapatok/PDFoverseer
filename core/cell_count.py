"""Canonical per-cell document-count derivation.

Single source of truth for "how many documents does this (hospital, sigla) cell
hold". The API (``api/state.py``), the Excel writer (``core/excel/writer.py``)
and the history upsert all derive their number from here, so the UI, the Excel
and the historical record can never disagree (the 2026-06-06 mismatch was caused
by the Excel writer carrying a stale, divergent copy of this cascade).

The frontend mirror lives in ``frontend/src/lib/cellCount.js`` and is kept in
sync by ``tests/test_cell_count_cross_language.py`` against
``tests/fixtures/cell_count_cases.json``.
"""

from __future__ import annotations


def _sum_marks(cell: dict, present_files: set[str] | None = None) -> int:
    """Suma de los ``count`` de todas las marcas (``worker_marks``), filtrando a
    los archivos presentes.

    Filtro canónico (F1): si ``present_files`` se entrega (incluido un set vacío),
    solo cuentan las marcas de esos archivos — las huérfanas (PDF renombrado/borrado)
    se descartan. Si ``present_files is None`` (llamador sin carpeta resuelta),
    cae al comportamiento legacy: filtra por las claves de ``per_file`` cuando no
    está vacío, o no filtra si ``per_file`` está vacío.

    Sirve tanto a trabajadores (charla/chintegral) como a chequeos (maquinaria);
    es el mismo mecanismo de marcas por página.
    """
    marks: dict = cell.get("worker_marks") or {}
    if present_files is not None:
        allowed = present_files
        filter_on = True
    else:
        per_file = cell.get("per_file") or {}
        allowed = set(per_file)
        filter_on = bool(per_file)
    total = 0
    for filename, page_marks in marks.items():
        if filter_on and filename not in allowed:
            continue
        for mark in page_marks or []:
            if isinstance(mark, dict):
                total += mark.get("count") or 0
    return total


def compute_cell_count(
    cell: dict,
    count_type: str = "documents",
    present_files: set[str] | None = None,
) -> int:
    """Cell count derivation per FASE 4 §6.2 precedence.

    1. ``user_override`` (FASE 2 escape hatch) wins absolutely.
    2. ``count_type == "checks"`` → sum of ``worker_marks`` filtered by
       ``present_files`` (maquinaria check-tally regime).
    3. ``per_file_overrides`` ∪ ``per_file`` → derived sum (a per-file override
       wins over that file's scanned ``per_file`` value).
    4. Fallback: ``ocr_count`` or ``filename_count`` or 0.

    Args:
        cell: the persisted state dict of a single cell.
        count_type: ``"documents"`` (default), ``"documents_workers"``, or
            ``"checks"``.  Only ``"checks"`` changes the derivation path; the
            other two follow the same document-count cascade.
        present_files: set of PDF filenames currently present in the cell
            folder (used by the ``"checks"`` path to discard orphan marks).
            Pass ``None`` to use legacy per_file-based filtering.

    Returns:
        The effective document (or check-tally) count for the cell.
    """
    if cell.get("user_override") is not None:
        return cell["user_override"]

    if count_type == "checks":
        return _sum_marks(cell, present_files)

    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    if per_file or per_file_overrides:
        all_files = set(per_file) | set(per_file_overrides)
        return sum(per_file_overrides.get(f, per_file.get(f, 0)) for f in all_files)

    return cell.get("ocr_count") or cell.get("filename_count") or 0
