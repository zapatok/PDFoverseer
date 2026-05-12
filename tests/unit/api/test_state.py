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
    assert state["cells"]["HPV"]["art"]["count"] == 767
