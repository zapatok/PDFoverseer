"""Integration tests for M3b: scanner lock-skip policy.

Task 5: pase-2 OCR scanner claims cells as the Claude agent and skips human-held cells.
Task 6: pase-1 filename scan skips cells under live human edit.

These tests bypass the actual OCR pipeline (no real PDFs are needed for the
lock/skip logic) and operate directly on the SessionManager + PresenceRegistry
layer, plus the FastAPI TestClient for the pase-1 HTTP route.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.presence import AGENT_PARTICIPANT_ID
from api.routes.sessions import _handle_scan_progress
from api.state import SessionManager
from core.db.connection import open_connection
from core.db.migrations import init_schema

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path) -> SessionManager:
    """Build a real SessionManager backed by a temp SQLite DB."""
    conn = open_connection(tmp_path / "test_m3b.db")
    init_schema(conn)
    return SessionManager(conn=conn)


def _register_human(
    mgr: SessionManager,
    session_id: str,
    pid: str = "human-1",
    name: str = "Daniel",
    color: str = "#a",
) -> None:
    """Seed a human editor via the public @_synchronized pass-throughs (same path
    production uses) — not the private registry — so the test reflects real locking."""
    mgr.presence_heartbeat(session_id, pid, name=name, color=color)


# ---------------------------------------------------------------------------
# Unit-level: PresenceRegistry.agent_focus
# ---------------------------------------------------------------------------


def test_skip_path_human_holds_cell(tmp_path):
    """agent_focus returns the holder's snapshot when a human editor holds the cell."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    # Register a human participant and focus them on the cell.
    _register_human(mgr, session_id, pid="human-1", name="Daniel", color="#a")
    mgr.presence_focus(session_id, "human-1", "HRB|odi")

    # agent_focus should detect the human editor and return their public snapshot.
    holder = mgr.agent_claim_cell(session_id, "HRB", "odi")

    assert holder is not None
    assert holder["participant_id"] == "human-1"
    assert holder["name"] == "Daniel"
    assert holder["mode"] == "editor"
    # The agent must NOT have been registered (it was skipped).
    snapshot = mgr.presence_snapshot(session_id)
    pids = {p["participant_id"] for p in snapshot}
    assert AGENT_PARTICIPANT_ID not in pids


def test_claim_path_free_cell(tmp_path):
    """agent_focus returns None and registers the agent when the cell is free."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    holder = mgr.agent_claim_cell(session_id, "HRB", "odi")

    assert holder is None
    snapshot = mgr.presence_snapshot(session_id)
    pids = {p["participant_id"] for p in snapshot}
    assert AGENT_PARTICIPANT_ID in pids
    agent = next(p for p in snapshot if p["participant_id"] == AGENT_PARTICIPANT_ID)
    assert agent["kind"] == "agent"
    assert agent["focused_cell"] == "HRB|odi"
    assert agent["mode"] == "editor"


def test_inertness_no_participants(tmp_path):
    """agent_claim_cell succeeds (returns None) when there are zero participants."""
    mgr = _make_manager(tmp_path)
    result = mgr.agent_claim_cell("2026-05", "HPV", "charla")
    assert result is None


def test_scan_cancelled_releases_agent_no_skipped_field(tmp_path):
    """agent_leave removes the agent from the roster."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    # Claim a cell.
    mgr.agent_claim_cell(session_id, "HRB", "odi")
    before = {p["participant_id"] for p in mgr.presence_snapshot(session_id)}
    assert AGENT_PARTICIPANT_ID in before

    # Release.
    changed = mgr.agent_leave(session_id)
    assert changed is True
    after = {p["participant_id"] for p in mgr.presence_snapshot(session_id)}
    assert AGENT_PARTICIPANT_ID not in after


def test_skip_then_claim_next_cell(tmp_path):
    """Agent skips a human-held cell, then claims the next free cell."""
    mgr = _make_manager(tmp_path)
    session_id = "2026-04"

    _register_human(mgr, session_id, pid="human-1", name="Daniel", color="#a")
    mgr.presence_focus(session_id, "human-1", "HRB|odi")

    # First cell is held — skip.
    holder_odi = mgr.agent_claim_cell(session_id, "HRB", "odi")
    assert holder_odi is not None  # skip

    # Second cell is free — claim.
    holder_charla = mgr.agent_claim_cell(session_id, "HRB", "charla")
    assert holder_charla is None  # claimed

    snapshot = mgr.presence_snapshot(session_id)
    agent = next(p for p in snapshot if p["participant_id"] == AGENT_PARTICIPANT_ID)
    assert agent["focused_cell"] == "HRB|charla"


