"""Presence endpoints — unit tests (M2).

Presence state is in-process/in-memory; each test creates its own app instance so
registries are fully isolated. No ``POST /api/sessions`` needed — presence is keyed
by session_id string and does not require a persisted session in the DB.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def _client():
    return TestClient(create_app())


def test_heartbeat_returns_snapshot():
    with _client() as c:
        r = c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "Daniel", "color": "#e5484d"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "presence"
        assert body["participants"][0]["participant_id"] == "p1"


def test_focus_then_heartbeat_reflects_cell():
    with _client() as c:
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "D", "color": "#x"},
        )
        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p1", "cell": "HRB|odi"},
        )
        r = c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "D", "color": "#x"},
        )
        me = next(p for p in r.json()["participants"] if p["participant_id"] == "p1")
        assert me["focused_cell"] == "HRB|odi"


def test_leave_removes_participant():
    with _client() as c:
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "D", "color": "#x"},
        )
        c.post(
            "/api/sessions/2026-04/presence/leave",
            json={"participant_id": "p1"},
        )
        r = c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p2", "name": "C", "color": "#y"},
        )
        assert {p["participant_id"] for p in r.json()["participants"]} == {"p2"}


def test_bad_session_id_400():
    with _client() as c:
        r = c.post(
            "/api/sessions/not-a-month/presence/heartbeat",
            json={"participant_id": "p1", "name": "D", "color": "#x"},
        )
        assert r.status_code == 400
