import json
from pathlib import Path

import pytest

from api.state import SessionManager, compute_worker_count
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def conn(tmp_path):
    conn = open_connection(tmp_path / "api.db")
    init_schema(conn)
    yield conn
    close_all()


def test_open_session_creates_new_if_not_exists(conn):
    mgr = SessionManager(conn=conn)
    state = mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    assert state["session_id"] == "2026-04"
    assert state["month_root"] == "A:/informe mensual/ABRIL"


def test_open_session_returns_existing(conn):
    mgr = SessionManager(conn=conn)
    s1 = mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    s2 = mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    assert s1["session_id"] == s2["session_id"]


def test_apply_cell_result_persists(conn):
    from core.scanners.base import ConfidenceLevel, ScanResult

    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4, month_root=Path("A:/informe mensual/ABRIL"))
    result = ScanResult(
        count=767,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=767,
    )
    mgr.apply_cell_result("2026-04", "HPV", "art", result)
    state = mgr.get_session_state("2026-04")
    assert state["cells"]["HPV"]["art"]["filename_count"] == 767


# Tests for the three new fine-grained setters


@pytest.fixture
def manager(tmp_path):

    conn = open_connection(tmp_path / "v2.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    yield mgr
    close_all()


def _filename_result(count: int):
    from core.scanners.base import ConfidenceLevel, ScanResult

    return ScanResult(
        count=count,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=count,
        duration_ms=10,
    )


def _ocr_result(count: int, method: str = "header_detect"):
    from core.scanners.base import ConfidenceLevel, ScanResult

    return ScanResult(
        count=count,
        confidence=ConfidenceLevel.HIGH,
        method=method,
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=1,
        duration_ms=23000,
    )


def test_apply_filename_result_sets_filename_count_only(manager):
    manager.apply_filename_result("2026-04", "HPV", "art", _filename_result(767))
    state = manager.get_session_state("2026-04")
    cell = state["cells"]["HPV"]["art"]
    assert cell["filename_count"] == 767
    assert cell["ocr_count"] is None
    assert cell["user_override"] is None
    assert cell["override_note"] is None
    assert cell["method"] == "filename_glob"
    assert cell["duration_ms_filename"] == 10
    # Lock the isolation contract from both sides — filename pass never sets OCR duration
    assert cell.get("duration_ms_ocr") is None


def test_apply_ocr_result_sets_ocr_count_and_method_without_touching_filename(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_ocr_result("2026-04", "HRB", "odi", _ocr_result(17, "header_detect"))
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["filename_count"] == 1
    assert cell["ocr_count"] == 17
    assert cell["method"] == "header_detect"
    assert cell["duration_ms_ocr"] == 23000


def test_apply_ocr_result_with_filename_glob_fallback_method(manager):
    # OCR scanner failed internally, fell back to filename_glob
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    fallback = _ocr_result(1, "filename_glob")
    manager.apply_ocr_result("2026-04", "HRB", "odi", fallback)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["ocr_count"] == 1
    assert cell["method"] == "filename_glob"


def test_filename_rescan_preserves_near_matches_for_ocr_cell(manager):
    """Supersedes the old Bug-B "clear on pase-1" behavior: the 2026-06-05 fix
    stops a bulk filename re-scan from touching an OCR-counted cell's per_file,
    so its near-matches stay consistent with that per_file and must be preserved
    too. A fresh per_file (and fresh near-matches) only land on an intentional
    re-OCR of the cell, not on the bulk "add a hospital" pass."""
    from core.scanners.base import (
        ConfidenceLevel,
        NearMatchEntry,
        ScanResult,
        ScanTelemetry,
    )

    ocr = ScanResult(
        count=1,
        confidence=ConfidenceLevel.LOW,
        method="header_band_anchors",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=1,
        duration_ms=1,
        per_file={"old.pdf": 1},
        telemetry=ScanTelemetry(
            near_matches=[
                NearMatchEntry(
                    pdf_name="old.pdf",
                    page_index=0,
                    flavor_name="f",
                    matched_anchors=["a"],
                    missing_anchors=["b"],
                )
            ]
        ),
    )
    manager.apply_ocr_result("2026-04", "HRB", "odi", ocr)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["near_matches"]  # the OCR run populated it

    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["near_matches"]  # preserved — the OCR cell was not clobbered
    assert cell["per_file"] == {"old.pdf": 1}  # OCR per_file intact too


def test_apply_results_write_per_file_method(manager):
    """Every cell run records how each file was counted (rev-2 §3)."""
    from core.scanners.base import ConfidenceLevel, ScanResult

    fr = ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"a.pdf": 1, "b.pdf": 1},
    )
    manager.apply_filename_result("2026-04", "HRB", "odi", fr)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["per_file_method"] == {
        "a.pdf": "filename_glob",
        "b.pdf": "filename_glob",
    }

    orr = ScanResult(
        count=3,
        confidence=ConfidenceLevel.HIGH,
        method="header_band_anchors",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"a.pdf": 3, "b.pdf": 0},
    )
    manager.apply_ocr_result("2026-04", "HRB", "odi", orr)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["per_file_method"] == {
        "a.pdf": "header_band_anchors",
        "b.pdf": "header_band_anchors",
    }


