import sqlite3
from pathlib import Path

import pytest
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


def test_open_connection_creates_db_file(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_connection(db_path)
    assert db_path.exists()
    assert isinstance(conn, sqlite3.Connection)
    close_all()


def test_open_connection_enables_wal(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_connection(db_path)
    cursor = conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"
    close_all()


def test_init_schema_creates_expected_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_connection(db_path)
    init_schema(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "sessions" in tables
    assert "historical_counts" in tables
    close_all()
