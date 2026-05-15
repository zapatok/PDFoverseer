"""SessionManager.apply_per_file_override persiste override y refleja count."""

from pathlib import Path

import pytest

from api.state import SessionManager, compute_cell_count
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema
from core.scanners.base import ConfidenceLevel, ScanResult


@pytest.fixture
def mgr_with_seeded_cell(tmp_path):
    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    sid_state = mgr.open_session(year=2026, month=4, month_root=Path(tmp_path))
    sid = sid_state["session_id"]
    mgr.apply_filename_result(
        sid,
        "HRB",
        "odi",
        ScanResult(
            count=2,
            confidence=ConfidenceLevel.HIGH,
            method="filename_glob",
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=5,
            files_scanned=2,
            per_file={"a.pdf": 5, "b.pdf": 3},
        ),
    )
    yield mgr, sid
    close_all()


def test_apply_per_file_override_persists(mgr_with_seeded_cell):
    mgr, sid = mgr_with_seeded_cell
    mgr.apply_per_file_override(sid, "HRB", "odi", "a.pdf", 10)

    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["odi"]
    assert cell["per_file_overrides"]["a.pdf"] == 10
    assert compute_cell_count(cell) == 13  # 10 (override) + 3 (b.pdf)


def test_apply_per_file_override_zero_is_valid(mgr_with_seeded_cell):
    mgr, sid = mgr_with_seeded_cell
    mgr.apply_per_file_override(sid, "HRB", "odi", "a.pdf", 0)
    state, _ = mgr._load_and_migrate(sid)
    cell = state["cells"]["HRB"]["odi"]
    assert cell["per_file_overrides"]["a.pdf"] == 0
    assert compute_cell_count(cell) == 3  # 0 (override) + 3 (b.pdf)


def test_apply_per_file_override_unknown_cell_raises(mgr_with_seeded_cell):
    mgr, sid = mgr_with_seeded_cell
    with pytest.raises((KeyError, ValueError)):
        mgr.apply_per_file_override(sid, "HXX", "yyy", "any.pdf", 5)
