"""WS broadcast helper must deliver JSON events to all connections for a session."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.ws import broadcast


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "ws_test.db"))
    return create_app()


def test_broadcast_with_no_connections_is_noop(app) -> None:
    """No connections for session → broadcast returns without error."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(broadcast("nonexistent-session", {"type": "ping"}))
    finally:
        loop.close()


def test_ws_connect_and_receive_broadcast(app) -> None:
    """A connected WS receives broadcasts addressed to its session."""
    sess_id = "2026-04-prueba"
    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/sessions/{sess_id}") as ws:
            loop = app.state.loop
            future = asyncio.run_coroutine_threadsafe(
                broadcast(sess_id, {"type": "cell_scanning", "hospital": "HPV", "sigla": "odi"}),
                loop,
            )
            future.result(timeout=2)
            msg = ws.receive_text()
            evt = json.loads(msg)
            assert evt["type"] == "cell_scanning"
            assert evt["hospital"] == "HPV"
