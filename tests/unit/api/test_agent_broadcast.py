"""Tests for M3b Task 4: write routes broadcast Claude's presence after an agent write.

Covers:
- agent override endpoint → 200 (free cell, auto-claim)
- agent override endpoint → 409 when a human holds the cell
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app

# ── Task 4: endpoint tests ────────────────────────────────────────────────────


def test_agent_override_endpoint_200_on_free_cell(tmp_path, monkeypatch):
    """Agent PATCH /override on a free cell → 200 (auto-claims, no conflict)."""
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "agent_broadcast_free.db"))
    app = create_app()
    with TestClient(app) as c:
        # 2026-07 isolation fix: the override endpoint 404s unless the session
        # already exists — open it explicitly (the real DB used to have it
        # pre-opened from prior usage, which this test was silently relying on).
        app.state.manager.open_session(year=2026, month=4, month_root=Path(tmp_path))
        r = c.patch(
            "/api/sessions/2026-04/cells/HRB/odi/override",
            json={"value": 3, "participant_id": "claude"},
        )
        assert r.status_code == 200


def test_agent_override_endpoint_409_when_human_holds(tmp_path, monkeypatch):
    """Agent PATCH /override on a human-held cell → 409 with lock_holder.name."""
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "agent_broadcast_held.db"))
    app = create_app()
    with TestClient(app) as c:
        # 2026-07 isolation fix: see test_agent_override_endpoint_200_on_free_cell.
        app.state.manager.open_session(year=2026, month=4, month_root=Path(tmp_path))
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