def test_filename_rescan_preserves_full_cell_ocr_count(manager):
    """Regression (real incident 2026-06-05): 'Escanear todos los hospitales'
    runs pase 1 over EVERY cell — including hospitals already counted by OCR.
    It must NOT overwrite an OCR-counted cell's per_file with filename counts,
    or the displayed total (which sums per_file) silently reverts. Adding HLL
    reset HRB/art from its OCR count back to the filename count."""
    from api.state import compute_cell_count
    from core.scanners.base import ConfidenceLevel, ScanResult

    ocr = ScanResult(
        count=3,
        confidence=ConfidenceLevel.HIGH,
        method="header_band_anchors",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"big.pdf": 2, "small.pdf": 1},
    )
    manager.apply_ocr_result("2026-04", "HRB", "art", ocr)
    assert compute_cell_count(manager.get_session_state("2026-04")["cells"]["HRB"]["art"]) == 3

    # A later bulk pase-1 re-scan sees the same 2 files → 1 doc each by name.
    rescan = ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"big.pdf": 1, "small.pdf": 1},
    )
    manager.apply_filename_result("2026-04", "HRB", "art", rescan)

    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["art"]
    assert cell["per_file"] == {"big.pdf": 2, "small.pdf": 1}, "OCR per_file was clobbered"
    assert cell["ocr_count"] == 3
    assert cell["method"] == "header_band_anchors"
    assert compute_cell_count(cell) == 3  # not 2
    # The filename hint may still refresh, but it must not drive the count.
    assert cell["filename_count"] == 2


def test_filename_rescan_preserves_per_file_ocr_only_cell(manager):
    """A cell OCR'd file-by-file from the viewer (rev-2 #1) carries per_file OCR
    data while ocr_count stays None. A bulk filename re-scan must still leave it
    intact — the guard cannot key on ocr_count alone."""
    manager.apply_filename_result("2026-04", "HRB", "art", _filename_result(2))
    manager.apply_per_file_ocr_result(
        "2026-04",
        "HRB",
        "art",
        "big.pdf",
        count=7,
        method="header_band_anchors",
        near_matches=[],
    )
    manager.apply_filename_result("2026-04", "HRB", "art", _filename_result(2))

    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["art"]
    assert cell["per_file"].get("big.pdf") == 7, "per-file OCR count was reset by re-scan"
    assert cell["per_file_method"].get("big.pdf") == "header_band_anchors"


def test_filename_rescan_still_refreshes_fresh_cell(manager):
    """A cell with no OCR/manual work is still fully refreshed by a re-scan, so
    a brand-new hospital (all cells fresh) and added files are picked up."""
    from core.scanners.base import ConfidenceLevel, ScanResult

    manager.apply_filename_result("2026-04", "HLL", "art", _filename_result(2))
    bigger = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=5,
        duration_ms=1,
        per_file={"a.pdf": 1, "b.pdf": 1, "c.pdf": 1, "d.pdf": 1, "e.pdf": 1},
    )
    manager.apply_filename_result("2026-04", "HLL", "art", bigger)
    cell = manager.get_session_state("2026-04")["cells"]["HLL"]["art"]
    assert cell["filename_count"] == 5
    assert len(cell["per_file"]) == 5


