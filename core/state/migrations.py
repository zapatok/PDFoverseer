"""Lazy cell-state migrations between schema versions."""

from __future__ import annotations

from core.domain import SIGLAS


def migrate_cell_v1_to_v2(cell: dict) -> dict:
    """Migrate a single cell dict from FASE 1 to FASE 2 schema.

    FASE 1: ``{count, confidence, method, user_override, excluded, ...}``
    FASE 2: ``{filename_count, ocr_count, confidence, method, excluded, ...}``

    Note: ``override_note`` is NOT introduced here — it was removed in favour
    of the v2→v3 ``note``/``note_status`` fields. Idempotent. Safe on
    already-migrated cells. Defensive against missing fields.
    """
    if "count" in cell:
        cell["filename_count"] = cell.pop("count", None)
    cell.setdefault("filename_count", None)
    cell.setdefault("ocr_count", None)
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
            had_legacy = "count" in cell or "filename_count" not in cell or "ocr_count" not in cell
            migrate_cell_v1_to_v2(cell)
            if had_legacy:
                changed = True
    return state, changed


def migrate_cell_v2_to_v3(cell: dict) -> dict:
    """Migrate a single cell dict from v2 to v3 schema.

    v2: may contain ``override_note`` (str | None) written by the now-deleted
        ``apply_user_override`` note param or by ``setdefault`` calls.
    v3: independent ``note`` (str | None) and ``note_status``
        (``"por_resolver"`` | ``"resuelto"`` | None) fields; no ``override_note``.

    Legacy mapping (D5 in spec): a non-None ``override_note`` becomes
    ``note_status="resuelto"`` (it was already resolved context, not an open
    issue). A None (or absent) ``override_note`` maps to ``note=None`` /
    ``note_status=None``.

    Idempotent: if ``"note"`` is already present the cell is already at v3;
    pop ``override_note`` as cleanup (safe no-op if it was never there).
    """
    if "note" not in cell:
        legacy = cell.get("override_note")
        cell["note"] = legacy or None
        cell["note_status"] = "resuelto" if legacy else None
    cell.pop("override_note", None)
    return cell


def migrate_state_v2_to_v3(state: dict) -> tuple[dict, bool]:
    """Migrate full session state JSON in-place from v2 to v3. Idempotent.

    Returns:
        (state, changed) where ``changed`` is True iff any cell was
        actually rewritten (only on the first call per session).
    """
    changed = False
    cells = state.get("cells")
    if not cells:
        return state, False
    for hosp_cells in cells.values():
        for cell in hosp_cells.values():
            had_legacy = "override_note" in cell or "note" not in cell
            migrate_cell_v2_to_v3(cell)
            if had_legacy:
                changed = True
    return state, changed


def migrate_state_v3_to_v4(state: dict) -> tuple[dict, bool]:
    """Seed an empty ``{}`` cell for every (present hospital, sigla) pair missing
    from the session. Idempotent; never overwrites an existing cell.

    The frontend renders only siglas that have a cell, so a sigla added to
    ``SIGLAS`` after a session was scanned (e.g. revdocmaq/espacios in Increment B)
    would stay hidden on that session until a re-scan. Seeding an empty cell is
    output-neutral — ``compute_cell_count({}, …) == 0`` and the Excel path already
    treats an absent cell as ``{}`` — it only makes the full category set appear.

    Returns:
        (state, changed) where ``changed`` is True iff a cell was seeded (only on
        the first call per session after a new sigla is introduced).
    """
    changed = False
    cells = state.get("cells")
    if not cells:
        return state, False
    for hosp_cells in cells.values():
        for sigla in SIGLAS:
            if sigla not in hosp_cells:
                hosp_cells[sigla] = {}
                changed = True
    return state, changed
