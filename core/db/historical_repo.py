"""Historical counts table CRUD + cross-month queries."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class HistoricalCount:
    year: int
    month: int
    hospital: str
    sigla: str
    count: int
    confidence: str
    method: str
    finalized_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def upsert_count(
    conn: sqlite3.Connection,
    *,
    year: int,
    month: int,
    hospital: str,
    sigla: str,
    count: int,
    confidence: str,
    method: str,
) -> None:
    """Insert or update a historical count record.

    Args:
        conn: Open SQLite connection.
        year: Calendar year of the count.
        month: Calendar month of the count (1-12).
        hospital: Hospital identifier string.
        sigla: Document type sigla (e.g. "art", "hll").
        count: Number of documents counted.
        confidence: Confidence level string (e.g. "high", "manual").
        method: Method used to derive the count.
    """
    conn.execute(
        "INSERT INTO historical_counts "
        "(year, month, hospital, sigla, count, confidence, method, finalized_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(year, month, hospital, sigla) DO UPDATE SET "
        "count = excluded.count, confidence = excluded.confidence, "
        "method = excluded.method, finalized_at = excluded.finalized_at",
        (year, month, hospital, sigla, count, confidence, method, _now_iso()),
    )


def get_counts_for_month(
    conn: sqlite3.Connection, *, year: int, month: int
) -> list[HistoricalCount]:
    """Return all historical count records for a given year/month.

    Args:
        conn: Open SQLite connection.
        year: Calendar year to query.
        month: Calendar month to query (1-12).

    Returns:
        List of HistoricalCount dataclasses for the requested month.
    """
    rows = conn.execute(
        "SELECT year, month, hospital, sigla, count, confidence, method, finalized_at "
        "FROM historical_counts WHERE year = ? AND month = ?",
        (year, month),
    ).fetchall()
    return [HistoricalCount(**dict(r)) for r in rows]


def query_range(
    conn: sqlite3.Connection,
    *,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> list[HistoricalCount]:
    """Return all records within an inclusive year/month range.

    Uses a computed key (year * 12 + month) to handle cross-year ranges
    without complex multi-column comparisons.

    Args:
        conn: Open SQLite connection.
        from_year: Start year (inclusive).
        from_month: Start month (inclusive, 1-12).
        to_year: End year (inclusive).
        to_month: End month (inclusive, 1-12).

    Returns:
        List of HistoricalCount records ordered by year, month, hospital, sigla.
    """
    from_key = from_year * 12 + from_month
    to_key = to_year * 12 + to_month
    rows = conn.execute(
        "SELECT year, month, hospital, sigla, count, confidence, method, finalized_at "
        "FROM historical_counts WHERE (year * 12 + month) BETWEEN ? AND ? "
        "ORDER BY year, month, hospital, sigla",
        (from_key, to_key),
    ).fetchall()
    return [HistoricalCount(**dict(r)) for r in rows]
