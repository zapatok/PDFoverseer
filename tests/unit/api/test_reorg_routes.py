"""Tests for refresh_reorg_deltas (Incr J T6) and scan wiring (T7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.domain import CATEGORY_FOLDERS


def _one_page_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page(width=595, height=842)
    buf = doc.tobytes()
    doc.close()
    return buf


@pytest.fixture
def reorg_mgr(tmp_path):
    """SessionManager on a temp DB + a temp month_root with HRB art/odi folders.

    The art folder holds one source PDF; the odi folder is empty (move target).
    """
    art_dir = tmp_path / "HRB" / CATEGORY_FOLDERS["art"]
    odi_dir = tmp_path / "HRB" / CATEGORY_FOLDERS["odi"]
    art_dir.mkdir(parents=True)
    odi_dir.mkdir(parents=True)
    (art_dir / "art_crs.pdf").write_bytes(_one_page_pdf())

    from api.state import SessionManager
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(tmp_path / "test.db")
    init_schema(conn)
    mgr = SessionManager(conn)
    mgr.open_session(year=2026, month=4, month_root=tmp_path)
    mgr.apply_per_file_ocr_result(
        "2026-04",
        "HRB",
        "art",
        "art_crs.pdf",
        count=1,
        method="header_band_anchors",
        near_matches=[],
    )
    mgr.apply_per_file_ocr_result(
        "2026-04",
        "HRB",
        "odi",
        "placeholder.pdf",
        count=0,
        method="header_band_anchors",
        near_matches=[],
    )
    mgr.add_reorg_op(
        "2026-04",
        {
            "op_type": "move_file",
            "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
            "dest": {"hospital": "HRB", "sigla": "odi"},
            "doc_count": 1,
            "worker_count": 0,
            "status": "pending",
        },
    )
    return mgr, art_dir


def test_refresh_recomputes_deltas_from_pending_ops(reorg_mgr):
    from api.routes.sessions import refresh_reorg_deltas

    mgr, _ = reorg_mgr
    refresh_reorg_deltas(mgr, "2026-04", check_applied=False)
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HRB"]["art"]["reorg_doc_delta"] == -1
    assert state["cells"]["HRB"]["odi"]["reorg_doc_delta"] == 1


def test_check_applied_marks_gone_source_as_applied(reorg_mgr):
    from api.routes.sessions import refresh_reorg_deltas

    mgr, art_dir = reorg_mgr
    (art_dir / "art_crs.pdf").unlink()  # simulate pase-1 having moved it physically
    refresh_reorg_deltas(mgr, "2026-04", check_applied=True)
    state = mgr.get_session_state("2026-04")
    assert state["reorg_ops"][0]["status"] == "applied"
    assert state["cells"]["HRB"]["art"]["reorg_doc_delta"] == 0
    assert state["cells"]["HRB"]["odi"]["reorg_doc_delta"] == 0


def test_check_applied_skips_op_without_source_file(reorg_mgr):
    """A malformed op missing source.file must never auto-apply (guard: file is None →
    `None not in present` would otherwise be True for any non-empty folder)."""
    from api.routes.sessions import refresh_reorg_deltas

    mgr, _ = reorg_mgr
    mgr.add_reorg_op(
        "2026-04",
        {
            "op_type": "rotate",
            "source": {"hospital": "HRB", "sigla": "art"},  # no "file"
            "dest": {"hospital": "HRB", "sigla": "art"},
            "doc_count": 0,
            "worker_count": 0,
            "status": "pending",
        },
    )
    refresh_reorg_deltas(mgr, "2026-04", check_applied=True)
    fileless = next(
        o for o in mgr.get_session_state("2026-04")["reorg_ops"] if "file" not in o["source"]
    )
    assert fileless["status"] == "pending"  # guard kept it pending


# ── Task 7: POST /scan wires refresh_reorg_deltas(check_applied=True) ─────


@pytest.fixture
def scan_client(tmp_path, monkeypatch):
    """TestClient with HRB/art source PDF present; session opened but not yet scanned."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))

    art_dir = tmp_path / "ABRIL" / "HRB" / CATEGORY_FOLDERS["art"]
    odi_dir = tmp_path / "ABRIL" / "HRB" / CATEGORY_FOLDERS["odi"]
    art_dir.mkdir(parents=True)
    odi_dir.mkdir(parents=True)
    (art_dir / "art_crs.pdf").write_bytes(_one_page_pdf())

    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c, app, art_dir


def _open_session(client) -> str:
    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    assert r.status_code == 200
    return r.json()["session_id"]


