"""Integration tests for M3b: scanner lock-skip policy.

Task 5: pase-2 OCR scanner claims cells as the Claude agent and skips human-held cells.
Task 6: pase-1 filename scan skips cells under live human edit.

These tests bypass the actual OCR pipeline (no real PDFs are needed for the
lock/skip logic) and operate directly on the SessionManager + PresenceRegistry
layer, plus the FastAPI TestClient for the pase-1 HTTP route.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.presence import AGENT_PARTICIPANT_ID, PresenceRegistry
from api.state import SessionManager
from core.db.connection import open_connection
from core.db.migrations import init_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path) -> SessionManager:
    """Build a real SessionManager backed by a temp SQLite DB."""
    conn = open_connection(tmp_path / "test_m3b.db")
    init_schema(conn)
    return SessionManager(conn=conn)


def _register_human(
    registry: PresenceRegistry,
    session_id: str,
    pid: str = "human-1",
    name: str = "Daniel",
    color: str = "#a",
) -> None:
    registry.heartbeat(session_id, pid, name=name, color=color, kind="human")


# ---------------------------------------------------------------------------
# Unit-level: PresenceRegistry.agent_focus
# ---------------------------------------------------------------------------


def test_skip_path_human_holds_cell(tmp_path):
    """agent_focus returns the holder's snapshot when a human editor holds the cell."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    # Register a human participant and focus them on the cell.
    registry: PresenceRegistry = mgr._presence  # type: ignore[attr-defined]
    _register_human(registry, session_id, pid="human-1", name="Daniel", color="#a")
    registry.focus(session_id, "human-1", "HRB|odi")

    # agent_focus should detect the human editor and return their public snapshot.
    holder = mgr.agent_claim_cell(session_id, "HRB", "odi")

    assert holder is not None
    assert holder["participant_id"] == "human-1"
    assert holder["name"] == "Daniel"
    assert holder["mode"] == "editor"
    # The agent must NOT have been registered (it was skipped).
    snapshot = mgr.presence_snapshot(session_id)
    pids = {p["participant_id"] for p in snapshot}
    assert AGENT_PARTICIPANT_ID not in pids


def test_claim_path_free_cell(tmp_path):
    """agent_focus returns None and registers the agent when the cell is free."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    holder = mgr.agent_claim_cell(session_id, "HRB", "odi")

    assert holder is None
    snapshot = mgr.presence_snapshot(session_id)
    pids = {p["participant_id"] for p in snapshot}
    assert AGENT_PARTICIPANT_ID in pids
    agent = next(p for p in snapshot if p["participant_id"] == AGENT_PARTICIPANT_ID)
    assert agent["kind"] == "agent"
    assert agent["focused_cell"] == "HRB|odi"
    assert agent["mode"] == "editor"


def test_inertness_no_participants(tmp_path):
    """agent_claim_cell succeeds (returns None) when there are zero participants."""
    mgr = _make_manager(tmp_path)
    result = mgr.agent_claim_cell("2026-05", "HPV", "charla")
    assert result is None


def test_scan_cancelled_releases_agent_no_skipped_field(tmp_path):
    """agent_leave removes the agent from the roster."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    # Claim a cell.
    mgr.agent_claim_cell(session_id, "HRB", "odi")
    before = {p["participant_id"] for p in mgr.presence_snapshot(session_id)}
    assert AGENT_PARTICIPANT_ID in before

    # Release.
    changed = mgr.agent_leave(session_id)
    assert changed is True
    after = {p["participant_id"] for p in mgr.presence_snapshot(session_id)}
    assert AGENT_PARTICIPANT_ID not in after


def test_skip_then_claim_next_cell(tmp_path):
    """Agent skips a human-held cell, then claims the next free cell."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    registry: PresenceRegistry = mgr._presence  # type: ignore[attr-defined]
    _register_human(registry, session_id, pid="human-1", name="Daniel", color="#a")
    registry.focus(session_id, "human-1", "HRB|odi")

    # First cell is held — skip.
    holder_odi = mgr.agent_claim_cell(session_id, "HRB", "odi")
    assert holder_odi is not None  # skip

    # Second cell is free — claim.
    holder_charla = mgr.agent_claim_cell(session_id, "HRB", "charla")
    assert holder_charla is None  # claimed

    snapshot = mgr.presence_snapshot(session_id)
    agent = next(p for p in snapshot if p["participant_id"] == AGENT_PARTICIPANT_ID)
    assert agent["focused_cell"] == "HRB|charla"


# ---------------------------------------------------------------------------
# HTTP-level: pase-1 scan skips human-held cells (Task 6)
# ---------------------------------------------------------------------------


def test_pase1_skips_human_held_cell(tmp_path, monkeypatch):
    """POST /api/sessions/{id}/scan skips a cell that a human currently holds.

    This test stubs scan_month so no real filesystem enumeration or OCR occurs.
    The presence state is seeded directly via the HTTP heartbeat + focus endpoints.
    The scan response must include the skipped cell in the ``skipped`` list and
    must NOT have applied the result for that cell.
    """
    # Point the app at a temp folder and DB.
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_pase1.db"))

    # Create a fake month folder so the scan route doesn't 404.
    month_root = tmp_path / "ABRIL"
    cell_dir = month_root / "HRB" / "3.-ODI Visitas"
    cell_dir.mkdir(parents=True)

    # Stub scan_month to return a fake result for HRB|odi without touching disk.
    from core.scanners.base import ConfidenceLevel, ScanResult

    fake_result = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=0,
        files_scanned=1,
        per_file={"fake.pdf": 5},
    )

    import api.routes.sessions as sessions_mod

    def _stub_scan_month(_inv):
        return {("HRB", "odi"): fake_result}

    monkeypatch.setattr(sessions_mod, "scan_month", _stub_scan_month)

    app = create_app()
    with TestClient(app) as c:
        # Open the session.
        r = c.post("/api/sessions", json={"year": 2026, "month": 4})
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]

        # Register a human and focus them on HRB|odi.
        c.post(
            f"/api/sessions/{sid}/presence/heartbeat",
            json={"participant_id": "human-1", "name": "Daniel", "color": "#a"},
        )
        c.post(
            f"/api/sessions/{sid}/presence/focus",
            json={"participant_id": "human-1", "cell": "HRB|odi"},
        )

        # Trigger pase-1 scan.
        r2 = c.post(f"/api/sessions/{sid}/scan")
        assert r2.status_code == 200, r2.text
        body = r2.json()

        # The cell was skipped — it must appear in ``skipped``.
        assert "skipped" in body
        skipped = body["skipped"]
        assert any(s["hospital"] == "HRB" and s["sigla"] == "odi" for s in skipped), (
            f"Expected HRB|odi in skipped, got: {skipped}"
        )

        # The scanned count must be 0 (1 result - 1 skipped).
        assert body["scanned"] == 0

        # The session state for HRB|odi must NOT have the fake count applied.
        r3 = c.get(f"/api/sessions/{sid}")
        assert r3.status_code == 200, r3.text
        cells = r3.json().get("cells", {})
        odi_cell = cells.get("HRB", {}).get("odi", {})
        # The cell should not have count=5 from the stub (it was skipped).
        assert odi_cell.get("count") != 5, "apply_cell_result should have been skipped for HRB|odi"
