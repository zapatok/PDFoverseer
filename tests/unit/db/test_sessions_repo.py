import json

import pytest

from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema
from core.db.sessions_repo import (
    SessionRecord,
    create_session,
    finalize_session,
    get_session,
    update_session_state,
)


@pytest.fixture
def conn(tmp_path):
    conn = open_connection(tmp_path / "t.db")
    init_schema(conn)
    yield conn
    close_all()


def test_create_session_persists(conn):
    rec = create_session(conn, year=2026, month=4, state_json='{"cells":{}}')
    assert rec.session_id == "2026-04"
    assert rec.status == "active"
    fetched = get_session(conn, "2026-04")
    assert fetched == rec


def test_get_session_missing_returns_none(conn):
    assert get_session(conn, "1999-12") is None


def test_update_state_changes_last_modified(conn):
    create_session(conn, year=2026, month=4, state_json='{"v":1}')
    update_session_state(conn, "2026-04", state_json='{"v":2}')
    rec = get_session(conn, "2026-04")
    assert json.loads(rec.state_json) == {"v": 2}


def test_finalize_session_changes_status(conn):
    create_session(conn, year=2026, month=4, state_json='{"v":1}')
    finalize_session(conn, "2026-04")
    rec = get_session(conn, "2026-04")
    assert rec.status == "finalized"


def test_create_session_existing_active_returns_same(conn):
    rec1 = create_session(conn, year=2026, month=4, state_json='{"v":1}')
    rec2 = create_session(conn, year=2026, month=4, state_json='{"v":99}')
    # second call returns existing, does not overwrite
    assert rec1.session_id == rec2.session_id
    assert json.loads(rec2.state_json) == {"v": 1}