# ---------------------------------------------------------------------------
# Handler-level: _handle_scan_progress event routing (Task 5)
# Drive the pase-2 progress handler directly with synthetic events + a capturing
# emit. Skipped cells drop their events before _apply_scan_event, and cell_scanning
# passes through it unchanged, so no real OCR/disk is needed.
# ---------------------------------------------------------------------------


def _new_ctx() -> dict:
    return {
        "skipped_set": set(),
        "skipped_cells": [],
        "agent_active": False,
        "current_cell_skipped": False,
        "lent": [],
    }


def test_handler_skip_sequence_drops_events_and_enriches_complete(tmp_path):
    """A human-held cell: cell_scanning emits ONE cell_skipped (not cell_scanning);
    later pdf_progress/file_result/cell_done for it are dropped; scan_complete is
    enriched with the skipped list."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    _register_human(mgr, sid, pid="human-1", name="Daniel", color="#a")
    mgr.presence_focus(sid, "human-1", "HRB|odi")

    out: list[dict] = []
    ctx = _new_ctx()
    emit = out.append

    _handle_scan_progress(
        mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": "odi"}, ctx, emit
    )
    # One cell_skipped, no cell_scanning, the cell recorded as skipped.
    assert [e["type"] for e in out] == ["cell_skipped"]
    assert out[0]["reason"] == "locked"
    assert out[0]["lock_holder"]["participant_id"] == "human-1"
    assert ("HRB", "odi") in ctx["skipped_set"]
    assert ctx["current_cell_skipped"] is True

    out.clear()
    _handle_scan_progress(mgr, sid, {"type": "pdf_progress", "done": 1, "total": 2}, ctx, emit)
    _handle_scan_progress(
        mgr,
        sid,
        {
            "type": "file_result",
            "hospital": "HRB",
            "sigla": "odi",
            "filename": "x.pdf",
            "count": 3,
            "method": "v4",
        },
        ctx,
        emit,
    )
    _handle_scan_progress(
        mgr, sid, {"type": "cell_done", "hospital": "HRB", "sigla": "odi", "result": {}}, ctx, emit
    )
    assert out == []  # every later event for the skipped cell is dropped

    _handle_scan_progress(
        mgr, sid, {"type": "scan_complete", "scanned": 0, "errors": 0, "cancelled": 0}, ctx, emit
    )
    complete = next(e for e in out if e["type"] == "scan_complete")
    assert complete["skipped"] == [{"hospital": "HRB", "sigla": "odi"}]


def test_handler_claim_path_emits_presence_then_cell_scanning(tmp_path):
    """A free cell: cell_scanning claims the agent (emits a presence snapshot with the
    Claude badge) then passes the cell_scanning event through."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    out: list[dict] = []
    ctx = _new_ctx()

    _handle_scan_progress(
        mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": "art"}, ctx, out.append
    )

    assert [e["type"] for e in out] == ["presence", "cell_scanning"]
    agent = next(p for p in out[0]["participants"] if p["participant_id"] == AGENT_PARTICIPANT_ID)
    assert agent["kind"] == "agent"
    assert agent["focused_cell"] == "HRB|art"
    assert ctx["agent_active"] is True
    assert ctx["current_cell_skipped"] is False

    # scan_complete releases the agent (presence WITHOUT claude) and reports no skips.
    out.clear()
    _handle_scan_progress(
        mgr,
        sid,
        {"type": "scan_complete", "scanned": 1, "errors": 0, "cancelled": 0},
        ctx,
        out.append,
    )
    presence = next(e for e in out if e["type"] == "presence")
    assert all(p["participant_id"] != AGENT_PARTICIPANT_ID for p in presence["participants"])
    complete = next(e for e in out if e["type"] == "scan_complete")
    assert complete["skipped"] == []
    assert ctx["agent_active"] is False


