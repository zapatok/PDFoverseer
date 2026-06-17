"""Cell state migration FASE 1 → FASE 2 and v2 → v3."""

from __future__ import annotations

from core.state.migrations import (
    migrate_cell_v1_to_v2,
    migrate_cell_v2_to_v3,
    migrate_state_v1_to_v2,
    migrate_state_v2_to_v3,
)


def test_migrate_cell_renames_count_to_filename_count():
    cell = {"count": 5, "confidence": "high", "method": "filename_glob"}
    result = migrate_cell_v1_to_v2(cell)
    assert result["filename_count"] == 5
    assert "count" not in result
    assert result["ocr_count"] is None


def test_migrate_cell_idempotent_on_already_v2():
    cell = {
        "filename_count": 5,
        "ocr_count": 17,
        "user_override": None,
        "override_note": "note",
        "confidence": "high",
    }
    result = migrate_cell_v1_to_v2(cell)
    assert result == cell


def test_migrate_cell_preserves_excluded_flag():
    cell = {"count": 0, "excluded": True}
    result = migrate_cell_v1_to_v2(cell)
    assert result["filename_count"] == 0
    assert result["excluded"] is True


def test_migrate_cell_handles_missing_count_field():
    # When the legacy `count` key is absent (cell never scanned), filename_count
    # ends up None via setdefault — no KeyError.
    cell = {"confidence": "high"}
    result = migrate_cell_v1_to_v2(cell)
    assert result["filename_count"] is None
    assert result["ocr_count"] is None


def test_migrate_state_walks_all_cells_returns_changed_true():
    state = {
        "cells": {
            "HPV": {
                "art": {"count": 767, "confidence": "high"},
                "odi": {"count": 1, "confidence": "low"},
            },
            "HRB": {"odi": {"count": 1, "excluded": False}},
        }
    }
    result, changed = migrate_state_v1_to_v2(state)
    assert changed is True
    assert result["cells"]["HPV"]["art"]["filename_count"] == 767
    assert "count" not in result["cells"]["HPV"]["art"]


def test_migrate_state_returns_changed_false_on_already_v2():
    state = {
        "cells": {
            "HPV": {"art": {"filename_count": 767, "ocr_count": None, "override_note": None}},
        }
    }
    result, changed = migrate_state_v1_to_v2(state)
    assert changed is False


def test_migrate_state_empty_cells_dict_is_fine():
    state = {"cells": {}}
    result, changed = migrate_state_v1_to_v2(state)
    assert result == {"cells": {}}
    assert changed is False


def test_migrate_state_no_cells_key_is_fine():
    state = {"session_id": "2026-04", "status": "active"}
    result, changed = migrate_state_v1_to_v2(state)
    assert result == state
    assert changed is False


# ---------------------------------------------------------------------------
# v2 → v3 migration tests
# ---------------------------------------------------------------------------


def test_v2_to_v3_migrates_override_note_to_resuelto_note():
    """A cell with a legacy override_note string migrates to note/note_status=resuelto."""
    cell = {"filename_count": 5, "ocr_count": None, "override_note": "17 ODIs in 1 PDF"}
    result = migrate_cell_v2_to_v3(cell)
    assert result["note"] == "17 ODIs in 1 PDF"
    assert result["note_status"] == "resuelto"
    assert "override_note" not in result


def test_v2_to_v3_no_legacy_note_yields_none_none():
    """A cell with override_note=None migrates to note=None / note_status=None."""
    cell = {"filename_count": 5, "ocr_count": None, "override_note": None}
    result = migrate_cell_v2_to_v3(cell)
    assert result["note"] is None
    assert result["note_status"] is None
    assert "override_note" not in result


def test_v2_to_v3_absent_override_note_yields_none_none():
    """A v2 cell that never had override_note still gets note/note_status=None."""
    cell = {"filename_count": 3, "ocr_count": 3}
    result = migrate_cell_v2_to_v3(cell)
    assert result["note"] is None
    assert result["note_status"] is None
    assert "override_note" not in result


def test_v2_to_v3_idempotent_preserves_existing_note():
    """Running v2→v3 on an already-migrated cell (note present) is a no-op."""
    cell = {
        "filename_count": 5,
        "ocr_count": None,
        "note": "existing note",
        "note_status": "por_resolver",
    }
    original = cell.copy()
    result = migrate_cell_v2_to_v3(cell)
    assert result["note"] == "existing note"
    assert result["note_status"] == "por_resolver"
    assert result == original


def test_migrate_state_v2_to_v3_changed_then_idempotent():
    """First call returns changed=True; second call returns changed=False."""
    state = {
        "cells": {
            "HPV": {
                "odi": {"filename_count": 1, "ocr_count": None, "override_note": "initial"},
                "art": {"filename_count": 5, "ocr_count": None, "override_note": None},
            }
        }
    }
    result, changed = migrate_state_v2_to_v3(state)
    assert changed is True
    assert result["cells"]["HPV"]["odi"]["note"] == "initial"
    assert result["cells"]["HPV"]["odi"]["note_status"] == "resuelto"
    assert result["cells"]["HPV"]["art"]["note"] is None
    assert result["cells"]["HPV"]["art"]["note_status"] is None
    assert "override_note" not in result["cells"]["HPV"]["odi"]
    assert "override_note" not in result["cells"]["HPV"]["art"]

    # Second call: already migrated → changed=False
    _, changed2 = migrate_state_v2_to_v3(result)
    assert changed2 is False


def test_chained_v1_v2_then_v2_v3_idempotent_no_churn():
    # The real load path runs both migrations chained. After one full pass, a
    # SECOND full pass must report changed=False on BOTH steps (no override_note
    # re-introduced) — this is what stops _load_and_migrate from rewriting the DB
    # on every load. It is the guarantee that justifies relinquishing override_note
    # from v1→v2.
    state = {
        "cells": {
            "HRB": {"odi": {"count": 4, "override_note": "x"}},
        }
    }
    state, c1 = migrate_state_v1_to_v2(state)
    state, c2 = migrate_state_v2_to_v3(state)
    assert (c1 or c2) is True
    cell = state["cells"]["HRB"]["odi"]
    assert "override_note" not in cell
    assert cell["note"] == "x"
    assert cell["note_status"] == "resuelto"
    # Second full chained pass: zero changes → no DB rewrite.
    state, c1b = migrate_state_v1_to_v2(state)
    state, c2b = migrate_state_v2_to_v3(state)
    assert c1b is False
    assert c2b is False
