"""GET /api/sessions/{id}/cells/{h}/{s}/files returns per_file + overrides + origin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.scanners.base import ConfidenceLevel, ScanResult


@pytest.fixture
def client_with_pdfs(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        from pathlib import Path

        sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
        sid = sid_state["session_id"]

        # Seed the cell folder so the endpoint can find the PDFs on disk.
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        (folder / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
        (folder / "b.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

        # Apply an OCR result so per_file is populated on the cell.
        mgr.apply_ocr_result(
            sid,
            "HRB",
            "odi",
            ScanResult(
                count=8,
                confidence=ConfidenceLevel.HIGH,
                method="header_detect",
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=8000,
                files_scanned=2,
                per_file={"a.pdf": 5, "b.pdf": 3},
            ),
        )
        # Apply a manual override on a.pdf only.
        mgr.apply_per_file_override(sid, "HRB", "odi", "a.pdf", 7)

        yield c, sid


def test_get_cell_files_includes_per_file_and_origin(client_with_pdfs):
    client, sid = client_with_pdfs
    r = client.get(f"/api/sessions/{sid}/cells/HRB/odi/files")
    assert r.status_code == 200, r.text
    files = r.json()
    by_name = {f["name"]: f for f in files}

    # a.pdf has per_file=5 and override=7 → effective=7, origin=manual
    assert by_name["a.pdf"]["per_file_count"] == 5
    assert by_name["a.pdf"]["override_count"] == 7
    assert by_name["a.pdf"]["effective_count"] == 7
    assert by_name["a.pdf"]["origin"] == "manual"

    # b.pdf has per_file=3, no override → effective=3, origin=OCR
    assert by_name["b.pdf"]["per_file_count"] == 3
    assert by_name["b.pdf"]["override_count"] is None
    assert by_name["b.pdf"]["effective_count"] == 3
    assert by_name["b.pdf"]["origin"] == "OCR"


def test_get_cell_files_r1_origin_for_filename_glob(tmp_path, monkeypatch):
    """Cells scanned via filename_glob should report origin='R1'."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test2.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        from pathlib import Path

        sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
        sid = sid_state["session_id"]

        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        (folder / "c.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

        mgr.apply_filename_result(
            sid,
            "HRB",
            "odi",
            ScanResult(
                count=2,
                confidence=ConfidenceLevel.HIGH,
                method="filename_glob",
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=10,
                files_scanned=1,
                per_file={"c.pdf": 2},
            ),
        )

        r = c.get(f"/api/sessions/{sid}/cells/HRB/odi/files")
        assert r.status_code == 200, r.text
        files = r.json()
        by_name = {f["name"]: f for f in files}

        assert by_name["c.pdf"]["per_file_count"] == 2
        assert by_name["c.pdf"]["override_count"] is None
        assert by_name["c.pdf"]["effective_count"] == 2
        assert by_name["c.pdf"]["origin"] == "R1"
