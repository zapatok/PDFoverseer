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


def _base_count(
    cell: dict,
    count_type: str = "documents",
    present_files: set[str] | None = None,
) -> int:
    """Base cell count per FASE 4 §6.2 precedence (the pre-Incr-J cascade).

    1. ``user_override`` wins absolutely.
    2. ``count_type == "checks"`` → ``_sum_marks`` filtered by ``present_files``.
    3. ``per_file_overrides`` ∪ ``per_file`` → derived sum.
    4. Fallback: ``ocr_count`` or ``filename_count`` or 0.
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

    # F9: ocr_count=0 is information (a real scan that found zero documents),
    # not absence — mirror the JS `??` cascade (frontend/src/lib/cellCount.js)
    # instead of Python's `or`, which would incorrectly fall through to
    # filename_count whenever ocr_count is exactly 0.
    if cell.get("ocr_count") is not None:
        return cell["ocr_count"]
    if cell.get("filename_count") is not None:
        return cell["filename_count"]
    return 0


def compute_cell_count(
    cell: dict,
    count_type: str = "documents",
    present_files: set[str] | None = None,
) -> int:
    """Effective cell count = base cascade + the Incr-J reorg delta (additive
    on top of every base path, including ``user_override`` and ``checks``).

    The base cascade (FASE 4 §6.2 precedence) is delegated to ``_base_count``:

    1. ``user_override`` (FASE 2 escape hatch) wins absolutely.
    2. ``count_type == "checks"`` → sum of ``worker_marks`` filtered by
       ``present_files`` (maquinaria check-tally regime).
    3. ``per_file_overrides`` ∪ ``per_file`` → derived sum (a per-file override
       wins over that file's scanned ``per_file`` value).
    4. Fallback: ``ocr_count`` or ``filename_count`` or 0.

    ``reorg_doc_delta`` (Incr J) is then added unconditionally on top of the
    base result, for all ``count_type`` values. The effective count is finally
    clamped at 0 (F5) — a reorg delta can never drive a cell negative.

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
    base = _base_count(cell, count_type, present_files)
    return max(0, base + (cell.get("reorg_doc_delta") or 0))


def compute_worker_count(cell: dict, present_files: set[str] | None = None) -> int:
    """Total de marcas de una celda (trabajadores en charla/chintegral, o
    chequeos en maquinaria — mismo mecanismo). Filtra por archivos presentes;
    ver :func:`_sum_marks` para la semántica de ``present_files``.

    Args:
        cell: el dict de estado de una celda.
        present_files: conjunto de nombres de archivo presentes en la carpeta
            de la celda. ``None`` usa el comportamiento legacy (filtra por
            per_file cuando no está vacío).

    Returns:
        La suma de marcas más el delta de reorganización ``reorg_worker_delta``
        (Incr J, aditivo sobre el total de marcas); 0 si no hay marcas ni delta.
        El resultado se acota a 0 (F5) — el delta nunca deja el total negativo.
    """
    return max(0, _sum_marks(cell, present_files) + (cell.get("reorg_worker_delta") or 0))
