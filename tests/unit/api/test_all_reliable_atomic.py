"""Tests for §B4: SessionManager.recompute_all_reliable — atomic
load→compute→persist of all_reliable in ONE RLock acquisition, with the
anti-colados gate (§4.5) living inside the atomic method itself.
"""

from __future__ import annotations

from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult, ScanTelemetry
from core.scanners.utils.colado_guard import find_foreign_filename_suspects

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_manager(tmp_path):
    from api.state import SessionManager
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    return SessionManager(conn=conn)


def _seed_reliable_cell(mgr, tmp_path, hospital="HRB", sigla="odi"):
    """Open a session and seed a cell whose single file is a settled R1
    (filename_glob, 1 page) — compute_settled must read True for it."""
    mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    result = ScanResult(
        count=1,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=1,
        duration_ms=1,
        per_file={"a.pdf": 1},
        telemetry=ScanTelemetry(present_files=["a.pdf"]),
    )
    mgr.apply_filename_result("2026-04", hospital, sigla, result)


# ── (a) fresh compute persisted under the lock ────────────────────────────────


def test_recompute_all_reliable_persists_fresh_settled_true(tmp_path):
    mgr = _make_manager(tmp_path)
    _seed_reliable_cell(mgr, tmp_path)
    # Force a stale False so the assertion below can only pass if the method
    # actually recomputed against the fresh state, not an old cached value.
    mgr.set_all_reliable("2026-04", "HRB", "odi", False)

    value = mgr.recompute_all_reliable(
        "2026-04",
        "HRB",
        "odi",
        tmp_path / "unused",
        pages={"a.pdf": 1},
        count_type="documents",
    )

    assert value is True
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HRB"]["odi"]["all_reliable"] is True


def test_recompute_all_reliable_persists_fresh_settled_false(tmp_path):
    mgr = _make_manager(tmp_path)
    _seed_reliable_cell(mgr, tmp_path)
    # A file OCR'd to "Revisar" (per_file count 0, OCR method) breaks settlement.
    mgr.apply_per_file_ocr_result(
        "2026-04", "HRB", "odi", "a.pdf", count=0, method="pagination", near_matches=[]
    )
    mgr.set_all_reliable("2026-04", "HRB", "odi", True)  # force a stale True

    value = mgr.recompute_all_reliable(
        "2026-04",
        "HRB",
        "odi",
        tmp_path / "unused",
        pages={"a.pdf": 1},
        count_type="documents",
    )

    assert value is False
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HRB"]["odi"]["all_reliable"] is False


# ── (b) anti-colados gate lives inside the atomic method ──────────────────────


def test_recompute_all_reliable_blocked_by_open_counted_suspect(tmp_path):
    """A cell whose files are otherwise fully settled (compute_settled → True)
    must still end up all_reliable=False when an OPEN, COUNTED colado suspect
    exists — the §4.5 gate must fire from INSIDE recompute_all_reliable, not
    rely on a separate caller-side check."""
    mgr = _make_manager(tmp_path)
    mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    # chps hosts a foreign-named file (odi token) — a counted suspect once
    # per_file gives it a positive contribution.
    filenames = ["crs.pdf", "2026-05_odi_x.pdf"]
    susp = find_foreign_filename_suspects(filenames, "chps")
    assert susp, "fixture sanity: the foreign file must be detected as a suspect"
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
        telemetry=ScanTelemetry(colado_suspects=susp, present_files=filenames),
    )
    mgr.apply_filename_result("2026-04", "HRB", "chps", result)
    # Force a stale True to prove the gate is evaluated fresh inside the method
    # (not merely inherited from whatever apply_filename_result already wrote).
    mgr.set_all_reliable("2026-04", "HRB", "chps", True)

    pages = {"crs.pdf": 1, "2026-05_odi_x.pdf": 1}  # both single-page → R1 origin
    value = mgr.recompute_all_reliable(
        "2026-04",
        "HRB",
        "chps",
        tmp_path / "unused",
        pages=pages,
        count_type="documents",
    )

    assert value is False
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HRB"]["chps"]["all_reliable"] is False
