"""Tests for M3a write-lock enforcement in SessionManager (Task 3) and route
409 handler (Task 4).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.presence import CellLockedError

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_manager(tmp_path):
    from api.state import SessionManager
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    return SessionManager(conn=conn)


def _make_session(mgr, tmp_path) -> str:
    """Create session 2026-04 in the DB; returns the session_id."""
    from pathlib import Path

    state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    return state["session_id"]


# ── Task 3: manager-level enforcement ────────────────────────────────────────


def test_write_to_cell_held_by_another_raises(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")  # Carla holds HRB|odi
    with pytest.raises(CellLockedError):
        mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")


def test_editor_can_write_its_own_cell(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_focus("2026-04", "p1", "HRB|odi")
    # no raise — the editor can write its own cell
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")


def test_free_cell_and_no_participant_id_are_unenforced(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    # free cell with a participant_id → ok
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5, participant_id="p1")
    # legacy call with no participant_id → always ok
    mgr.apply_user_override("2026-04", "HRB", "odi", value=5)


def test_check_cell_lock_gate(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    with pytest.raises(CellLockedError):
        mgr.check_cell_lock("2026-04", "HRB", "odi", "p1")
    mgr.check_cell_lock("2026-04", "HRB", "odi", "p2")  # editor: no raise
    mgr.check_cell_lock("2026-04", "HRB", "art", "p1")  # free: no raise


def test_set_note_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    with pytest.raises(CellLockedError):
        mgr.set_note(
            "2026-04", "HRB", "odi", text="hello", status="por_resolver", participant_id="p1"
        )


def test_apply_worker_count_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|charla")
    with pytest.raises(CellLockedError):
        mgr.apply_worker_count("2026-04", "HRB", "charla", status="terminado", participant_id="p1")


def test_apply_confirmed_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    # apply_user_override with p2 (the editor) creates the cell
    mgr.apply_user_override("2026-04", "HRB", "odi", value=3, participant_id="p2")
    with pytest.raises(CellLockedError):
        mgr.apply_confirmed("2026-04", "HRB", "odi", confirmed=True, participant_id="p1")


def test_clear_near_matches_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    with pytest.raises(CellLockedError):
        mgr.clear_near_matches("2026-04", "HRB", "odi", participant_id="p1")


def test_apply_per_file_override_enforces_lock(tmp_path):
    mgr = _make_manager(tmp_path)
    _make_session(mgr, tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|odi")
    # create the cell first (p2 is editor so no conflict)
    mgr.apply_user_override("2026-04", "HRB", "odi", value=1, participant_id="p2")
    with pytest.raises(CellLockedError):
        mgr.apply_per_file_override("2026-04", "HRB", "odi", "doc.pdf", 2, "p1")


def test_reconcile_worker_marks_enforces_lock(tmp_path):
    # F1: the lock check is the first statement — it fires even before the
    # unknown-from_file KeyError.
    mgr = _make_manager(tmp_path)
    mgr.presence_heartbeat("2026-04", "p1", name="Daniel", color="#a")
    mgr.presence_heartbeat("2026-04", "p2", name="Carla", color="#b")
    mgr.presence_focus("2026-04", "p2", "HRB|charla")
    with pytest.raises(CellLockedError):
        mgr.reconcile_worker_marks(
            "2026-04", "HRB", "charla", action="discard", from_file="x.pdf", participant_id="p1"
        )


# ── Task 4: endpoint 409 ──────────────────────────────────────────────────────


def test_override_endpoint_409_when_locked_by_another(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "override_409.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        # 2026-07 isolation fix: the override endpoint 404s unless the session
        # already exists — open it explicitly (the real DB used to have it
        # pre-opened from prior usage, which this test was silently relying on).
        app.state.manager.open_session(year=2026, month=4, month_root=Path(tmp_path))
        c.post(
            "/api/sessions/2026-04/presence/heartbeat",
            json={"participant_id": "p2", "name": "Carla", "color": "#b"},
        )
        c.post(
            "/api/sessions/2026-04/presence/focus",
            json={"participant_id": "p2", "cell": "HRB|odi"},
        )
        r = c.patch(
            "/api/sessions/2026-04/cells/HRB/odi/override",
            json={"value": 5, "participant_id": "p1"},
        )
        assert r.status_code == 409
        assert r.json()["lock_holder"]["name"] == "Carla"


def test_reconcile_worker_marks_endpoint_409_when_locked_by_another(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "recon.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
        c.post(
            f"/api/sessions/{sid}/presence/heartbeat",
            json={"participant_id": "p2", "name": "Carla", "color": "#b"},
        )
        c.post(
            f"/api/sessions/{sid}/presence/focus",
            json={"participant_id": "p2", "cell": "HLL|charla"},
        )
        r = c.post(
            f"/api/sessions/{sid}/cells/HLL/charla/worker-marks/reconcile",
            json={"action": "discard", "from_file": "x.pdf", "participant_id": "p1"},
        )
        assert r.status_code == 409, r.text
        assert r.json()["lock_holder"]["name"] == "Carla"


# ── B1: scan_file_ocr (single-file OCR) endpoint lock gate ────────────────────


def _make_pdf(path, pages: int) -> None:
    import fitz

    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def test_scan_file_ocr_endpoint_409_when_locked_by_another(tmp_path, monkeypatch):
    """B1: single-file OCR 409s when another participant holds the cell.

    The file must exist (the route 404s a missing file BEFORE the lock check), so
    set up a real month_root + a 1-page a.pdf under HRB/odi.
    """
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "b1.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        _make_pdf(folder / "a.pdf", 1)

        # Carla (p2) holds HRB|odi
        c.post(
            f"/api/sessions/{sid}/presence/heartbeat",
            json={"participant_id": "p2", "name": "Carla", "color": "#b"},
        )
        c.post(
            f"/api/sessions/{sid}/presence/focus",
            json={"participant_id": "p2", "cell": "HRB|odi"},
        )

        # Daniel (p1) tries to OCR a file in Carla's cell → 409
        r = c.post(
            f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr",
            json={"participant_id": "p1"},
        )
        assert r.status_code == 409, r.text
        assert r.json()["lock_holder"]["name"] == "Carla"


def test_scan_file_ocr_endpoint_allows_editor_and_legacy(tmp_path, monkeypatch):
    """B1: the editor + the legacy (no participant_id) paths still 200."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "b1b.db"))
    app = create_app()
    with TestClient(app) as c:
        from pathlib import Path

        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        _make_pdf(folder / "a.pdf", 1)

        c.post(
            f"/api/sessions/{sid}/presence/heartbeat",
            json={"participant_id": "p1", "name": "Daniel", "color": "#a"},
        )
        c.post(
            f"/api/sessions/{sid}/presence/focus",
            json={"participant_id": "p1", "cell": "HRB|odi"},
        )

        # editor (p1) → 200
        ed = c.post(
            f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr",
            json={"participant_id": "p1"},
        )
        assert ed.status_code == 200, ed.text
        # U6: the scan now occupies the batch registry slot for this session —
        # wait for it to finish (and free the slot) before firing the second
        # scan, since the two are no longer free to run concurrently.
        _await_batch_slot_free(app, sid)
        # legacy no-body → 200 (unenforced)
        legacy = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr")
        assert legacy.status_code == 200, legacy.text
        _await_batch_slot_free(app, sid)


