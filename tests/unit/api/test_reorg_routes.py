"""Tests for refresh_reorg_deltas (Incr J T6) and scan wiring (T7)."""

from __future__ import annotations

import sqlite3
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
