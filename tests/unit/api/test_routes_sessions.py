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


def test_patch_override_unknown_hospital_400(client, monkeypatch):
    # F13: an unknown hospital coordinate is a clean 400 (bad request), never a
    # phantom cell. Prevents the `no_existe`-in-DB hole at the route boundary.
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/BOGUS/odi/override",
        json={"value": 1},
    )
    assert r.status_code == 400


def test_patch_worker_count_unknown_sigla_400(client, monkeypatch):
    # F13: an unknown sigla coordinate is rejected with 400 before any state write.
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HPV/FAKE/worker-count",
        json={"status": "terminado"},
    )
    assert r.status_code == 400


def test_get_session_enriches_worker_count_present_filtered(client, monkeypatch, tmp_path):
    """F1/Task 2.1: GET session carries a canonical present-filtered ``worker_count``
    on every worker/checks cell. Marks for files no longer on disk (orphans) are
    excluded; document siglas carry NO ``worker_count`` key."""
    charla_dir = tmp_path / "ABRIL" / "HLL" / "4.-Charlas"
    charla_dir.mkdir(parents=True)
    (charla_dir / "real.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    # real.pdf is present on disk (counted); gone.pdf is an orphan (excluded).
    client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={
            "marks": {
                "real.pdf": [{"page": 1, "count": 5}],
                "gone.pdf": [{"page": 1, "count": 9}],
            }
        },
    )
    state = client.get("/api/sessions/2026-04").json()
    charla = state["cells"]["HLL"]["charla"]
    assert charla["worker_count"] == 5  # gone.pdf orphan excluded, real.pdf counted
    # A document sigla (odi) is seeded by the v3→v4 reconcile but carries no worker_count.
    assert "worker_count" not in state["cells"]["HLL"]["odi"]


def test_reconcile_worker_marks_migrate_returns_enriched(client, monkeypatch, tmp_path):
    """F1/Task 2.3: migrate re-keys the orphan onto a present file, response is the
    enriched cell (present-filtered worker_count included)."""
    charla_dir = tmp_path / "ABRIL" / "HLL" / "4.-Charlas"
    charla_dir.mkdir(parents=True)
    (charla_dir / "new.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"marks": {"old.pdf": [{"page": 1, "count": 7}]}},
    )
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "migrate", "from_file": "old.pdf", "to_file": "new.pdf"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "old.pdf" not in body["worker_marks"]
    assert body["worker_marks"]["new.pdf"] == [{"page": 1, "count": 7}]
    assert body["worker_count"] == 7  # migrated onto a present file → now counted


def test_reconcile_migrate_without_to_file_400(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "migrate", "from_file": "old.pdf"},
    )
    assert r.status_code == 400


def test_reconcile_bad_action_400(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "explode", "from_file": "old.pdf"},
    )
    assert r.status_code == 400


def test_reconcile_unknown_from_file_404(client, monkeypatch, tmp_path):
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"marks": {"a.pdf": [{"page": 1, "count": 1}]}},
    )
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "discard", "from_file": "nope.pdf"},
    )
    assert r.status_code == 404
