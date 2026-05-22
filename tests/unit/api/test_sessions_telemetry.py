"""A14: near-match telemetry survives the OCR result → cell-state → GET path.

Tests that:
1. apply_ocr_result persists NearMatchEntry data into the cell state dict.
2. get_session_state returns near_matches in the cell payload.
3. apply_ocr_result with no telemetry yields an empty near_matches list.
"""

from __future__ import annotations

import pytest

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema
from core.scanners.base import (
    ConfidenceLevel,
    NearMatchEntry,
    ScanResult,
    ScanTelemetry,
)


@pytest.fixture
def mgr(tmp_path):
    conn = open_connection(tmp_path / "test_telemetry.db")
    init_schema(conn)
    manager = SessionManager(conn=conn)
    yield manager
    close_all()


def _open_session(mgr: SessionManager, tmp_path) -> str:
    state = mgr.open_session(year=2026, month=4, month_root=tmp_path)
    return state["session_id"]


def _make_result_with_near_match() -> ScanResult:
    entry = NearMatchEntry(
        pdf_name="ejemplo.pdf",
        page_index=3,
        flavor_name="f_lch_05",
        matched_anchors=["LISTA DE CHEQUEO", "Empresa"],
        missing_anchors=["Código"],
    )
    return ScanResult(
        count=2,
        confidence=ConfidenceLevel.HIGH,
        method="header_band_anchors",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=120,
        files_scanned=3,
        telemetry=ScanTelemetry(near_matches=[entry]),
    )


def test_apply_ocr_result_persists_near_matches(mgr, tmp_path):
    """near_matches from telemetry land in the cell state after apply_ocr_result."""
    sid = _open_session(mgr, tmp_path)
    result = _make_result_with_near_match()
    mgr.apply_ocr_result(sid, "HPV", "odi", result)

    state = mgr.get_session_state(sid)
    cell = state["cells"]["HPV"]["odi"]

    assert "near_matches" in cell
    assert len(cell["near_matches"]) == 1
    nm = cell["near_matches"][0]
    assert nm["pdf_name"] == "ejemplo.pdf"
    assert nm["page_index"] == 3
    assert nm["flavor_name"] == "f_lch_05"
    assert nm["matched_anchors"] == ["LISTA DE CHEQUEO", "Empresa"]
    assert nm["missing_anchors"] == ["Código"]


def test_apply_ocr_result_no_telemetry_yields_empty_list(mgr, tmp_path):
    """When result.telemetry is None, near_matches is an empty list (not absent)."""
    sid = _open_session(mgr, tmp_path)
    result = ScanResult(
        count=1,
        confidence=ConfidenceLevel.MEDIUM,
        method="header_band_anchors",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=50,
        files_scanned=1,
        telemetry=None,
    )
    mgr.apply_ocr_result(sid, "HRB", "charla", result)

    state = mgr.get_session_state(sid)
    cell = state["cells"]["HRB"]["charla"]
    assert cell.get("near_matches") == []


def test_get_session_state_includes_near_matches(mgr, tmp_path):
    """get_session_state returns near_matches in the cell (round-trip through DB)."""
    sid = _open_session(mgr, tmp_path)
    result = _make_result_with_near_match()
    mgr.apply_ocr_result(sid, "HLL", "odi", result)

    # Reload from DB to verify persistence is real, not just in-memory.
    state = mgr.get_session_state(sid)
    cell = state["cells"]["HLL"]["odi"]
    assert len(cell["near_matches"]) == 1
    assert cell["near_matches"][0]["flavor_name"] == "f_lch_05"
