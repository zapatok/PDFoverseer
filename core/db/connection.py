"""SQLite connection lifecycle for PDFoverseer.

Single connection per process (orchestrator owns it). WAL mode for
crash safety. close_all() called from FastAPI lifespan shutdown.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_CONNECTIONS: dict[Path, sqlite3.Connection] = {}
_LOCK = threading.Lock()


def open_connection(db_path: Path) -> sqlite3.Connection:
    """Open or return cached connection. Enables WAL mode + foreign keys.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open sqlite3.Connection with WAL mode and foreign keys enabled.
    """
    db_path = Path(db_path).resolve()
    with _LOCK:
        if db_path in _CONNECTIONS:
            return _CONNECTIONS[db_path]
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        _CONNECTIONS[db_path] = conn
        return conn


def close_all() -> None:
    """Close all cached connections — call from app shutdown."""
    with _LOCK:
        for conn in _CONNECTIONS.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _CONNECTIONS.clear()
