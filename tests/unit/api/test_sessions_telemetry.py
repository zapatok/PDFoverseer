"""A14: near-match telemetry survives the OCR result → cell-state → GET path.

Tests that:
1. apply_per_file_ocr_result persists near-match dicts into the cell state.
2. get_session_state returns near_matches in the cell payload.
3. apply_per_file_ocr_result with an empty near_matches list yields an empty
   list (not absent).
"""

from __future__ import annotations

import pytest

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


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


_NEAR_MATCH = {
    "pdf_name": "ejemplo.pdf",
    "page_index": 3,
    "flavor_name": "f_lch_05",
    "matched_anchors": ["LISTA DE CHEQUEO", "Empresa"],
    "missing_anchors": ["Código"],
}


def test_apply_per_file_ocr_result_persists_near_matches(mgr, tmp_path):
    """near_matches from a per-file OCR merge land in the cell state."""
    sid = _open_session(mgr, tmp_path)
    mgr.apply_per_file_ocr_result(
        sid,
        "HPV",
        "odi",
        "ejemplo.pdf",
        count=2,
        method="header_band_anchors",
        near_matches=[_NEAR_MATCH],
    )

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


def test_apply_per_file_ocr_result_no_near_matches_yields_empty_list(mgr, tmp_path):
    """An empty near_matches list persists as an empty list (not absent)."""
    sid = _open_session(mgr, tmp_path)
    mgr.apply_per_file_ocr_result(
        sid,
        "HRB",
        "charla",
        "a.pdf",
        count=1,
        method="header_band_anchors",
        near_matches=[],
    )

    state = mgr.get_session_state(sid)
    cell = state["cells"]["HRB"]["charla"]
    assert cell.get("near_matches") == []


def test_get_session_state_includes_near_matches(mgr, tmp_path):
    """get_session_state returns near_matches in the cell (round-trip through DB)."""
    sid = _open_session(mgr, tmp_path)
    mgr.apply_per_file_ocr_result(
        sid,
        "HLL",
        "odi",
        "ejemplo.pdf",
        count=2,
        method="header_band_anchors",
        near_matches=[_NEAR_MATCH],
    )

    # Reload from DB to verify persistence is real, not just in-memory.
    state = mgr.get_session_state(sid)
    cell = state["cells"]["HLL"]["odi"]
    assert len(cell["near_matches"]) == 1
    assert cell["near_matches"][0]["flavor_name"] == "f_lch_05"
