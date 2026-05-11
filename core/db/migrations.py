"""Schema initialization for PDFoverseer DB. Idempotent."""

from __future__ import annotations

import sqlite3

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_modified TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'finalized'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_status
    ON sessions(status, last_modified);

CREATE TABLE IF NOT EXISTS historical_counts (
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    hospital TEXT NOT NULL,
    sigla TEXT NOT NULL,
    count INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    method TEXT NOT NULL,
    finalized_at TEXT NOT NULL,
    PRIMARY KEY (year, month, hospital, sigla)
);

CREATE INDEX IF NOT EXISTS idx_historical_year
    ON historical_counts(year, month);

CREATE INDEX IF NOT EXISTS idx_historical_sigla
    ON historical_counts(sigla, year);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indices if missing. Idempotent.

    Args:
        conn: An open sqlite3.Connection to initialize.
    """
    conn.executescript(_SCHEMA_SQL)
