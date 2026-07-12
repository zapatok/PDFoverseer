"""U11: lifespan shutdown drains single-file OCR dispatches, not just batches.

Since Task 3.2 (U6), scan_file_ocr registers a BatchHandle in
app.state.batches the same way scan_ocr does — so the shutdown drain loop in
api/main.py (which already iterated app.state.batches for multi-cell batches)
now covers single-file scans "for free", with no shutdown-code change needed.
This file is the regression test that proves it.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import create_app
from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.pagination_scanner import PaginationScanner


def test_shutdown_awaits_an_in_flight_single_file_scan(tmp_path, monkeypatch, make_pdf):
    """U11: a single-file OCR still "running" when the app shuts down must be
    awaited (not abandoned) before the DB connection closes — otherwise its
    merge silently fails against a closed connection and the count is lost.

    Verified two ways: (1) the handle is registered in app.state.batches while
    the scan is in flight — the wiring that makes shutdown's existing
    batches-drain loop cover it "for free" (Task 3.2); (2) durably, by
    re-opening the DB file after the TestClient's `with` block (which runs
    lifespan shutdown) exits and confirming the merge actually landed —
    proving the background thread's write completed BEFORE close_all().
    """
    db_path = tmp_path / "u11.db"
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(db_path))
    app = create_app()

    started = threading.Event()

    def slow_count_ocr(self, folder, *, cancel, on_pdf=None, only=None, skip=None, on_page=None):
        started.set()
        # Still "running" when the test exits the `with` block below — long
        # enough to prove shutdown waits, short enough to keep the test fast.
        time.sleep(0.3)
        return ScanResult(
            count=1,
            confidence=ConfidenceLevel.HIGH,
            method="pagination",
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=1,
            files_scanned=1,
            per_file={only: 1},
        )

    monkeypatch.setattr(PaginationScanner, "count_ocr", slow_count_ocr)

    sid: str
    with TestClient(app) as c:
        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        make_pdf(folder / "a.pdf", 1)

        r1 = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr")
        assert r1.status_code == 200, r1.text
        assert started.wait(timeout=5), "single-file scan never started"

        # (1) registration: the single-file scan occupies the same registry
        # slot a batch would — this is what makes it visible to shutdown.
        handle = app.state.batches.get(sid)
        assert handle is not None, "scan_file_ocr must register a handle (U6/U11)"
        assert handle.future is not None
        # Exiting the `with` block here runs lifespan shutdown while the scan
        # (0.3s) is still in flight.

    # (2) durability: a fresh connection to the same DB file must see the merge
    # — only possible if the background thread wrote before close_all() ran.
    from api.state import SessionManager
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(db_path)
    try:
        init_schema(conn)
        mgr2 = SessionManager(conn=conn)
        state = mgr2.get_session_state(sid)
        cell = state["cells"].get("HRB", {}).get("odi", {})
        assert cell.get("per_file", {}).get("a.pdf") == 1
    finally:
        conn.close()
