"""PATCH /api/sessions/{id}/cells/{h}/{s}/files/{f}/override endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.scanners.base import ConfidenceLevel, ScanResult


@pytest.fixture
def client_with_seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    with TestClient(app) as c:
        # Open a session directly via POST (uses a tmp month_root so no real
        # folder resolution is needed — open_session accepts any Path).
        from api.state import SessionManager
        from core.db.connection import open_connection
        from core.db.migrations import init_schema

        mgr = app.state.manager
        # Open a session by calling the manager directly so we control month_root.
        from pathlib import Path

        sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
        sid = sid_state["session_id"]
        # Seed one cell with per_file data so override has something to work with.
        mgr.apply_filename_result(
            sid,
            "HRB",
            "odi",
            ScanResult(
                count=1,
                confidence=ConfidenceLevel.HIGH,
                method="filename_glob",
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=5,
                files_scanned=1,
                per_file={"a.pdf": 5},
            ),
        )
        yield c, sid


def test_patch_per_file_override_writes_value(client_with_seeded):
    client, sid = client_with_seeded
    r = client.patch(
        f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/override",
        json={"count": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["filename"] == "a.pdf"
    assert body["count"] == 10
    assert body["new_cell_count"] == 10


def test_patch_per_file_override_404_unknown_cell(client_with_seeded):
    client, sid = client_with_seeded
    r = client.patch(
        f"/api/sessions/{sid}/cells/HXX/yyy/files/whatever.pdf/override",
        json={"count": 5},
    )
    assert r.status_code == 404
