"""Project-root pytest fixtures visible to both eval/tests/ and tests/.

make_pagination_pdf: generate a synthetic compilation PDF with clean pagination
text in the top-right corner. NO personal data — safe to commit and use in tests.

make_pdf / make_manager (§C5 suite-diet dedup, 2026-07-11): ~8 near-identical
``_make_pdf(path, pages)`` and ~5 near-identical ``_make_manager(tmp_path)``
per-file helpers, unified here so tests inject them by fixture name instead of
each file redefining its own copy.
"""

import fitz
import pytest


@pytest.fixture
def make_pdf():
    """Write a real *pages*-page PDF at *path* (creating parent dirs as needed).

    Dedup of ~8 near-identical per-file ``_make_pdf`` helpers (some required
    ``n_pages``/``pages`` positionally, one defaulted to 1, one pre-created
    the parent folder) — this version covers every call-site variant.
    """

    def _make(path, pages: int = 1) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open()
        for _ in range(pages):
            doc.new_page()
        doc.save(str(path))
        doc.close()

    return _make


@pytest.fixture
def make_manager(tmp_path):
    """A real ``SessionManager`` backed by a temp SQLite DB.

    Dedup of ~5 near-identical per-file ``_make_manager(tmp_path)`` helpers
    (open_connection + init_schema + SessionManager(conn=conn)).
    """
    from api.state import SessionManager
    from core.db.connection import open_connection
    from core.db.migrations import init_schema

    conn = open_connection(tmp_path / "test.db")
    init_schema(conn)
    return SessionManager(conn=conn)


@pytest.fixture
def make_pagination_pdf():
    """Generate a synthetic compilation PDF: docs=[(n_pages, code), ...].

    Draws "Codigo: {code}" and "Pagina {c} de {n}" in the top-right corner of each
    page. NO personal data — safe to commit and use in tests. landscape=True emits
    A4-landscape pages (exercises the orientation branch).
    """

    def _make(path, docs, landscape=False):
        doc = fitz.open()
        rect = fitz.paper_rect("a4-l" if landscape else "a4")
        for n_pages, code in docs:
            for c in range(1, n_pages + 1):
                page = doc.new_page(width=rect.width, height=rect.height)
                x = page.rect.width - 230
                page.insert_text((x, 36), f"Codigo: {code}", fontsize=10)
                page.insert_text((x, 52), f"Pagina {c} de {n_pages}", fontsize=10)
                page.insert_text((72, 200), "contenido de prueba", fontsize=12)
        doc.save(path)
        doc.close()
        return path

    return _make
