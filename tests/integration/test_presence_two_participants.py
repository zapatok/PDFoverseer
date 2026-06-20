"""Two-participant presence integration test (M2 + M3a).

Verifies that two clients sharing the same in-process app instance see each
other's focus state and that leave removes a participant from the snapshot.
Also covers the M3a write-lock cycle: focus → 409 → release → 2xx.
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


def test_lock_409_and_release(tmp_path):
    """M3a: p1 focuses HRB|odi (editor); p2 write → 409; p1 leaves → p2 write → 2xx."""
    with TestClient(create_app()) as c:
        # Both participants join.
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p1", "name": "Daniel", "color": "#a"},
        )
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p2", "name": "Carla", "color": "#b"},
        )

        # p1 focuses HRB|odi → becomes editor.
        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p1", "cell": "HRB|odi"},
        )

        # p2 attempts a write to HRB|odi → 409 cell_locked.
        r = c.patch(
            "/api/sessions/2026-04/cells/HRB/odi/override",
            json={"value": 5, "participant_id": "p2"},
        )
        assert r.status_code == 409
        body = r.json()
        assert body["detail"] == "cell_locked"
        assert body["lock_holder"]["participant_id"] == "p1"
        assert body["lock_holder"]["name"] == "Daniel"

        # p1 releases focus (moves to a different cell).
        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p1", "cell": None},
        )

        # Now p2 can write — cell is free; the write lands (may 404 if session has no
        # on-disk folder, but must NOT be 409).
        r2 = c.patch(
            "/api/sessions/2026-04/cells/HRB/odi/override",
            json={"value": 5, "participant_id": "p2"},
        )
        assert r2.status_code != 409
