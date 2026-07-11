"""POST /scan-ocr and POST /cancel route behavior."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    # Pre-create a minimal ABRIL/HPV/3.-ODI Visitas folder with 1 PDF
    odi = tmp_path / "ABRIL" / "HPV" / "3.-ODI Visitas"
    odi.mkdir(parents=True)
    (odi / "2026-04-10_odi_TITAN.pdf").write_bytes(_one_page_pdf())
    app = create_app()
    with TestClient(app) as c:
        yield c


def _one_page_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf


def _open_and_scan(client) -> str:
    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/scan")  # populates cell folder_path
    return sid


def test_scan_ocr_unknown_session_returns_404(client) -> None:
    r = client.post("/api/sessions/2027-12/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert r.status_code == 404


def test_scan_ocr_malformed_session_id_returns_400(client) -> None:
    r = client.post("/api/sessions/does-not-exist/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert r.status_code == 400


def test_scan_ocr_empty_cells_returns_400(client) -> None:
    sid = _open_and_scan(client)
    r = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": []})
    assert r.status_code == 400


def test_scan_ocr_dispatches(client) -> None:
    sid = _open_and_scan(client)
    r = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert r.status_code == 200
    assert r.json()["accepted"] is True
    assert r.json()["total"] == 1


def test_scan_ocr_returns_total_pdfs(client) -> None:
    # The fixture seeds exactly one odi PDF, so the progress bar's denominator
    # (total_pdfs) must be 1 (audit finding #1 — real progress denominator).
    sid = _open_and_scan(client)
    r = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is True
    assert body["total_pdfs"] == 1


def test_cancel_no_active_batch_is_idempotent(client) -> None:
    r = client.post("/api/sessions/2027-12/cancel")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_cancel_malformed_session_id_returns_400(client) -> None:
    """§B8.1: cancel joins the rest of the package's session_id format check."""
    r = client.post("/api/sessions/does-not-exist/cancel")
    assert r.status_code == 400


def test_scan_ocr_409_when_batch_already_running(client) -> None:
    from api.batch import make_handle

    sid = _open_and_scan(client)
    client.app.state.batches[sid] = make_handle(session_id=sid, total=1)
    try:
        r = client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HPV", "odi"]]})
        assert r.status_code == 409
    finally:
        client.app.state.batches.pop(sid, None)


def test_scan_ocr_releases_batch_handle_when_dispatch_fails(client, monkeypatch) -> None:
    """§B7: a failed ``_DISPATCH_POOL.submit`` must not leak the batch slot —
    the route propagates the error (an unhandled exception, not swallowed
    into a 409), AND a second attempt must NOT 409 ("another batch is
    already running") since the handle was released on the failed dispatch."""
    import api.routes.sessions._common as common_mod

    def _raise_submit(fn):
        raise RuntimeError("boom")

    monkeypatch.setattr(common_mod._DISPATCH_POOL, "submit", _raise_submit)

    sid = _open_and_scan(client)
    with pytest.raises(RuntimeError):
        client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HPV", "odi"]]})
    assert sid not in client.app.state.batches  # the slot must be released, not leaked

    # A second attempt must fail the same way (submit still raises) — NOT 409.
    with pytest.raises(RuntimeError):
        client.post(f"/api/sessions/{sid}/scan-ocr", json={"cells": [["HPV", "odi"]]})
