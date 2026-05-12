import json
from pathlib import Path

import pytest

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def conn(tmp_path):
    conn = open_connection(tmp_path / "api.db")
    init_schema(conn)
    yield conn
    close_all()


def test_open_session_creates_new_if_not_exists(conn):
    mgr = SessionManager(conn=conn)
    state = mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    assert state["session_id"] == "2026-04"
    assert state["month_root"] == "A:/informe mensual/ABRIL"


def test_open_session_returns_existing(conn):
    mgr = SessionManager(conn=conn)
    s1 = mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    s2 = mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    assert s1["session_id"] == s2["session_id"]


def test_apply_cell_result_persists(conn):
    from core.scanners.base import ConfidenceLevel, ScanResult

    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    result = ScanResult(
        count=767,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=767,
    )
    mgr.apply_cell_result("2026-04", "HPV", "art", result)
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HPV"]["art"]["filename_count"] == 767


# Tests for the three new fine-grained setters


@pytest.fixture
def manager(tmp_path):

    conn = open_connection(tmp_path / "v2.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    yield mgr
    close_all()


def _filename_result(count: int):
    from core.scanners.base import ConfidenceLevel, ScanResult

    return ScanResult(
        count=count,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=count,
        duration_ms=10,
    )


def _ocr_result(count: int, method: str = "header_detect"):
    from core.scanners.base import ConfidenceLevel, ScanResult

    return ScanResult(
        count=count,
        confidence=ConfidenceLevel.HIGH,
        method=method,
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=1,
        duration_ms=23000,
    )


def test_apply_filename_result_sets_filename_count_only(manager):
    manager.apply_filename_result("2026-04", "HPV", "art", _filename_result(767))
    state = manager.get_session_state("2026-04")
    cell = state["cells"]["HPV"]["art"]
    assert cell["filename_count"] == 767
    assert cell["ocr_count"] is None
    assert cell["user_override"] is None
    assert cell["override_note"] is None
    assert cell["method"] == "filename_glob"
    assert cell["duration_ms_filename"] == 10
    # Lock the isolation contract from both sides — filename pass never sets OCR duration
    assert cell.get("duration_ms_ocr") is None


def test_apply_ocr_result_sets_ocr_count_and_method_without_touching_filename(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_ocr_result("2026-04", "HRB", "odi", _ocr_result(17, "header_detect"))
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["filename_count"] == 1
    assert cell["ocr_count"] == 17
    assert cell["method"] == "header_detect"
    assert cell["duration_ms_ocr"] == 23000


def test_apply_ocr_result_with_filename_glob_fallback_method(manager):
    # OCR scanner failed internally, fell back to filename_glob
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    fallback = _ocr_result(1, "filename_glob")
    manager.apply_ocr_result("2026-04", "HRB", "odi", fallback)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["ocr_count"] == 1
    assert cell["method"] == "filename_glob"


def test_apply_user_override_sets_value_and_note(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_user_override("2026-04", "HRB", "odi", value=17, note="17 ODIs in 1 PDF")
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["user_override"] == 17
    assert cell["override_note"] == "17 ODIs in 1 PDF"
    assert cell["filename_count"] == 1  # untouched


def test_apply_user_override_with_null_value_clears_override(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_user_override("2026-04", "HRB", "odi", value=17, note="initial")
    manager.apply_user_override("2026-04", "HRB", "odi", value=None, note=None)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["user_override"] is None
    assert cell["override_note"] is None


def test_apply_user_override_can_be_used_before_any_scan(manager):
    manager.apply_user_override("2026-04", "HPV", "chps", value=2, note="manual count")
    cell = manager.get_session_state("2026-04")["cells"]["HPV"]["chps"]
    assert cell["filename_count"] is None
    assert cell["ocr_count"] is None
    assert cell["user_override"] == 2


def test_get_session_state_migrates_legacy_count_on_first_read(manager, tmp_path):
    # Inject legacy state directly via raw connection
    from core.db.sessions_repo import update_session_state

    legacy_state = {
        "month_root": str(tmp_path),
        "hospitals_present": ["HPV"],
        "hospitals_missing": [],
        "cells": {"HPV": {"art": {"count": 767, "confidence": "high", "method": "filename_glob"}}},
    }
    update_session_state(manager._conn, "2026-04", state_json=json.dumps(legacy_state))
    cell = manager.get_session_state("2026-04")["cells"]["HPV"]["art"]
    assert cell["filename_count"] == 767
    assert "count" not in cell
    assert cell["ocr_count"] is None
    assert cell["override_note"] is None
    # Idempotent: second read returns the same
    cell2 = manager.get_session_state("2026-04")["cells"]["HPV"]["art"]
    assert cell2 == cell
