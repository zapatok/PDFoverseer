"""apply_filename_result and apply_ocr_result persist per_file from ScanResult."""

from pathlib import Path

import pytest

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema
from core.scanners.base import ConfidenceLevel, ScanResult


@pytest.fixture
def mgr_session(tmp_path):
    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    sid = sid_state["session_id"]
    yield mgr, sid
    close_all()


def test_apply_filename_result_persists_per_file(mgr_session):
    mgr, sid = mgr_session
    result = ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=2,
        per_file={"a.pdf": 1, "b.pdf": 1},
    )
    mgr.apply_filename_result(sid, "HRB", "art", result)

    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["art"]
    assert cell["per_file"] == {"a.pdf": 1, "b.pdf": 1}
    assert cell["per_file_overrides"] == {}
    assert cell["manual_entry"] is False


def test_apply_ocr_result_persists_per_file(mgr_session):
    mgr, sid = mgr_session
    base = ScanResult(
        count=1,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=5,
        files_scanned=1,
        per_file={"compilacion.pdf": 1},
    )
    mgr.apply_filename_result(sid, "HRB", "odi", base)

    ocr_result = ScanResult(
        count=24,
        confidence=ConfidenceLevel.HIGH,
        method="header_detect",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=8000,
        files_scanned=1,
        per_file={"compilacion.pdf": 24},
    )
    mgr.apply_ocr_result(sid, "HRB", "odi", ocr_result)

    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["odi"]
    assert cell["per_file"] == {"compilacion.pdf": 24}
