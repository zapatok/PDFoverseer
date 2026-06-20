"""Two-participant presence integration test (M2).

Verifies that two clients sharing the same in-process app instance see each
other's focus state and that leave removes a participant from the snapshot.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def test_two_participants_see_each_other():
    with TestClient(create_app()) as c:
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "Daniel", "color": "#a"},
        )
        r = c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p2", "name": "Carla", "color": "#b"},
        )
        assert {p["participant_id"] for p in r.json()["participants"]} == {"p1", "p2"}

        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p2", "cell": "HRB|odi"},
        )
        r = c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "Daniel", "color": "#a"},
        )
        carla = next(p for p in r.json()["participants"] if p["participant_id"] == "p2")
        assert carla["focused_cell"] == "HRB|odi"

        c.post(
            "/api/sessions/2026-04/presence/leave",
            json={"participant_id": "p2"},
        )
        r = c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "Daniel", "color": "#a"},
        )
        assert {p["participant_id"] for p in r.json()["participants"]} == {"p1"}
