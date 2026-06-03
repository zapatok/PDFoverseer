"""GET /api/sessions/{id}/output (serve) + GET /api/outputs (list) — G5."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_serve_and_list_output(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERSEER_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "t.db"))
    (tmp_path / "RESUMEN_2026-04.xlsx").write_bytes(b"PK\x03\x04stub")

    from api.main import create_app

    with TestClient(create_app()) as c:
        r = c.get("/api/sessions/2026-04/output")
        assert r.status_code == 200, r.text
        assert "spreadsheetml" in r.headers["content-type"]

        assert c.get("/api/sessions/2026-13/output").status_code == 400  # bad id
        assert c.get("/api/sessions/2026-05/output").status_code == 404  # missing

        lst = c.get("/api/outputs").json()
        assert any(o["session_id"] == "2026-04" for o in lst)
