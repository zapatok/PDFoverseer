"""Tests for M3b Task 4: write routes broadcast Claude's presence after an agent write.

Covers:
- agent override endpoint → 200 (free cell, auto-claim)
- agent override endpoint → 409 when a human holds the cell
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app

# ── Task 4: endpoint tests ────────────────────────────────────────────────────


def test_agent_override_endpoint_200_on_free_cell():
    """Agent PATCH /override on a free cell → 200 (auto-claims, no conflict)."""
    with TestClient(create_app()) as c:
        r = c.patch(
            "/api/sessions/2026-04/cells/HRB/odi/override",
            json={"value": 3, "participant_id": "claude"},
        )
        assert r.status_code == 200


def test_agent_override_endpoint_409_when_human_holds():
    """Agent PATCH /override on a human-held cell → 409 with lock_holder.name."""
    with TestClient(create_app()) as c:
        # Human p2 heartbeat + focus to claim the cell
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p2", "name": "Daniel", "color": "#a"},
        )
        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p2", "cell": "HRB|odi"},
        )
        # Agent tries to write → 409
        r = c.patch(
            "/api/sessions/2026-04/cells/HRB/odi/override",
            json={"value": 5, "participant_id": "claude"},
        )
        assert r.status_code == 409
        assert r.json()["lock_holder"]["name"] == "Daniel"
