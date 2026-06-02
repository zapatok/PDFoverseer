"""GET /api/sessions/{id}/history?n=12 endpoint.

The endpoint's window is **time-based**: it returns the last N months counting
back from today (see api/routes/history.py — session_id is only used for
routing). The fixture therefore seeds data relative to the current UTC month so
the assertions hold regardless of the wall-clock date the suite runs on.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.db.historical_repo import upsert_count


def _ym(month_idx: int) -> tuple[int, int]:
    """Convert an absolute year*12+month0 index back to (year, month)."""
    year, month_zero = divmod(month_idx, 12)
    return year, month_zero + 1


@pytest.fixture
def client_with_history(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        from pathlib import Path

        sid_state = mgr.open_session(year=2026, month=5, month_root=Path(tmp_path))
        sid = sid_state["session_id"]

        # Seed 12 months ending at the current UTC month (count = 10..21), so the
        # newest entry always lands inside the endpoint's "last N from today"
        # window no matter when the test runs.
        now = datetime.utcnow()
        end_idx = now.year * 12 + (now.month - 1)
        for offset in range(12):
            year, month = _ym(end_idx - 11 + offset)
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

    now = datetime.utcnow()
    end_idx = now.year * 12 + (now.month - 1)
    first_year, first_month = _ym(end_idx - 11)
    # Oldest entry is 11 months before today, with the lowest seeded count.
    assert series[0]["year"] == first_year
    assert series[0]["month"] == first_month
    assert series[0]["count"] == 10
    # Newest entry is the current UTC month, with the highest seeded count.
    assert series[-1]["year"] == now.year
    assert series[-1]["month"] == now.month
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
