"""M1 multiplayer — broadcast-on-write: cell_updated + session_refresh."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.sessions import _cell_updated_event, get_manager


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "mp_test.db"))
    return create_app()


def _recv_type(ws, expected_type, tries=5):
    """Lee frames del WS hasta hallar el tipo esperado (salta el keepalive ``ping``
    u otros eventos que lleguen antes). Evita flakes y mantiene TODOS los tests WS
    consistentes (un solo patrón de recepción)."""
    for _ in range(tries):
        evt = json.loads(ws.receive_text())
        if evt.get("type") == expected_type:
            return evt
    raise AssertionError(f"no se recibió {expected_type} en {tries} frames")


def test_cell_updated_event_carries_full_cell(app) -> None:
    """_cell_updated_event devuelve el snapshot COMPLETO de la celda (no parcial)."""
    with TestClient(app) as client:  # noqa: F841 — starts lifespan so app.state.manager exists
        mgr = app.state.manager
        mgr.open_session(year=2026, month=4, month_root=__import__("pathlib").Path("."))
        mgr.apply_user_override("2026-04", "HPV", "odi", value=7)
        mgr.set_note("2026-04", "HPV", "odi", text="ojo", status="por_resolver")

        event = _cell_updated_event(mgr, "2026-04", "HPV", "odi")

        assert event["type"] == "cell_updated"
        assert event["hospital"] == "HPV"
        assert event["sigla"] == "odi"
        assert event["actor"] is None  # M1: sin identidad todavía
        # snapshot completo: incluye override Y note (un merge de 6 campos los perdería)
        assert event["cell"]["user_override"] == 7
        assert event["cell"]["note"] == "ojo"
        assert event["cell"]["note_status"] == "por_resolver"


def test_cell_updated_event_missing_cell_returns_none(app) -> None:
    """Celda ausente → None (no revienta)."""
    with TestClient(app) as client:  # noqa: F841
        mgr = app.state.manager
        mgr.open_session(year=2026, month=4, month_root=__import__("pathlib").Path("."))
        assert _cell_updated_event(mgr, "2026-04", "HPV", "nope") is None


def _open_session(client: TestClient) -> None:
    """Abre la sesión 2026-04 vía API (usa el corpus real montado en el repo)."""
    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    assert r.status_code == 200


def test_patch_override_broadcasts_cell_updated(app) -> None:
    """Un PATCH de override entrega cell_updated (celda completa) por el WS."""
    with TestClient(app) as client:
        _open_session(client)
        with client.websocket_connect("/ws/sessions/2026-04") as ws:
            r = client.patch(
                "/api/sessions/2026-04/cells/HPV/odi/override",
                json={"value": 9},
            )
            assert r.status_code == 200
            evt = _recv_type(ws, "cell_updated")
            assert evt["hospital"] == "HPV"
            assert evt["sigla"] == "odi"
            assert evt["cell"]["user_override"] == 9
