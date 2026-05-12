"""Cell state migration FASE 1 → FASE 2."""

from __future__ import annotations

from core.state.migrations import migrate_cell_v1_to_v2, migrate_state_v1_to_v2


def test_migrate_cell_renames_count_to_filename_count():
    cell = {"count": 5, "confidence": "high", "method": "filename_glob"}
    result = migrate_cell_v1_to_v2(cell)
    assert result["filename_count"] == 5
    assert "count" not in result
    assert result["ocr_count"] is None
    assert result["override_note"] is None


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
    assert result["override_note"] is None


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
