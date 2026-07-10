import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.months import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


@pytest.mark.corpus
def test_get_months_returns_list(client, monkeypatch):
    """Lists real folders under the corpus root (ABRIL's presence) — needs the live corpus."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.get("/api/months")
    assert response.status_code == 200
    data = response.json()
    assert "months" in data
    assert any(m["name"] == "ABRIL" for m in data["months"])


@pytest.mark.corpus
def test_get_month_returns_inventory(client, monkeypatch):
    """Checks hospitals_present count against the real ABRIL corpus — needs the live corpus."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    response = client.get("/api/months/2026-04")
    assert response.status_code == 200
    inv = response.json()
    assert "hospitals_present" in inv
    assert len(inv["hospitals_present"]) >= 3


def test_months_chronological(client, tmp_path, monkeypatch):
    """Months come back in (year, month) order, not folder-name order (M1:
    alphabetical gave ABRIL, JUNIO, MAYO)."""
    for name in ("ABRIL", "JUNIO", "MAYO", "FEBRERO"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    response = client.get("/api/months")
    assert response.status_code == 200
    nums = [m["month"] for m in response.json()["months"]]
    assert nums == [2, 4, 5, 6], f"months not chronological: {nums}"
