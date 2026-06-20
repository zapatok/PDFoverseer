"""Tests for M3a write-lock enforcement in SessionManager (Task 3) and route
409 handler (Task 4).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.presence import CellLockedError


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_manager(tmp_path):
    from api.state import SessionManager
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    return SessionManager(conn=conn)


def _make_session(mgr, tmp_path) -> str:
    """Create session 2026-04 in the DB; returns the session_id."""
    from pathlib import Path

    state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    return state["session_id"]


# ── Task 3: manager-level enforcement ────────────────────────────────────────


def test_write_to_cell_held_by_another_raises(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")  # Carla holds HRB|odi
    with pytest.raises(CellLockedError):
        mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")


def test_editor_can_write_its_own_cell(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")
    # no raise — the editor can write its own cell
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")


def test_free_cell_and_no_participant_id_are_unenforced(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    # free cell with a participant_id → ok
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")
    # legacy call with no participant_id → always ok
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5)


def test_check_cell_lock_gate(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    with pytest.raises(CellLockedError):
        mgr.check_cell_lock("2026-04", "HRB", "odi", "p1")
    mgr.check_cell_lock("2026-04", "HRB", "odi", "p2")  # editor: no raise
    mgr.check_cell_lock("2026-04", "HRB", "art", "p1")  # free: no raise


def test_set_note_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    with pytest.raises(CellLockedError):
        mgr.set_note(
            "2026-04", "HRB", "odi", text="hello", status="por_resolver", participant_id="p1"
        )


def test_apply_worker_count_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|charla")
    with pytest.raises(CellLockedError):
        mgr.apply_worker_count("2026-04", "HRB", "charla", status="terminado", participant_id="p1")


def test_apply_confirmed_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    # apply_user_override with p2 (the editor) creates the cell
    mgr.apply_user_override("2026-04", "HRB", "odi", value=3, participant_id="p2")
    with pytest.raises(CellLockedError):
        mgr.apply_confirmed("2026-04", "HRB", "odi", confirmed=True, participant_id="p1")


def test_clear_near_matches_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    with pytest.raises(CellLockedError):
        mgr.clear_near_matches("2026-04", "HRB", "odi", participant_id="p1")


def test_apply_per_file_override_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    # create the cell first (p2 is editor so no conflict)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=1, participant_id="p2")
    with pytest.raises(CellLockedError):
        mgr.apply_per_file_override("2026-04", "HRB", "odi", "doc.pdf", 2, "p1")


# ── Task 4: endpoint 409 ──────────────────────────────────────────────────────


def test_override_endpoint_409_when_locked_by_another():
    with TestClient(create_app()) as c:
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p2", "name": "Carla", "color": "#b"},
        )
        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p2", "cell": "HRB|odi"},
        )
        r = c.patch(
            "/api/sessions/2026-04/cells/HRB/odi/override",
            json={"value": 5, "participant_id": "p1"},
        )
        assert r.status_code == 409
        assert r.json()["lock_holder"]["name"] == "Carla"
