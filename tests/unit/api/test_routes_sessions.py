import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.sessions import get_manager, router
from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    conn = open_connection(tmp_path / "api_sessions.db")
    init_schema(conn)
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    app.include_router(router, prefix="/api")
    yield TestClient(app)
    close_all()


def test_create_session(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.post("/api/sessions", json={"year": 2026, "month": 4})
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["session_id"] == "2026-04"


def test_get_session(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    response = client.get("/api/sessions/2026-04")
    assert response.status_code == 200
    assert response.json()["session_id"] == "2026-04"


def test_scan_session_populates_cells(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    response = client.post("/api/sessions/2026-04/scan", json={"scope": "all"})
    assert response.status_code == 200
    state = client.get("/api/sessions/2026-04").json()
    assert "cells" in state
    assert "HPV" in state["cells"]


def test_patch_worker_count_persists(client, monkeypatch, tmp_path):
    # Use tmp_path as root so the charla folder doesn't contain real PDFs →
    # present_files=None (legacy: sum-all), worker_count == sum of synthetic marks.
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={
            "marks": {"a.pdf": [{"page": 1, "count": 12}]},
            "status": "en_progreso",
            "cursor": {"file": 0, "page": 1},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["worker_status"] == "en_progreso"
    assert body["worker_count"] == 12


def test_patch_worker_count_rejects_bad_status(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"status": "no-es-valido"},
    )
    assert r.status_code == 422


def test_patch_worker_count_session_404(client):
    # Sin crear la sesión: apply_worker_count → KeyError → 404.
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"status": "terminado"},
    )
    assert r.status_code == 404
