"""GET /api/sessions/{id}/history?n=12 endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.db.historical_repo import upsert_count


@pytest.fixture
def client_with_history(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        from pathlib import Path

        sid_state = mgr.open_session(year=2026, month=5, month_root=Path(tmp_path))
        sid = sid_state["session_id"]

        # Seed 12 months: 2025-06 → 2026-05, count=10..21
        for offset in range(12):
            total = 2025 * 12 + 6 + offset - 1
            year, month_zero = divmod(total, 12)
            month = month_zero + 1
            upsert_count(
                mgr._conn,
                year=year,
                month=month,
                hospital="HPV",
                sigla="reunion",
                count=10 + offset,
                confidence="high",
                method="filename_glob",
            )
        mgr._conn.commit()
        yield c, sid


def test_history_endpoint_returns_n_months(client_with_history):
    client, sid = client_with_history
    r = client.get(f"/api/sessions/{sid}/history?n=12")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "HPV|reunion" in data
    series = data["HPV|reunion"]
    assert len(series) == 12
    assert series[0]["year"] == 2025
    assert series[0]["month"] == 6
    assert series[-1]["year"] == 2026
    assert series[-1]["month"] == 5
    assert series[-1]["count"] == 21


def test_history_endpoint_default_n_is_12(client_with_history):
    client, sid = client_with_history
    r1 = client.get(f"/api/sessions/{sid}/history")
    r2 = client.get(f"/api/sessions/{sid}/history?n=12")
    assert r1.json() == r2.json()


def test_history_endpoint_n_can_be_smaller(client_with_history):
    client, sid = client_with_history
    r = client.get(f"/api/sessions/{sid}/history?n=3")
    series = r.json()["HPV|reunion"]
    assert len(series) == 3
