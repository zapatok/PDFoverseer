import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.sessions import get_manager, router
from api.routes.sessions._common import enrich_cell_colado_suspects
from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema

# Only test_scan_session_populates_cells performs a real scan against the
# corpus (marked @pytest.mark.corpus); every other test below either doesn't
# need a real path at all (open_session just stores month_root as a string)
# or already uses a tmp_path-based synthetic root.


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    conn = open_connection(tmp_path / "api_sessions.db")
    init_schema(conn)
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    app.include_router(router, prefix="/api")
    yield TestClient(app)
    close_all()


def test_enrich_cell_colado_suspects_open_filter():
    """Unit: the wrapper returns only suspects not covered by a matching pending op."""
    cell = {
        "colado_suspects": [
            {"kind": "filename", "file": "F.pdf", "page_range": None, "counted": True},
            {"kind": "filename", "file": "G.pdf", "page_range": None, "counted": True},
        ]
    }
    ops = [
        {
            "op_type": "move_file",
            "status": "pending",
            "source": {"hospital": "HRB", "sigla": "art", "file": "F.pdf"},
        }
    ]
    out = enrich_cell_colado_suspects(cell, ops, "HRB", "art")
    files = {s["file"] for s in out["colado_suspects"]}
    assert files == {"G.pdf"}  # F.pdf suppressed by the pending move_file op
    # No suspects → unchanged object (no-op).
    assert enrich_cell_colado_suspects({}, ops, "HRB", "art") == {}


def test_get_session_hides_op_suppressed_suspect(tmp_path):
    """Integration: a pending reorg op on the suspect's (cell, file) hides it from
    the GET payload; deleting the op un-suppresses it (derived, §5)."""
    conn = open_connection(tmp_path / "colado.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4, month_root=tmp_path)

    from core.scanners.base import ConfidenceLevel, ScanResult, ScanTelemetry
    from core.scanners.utils.colado_guard import find_foreign_filename_suspects

    susp = find_foreign_filename_suspects(["2026-05_odi_x.pdf"], "chps")
    result = ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"crs.pdf": 1, "2026-05_odi_x.pdf": 1},
        telemetry=ScanTelemetry(
            colado_suspects=susp, present_files=["crs.pdf", "2026-05_odi_x.pdf"]
        ),
    )
    mgr.apply_filename_result("2026-04", "HRB", "chps", result)

    app = FastAPI()
    app.dependency_overrides[get_manager] = lambda: SessionManager(conn=conn)
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    # No op yet → the suspect shows in the GET payload.
    cell = client.get("/api/sessions/2026-04").json()["cells"]["HRB"]["chps"]
    assert len(cell["colado_suspects"]) == 1

    # A pending move_file op on that (cell, file) suppresses it.
    mgr.add_reorg_op(
        "2026-04",
        {
            "op_type": "move_file",
            "status": "pending",
            "source": {"hospital": "HRB", "sigla": "chps", "file": "2026-05_odi_x.pdf"},
            "dest": {"hospital": "HRB", "sigla": "odi"},
        },
    )
    cell = client.get("/api/sessions/2026-04").json()["cells"]["HRB"]["chps"]
    assert cell["colado_suspects"] == []

    # Delete the op → the suspect re-appears (dedupe is derived, not persisted).
    ops = mgr.get_session_state("2026-04").get("reorg_ops", [])
    mgr.delete_reorg_op("2026-04", ops[0]["id"])
    cell = client.get("/api/sessions/2026-04").json()["cells"]["HRB"]["chps"]
    assert len(cell["colado_suspects"]) == 1
    close_all()


def test_create_session(client, monkeypatch, tmp_path):
    # _resolve_month_dir requires INFORME_MENSUAL_ROOT to exist and contain a
    # month-named subfolder; open_session itself only stores month_root as a
    # string (no disk read), so a synthetic ABRIL dir is equivalent to the
    # real corpus here — see QA-3 audit.
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    response = client.post("/api/sessions", json={"year": 2026, "month": 4})
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["session_id"] == "2026-04"


def test_get_session(client, monkeypatch, tmp_path):
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    response = client.get("/api/sessions/2026-04")
    assert response.status_code == 200
    assert response.json()["session_id"] == "2026-04"


@pytest.mark.corpus
def test_scan_session_populates_cells(client, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", "A:/informe mensual")
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    response = client.post("/api/sessions/2026-04/scan", json={"scope": "all"})
    assert response.status_code == 200
    state = client.get("/api/sessions/2026-04").json()
    assert "cells" in state
    assert "HPV" in state["cells"]


def test_patch_worker_count_persists(client, monkeypatch, tmp_path):
    # Use tmp_path as root so the charla folder doesn't contain real PDFs →
    # present_files=None (legacy: sum-all), worker_count == sum of synthetic marks.
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={
            "marks": {"a.pdf": [{"page": 1, "count": 12}]},
            "status": "en_progreso",
            "cursor": {"file": 0, "page": 1},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["worker_status"] == "en_progreso"
    assert body["worker_count"] == 12


def test_patch_worker_count_rejects_bad_status(client, monkeypatch, tmp_path):
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"status": "no-es-valido"},
    )
    assert r.status_code == 422


def test_patch_worker_count_session_404(client):
    # Sin crear la sesión: apply_worker_count → KeyError → 404.
    r = client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"status": "terminado"},
    )
    assert r.status_code == 404


