"""Project-root pytest fixtures visible to both eval/tests/ and tests/.

make_pagination_pdf: generate a synthetic compilation PDF with clean pagination
text in the top-right corner. NO personal data — safe to commit and use in tests.
"""

import fitz
import pytest


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
