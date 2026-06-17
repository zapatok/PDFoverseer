"""PATCH override + GET files + GET pdf route behavior."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
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
    client.post(f"/api/sessions/{sid}/scan")
    return sid


def test_patch_override_sets_value(client) -> None:
    sess = _open_and_scan(client)
    # 1 doc for a 1-page odi PDF — within the ≤páginas cap (Incr 2 §7). Was 17,
    # which the cap correctly rejects (a documents cell can't exceed its page count).
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_override"] == 1
    assert "override_note" not in body


def test_patch_override_null_clears(client) -> None:
    sess = _open_and_scan(client)
    client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": 1, "note": "x"},  # within cap (1-page odi); set then clear
    )
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": None, "note": None},
    )
    assert r.status_code == 200
    assert r.json()["user_override"] is None


def test_patch_override_validates_range(client) -> None:
    sess = _open_and_scan(client)
    for bad in (-1, 999_999, "seventeen"):
        r = client.patch(
            f"/api/sessions/{sess}/cells/HPV/odi/override",
            json={"value": bad, "note": None},
        )
        assert r.status_code == 400, f"expected 400 for value={bad!r}"


def test_get_files_lists_pdfs(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/files")
    assert r.status_code == 200
    files = r.json()
    assert len(files) == 1
    assert files[0]["name"] == "2026-04-10_odi_TITAN.pdf"
    assert files[0]["page_count"] == 1


def test_get_files_missing_cell_returns_404(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/inexistente/files")
    assert r.status_code == 404


def test_get_pdf_streams_file(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/pdf?index=0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_get_pdf_out_of_range_returns_400(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/pdf?index=99")
    assert r.status_code == 400


def test_get_pdf_negative_index_returns_400(client) -> None:
    sess = _open_and_scan(client)
    r = client.get(f"/api/sessions/{sess}/cells/HPV/odi/pdf?index=-1")
    assert r.status_code == 400


def test_compute_settled_por_resolver_forces_false(tmp_path) -> None:
    from api.routes.sessions import compute_settled

    # empty folder is fine; the note gate short-circuits before the folder walk
    cell = {"worker_status": "terminado", "note_status": "por_resolver"}
    assert compute_settled(cell, tmp_path, count_type="checks") is False


def test_compute_settled_resuelto_does_not_block(tmp_path) -> None:
    from api.routes.sessions import compute_settled

    cell = {"worker_status": "terminado", "note_status": "resuelto"}
    assert compute_settled(cell, tmp_path, count_type="checks") is True


# ---------------------------------------------------------------------------
# Task 5: PATCH .../note endpoint
# ---------------------------------------------------------------------------


def test_patch_note_persists_text_and_status(client) -> None:
    sess = _open_and_scan(client)
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "revisar firma", "status": "por_resolver"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["note"] == "revisar firma"
    assert body["note_status"] == "por_resolver"


def test_patch_note_blank_clears(client) -> None:
    sess = _open_and_scan(client)
    client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "algo", "status": "por_resolver"},
    )
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "", "status": "resuelto"},
    )
    assert r.json()["note"] is None
    assert r.json()["note_status"] is None


def test_patch_note_rejects_bad_status(client) -> None:
    sess = _open_and_scan(client)
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/note",
        json={"text": "x", "status": "no_existe"},
    )
    assert r.status_code == 422


def test_patch_note_unknown_session_404(client) -> None:
    r = client.patch(
        "/api/sessions/2099-01/cells/HPV/odi/note",
        json={"text": "x", "status": "por_resolver"},
    )
    assert r.status_code == 404


def test_patch_override_response_has_no_note(client) -> None:
    sess = _open_and_scan(client)
    # value=1 stays within the ≤páginas cap (odi PDF is 1 page)
    r = client.patch(
        f"/api/sessions/{sess}/cells/HPV/odi/override",
        json={"value": 1},
    )
    assert r.status_code == 200
    assert "override_note" not in r.json()
