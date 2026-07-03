"""Regression test for the 2026-07 OVERSEER_DB_PATH test-isolation incident.

Incident: several tests called api.main.create_app() without setting
OVERSEER_DB_PATH, so they opened + wrote to the REAL production DB
(data/overseer.db) on every fast-suite run. Confirmed writer:
test_agent_broadcast.py::test_agent_override_endpoint_200_on_free_cell
PATCHed the real 2026-04 HRB|odi cell with user_override=3.

This test proves the autouse ``_db_path_isolation`` fixture in conftest.py
keeps EVERY test — even one that calls create_app()/_db_path() bare, with no
explicit monkeypatch of its own — off the real DB file.
"""

from __future__ import annotations

from pathlib import Path

from api.main import _db_path

_REAL_DB_PATH = Path("A:/PROJECTS/PDFoverseer/data/overseer.db").resolve()


def test_bare_db_path_does_not_resolve_to_real_db():
    """A bare _db_path() call under pytest must never resolve to the real
    production database — the autouse fixture must have redirected
    OVERSEER_DB_PATH to a per-test tmp path."""
    resolved = _db_path().resolve()
    assert resolved != _REAL_DB_PATH, (
        f"_db_path() resolved to the REAL db ({resolved}) — the "
        "OVERSEER_DB_PATH test-isolation guard is not active"
    )
