"""Tests for §B4: SessionManager.recompute_all_reliable — atomic
load→compute→persist of all_reliable in ONE RLock acquisition, with the
anti-colados gate (§4.5) living inside the atomic method itself.
"""

from __future__ import annotations

from pathlib import Path

from core.scanners.base import ConfidenceLevel, ScanResult, ScanTelemetry
from core.scanners.utils.colado_guard import find_foreign_filename_suspects

# ── helpers ──────────────────────────────────────────────────────────────────


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


def test_recompute_all_reliable_persists_fresh_settled_true(tmp_path, make_manager):
    mgr = make_manager
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


def test_recompute_all_reliable_persists_fresh_settled_false(tmp_path, make_manager):
    mgr = make_manager
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


def test_recompute_all_reliable_blocked_by_open_counted_suspect(tmp_path, make_manager):
    """A cell whose files are otherwise fully settled (compute_settled → True)
    must still end up all_reliable=False when an OPEN, COUNTED colado suspect
    exists — the §4.5 gate must fire from INSIDE recompute_all_reliable, not
    rely on a separate caller-side check."""
    mgr = make_manager
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


# ── (c) the wrapper resolves the disk I/O BEFORE delegating (lock-free walk) ──


def _spy_recompute(mgr, monkeypatch):
    """Wrap mgr.recompute_all_reliable recording the kwargs the WRAPPER passed."""
    received: dict = {}
    orig = mgr.recompute_all_reliable

    def spy(session_id, hospital, sigla, folder, *, pages, count_type=None):
        received["pages"] = pages
        return orig(session_id, hospital, sigla, folder, pages=pages, count_type=count_type)

    monkeypatch.setattr(mgr, "recompute_all_reliable", spy)
    return received


def test_refresh_all_reliable_resolves_pages_before_delegating(tmp_path, monkeypatch, make_manager):
    """§B4's point: with pages=None, the folder walk (cell_page_counts) happens in
    the WRAPPER — before the delegate acquires the RLock — and the atomic method
    receives the already-resolved dict, never None. This test fails if the wrapper
    forwards None and lets compute_settled walk the disk under the lock."""
    from api.routes.sessions import _common

    mgr = make_manager
    _seed_reliable_cell(mgr, tmp_path)

    walk_calls: list[Path] = []

    def fake_cell_page_counts(folder):
        walk_calls.append(folder)
        return {"a.pdf": 1}

    monkeypatch.setattr(_common, "cell_page_counts", fake_cell_page_counts)
    received = _spy_recompute(mgr, monkeypatch)

    folder = tmp_path / "HRB" / "3.-ODI Visitas"
    _common.refresh_all_reliable(
        mgr, "2026-04", "HRB", "odi", folder, pages=None, count_type="documents"
    )

    assert walk_calls == [folder], "the wrapper must resolve the walk exactly once"
    assert received["pages"] == {"a.pdf": 1}, "the delegate must receive resolved pages, not None"
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HRB"]["odi"]["all_reliable"] is True


def test_refresh_all_reliable_precomputed_pages_skip_the_walk(tmp_path, monkeypatch, make_manager):
    """When the caller already computed pages, the wrapper must NOT walk again."""
    from api.routes.sessions import _common

    mgr = make_manager
    _seed_reliable_cell(mgr, tmp_path)

    def boom(folder):
        raise AssertionError("cell_page_counts must not be called when pages is given")

    monkeypatch.setattr(_common, "cell_page_counts", boom)
    received = _spy_recompute(mgr, monkeypatch)

    _common.refresh_all_reliable(
        mgr,
        "2026-04",
        "HRB",
        "odi",
        tmp_path / "unused",
        pages={"a.pdf": 1},
        count_type="documents",
    )

    assert received["pages"] == {"a.pdf": 1}


def test_refresh_all_reliable_checks_cells_never_walk_the_folder(tmp_path, monkeypatch, make_manager):
    """checks cells settle on worker_status alone (compute_settled short-circuits
    before reading pages) — the old code therefore never walked their folder, and
    the wrapper must not start doing so: it delegates inert empty pages instead."""
    from api.routes.sessions import _common

    mgr = make_manager
    _seed_reliable_cell(mgr, tmp_path, sigla="maquinaria")

    walk_calls: list[Path] = []

    def fake_cell_page_counts(folder):
        walk_calls.append(folder)
        return {}

    monkeypatch.setattr(_common, "cell_page_counts", fake_cell_page_counts)
    received = _spy_recompute(mgr, monkeypatch)

    _common.refresh_all_reliable(
        mgr,
        "2026-04",
        "HRB",
        "maquinaria",
        tmp_path / "unused",
        pages=None,
        count_type="checks",
    )

    assert walk_calls == [], "checks cells must not pay a folder walk"
    assert received["pages"] == {}, "the delegate still receives resolved (empty) pages"
    state = mgr.get_session_state("2026-04")
    # worker_status is unset → not 'terminado' → not settled.
    assert state["cells"]["HRB"]["maquinaria"]["all_reliable"] is False
