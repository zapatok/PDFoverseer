"""Tests for M3a lock semantics in PresenceRegistry and SessionManager."""

from api.presence import PresenceRegistry


def _reg():
    return PresenceRegistry(now=lambda: 1000.0)


def test_first_to_focus_a_free_cell_is_editor():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.focus("m", "p1", "HRB|odi")
    rec = next(p for p in r.snapshot("m") if p["participant_id"] == "p1")
    assert rec["mode"] == "editor"
    assert rec["focused_cell"] == "HRB|odi"


def test_second_to_focus_held_cell_is_viewer_holder_keeps_editor():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.heartbeat("m", "p2", name="C", color="#b")
    r.focus("m", "p1", "HRB|odi")  # p1 editor
    r.focus("m", "p2", "HRB|odi")  # p2 joins -> viewer
    snap = {p["participant_id"]: p for p in r.snapshot("m")}
    assert snap["p1"]["mode"] == "editor"
    assert snap["p2"]["mode"] == "viewer"


def test_lock_holder_reports_the_editor_excluding_self():
    r = _reg()
    r.heartbeat("m", "p1", name="Daniel", color="#a")
    r.heartbeat("m", "p2", name="Carla", color="#b")
    r.focus("m", "p1", "HRB|odi")
    assert r.lock_holder("m", "HRB|odi", exclude="p2")["participant_id"] == "p1"
    assert r.lock_holder("m", "HRB|odi", exclude="p1") is None
    assert r.lock_holder("m", "HRB|art", exclude="p2") is None  # free cell


def test_releasing_a_cell_frees_the_lock():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.focus("m", "p1", "HRB|odi")  # editor
    r.focus("m", "p1", None)  # back to month view
    assert r.lock_holder("m", "HRB|odi", exclude="p2") is None


def test_moving_to_another_cell_frees_the_previous():
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.focus("m", "p1", "HRB|odi")
    r.focus("m", "p1", "HRB|art")
    assert r.lock_holder("m", "HRB|odi", exclude="p2") is None
    assert r.lock_holder("m", "HRB|art", exclude="p2")["participant_id"] == "p1"


def test_viewer_reclaims_as_editor_after_holder_leaves():
    # Design decision 4: gating auto-recovers when the holder leaves. A viewer who
    # re-focuses a now-free cell must be promoted to editor.
    r = _reg()
    r.heartbeat("m", "p1", name="D", color="#a")
    r.heartbeat("m", "p2", name="C", color="#b")
    r.focus("m", "p1", "HRB|odi")  # p1 editor
    r.focus("m", "p2", "HRB|odi")  # p2 viewer
    r.leave("m", "p1")  # editor leaves -> cell is free
    r.focus("m", "p2", "HRB|odi")  # p2 re-focuses the now-free cell
    rec = next(p for p in r.snapshot("m") if p["participant_id"] == "p2")
    assert rec["mode"] == "editor"
    # from p2's own perspective no one else holds it; p2 is now the editor of record
    assert r.lock_holder("m", "HRB|odi", exclude="p2") is None
    assert r.lock_holder("m", "HRB|odi", exclude="p1")["participant_id"] == "p2"


# ── Task 2: SessionManager / CellLockedError ──────────────────────────────────


def test_cell_locked_error_attributes():
    from api.presence import CellLockedError

    holder = {"participant_id": "p1", "name": "Daniel", "color": "#a"}
    err = CellLockedError("HRB", "odi", holder)
    assert err.hospital == "HRB"
    assert err.sigla == "odi"
    assert err.holder is holder
    assert "Daniel" in str(err)


def _make_manager(tmp_path):
    from api.state import SessionManager
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    return SessionManager(conn=conn)


def test_manager_presence_lock_holder(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")  # p2 is editor

    # p1 calling lock_holder sees p2 as the holder
    holder = mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="p1")
    assert holder is not None
    assert holder["participant_id"] == "p2"
    assert holder["name"] == "Carla"

    # p2 excluding themselves -> free (no other editor)
    assert mgr.presence_lock_holder("2026-04", "HRB|odi", exclude="p2") is None

    # free cell
    assert mgr.presence_lock_holder("2026-04", "HRB|art", exclude="p1") is None


def test_manager_editor_conflict(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")  # p2 is editor

    # p1 writing -> conflict: p2 holds the cell
    conflict = mgr._editor_conflict("2026-04", "HRB", "odi", "p1")
    assert conflict is not None
    assert conflict["participant_id"] == "p2"

    # p2 writing its own cell -> no conflict (exclude matches)
    assert mgr._editor_conflict("2026-04", "HRB", "odi", "p2") is None

    # free cell
    assert mgr._editor_conflict("2026-04", "HRB", "art", "p1") is None

    # legacy: participant_id=None -> no enforcement
    assert mgr._editor_conflict("2026-04", "HRB", "odi", None) is None