def test_handler_scan_cancelled_releases_agent_without_skipped_field(tmp_path):
    """scan_cancelled releases the agent but must NOT carry a `skipped` field."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    out: list[dict] = []
    ctx = _new_ctx()

    _handle_scan_progress(
        mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": "art"}, ctx, out.append
    )
    out.clear()
    _handle_scan_progress(
        mgr,
        sid,
        {"type": "scan_cancelled", "scanned": 0, "errors": 0, "cancelled": 1},
        ctx,
        out.append,
    )

    cancelled = next(e for e in out if e["type"] == "scan_cancelled")
    assert "skipped" not in cancelled
    assert ctx["agent_active"] is False
    # agent released
    assert all(p["participant_id"] != AGENT_PARTICIPANT_ID for p in mgr.presence_snapshot(sid))


def test_handler_inertness_no_human_no_skips(tmp_path):
    """With no human present, the handler never skips: scan_complete.skipped == []
    and no cell_skipped is ever emitted (the agent badge still appears — that's the feature)."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    out: list[dict] = []
    ctx = _new_ctx()

    for sigla in ("art", "charla"):
        _handle_scan_progress(
            mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": sigla}, ctx, out.append
        )
    _handle_scan_progress(
        mgr,
        sid,
        {"type": "scan_complete", "scanned": 2, "errors": 0, "cancelled": 0},
        ctx,
        out.append,
    )

    assert not any(e["type"] == "cell_skipped" for e in out)
    complete = next(e for e in out if e["type"] == "scan_complete")
    assert complete["skipped"] == []


# ---------------------------------------------------------------------------
# HTTP-level: pase-1 scan skips human-held cells (Task 6)
# ---------------------------------------------------------------------------


def test_pase1_skips_human_held_cell(tmp_path, monkeypatch):
    """POST /api/sessions/{id}/scan skips a cell that a human currently holds.

    This test stubs scan_month so no real filesystem enumeration or OCR occurs.
    The presence state is seeded directly via the HTTP heartbeat + focus endpoints.
    The scan response must include the skipped cell in the ``skipped`` list and
    must NOT have applied the result for that cell.
    """
    # Point the app at a temp folder and DB.
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test_pase1.db"))

    # Create a fake month folder so the scan route doesn't 404.
    month_root = tmp_path / "ABRIL"
    cell_dir = month_root / "HRB" / "3.-ODI Visitas"
    cell_dir.mkdir(parents=True)

    # Stub scan_month to return a fake result for HRB|odi without touching disk.
    from core.scanners.base import ConfidenceLevel, ScanResult

    fake_result = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=0,
        files_scanned=1,
        per_file={"fake.pdf": 5},
    )

    import api.routes.sessions.scan as scan_mod

    def _stub_scan_month(_inv):
        return {("HRB", "odi"): fake_result}

    # scan_month is now imported into the scan sub-router module; patch it there
    # (the route resolves the name in its own module namespace).
    monkeypatch.setattr(scan_mod, "scan_month", _stub_scan_month)

    app = create_app()
    with TestClient(app) as c:
        # Open the session.
        r = c.post("/api/sessions", json={"year": 2026, "month": 4})
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]

        # Register a human and focus them on HRB|odi.
        c.post(
            f"/api/sessions/{sid}/presence/heartbeat",
            json={"participant_id": "human-1", "name": "Daniel", "color": "#a"},
        )
        c.post(
            f"/api/sessions/{sid}/presence/focus",
            json={"participant_id": "human-1", "cell": "HRB|odi"},
        )

        # Trigger pase-1 scan.
        r2 = c.post(f"/api/sessions/{sid}/scan")
        assert r2.status_code == 200, r2.text
        body = r2.json()

        # The cell was skipped — it must appear in ``skipped``.
        assert "skipped" in body
        skipped = body["skipped"]
        assert any(s["hospital"] == "HRB" and s["sigla"] == "odi" for s in skipped), (
            f"Expected HRB|odi in skipped, got: {skipped}"
        )

        # The scanned count must be 0 (1 result - 1 skipped).
        assert body["scanned"] == 0

        # The session state for HRB|odi must NOT have the fake count applied.
        r3 = c.get(f"/api/sessions/{sid}")
        assert r3.status_code == 200, r3.text
        cells = r3.json().get("cells", {})
        odi_cell = cells.get("HRB", {}).get("odi", {})
        # The cell should not have count=5 from the stub (it was skipped).
        assert odi_cell.get("count") != 5, "apply_cell_result should have been skipped for HRB|odi"


