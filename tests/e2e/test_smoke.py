"""End-to-end smoke: list → create → scan → output, then verify Excel cells."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.routes.sessions import get_manager
from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "smoke.db"))
    app = create_app()
    conn = open_connection(tmp_path / "smoke.db")
    init_schema(conn)
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    yield TestClient(app)
    close_all()


@pytest.mark.slow
def test_end_to_end_abril_flow(client, tmp_path):
    import openpyxl

    months = client.get("/api/months").json()["months"]
    abril = next(m for m in months if m["name"].upper() == "ABRIL")

    r = client.post(
        "/api/sessions",
        json={"year": abril["year"], "month": abril["month"]},
    )
    assert r.status_code in (200, 201)

    scan_result = client.post(
        f"/api/sessions/{abril['session_id']}/scan",
        json={"scope": "all"},
    ).json()
    assert scan_result["scanned"] == 54

    out = client.post(
        f"/api/sessions/{abril['session_id']}/output",
        json={},
    ).json()
    output_path = Path(out["output_path"])
    assert output_path.exists()
    assert out["cells_written"] >= 50

    # Spec §1.5 acceptance #2: every Excel cell must equal the scanned count.
    wb = openpyxl.load_workbook(output_path)
    summary = scan_result["summary"]
    matched = 0
    for name in wb.defined_names:
        if not name.endswith("_count"):
            continue
        prefix = name[: -len("_count")]
        if prefix not in summary:
            continue
        destinations = list(wb.defined_names[name].destinations)
        sheet, coord = destinations[0]
        cell_value = wb[sheet][coord].value
        if cell_value is not None:
            assert cell_value == summary[prefix], (
                f"Cell {name} = {cell_value} but scan said {summary[prefix]}"
            )
            matched += 1
    assert matched >= 50, f"Only {matched} cells matched the scan result"
