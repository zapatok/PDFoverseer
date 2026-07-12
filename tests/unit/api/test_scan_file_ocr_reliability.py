"""Tests for §B1: scan_file_ocr must recompute all_reliable on merge.

Defect: the file_scan_done handler in scan.py merged the per-file OCR result
and broadcast cell_updated, but never called refresh_all_reliable — a cell
that started all_reliable=True stayed green after a file OCR'd to a low-trust
"Revisar" result, and the stale True propagated to every connected client via
the cell_updated broadcast.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from core.scanners.base import ConfidenceLevel, ScanResult, ScanTelemetry
from core.scanners.pagination_scanner import PaginationScanner


def _seed_settled_cell(mgr, sid, hospital, sigla, filename):
    """Seed a cell whose single file is a settled R1 (filename_glob, 1 page) —
    apply_filename_result computes all_reliable=True for it naturally."""
    result = ScanResult(
        count=1,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=1,
        duration_ms=1,
        per_file={filename: 1},
        telemetry=ScanTelemetry(present_files=[filename]),
    )
    mgr.apply_filename_result(sid, hospital, sigla, result)


def test_scan_file_ocr_recomputes_all_reliable_on_low_trust_result(tmp_path, monkeypatch, make_pdf):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "b1_reliability.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "a.pdf", 1)

        _seed_settled_cell(mgr, sid, "HRB", "odi", "a.pdf")
        pre_state = mgr.get_session_state(sid)
        assert pre_state["cells"]["HRB"]["odi"]["all_reliable"] is True

        def fake_count_ocr(
            self, folder, *, cancel, on_pdf=None, only=None, skip=None, on_page=None
        ):
            # Low-trust: count=0 with an OCR method → per-file chip reads
            # "Revisar", which breaks compute_settled.
            return ScanResult(
                count=0,
                confidence=ConfidenceLevel.LOW,
                method="pagination",
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=1,
                files_scanned=1,
                per_file={"a.pdf": 0},
            )

        monkeypatch.setattr(PaginationScanner, "count_ocr", fake_count_ocr)

        with c.websocket_connect(f"/ws/sessions/{sid}") as ws:
            r = c.post(
                f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr",
                json={},
            )
            assert r.status_code == 200, r.text

            seen_types = []
            cell_updated = None
            for _ in range(10):
                evt = json.loads(ws.receive_text())
                seen_types.append(evt.get("type"))
                if evt.get("type") == "cell_updated":
                    cell_updated = evt
                    break

        assert cell_updated is not None, f"expected cell_updated, saw {seen_types}"
        assert cell_updated["cell"]["all_reliable"] is False, (
            "the broadcast cell_updated must carry the recomputed (honest) value"
        )

        post_state = mgr.get_session_state(sid)
        assert post_state["cells"]["HRB"]["odi"]["all_reliable"] is False
