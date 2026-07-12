"""GET /api/sessions/{id}/cells/{h}/{s}/files returns per_file + overrides + origin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.scanners.base import ConfidenceLevel, ScanResult


@pytest.fixture
def client_with_pdfs(tmp_path, monkeypatch, make_pdf):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        from pathlib import Path

        sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
        sid = sid_state["session_id"]

        # Seed the cell folder so the endpoint can find the PDFs on disk.
        # Real PDFs: b.pdf must read a true page_count (>0) so the OCR method
        # surfaces "OCR" rather than the page_count==0 "Error" branch.
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "a.pdf", 5)
        make_pdf(folder / "b.pdf", 3)

        # Apply per-file OCR results (Incr 1A merge) so per_file is populated.
        mgr.apply_per_file_ocr_result(
            sid, "HRB", "odi", "a.pdf", count=5, method="header_detect", near_matches=[]
        )
        mgr.apply_per_file_ocr_result(
            sid, "HRB", "odi", "b.pdf", count=3, method="header_detect", near_matches=[]
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

    # a.pdf has per_file=5 and override=7 → effective=7, origin=Manual
    assert by_name["a.pdf"]["per_file_count"] == 5
    assert by_name["a.pdf"]["override_count"] == 7
    assert by_name["a.pdf"]["effective_count"] == 7
    assert by_name["a.pdf"]["origin"] == "Manual"

    # b.pdf has per_file=3, no override → effective=3, origin=OCR
    assert by_name["b.pdf"]["per_file_count"] == 3
    assert by_name["b.pdf"]["override_count"] is None
    assert by_name["b.pdf"]["effective_count"] == 3
    assert by_name["b.pdf"]["origin"] == "OCR"


def test_get_cell_files_r1_origin_for_filename_glob(tmp_path, monkeypatch, make_pdf):
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
        # Real 1-page PDF: filename_glob + page_count == 1 → "R1".
        make_pdf(folder / "c.pdf", 1)

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


def test_origin_chip_rule(tmp_path, monkeypatch, make_pdf):
    """_origin_for: a filename_glob 1-page file → R1, a multipage one → Pendiente."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_rule.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]

        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "one.pdf", 1)
        make_pdf(folder / "many.pdf", 28)

        # filename_glob (not OCR): the rule decides per page_count.
        mgr.apply_filename_result(
            sid,
            "HRB",
            "odi",
            ScanResult(
                count=2,
                confidence=ConfidenceLevel.LOW,
                method="filename_glob",
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=1,
                files_scanned=2,
                per_file={"one.pdf": 1, "many.pdf": 1},
            ),
        )

        rows = {r["name"]: r for r in c.get(f"/api/sessions/{sid}/cells/HRB/odi/files").json()}
        assert rows["one.pdf"]["origin"] == "R1"  # 1 page
        assert rows["many.pdf"]["origin"] == "Pendiente"  # multipage, filename_glob


def test_effective_count_defaults_to_one_for_unscanned_file(tmp_path, monkeypatch):
    """Audit #7: a PDF present on disk but absent from per_file/overrides
    defaults to effective_count=1 in the per-file view — intentionally
    asymmetric with api.state.compute_cell_count, which defaults a dataless
    cell to 0. The divergence is presentation-only and pre-scan."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_eff.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
        sid = sid_state["session_id"]

        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        (folder / "a.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
        (folder / "b.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

        # Scan recorded only a.pdf; b.pdf is on disk but absent from per_file.
        mgr.apply_filename_result(
            sid,
            "HRB",
            "odi",
            ScanResult(
                count=1,
                confidence=ConfidenceLevel.HIGH,
                method="filename_glob",
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=10,
                files_scanned=1,
                per_file={"a.pdf": 1},
            ),
        )

        files = c.get(f"/api/sessions/{sid}/cells/HRB/odi/files").json()
        by_name = {f["name"]: f for f in files}
        assert by_name["b.pdf"]["per_file_count"] is None
        assert by_name["b.pdf"]["override_count"] is None
        assert by_name["b.pdf"]["effective_count"] == 1


def test_origin_ocr_and_count_after_scan(tmp_path, monkeypatch, make_pdf):
    """After an OCR scan, the per-file row reports origin='OCR' and the OCR
    per-file count (review #5/#6: the chip + count surface the scan result)."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_ocr.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]

        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "x.pdf", 4)  # multipage, OCR found 3 documents

        mgr.apply_per_file_ocr_result(
            sid, "HRB", "odi", "x.pdf", count=3, method="header_band_anchors", near_matches=[]
        )

        rows = {r["name"]: r for r in c.get(f"/api/sessions/{sid}/cells/HRB/odi/files").json()}
        assert rows["x.pdf"]["origin"] == "OCR"
        assert rows["x.pdf"]["effective_count"] == 3


def test_origin_revisar_when_ocr_finds_zero(tmp_path, monkeypatch, make_pdf):
    """An OCR-scanned file that read 0 documents (poor scan / no registered
    flavor) shows 'Revisar', not a plain 'OCR' — the operator must check it by
    hand (Bug A)."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_revisar.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]

        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "good.pdf", 4)
        make_pdf(folder / "bad.pdf", 4)  # readable, but OCR found nothing

        mgr.apply_per_file_ocr_result(
            sid, "HRB", "odi", "good.pdf", count=2, method="header_band_anchors", near_matches=[]
        )
        mgr.apply_per_file_ocr_result(
            sid, "HRB", "odi", "bad.pdf", count=0, method="header_band_anchors", near_matches=[]
        )

        rows = {r["name"]: r for r in c.get(f"/api/sessions/{sid}/cells/HRB/odi/files").json()}
        assert rows["good.pdf"]["origin"] == "OCR"
        assert rows["bad.pdf"]["origin"] == "Revisar"


def test_origin_divergent_per_file_method_after_single_file_ocr(tmp_path, monkeypatch, make_pdf):
    """rev-2 §3/#1: OCR-ing one file of a filename_glob cell makes that file's
    chip 'OCR' while the rest stay 'Pendiente' — _origin_for reads per_file_method,
    not cell.method."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_div.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]

        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "a.pdf", 6)
        make_pdf(folder / "b.pdf", 6)

        mgr.apply_filename_result(
            sid,
            "HRB",
            "odi",
            ScanResult(
                count=2,
                confidence=ConfidenceLevel.LOW,
                method="filename_glob",
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=1,
                files_scanned=2,
                per_file={"a.pdf": 1, "b.pdf": 1},
            ),
        )
        # OCR only a.pdf → its per_file_method diverges from the cell's.
        mgr.apply_per_file_ocr_result(
            sid,
            "HRB",
            "odi",
            "a.pdf",
            count=4,
            method="header_band_anchors",
            near_matches=[],
        )

        rows = {r["name"]: r for r in c.get(f"/api/sessions/{sid}/cells/HRB/odi/files").json()}
        assert rows["a.pdf"]["origin"] == "OCR"  # per-file method
        assert rows["b.pdf"]["origin"] == "Pendiente"  # cell method (multipage)


def test_scan_file_ocr_endpoint_accept_and_404(tmp_path, monkeypatch, make_pdf):
    """The single-file scan endpoint accepts an existing file, 404s a missing one."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_endpoint.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]

        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "a.pdf", 1)

        ok = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr")
        assert ok.status_code == 200, ok.text
        assert ok.json()["accepted"] is True

        missing = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/missing.pdf/scan-ocr")
        assert missing.status_code == 404