def test_patch_override_unknown_hospital_400(client, monkeypatch, tmp_path):
    # F13: an unknown hospital coordinate is a clean 400 (bad request), never a
    # phantom cell. Prevents the `no_existe`-in-DB hole at the route boundary.
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/BOGUS/odi/override",
        json={"value": 1},
    )
    assert r.status_code == 400


def test_patch_worker_count_unknown_sigla_400(client, monkeypatch, tmp_path):
    # F13: an unknown sigla coordinate is rejected with 400 before any state write.
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.patch(
        "/api/sessions/2026-04/cells/HPV/FAKE/worker-count",
        json={"status": "terminado"},
    )
    assert r.status_code == 400


def test_get_session_enriches_worker_count_present_filtered(client, monkeypatch, tmp_path):
    """F1/Task 2.1: GET session carries a canonical present-filtered ``worker_count``
    on every worker/checks cell. Marks for files no longer on disk (orphans) are
    excluded; document siglas carry NO ``worker_count`` key."""
    charla_dir = tmp_path / "ABRIL" / "HLL" / "4.-Charlas"
    charla_dir.mkdir(parents=True)
    (charla_dir / "real.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    # real.pdf is present on disk (counted); gone.pdf is an orphan (excluded).
    client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={
            "marks": {
                "real.pdf": [{"page": 1, "count": 5}],
                "gone.pdf": [{"page": 1, "count": 9}],
            }
        },
    )
    state = client.get("/api/sessions/2026-04").json()
    charla = state["cells"]["HLL"]["charla"]
    assert charla["worker_count"] == 5  # gone.pdf orphan excluded, real.pdf counted
    # A document sigla (odi) is seeded by the v3→v4 reconcile but carries no worker_count.
    assert "worker_count" not in state["cells"]["HLL"]["odi"]


def test_get_session_worker_count_missing_folder_uses_legacy_filter(client, monkeypatch, tmp_path):
    """F1 review fix: when the category folder is MISSING, GET's enrichment falls
    back to the legacy ``None`` filter (per_file keys; empty per_file → sum all) —
    the exact conditional patch_worker_count and the Excel builders use, so the
    UI can never diverge from the Excel on this edge."""
    (tmp_path / "ABRIL").mkdir()  # month exists; HLL/4.-Charlas does NOT
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"marks": {"gone.pdf": [{"page": 1, "count": 9}]}},
    )
    state = client.get("/api/sessions/2026-04").json()
    # Missing folder → legacy sum-all (9), NOT the empty-set collapse to 0.
    assert state["cells"]["HLL"]["charla"]["worker_count"] == 9


def test_hospital_category_folders_matches_find_category_folder(tmp_path):
    """The batched per-hospital resolver (one iterdir) must resolve exactly like
    ``_find_category_folder`` per sigla: canonical direct hit, renumbered folder,
    and missing folder (nominal path)."""
    from api.routes.sessions import hospital_category_folders
    from core.orchestrator import _find_category_folder

    hosp = tmp_path / "HRB"
    (hosp / "4.-Charlas").mkdir(parents=True)  # canonical direct hit
    (hosp / "7.-Charla Integral").mkdir()  # renumbered (canonical is 5.-)
    # maquinaria: no folder at all → nominal canonical path
    siglas = ["charla", "chintegral", "maquinaria", "dif_pts"]
    batched = hospital_category_folders(hosp, siglas)
    for sigla in siglas:
        assert batched[sigla] == _find_category_folder(hosp, sigla), sigla
    # And on a missing hospital dir entirely:
    ghost = tmp_path / "HLL"
    batched_ghost = hospital_category_folders(ghost, siglas)
    for sigla in siglas:
        assert batched_ghost[sigla] == _find_category_folder(ghost, sigla), sigla


def test_reconcile_worker_marks_migrate_returns_enriched(client, monkeypatch, tmp_path):
    """F1/Task 2.3: migrate re-keys the orphan onto a present file, response is the
    enriched cell (present-filtered worker_count included)."""
    charla_dir = tmp_path / "ABRIL" / "HLL" / "4.-Charlas"
    charla_dir.mkdir(parents=True)
    (charla_dir / "new.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"marks": {"old.pdf": [{"page": 1, "count": 7}]}},
    )
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "migrate", "from_file": "old.pdf", "to_file": "new.pdf"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "old.pdf" not in body["worker_marks"]
    assert body["worker_marks"]["new.pdf"] == [{"page": 1, "count": 7}]
    assert body["worker_count"] == 7  # migrated onto a present file → now counted


def test_reconcile_migrate_without_to_file_400(client, monkeypatch, tmp_path):
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "migrate", "from_file": "old.pdf"},
    )
    assert r.status_code == 400


def test_reconcile_bad_action_400(client, monkeypatch, tmp_path):
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "explode", "from_file": "old.pdf"},
    )
    assert r.status_code == 400


def test_reconcile_unknown_from_file_404(client, monkeypatch, tmp_path):
    (tmp_path / "ABRIL").mkdir()
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    client.post("/api/sessions", json={"year": 2026, "month": 4})
    client.patch(
        "/api/sessions/2026-04/cells/HLL/charla/worker-count",
        json={"marks": {"a.pdf": [{"page": 1, "count": 1}]}},
    )
    r = client.post(
        "/api/sessions/2026-04/cells/HLL/charla/worker-marks/reconcile",
        json={"action": "discard", "from_file": "nope.pdf"},
    )
    assert r.status_code == 404
