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


def compute_cell_count(cell: dict) -> int:
    """Cell count derivation per FASE 4 §6.2 precedence.

    1. ``user_override`` (FASE 2 escape hatch) wins absolutely.
    2. ``per_file_overrides`` ∪ ``per_file`` → derived sum (a per-file override
       wins over that file's scanned ``per_file`` value).
    3. Fallback: ``ocr_count`` or ``filename_count`` or 0.

    Args:
        cell: the persisted state dict of a single cell.

    Returns:
        The effective document count for the cell.
    """
    if cell.get("user_override") is not None:
        return cell["user_override"]

    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    if per_file or per_file_overrides:
        all_files = set(per_file) | set(per_file_overrides)
        return sum(per_file_overrides.get(f, per_file.get(f, 0)) for f in all_files)

    return cell.get("ocr_count") or cell.get("filename_count") or 0
