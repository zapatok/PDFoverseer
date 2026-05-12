"""Lazy cell-state migrations between schema versions."""

from __future__ import annotations


def migrate_cell_v1_to_v2(cell: dict) -> dict:
    """Migrate a single cell dict from FASE 1 to FASE 2 schema.

    FASE 1: ``{count, confidence, method, user_override, excluded, ...}``
    FASE 2: ``{filename_count, ocr_count, user_override, override_note,
             confidence, method, excluded, ...}``

    Idempotent. Safe on already-migrated cells. Defensive against missing
    fields. Does not raise on empty or partial cells.
    """
    if "count" in cell:
        cell["filename_count"] = cell.pop("count", None)
    cell.setdefault("filename_count", None)
    cell.setdefault("ocr_count", None)
    cell.setdefault("override_note", None)
    # excluded (bool, FASE 1) preserved as-is. user_override (FASE 1) preserved.
    return cell


def migrate_state_v1_to_v2(state: dict) -> tuple[dict, bool]:
    """Migrate full session state JSON in-place. Idempotent.

    Returns:
        (state, changed) where ``changed`` is True iff any cell was
        actually rewritten. Caller uses this to skip the DB write-back
        when nothing changed (every call after the first one).
    """
    changed = False
    cells = state.get("cells")
    if not cells:
        return state, False
    for hosp_cells in cells.values():
        for cell in hosp_cells.values():
            had_legacy = (
                "count" in cell
                or "filename_count" not in cell
                or "ocr_count" not in cell
                or "override_note" not in cell
            )
            migrate_cell_v1_to_v2(cell)
            if had_legacy:
                changed = True
    return state, changed
