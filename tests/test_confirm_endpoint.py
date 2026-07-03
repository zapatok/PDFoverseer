"""PATCH /api/sessions/{id}/cells/{h}/{s}/confirm endpoint.

The 'confirmed' flag is the manual "marcar listo" escape hatch (conteo-confiable
spec, Tema A2). It must survive a later re-scan (apply_filename_result and
finalize_cell_ocr re-assert it via setdefault).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.scanners.base import ConfidenceLevel, ScanResult


def _scan_result(count: int) -> ScanResult:
    return ScanResult(
        count=count,
        confidence=ConfidenceLevel.LOW,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=5,
        files_scanned=count,
        per_file={"a.pdf": 1},
    )


@pytest.fixture
def client_with_seeded(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    with TestClient(app) as c:
        mgr = app.state.manager
        sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
        sid = sid_state["session_id"]
        mgr.apply_filename_result(sid, "HRB", "charla", _scan_result(1))
        yield c, sid, mgr


def test_patch_confirm_sets_flag(client_with_seeded):
    client, sid, _mgr = client_with_seeded
    r = client.patch(
        f"/api/sessions/{sid}/cells/HRB/charla/confirm",
        json={"confirmed": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["confirmed"] is True


def test_confirm_preserved_across_rescan(client_with_seeded):
    client, sid, mgr = client_with_seeded
    client.patch(
        f"/api/sessions/{sid}/cells/HRB/charla/confirm",
        json={"confirmed": True},
    )
    # A fresh pase-1 scan overwrites per_file etc. — confirmed must survive.
    mgr.apply_filename_result(sid, "HRB", "charla", _scan_result(2))
    state = mgr.get_session_state(sid)
    assert state["cells"]["HRB"]["charla"]["confirmed"] is True


def test_patch_confirm_can_clear(client_with_seeded):
    client, sid, _mgr = client_with_seeded
    client.patch(
        f"/api/sessions/{sid}/cells/HRB/charla/confirm",
        json={"confirmed": True},
    )
    r = client.patch(
        f"/api/sessions/{sid}/cells/HRB/charla/confirm",
        json={"confirmed": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["confirmed"] is False


def test_patch_confirm_unknown_cell_400(client_with_seeded):
    # F13: unknown hospital+sigla coordinate → 400 (was 404), rejected before any
    # state write.
    client, sid, _mgr = client_with_seeded
    r = client.patch(
        f"/api/sessions/{sid}/cells/HXX/yyy/confirm",
        json={"confirmed": True},
    )
    assert r.status_code == 400