def test_worker_marks_alone_mark_cell_as_worked():
    """A charla/chintegral cell counted only via worker marks (Feature 1) — no
    OCR, override, 'listo' or per-file override — must still count as worked, so a
    bulk filename re-scan does not clobber the per_file its marks are linked to."""
    from api.state import _cell_has_work

    cell = {
        "filename_count": 5,
        "per_file": {"a.pdf": 5},
        "per_file_method": {"a.pdf": "filename_glob"},
    }
    assert _cell_has_work(cell) is False  # plain filename cell
    cell["worker_marks"] = {"a.pdf": [{"page": 0, "count": 12}]}
    assert _cell_has_work(cell) is True


def test_filename_rescan_preserves_worker_counted_cell(manager):
    """End-to-end: a worker-counted cell that is NOT yet marked 'listo' survives a
    bulk filename re-scan that brings new files — its per_file is left intact so the
    worker total stays correct."""
    from core.scanners.base import ConfidenceLevel, ScanResult

    seed = ScanResult(
        count=1,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=1,
        duration_ms=1,
        per_file={"charla1.pdf": 1},
    )
    manager.apply_filename_result("2026-04", "HRB", "charla", seed)
    manager.apply_worker_count(
        "2026-04",
        "HRB",
        "charla",
        marks={"charla1.pdf": [{"page": 0, "count": 12}]},
        status="en_progreso",
    )
    rescan = ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="filename_glob",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"charla1.pdf": 1, "charla2.pdf": 1},
    )
    manager.apply_filename_result("2026-04", "HRB", "charla", rescan)

    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["charla"]
    assert cell["per_file"] == {"charla1.pdf": 1}, "worker cell per_file was clobbered"
    assert compute_worker_count(cell) == 12


def test_apply_per_file_ocr_result_merges_one_file(manager):
    """rev-2 #1: a single-file OCR merge touches only that file's count, method
    and near-matches; everything else in the cell is preserved."""
    from core.scanners.base import ConfidenceLevel, ScanResult

    seed = ScanResult(
        count=5,
        confidence=ConfidenceLevel.HIGH,
        method="header_band_anchors",
        breakdown={},
        flags=[],
        errors=[],
        files_scanned=2,
        duration_ms=1,
        per_file={"a.pdf": 3, "b.pdf": 2},
    )
    manager.apply_ocr_result("2026-04", "HRB", "odi", seed)

    manager.apply_per_file_ocr_result(
        "2026-04",
        "HRB",
        "odi",
        "a.pdf",
        count=5,
        method="header_band_anchors",
        near_matches=[
            {
                "pdf_name": "a.pdf",
                "page_index": 0,
                "flavor_name": "f",
                "matched_anchors": ["x"],
                "missing_anchors": ["y"],
            }
        ],
    )

    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["per_file"] == {"a.pdf": 5, "b.pdf": 2}  # b untouched
    assert cell["per_file_method"]["a.pdf"] == "header_band_anchors"
    assert cell["per_file_method"]["b.pdf"] == "header_band_anchors"  # from the seed
    assert [nm["pdf_name"] for nm in cell["near_matches"]] == ["a.pdf"]


