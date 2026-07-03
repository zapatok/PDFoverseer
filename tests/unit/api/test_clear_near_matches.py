"""E5 — clear near-match suspects (all / individual / no-op)."""

from __future__ import annotations

import json

import pytest

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def manager(tmp_path):
    # open_session only stores month_root as a string (no disk read), so a
    # synthetic path is equivalent to the real corpus here — see QA-3 audit.
    conn = open_connection(tmp_path / "clear_nm.db")
    init_schema(conn)
    mgr = SessionManager(conn=conn)
    mgr.open_session(year=2026, month=4, month_root=tmp_path / "ABRIL")
    yield mgr
    close_all()


def _seed(manager, *, near_matches):
    state = manager.get_session_state("2026-04")
    state.setdefault("cells", {}).setdefault("HPV", {})["andamios"] = {
        "per_file": {"a.pdf": 0},
        "near_matches": near_matches,
    }
    from core.db.sessions_repo import update_session_state

    update_session_state(manager._conn, "2026-04", state_json=json.dumps(state))


def _near(manager):
    cell = manager.get_session_state("2026-04")["cells"]["HPV"]["andamios"]
    return cell.get("near_matches")


def test_clear_individual_removes_only_that_entry(manager):
    _seed(
        manager,
        near_matches=[
            {"pdf_name": "a.pdf", "page_index": 2, "flavor_name": "f_x"},
            {"pdf_name": "a.pdf", "page_index": 5, "flavor_name": "f_y"},
            {"pdf_name": "b.pdf", "page_index": 1, "flavor_name": "f_z"},
        ],
    )
    manager.clear_near_matches("2026-04", "HPV", "andamios", pdf_name="a.pdf", page_index=2)
    remaining = _near(manager)
    assert len(remaining) == 2
    assert {(nm["pdf_name"], nm["page_index"]) for nm in remaining} == {("a.pdf", 5), ("b.pdf", 1)}


def test_clear_all_empties_the_list(manager):
    _seed(
        manager,
        near_matches=[
            {"pdf_name": "a.pdf", "page_index": 2, "flavor_name": "f_x"},
            {"pdf_name": "b.pdf", "page_index": 1, "flavor_name": "f_z"},
        ],
    )
    manager.clear_near_matches("2026-04", "HPV", "andamios")
    assert _near(manager) == []


def test_clear_is_noop_on_absent_cell(manager):
    # No cell seeded → must not raise.
    manager.clear_near_matches("2026-04", "HRB", "odi")
    manager.clear_near_matches("2026-04", "HRB", "odi", pdf_name="x.pdf", page_index=0)