def test_scan_keeps_pending_op_while_source_file_present(scan_client):
    """POST /scan must NOT flip a pending op to applied while the source still exists."""
    client, app, art_dir = scan_client
    sid = _open_session(client)

    # Seed a pending op directly via the live manager (app.state.manager).
    mgr = app.state.manager
    mgr.add_reorg_op(
        sid,
        {
            "op_type": "move_file",
            "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
            "dest": {"hospital": "HRB", "sigla": "odi"},
            "doc_count": 1,
            "worker_count": 0,
            "status": "pending",
        },
    )

    r = client.post(f"/api/sessions/{sid}/scan")
    assert r.status_code == 200

    state = mgr.get_session_state(sid)
    assert state["reorg_ops"][0]["status"] == "pending"
    assert state["cells"]["HRB"]["art"]["reorg_doc_delta"] == -1
    assert state["cells"]["HRB"]["odi"]["reorg_doc_delta"] == 1


def test_scan_flips_op_applied_when_source_file_gone(scan_client):
    """POST /scan must flip a pending op to applied when the source file is absent."""
    client, app, art_dir = scan_client
    sid = _open_session(client)

    mgr = app.state.manager
    mgr.add_reorg_op(
        sid,
        {
            "op_type": "move_file",
            "source": {"hospital": "HRB", "sigla": "art", "file": "art_crs.pdf"},
            "dest": {"hospital": "HRB", "sigla": "odi"},
            "doc_count": 1,
            "worker_count": 0,
            "status": "pending",
        },
    )

    # Simulate pase-1 having physically moved the file.
    (art_dir / "art_crs.pdf").unlink()

    r = client.post(f"/api/sessions/{sid}/scan")
    assert r.status_code == 200

    state = mgr.get_session_state(sid)
    assert state["reorg_ops"][0]["status"] == "applied"
    assert state["cells"]["HRB"]["art"]["reorg_doc_delta"] == 0
    assert state["cells"]["HRB"]["odi"]["reorg_doc_delta"] == 0


# ── Task 9: POST /reorg/ops ────────────────────────────────────────────────


@pytest.fixture
def endpoint_client(tmp_path, monkeypatch):
    """TestClient with HPV/odi containing one 1-page PDF (mirrors test_cells_routes)."""
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    odi_dir = tmp_path / "ABRIL" / "HPV" / "3.-ODI Visitas"
    odi_dir.mkdir(parents=True)
    (odi_dir / "2026-04-10_odi_TITAN.pdf").write_bytes(_one_page_pdf())

    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _open_and_scan(client) -> str:
    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    sid = r.json()["session_id"]
    client.post(f"/api/sessions/{sid}/scan")
    return sid


