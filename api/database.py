import sqlite3
from pathlib import Path
from core.utils import _PageRead

DB_PATH = Path("data/sessions.db")
DB_PATH.parent.mkdir(exist_ok=True, parents=True)

def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS page_reads (
                session_id TEXT,
                pdf_path TEXT,
                page_idx INTEGER,
                curr INTEGER,
                total INTEGER,
                method TEXT,
                confidence REAL,
                PRIMARY KEY (session_id, pdf_path, page_idx)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pdf_session ON page_reads (session_id, pdf_path)")

_init_db()

def save_reads(session_id: str, pdf_path: str, reads: list[_PageRead]):
    # with conn: provides atomic transaction (auto-rollback on exception)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM page_reads WHERE session_id=? AND pdf_path=?", (session_id, pdf_path))
        data = [
            (session_id, pdf_path, r.pdf_page, r.curr, r.total, r.method, r.confidence)
            for r in reads
        ]
        conn.executemany(
            "INSERT INTO page_reads VALUES (?, ?, ?, ?, ?, ?, ?)",
            data
        )

def has_reads(session_id: str, pdf_path: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT 1 FROM page_reads WHERE session_id=? AND pdf_path=? LIMIT 1",
            (session_id, pdf_path)
        )
        return cur.fetchone() is not None

def get_reads(session_id: str, pdf_path: str) -> list[_PageRead]:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT page_idx, curr, total, method, confidence FROM page_reads WHERE session_id=? AND pdf_path=? ORDER BY page_idx",
            (session_id, pdf_path)
        )
        return [_PageRead(*row) for row in cur.fetchall()]

def clear_session(session_id: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM page_reads WHERE session_id=?", (session_id,))
