from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.output import router as output_router
from api.routes.sessions import get_manager
from api.routes.sessions import router as sessions_router
from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path / "outputs"))
    app = FastAPI()
    conn = open_connection(tmp_path / "out.db")
    init_schema(conn)
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    app.include_router(sessions_router, prefix="/api")
    app.include_router(output_router, prefix="/api")
    yield TestClient(app)
    close_all()


def test_generate_output_creates_xlsx(client, tmp_path):
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.post("/api/sessions/2026-04/scan", json={"scope": "all"})
    response = client.post("/api/sessions/2026-04/output", json={})
    assert response.status_code == 200
    data = response.json()
    assert Path(data["output_path"]).exists()
    assert data["output_path"].endswith(".xlsx")
