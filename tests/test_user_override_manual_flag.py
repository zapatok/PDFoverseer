"""apply_user_override accepts manual flag and persists cell.manual_entry."""

from pathlib import Path

import pytest

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def mgr_session(tmp_path):
    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    sid = sid_state["session_id"]
    yield mgr, sid
    close_all()


def test_manual_flag_sets_manual_entry_true(mgr_session):
    mgr, sid = mgr_session
    mgr.apply_user_override(sid, "HLL", "reunion", value=12, note=None, manual=True)
    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HLL"]["reunion"]
    assert cell["user_override"] == 12
    assert cell["manual_entry"] is True


def test_default_manual_flag_false_preserves_legacy_behavior(mgr_session):
    mgr, sid = mgr_session
    mgr.apply_user_override(sid, "HRB", "art", value=5, note="ajuste")
    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["art"]
    assert cell["user_override"] == 5
    assert cell.get("manual_entry") is False
