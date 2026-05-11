import pytest
from core.db.historical_repo import (
    get_counts_for_month,
    query_range,
    upsert_count,
)

from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def conn(tmp_path):
    conn = open_connection(tmp_path / "h.db")
    init_schema(conn)
    yield conn
    close_all()


def test_upsert_inserts_new(conn):
    upsert_count(
        conn,
        year=2026,
        month=4,
        hospital="HPV",
        sigla="art",
        count=767,
        confidence="high",
        method="filename_glob",
    )
    rows = get_counts_for_month(conn, year=2026, month=4)
    assert len(rows) == 1
    assert rows[0].count == 767


def test_upsert_updates_existing(conn):
    upsert_count(
        conn,
        year=2026,
        month=4,
        hospital="HPV",
        sigla="art",
        count=767,
        confidence="high",
        method="filename_glob",
    )
    upsert_count(
        conn,
        year=2026,
        month=4,
        hospital="HPV",
        sigla="art",
        count=800,
        confidence="manual",
        method="manual",
    )
    rows = get_counts_for_month(conn, year=2026, month=4)
    assert len(rows) == 1
    assert rows[0].count == 800
    assert rows[0].method == "manual"


def test_query_range_across_months(conn):
    for month in (3, 4, 5):
        upsert_count(
            conn,
            year=2026,
            month=month,
            hospital="HPV",
            sigla="art",
            count=100 * month,
            confidence="high",
            method="filename_glob",
        )
    rows = query_range(conn, from_year=2026, from_month=3, to_year=2026, to_month=5)
    assert len(rows) == 3
    counts = sorted(r.count for r in rows)
    assert counts == [300, 400, 500]