def test_post_reorg_op_move_file_resolves_defaults(endpoint_client):
    """POST /reorg/ops with doc_count omitted → 200, defaults filled, delta applied."""
    client = endpoint_client
    sid = _open_and_scan(client)

    r = client.post(
        f"/api/sessions/{sid}/reorg/ops",
        json={
            "op_type": "move_file",
            "source": {"hospital": "HPV", "sigla": "odi", "file": "2026-04-10_odi_TITAN.pdf"},
            "dest": {"hospital": "HPV", "sigla": "reunion"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    op = body["op"]
    assert op["id"] == "op_001"
    assert op["doc_count"] == 1  # resolved from per_file (1-page → 1 doc)
    assert op["status"] == "pending"

    # deltas must be reflected in the same response
    cells = body["cells"]
    assert cells["HPV"]["odi"]["reorg_doc_delta"] == -1
    assert cells["HPV"]["reunion"]["reorg_doc_delta"] == 1


def test_post_reorg_op_extract_pages_through_endpoint(endpoint_client):
    """Regression: page_range is nested under source, so it must survive model_dump()
    and reach validate_op/resolve_op_defaults. A valid in-bounds extract_pages → 200."""
    client = endpoint_client
    sid = _open_and_scan(client)

    r = client.post(
        f"/api/sessions/{sid}/reorg/ops",
        json={
            "op_type": "extract_pages",
            "source": {
                "hospital": "HPV",
                "sigla": "odi",
                "file": "2026-04-10_odi_TITAN.pdf",
                "page_range": [1, 1],  # the odi PDF is 1 page
            },
            "dest": {"hospital": "HPV", "sigla": "reunion"},
        },
    )
    assert r.status_code == 200, r.text
    op = r.json()["op"]
    assert op["op_type"] == "extract_pages"
    assert op["doc_count"] == 1  # default for extract_pages
    cells = r.json()["cells"]
    assert cells["HPV"]["odi"]["reorg_doc_delta"] == -1
    assert cells["HPV"]["reunion"]["reorg_doc_delta"] == 1


def test_post_reorg_op_invalid_dest_equals_source(endpoint_client):
    """dest == source → 400."""
    client = endpoint_client
    sid = _open_and_scan(client)
    r = client.post(
        f"/api/sessions/{sid}/reorg/ops",
        json={
            "op_type": "move_file",
            "source": {"hospital": "HPV", "sigla": "odi", "file": "2026-04-10_odi_TITAN.pdf"},
            "dest": {"hospital": "HPV", "sigla": "odi"},
        },
    )
    assert r.status_code == 400


def test_post_reorg_op_unknown_session(endpoint_client):
    """Unknown session_id → 404."""
    client = endpoint_client
    r = client.post(
        "/api/sessions/2099-01/reorg/ops",
        json={
            "op_type": "move_file",
            "source": {"hospital": "HPV", "sigla": "odi", "file": "x.pdf"},
            "dest": {"hospital": "HPV", "sigla": "reunion"},
        },
    )
    assert r.status_code == 404


def test_post_reorg_op_unknown_sigla(endpoint_client):
    """Unknown sigla → 404."""
    client = endpoint_client
    sid = _open_and_scan(client)
    r = client.post(
        f"/api/sessions/{sid}/reorg/ops",
        json={
            "op_type": "move_file",
            "source": {"hospital": "HPV", "sigla": "induccion", "file": "x.pdf"},
            "dest": {"hospital": "HPV", "sigla": "odi"},
        },
    )
    assert r.status_code == 404


# ── Task 10: DELETE /reorg/ops/{op_id} ────────────────────────────────────


def test_delete_reorg_op_removes_op_and_resets_deltas(endpoint_client):
    """Create an op, DELETE it → 200; reorg_ops empty; deltas back to 0."""
    client = endpoint_client
    sid = _open_and_scan(client)

    # Create op first
    r = client.post(
        f"/api/sessions/{sid}/reorg/ops",
        json={
            "op_type": "move_file",
            "source": {"hospital": "HPV", "sigla": "odi", "file": "2026-04-10_odi_TITAN.pdf"},
            "dest": {"hospital": "HPV", "sigla": "reunion"},
        },
    )
    assert r.status_code == 200
    op_id = r.json()["op"]["id"]

    # Delete it
    r = client.delete(f"/api/sessions/{sid}/reorg/ops/{op_id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] == op_id

    # Session state: no ops, deltas reset
    r2 = client.get(f"/api/sessions/{sid}")
    state = r2.json()
    assert state["reorg_ops"] == []
    assert state["cells"]["HPV"]["odi"].get("reorg_doc_delta", 0) == 0
    assert state["cells"]["HPV"]["reunion"].get("reorg_doc_delta", 0) == 0


def test_delete_reorg_op_unknown_id(endpoint_client):
    """DELETE unknown op_id → 404."""
    client = endpoint_client
    sid = _open_and_scan(client)
    r = client.delete(f"/api/sessions/{sid}/reorg/ops/op_999")
    assert r.status_code == 404


def test_delete_reorg_op_unknown_session(endpoint_client):
    """DELETE on unknown session → 404."""
    client = endpoint_client
    r = client.delete("/api/sessions/2099-01/reorg/ops/op_001")
    assert r.status_code == 404


# ── Task 11: POST /reorg/export ───────────────────────────────────────────


@pytest.fixture
def export_client(tmp_path, monkeypatch):
    """TestClient with HPV/odi + a dedicated tmp output dir.

    The corpus and the output dir are SEPARATE trees (sibling subdirs of tmp_path),
    mirroring production — and satisfying the export guard that forbids writing the
    manifest under INFORME_MENSUAL_ROOT (the read-only corpus).
    """
    corpus = tmp_path / "corpus"
    out_dir = tmp_path / "outputs"
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(corpus))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(out_dir))
    odi_dir = corpus / "ABRIL" / "HPV" / "3.-ODI Visitas"
    odi_dir.mkdir(parents=True)
    (odi_dir / "2026-04-10_odi_TITAN.pdf").write_bytes(_one_page_pdf())

    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c, out_dir


def test_export_writes_manifest_json(export_client):
    """POST /reorg/export with one pending op → 200; JSON file exists; correct content."""
    client, out_dir = export_client
    sid = _open_and_scan(client)

    client.post(
        f"/api/sessions/{sid}/reorg/ops",
        json={
            "op_type": "move_file",
            "source": {"hospital": "HPV", "sigla": "odi", "file": "2026-04-10_odi_TITAN.pdf"},
            "dest": {"hospital": "HPV", "sigla": "reunion"},
        },
    )

    r = client.post(f"/api/sessions/{sid}/reorg/export")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["operation_count"] == 1

    dest = Path(body["path"])
    assert dest.exists()
    import json

    manifest = json.loads(dest.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == 1
    assert manifest["month"] == "2026-04"
    assert len(manifest["operations"]) == 1


def test_export_no_pending_ops_returns_400(export_client):
    """POST /reorg/export with no pending ops → 400."""
    client, _ = export_client
    sid = _open_and_scan(client)
    r = client.post(f"/api/sessions/{sid}/reorg/export")
    assert r.status_code == 400