def test_apply_user_override_sets_value_and_note(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_user_override("2026-04", "HRB", "odi", value=17, note="17 ODIs in 1 PDF")
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["user_override"] == 17
    assert cell["override_note"] == "17 ODIs in 1 PDF"
    assert cell["filename_count"] == 1  # untouched


def test_apply_user_override_with_null_value_clears_override(manager):
    manager.apply_filename_result("2026-04", "HRB", "odi", _filename_result(1))
    manager.apply_user_override("2026-04", "HRB", "odi", value=17, note="initial")
    manager.apply_user_override("2026-04", "HRB", "odi", value=None, note=None)
    cell = manager.get_session_state("2026-04")["cells"]["HRB"]["odi"]
    assert cell["user_override"] is None
    assert cell["override_note"] is None


def test_apply_user_override_can_be_used_before_any_scan(manager):
    manager.apply_user_override("2026-04", "HPV", "chps", value=2, note="manual count")
    cell = manager.get_session_state("2026-04")["cells"]["HPV"]["chps"]
    assert cell["filename_count"] is None
    assert cell["ocr_count"] is None
    assert cell["user_override"] == 2


def test_get_session_state_migrates_legacy_count_on_first_read(manager, tmp_path):
    # Inject legacy state directly via raw connection
    from core.db.sessions_repo import update_session_state

    legacy_state = {
        "month_root": str(tmp_path),
        "hospitals_present": ["HPV"],
        "hospitals_missing": [],
        "cells": {"HPV": {"art": {"count": 767, "confidence": "high", "method": "filename_glob"}}},
    }
    update_session_state(manager._conn, "2026-04", state_json=json.dumps(legacy_state))
    cell = manager.get_session_state("2026-04")["cells"]["HPV"]["art"]
    assert cell["filename_count"] == 767
    assert "count" not in cell
    assert cell["ocr_count"] is None
    assert cell["override_note"] is None
    # Idempotent: second read returns the same
    cell2 = manager.get_session_state("2026-04")["cells"]["HPV"]["art"]
    assert cell2 == cell


def test_compute_worker_count_sums_marks_across_files():
    cell = {
        "per_file": {"a.pdf": 1, "b.pdf": 1},
        "worker_marks": {
            "a.pdf": [{"page": 1, "count": 12}, {"page": 2, "count": 8}],
            "b.pdf": [{"page": 1, "count": 20}],
        },
    }
    assert compute_worker_count(cell) == 40


def test_compute_worker_count_ignores_orphan_files():
    cell = {
        "per_file": {"a.pdf": 1},
        "worker_marks": {
            "a.pdf": [{"page": 1, "count": 12}],
            "renamed_old.pdf": [{"page": 1, "count": 99}],
        },
    }
    assert compute_worker_count(cell) == 12


def test_compute_worker_count_zero_when_no_marks():
    assert compute_worker_count({"per_file": {"a.pdf": 1}}) == 0
    assert compute_worker_count({}) == 0


def test_compute_worker_count_tolerates_malformed_marks():
    # worker_marks viene de un blob JSON sin tipado; debe tolerar basura.
    cell = {
        "per_file": {"a.pdf": 1},
        "worker_marks": {"a.pdf": [{"page": 1, "count": 7}, {"page": 2}, None]},
    }
    assert compute_worker_count(cell) == 7


def test_apply_worker_count_persists_all_fields(manager):
    manager.apply_worker_count(
        "2026-04",
        "HLL",
        "charla",
        marks={"a.pdf": [{"page": 1, "count": 12}]},
        status="en_progreso",
        cursor={"file": 0, "page": 1},
    )
    cell = manager.get_session_state("2026-04")["cells"]["HLL"]["charla"]
    assert cell["worker_marks"] == {"a.pdf": [{"page": 1, "count": 12}]}
    assert cell["worker_status"] == "en_progreso"
    assert cell["worker_cursor"] == {"file": 0, "page": 1}


def test_apply_worker_count_partial_patch_leaves_other_fields(manager):
    manager.apply_worker_count(
        "2026-04", "HLL", "charla", marks={"a.pdf": [{"page": 1, "count": 5}]}
    )
    manager.apply_worker_count("2026-04", "HLL", "charla", status="terminado")
    cell = manager.get_session_state("2026-04")["cells"]["HLL"]["charla"]
    assert cell["worker_marks"] == {"a.pdf": [{"page": 1, "count": 5}]}
    assert cell["worker_status"] == "terminado"


def test_apply_worker_count_empty_marks_clears(manager):
    manager.apply_worker_count(
        "2026-04", "HLL", "charla", marks={"a.pdf": [{"page": 1, "count": 5}]}
    )
    manager.apply_worker_count("2026-04", "HLL", "charla", marks={})
    cell = manager.get_session_state("2026-04")["cells"]["HLL"]["charla"]
    assert cell["worker_marks"] == {}
