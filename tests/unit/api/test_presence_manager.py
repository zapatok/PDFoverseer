from api.state import SessionManager


def test_manager_presence_roundtrip(tmp_path):
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    assert mgr.presence_heartbeat("2026-04", "p1", name="D", color="#x") is True
    assert mgr.presence_focus("2026-04", "p1", "HRB|odi") is True
    snap = mgr.presence_snapshot("2026-04")
    assert snap[0]["focused_cell"] == "HRB|odi"
    assert mgr.presence_leave("2026-04", "p1") is True
    assert mgr.presence_snapshot("2026-04") == []
