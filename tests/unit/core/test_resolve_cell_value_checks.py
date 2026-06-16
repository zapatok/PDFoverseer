"""Task 2.3 — resolve_cell_value enruta el tally de chequeos al Excel.

Para count_type="checks" (maquinaria) el valor de la celda del Excel es el tally
de chequeos (worker_marks filtrado por present_files), no la cascada de documentos.
"""

from core.excel.writer import resolve_cell_value


def test_resolve_checks_returns_tally():
    cell = {"worker_marks": {"m.pdf": [{"page": 1, "count": 7}]}}
    assert resolve_cell_value(cell, count_type="checks", present_files={"m.pdf"}) == 7


def test_resolve_checks_drops_orphan_marks():
    cell = {
        "worker_marks": {
            "m.pdf": [{"page": 1, "count": 7}],
            "orphan.pdf": [{"page": 1, "count": 9}],
        }
    }
    assert resolve_cell_value(cell, count_type="checks", present_files={"m.pdf"}) == 7


def test_resolve_documents_unchanged():
    assert resolve_cell_value({"per_file": {"a.pdf": 4}}) == 4


def test_resolve_excluded_still_none():
    assert resolve_cell_value({"excluded": True}, count_type="checks") is None
