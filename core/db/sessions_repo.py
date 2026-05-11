"""Sessions table CRUD."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    year: int
    month: int
    state_json: str
    created_at: str
    last_modified: str
    status: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_id(year: int, month: int) -> str:
    if not (1 <= month <= 12):
        raise ValueError(f"month out of range: {month}")
    return f"{year:04d}-{month:02d}"


def create_session(
    conn: sqlite3.Connection,
    *,
    year: int,
    month: int,
    state_json: str,
) -> SessionRecord:
    """Create or return existing active session for (year, month).

    Args:
        conn: Open SQLite connection with sessions table initialised.
        year: Calendar year of the session.
        month: Calendar month (1-12).
        state_json: Initial JSON state blob.

    Returns:
        The newly created SessionRecord, or the existing one if a session
        for (year, month) already exists.
    """
    sid = _session_id(year, month)
    existing = get_session(conn, sid)
    if existing is not None:
        return existing
    now = _now_iso()
    conn.execute(
        "INSERT INTO sessions "
        "(session_id, year, month, state_json, created_at, last_modified, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active')",
        (sid, year, month, state_json, now, now),
    )
    return SessionRecord(sid, year, month, state_json, now, now, "active")


def get_session(conn: sqlite3.Connection, session_id: str) -> SessionRecord | None:
    """Fetch a session by its ID.

    Args:
        conn: Open SQLite connection.
        session_id: The session identifier (e.g. ``"2026-04"``).

    Returns:
        A SessionRecord if found, or ``None``.
    """
    row = conn.execute(
        "SELECT session_id, year, month, state_json, created_at, last_modified, status "
        "FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return SessionRecord(**dict(row))


def update_session_state(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    state_json: str,
) -> None:
    """Overwrite the state blob and bump last_modified.

    Args:
        conn: Open SQLite connection.
        session_id: Target session identifier.
        state_json: New JSON state blob.
    """
    conn.execute(
        "UPDATE sessions SET state_json = ?, last_modified = ? WHERE session_id = ?",
        (state_json, _now_iso(), session_id),
    )


def finalize_session(conn: sqlite3.Connection, session_id: str) -> None:
    """Mark a session as finalized.

    Args:
        conn: Open SQLite connection.
        session_id: Target session identifier.
    """
    conn.execute(
        "UPDATE sessions SET status = 'finalized', last_modified = ? WHERE session_id = ?",
        (_now_iso(), session_id),
    )
