"""POST /output writes historical_counts after successful Excel generation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.db.connection import open_connection
from core.db.historical_repo import get_counts_for_month


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path / "out"))
    # Minimal corpus: 1 cell in HPV/odi to write to history.
    odi = tmp_path / "ABRIL" / "HPV" / "3.-ODI Visitas"
    odi.mkdir(parents=True)
    (odi / "2026-04-10_odi_TITAN.pdf").write_bytes(_one_page_pdf())
    app = create_app()
    with TestClient(app) as c:
        yield c, tmp_path / "history.db"


def _one_page_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf


def test_output_writes_history_with_filename_glob_method(client) -> None:
    test_client, db_path = client
    r = test_client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    test_client.post(f"/api/sessions/{sid}/scan")
    test_client.post(f"/api/sessions/{sid}/output")

    conn = open_connection(db_path)
    rows = get_counts_for_month(conn, year=2026, month=4)
    assert any(r.hospital == "HPV" and r.sigla == "odi" for r in rows)
    odi_row = next(r for r in rows if r.hospital == "HPV" and r.sigla == "odi")
    assert odi_row.count == 1
    assert odi_row.method == "filename_glob"


def test_output_history_method_reflects_override(client) -> None:
    test_client, db_path = client
    r = test_client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    test_client.post(f"/api/sessions/{sid}/scan")
    test_client.patch(
        f"/api/sessions/{sid}/cells/HPV/odi/override",
        json={"value": 17, "note": "compilation"},
    )
    test_client.post(f"/api/sessions/{sid}/output")

    conn = open_connection(db_path)
    odi_row = next(
        r
        for r in get_counts_for_month(conn, year=2026, month=4)
        if r.hospital == "HPV" and r.sigla == "odi"
    )
    assert odi_row.count == 17
    assert odi_row.method == "override"


def test_output_history_method_reflects_ocr_when_present(client) -> None:
    """When ocr_count is the winner over filename_count, method should reflect
    the technique that produced ocr_count, not 'filename_glob'."""
    test_client, db_path = client
    r = test_client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    test_client.post(f"/api/sessions/{sid}/scan")

    # Simulate an OCR result by hitting the same setter the orchestrator uses.
    from core.scanners.base import ConfidenceLevel, ScanResult

    mgr = test_client.app.state.manager
    mgr.apply_ocr_result(
        sid,
        "HPV",
        "odi",
        ScanResult(
            count=17,
            confidence=ConfidenceLevel.HIGH,
            method="header_detect",
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=100,
            files_scanned=1,
        ),
    )

    test_client.post(f"/api/sessions/{sid}/output")

    conn = open_connection(db_path)
    odi_row = next(
        r
        for r in get_counts_for_month(conn, year=2026, month=4)
        if r.hospital == "HPV" and r.sigla == "odi"
    )
    assert odi_row.count == 17
    assert odi_row.method == "header_detect"