def _await_batch_slot_free(app, session_id, timeout=5) -> None:
    """U6: block until the background single-file/batch scan for *session_id*
    finishes and pops its ``app.state.batches`` slot (or return immediately if
    it already has)."""
    handle = app.state.batches.get(session_id)
    if handle is not None and handle.future is not None:
        handle.future.result(timeout=timeout)


def test_scan_file_ocr_excludes_concurrent_batch_scan(tmp_path, monkeypatch):
    """U6: a running single-file OCR occupies the same batch registry slot a
    multi-cell batch uses — a concurrent POST /scan-ocr 409s while it's in
    flight, and the slot frees once it ends."""
    import threading
    from pathlib import Path

    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "u6a.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        _make_pdf(folder / "a.pdf", 1)

        started = threading.Event()
        release = threading.Event()

        def fake_scan_one_file_ocr(hosp, sig, fld, fname, *, on_progress, cancel):
            started.set()
            release.wait(timeout=5)

        import api.routes.sessions.scan as scan_mod

        monkeypatch.setattr(scan_mod, "scan_one_file_ocr", fake_scan_one_file_ocr)

        r1 = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr")
        assert r1.status_code == 200, r1.text
        assert started.wait(timeout=5), "single-file scan never started"

        r2 = c.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HRB", "odi"]]})
        assert r2.status_code == 409, r2.text

        release.set()
        _await_batch_slot_free(app, sid)

        # slot freed → a batch scan is now accepted.
        r3 = c.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HRB", "odi"]]})
        assert r3.status_code == 200, r3.text
        c.post(f"/api/sessions/{sid}/cancel")  # avoid a real OCR run finishing async
        _await_batch_slot_free(app, sid)


