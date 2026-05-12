import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.months import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_get_months_returns_list(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.get("/api/months")
    assert response.status_code == 200
    data = response.json()
    assert "months" in data
    assert any(m["name"] == "ABRIL" for m in data["months"])


def test_get_month_returns_inventory(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.get("/api/months/2026-04")
    assert response.status_code == 200
    inv = response.json()
    assert "hospitals_present" in inv
    assert len(inv["hospitals_present"]) >= 3
