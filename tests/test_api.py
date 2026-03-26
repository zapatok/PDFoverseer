"""
API integration tests — no real OCR processing occurs.
Uses FastAPI TestClient with monkeypatched DB_PATH and session_manager.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import api.database as database

# Patch out the eviction loop and WebSocket broadcast to avoid asyncio issues
import api.websocket as ws_module
from api.state import SessionState, session_manager
from core.utils import _PageRead


def _make_read(page, curr, total, method="direct", confidence=1.0):
    return _PageRead(pdf_page=page, curr=curr, total=total,
                     method=method, confidence=confidence)


TEST_SESSION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TEST_PDF_PATH = "/fake/test.pdf"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database._init_db()
    return db_path


@pytest.fixture
def client(temp_db):
    # Suppress background tasks (eviction loop) during tests
    with patch("api.websocket._emit", return_value=None):
        from server import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


def _sid_headers():
    return {"x-session-id": TEST_SESSION_ID}


def test_get_state_empty(client):
    res = client.get("/api/state", headers=_sid_headers())
    assert res.status_code == 200
    data = res.json()
    assert "running" in data
    assert "pdf_list" in data
    assert data["running"] is False
    assert data["pdf_list"] == []


def test_reset(client):
    # Pre-populate session with some state
    s = session_manager.get_or_create(TEST_SESSION_ID)
    s.total_docs = 5
    s.issues = [{"id": 1}]

    res = client.post("/api/reset", headers=_sid_headers())
    assert res.status_code == 200
    assert res.json()["success"] is True

    s2 = session_manager.get_or_create(TEST_SESSION_ID)
    assert s2.total_docs == 0
    assert s2.issues == []


def test_start_no_pdfs(client):
    res = client.post("/api/start", json={"start_index": 0}, headers=_sid_headers())
    assert res.status_code == 200
    # No PDFs loaded → should not start
    assert res.json()["success"] is False


def test_stop_not_running(client):
    res = client.post("/api/stop", headers=_sid_headers())
    assert res.status_code == 200
    assert res.json()["success"] is False


def test_sessions_list(client):
    res = client.get("/api/sessions")
    assert res.status_code == 200
    data = res.json()
    assert "sessions" in data


def test_correct_no_reads(client):
    """Correct endpoint with no DB reads → returns failure."""
    res = client.post("/api/correct", json={
        "pdf_path": TEST_PDF_PATH,
        "page": 1,
        "correct_curr": 1,
        "correct_tot": 3,
    }, headers=_sid_headers())
    assert res.status_code == 200
    assert res.json()["success"] is False


def test_correct_with_reads(client, temp_db):
    """Correct endpoint with DB reads → returns success and updates DB."""
    reads = [_make_read(1, 1, 3), _make_read(2, 2, 3), _make_read(3, 3, 3)]
    database.save_reads(TEST_SESSION_ID, TEST_PDF_PATH, reads)

    res = client.post("/api/correct", json={
        "pdf_path": TEST_PDF_PATH,
        "page": 1,
        "correct_curr": 1,
        "correct_tot": 5,
    }, headers=_sid_headers())
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Reads should be updated in DB
    updated = database.get_reads(TEST_SESSION_ID, TEST_PDF_PATH)
    assert len(updated) > 0


def test_invalid_session_id_rejected(client):
    """Non-UUID session_id should return 400."""
    res = client.get("/api/state", headers={"x-session-id": "../../etc/passwd"})
    assert res.status_code == 400