def test_handler_self_lend_scans_launchers_own_cell(tmp_path):
    """Auto-préstamo (2026-07-10): la celda que el LANZADOR del scan tiene
    abierta NO se salta — el agente la toma (lanzador demote a viewer, badge
    del bot vía presence) y el cell_scanning pasa normal."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    _register_human(mgr, sid, pid="human-1", name="Daniel", color="#a")
    mgr.presence_focus(sid, "human-1", "HRB|odi")

    out: list[dict] = []
    ctx = _new_ctx()
    ctx["launcher_id"] = "human-1"

    _handle_scan_progress(
        mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": "odi"}, ctx, out.append
    )

    assert [e["type"] for e in out] == ["presence", "cell_scanning"]
    assert ctx["skipped_set"] == set()
    snap = {p["participant_id"]: p for p in out[0]["participants"]}
    assert snap["human-1"]["mode"] == "viewer"
    assert snap[AGENT_PARTICIPANT_ID]["mode"] == "editor"
    assert snap[AGENT_PARTICIPANT_ID]["focused_cell"] == "HRB|odi"


def test_handler_self_lend_never_borrows_someone_elses_cell(tmp_path):
    """Con launcher_id ajeno al holder (Carla edita, Daniel lanza) el skip M3b
    queda intacto."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    _register_human(mgr, sid, pid="carla", name="Carla", color="#b")
    mgr.presence_focus(sid, "carla", "HRB|odi")

    out: list[dict] = []
    ctx = _new_ctx()
    ctx["launcher_id"] = "daniel"

    _handle_scan_progress(
        mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": "odi"}, ctx, out.append
    )

    assert [e["type"] for e in out] == ["cell_skipped"]
    assert out[0]["lock_holder"]["participant_id"] == "carla"
    assert ("HRB", "odi") in ctx["skipped_set"]


def test_handler_self_lend_promotes_launcher_back_at_scan_complete(tmp_path):
    """§B2: at the batch terminal, the lender (launcher) gets editorship back —
    the scan_complete-triggered presence broadcast shows them as editor again
    and the agent gone."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    _register_human(mgr, sid, pid="human-1", name="Daniel", color="#a")
    mgr.presence_focus(sid, "human-1", "HRB|odi")

    out: list[dict] = []
    ctx = _new_ctx()
    ctx["launcher_id"] = "human-1"

    _handle_scan_progress(
        mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": "odi"}, ctx, out.append
    )
    out.clear()
    _handle_scan_progress(
        mgr,
        sid,
        {"type": "scan_complete", "scanned": 1, "errors": 0, "cancelled": 0},
        ctx,
        out.append,
    )

    presence = next(e for e in out if e["type"] == "presence")
    snap = {p["participant_id"]: p for p in presence["participants"]}
    assert snap["human-1"]["mode"] == "editor"
    assert AGENT_PARTICIPANT_ID not in snap


def test_handler_pdf_page_progress_filtered_by_own_cell_identity(tmp_path):
    """pdf_page_progress trae hospital/sigla: se filtra por SU celda (skipped_set),
    no por el booleano current_cell_skipped de la última celda — con 2 workers
    los eventos de una celda viva no deben caerse porque otra se saltó."""
    mgr = _make_manager(tmp_path)
    sid = "2026-04"
    _register_human(mgr, sid, pid="human-1", name="Daniel", color="#a")
    mgr.presence_focus(sid, "human-1", "HRB|odi")

    out: list[dict] = []
    ctx = _new_ctx()
    # Celda A (HRB|odi) se salta; current_cell_skipped queda True.
    _handle_scan_progress(
        mgr, sid, {"type": "cell_scanning", "hospital": "HRB", "sigla": "odi"}, ctx, out.append
    )
    assert ctx["current_cell_skipped"] is True
    out.clear()

    # Páginas de la celda VIVA (HPV|art) llegan intercaladas → deben pasar.
    alive = {
        "type": "pdf_page_progress",
        "hospital": "HPV",
        "sigla": "art",
        "page": 3,
        "pages_total": 9,
    }
    _handle_scan_progress(mgr, sid, alive, ctx, out.append)
    assert out == [alive]
    out.clear()

    # Páginas de la celda SALTADA se caen aunque current_cell_skipped ya sea False.
    ctx["current_cell_skipped"] = False
    skipped = {
        "type": "pdf_page_progress",
        "hospital": "HRB",
        "sigla": "odi",
        "page": 1,
        "pages_total": 9,
    }
    _handle_scan_progress(mgr, sid, skipped, ctx, out.append)
    assert out == []