def test_scan_file_ocr_cancel_stops_the_run_and_frees_the_slot(tmp_path, monkeypatch):
    """U6: POST /cancel cancels an in-flight single-file OCR — the merge never
    happens, and the batch registry slot frees for the next scan."""
    import threading
    import time
    from pathlib import Path

    from core.scanners.base import ConfidenceLevel, ScanResult
    from core.scanners.cancellation import CancelledError
    from core.scanners.pagination_scanner import PaginationScanner

    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "u6b.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        sid = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))["session_id"]
        folder = tmp_path / "HRB" / "3.-ODI Visitas"
        folder.mkdir(parents=True)
        _make_pdf(folder / "a.pdf", 1)

        started = threading.Event()
        finished = threading.Event()

        def blocking_count_ocr(
            self, folder, *, cancel, on_pdf=None, only=None, skip=None, on_page=None
        ):
            started.set()
            try:
                for _ in range(200):  # up to 2s, polling every 10ms
                    if cancel.cancelled:
                        raise CancelledError()
                    time.sleep(0.01)
                # /cancel never reached this run (e.g. the token isn't wired to
                # the handle the route registered) — complete normally instead
                # of self-cancelling, so a broken wiring makes the assertions
                # below fail loudly instead of passing by accident.
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
            finally:
                finished.set()

        monkeypatch.setattr(PaginationScanner, "count_ocr", blocking_count_ocr)

        r1 = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr")
        assert r1.status_code == 200, r1.text
        assert started.wait(timeout=5), "single-file scan never started"

        cr = c.post(f"/api/sessions/{sid}/cancel")
        assert cr.status_code == 200

        # Wait for the fake's own completion signal (not the registry slot —
        # pre-fix, scan_file_ocr never registers a handle at all, so waiting on
        # the slot would return immediately and check state before the run
        # actually concluded). A short buffer lets the synchronous
        # on_progress/merge continuation land right after count_ocr returns.
        assert finished.wait(timeout=5), "the scan never finished"
        time.sleep(0.2)

        # never merged: the cell has no per_file entry for a.pdf.
        state = mgr.get_session_state(sid)
        cell = state["cells"].get("HRB", {}).get("odi", {})
        assert "a.pdf" not in (cell.get("per_file") or {})

        _await_batch_slot_free(app, sid)

        # slot freed → a subsequent single-file scan is accepted, not 409.
        r2 = c.post(f"/api/sessions/{sid}/cells/HRB/odi/files/a.pdf/scan-ocr")
        assert r2.status_code == 200, r2.text
        c.post(f"/api/sessions/{sid}/cancel")
        _await_batch_slot_free(app, sid)
