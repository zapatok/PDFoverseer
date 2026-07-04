"""Dismiss endpoint for anti-colados suspects (spec §6): M3-gated, 404 on an
unknown id (so dismissing twice → 404), and it recomputes all_reliable.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from core.scanners.base import ConfidenceLevel, ScanResult, ScanTelemetry
from core.scanners.utils.colado_guard import find_foreign_filename_suspects


def _seed_suspect(mgr, tmp_path):
    """Open a session and seed HRB|chps with one counted foreign-file suspect.
    Returns the suspect id."""
    mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    susp = find_foreign_filename_suspects(["2026-05_odi_x.pdf"], "chps")
    result = ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"crs.pdf": 1, "2026-05_odi_x.pdf": 1},
        telemetry=ScanTelemetry(
            colado_suspects=susp, present_files=["crs.pdf", "2026-05_odi_x.pdf"]
        ),
    )
    mgr.apply_filename_result("2026-04", "HRB", "chps", result)
    return susp[0]["id"]


def test_dismiss_removes_suspect_and_returns_open_list(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "dismiss.db"))
    app = create_app()
    with TestClient(app) as c:
        sid = _seed_suspect(app.state.manager, tmp_path)
        r = c.post(f"/api/sessions/2026-04/cells/HRB/chps/colado-suspects/{sid}/dismiss", json={})
        assert r.status_code == 200
        assert r.json()["colado_suspects"] == []
        # And the GET payload no longer shows it.
        cell = c.get("/api/sessions/2026-04").json()["cells"]["HRB"]["chps"]
        assert cell["colado_suspects"] == []


def test_dismiss_twice_second_is_404(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "dismiss2.db"))
    app = create_app()
    with TestClient(app) as c:
        sid = _seed_suspect(app.state.manager, tmp_path)
        first = c.post(
            f"/api/sessions/2026-04/cells/HRB/chps/colado-suspects/{sid}/dismiss", json={}
        )
        assert first.status_code == 200
        second = c.post(
            f"/api/sessions/2026-04/cells/HRB/chps/colado-suspects/{sid}/dismiss", json={}
        )
        assert second.status_code == 404


def test_dismiss_unknown_id_404(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "dismiss3.db"))
    app = create_app()
    with TestClient(app) as c:
        _seed_suspect(app.state.manager, tmp_path)
        r = c.post(
            "/api/sessions/2026-04/cells/HRB/chps/colado-suspects/cs_deadbeef00/dismiss", json={}
        )
        assert r.status_code == 404


def test_dismiss_409_when_locked_by_another(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "dismiss409.db"))
    app = create_app()
    with TestClient(app) as c:
        sid = _seed_suspect(app.state.manager, tmp_path)
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p2", "name": "Carla", "color": "#b"},
        )
        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p2", "cell": "HRB|chps"},
        )
        r = c.post(
            f"/api/sessions/2026-04/cells/HRB/chps/colado-suspects/{sid}/dismiss",
            json={"participant_id": "p1"},
        )
        assert r.status_code == 409
        assert r.json()["lock_holder"]["name"] == "Carla"
