"""Task 2.1 — compute_cell_count checks branch.

Verifica que cuando count_type="checks" compute_cell_count suma las marcas de
worker_marks filtradas por present_files en lugar de seguir la cascada de
documentos.
"""

import pytest

from core.cell_count import compute_cell_count


def test_checks_sums_marks_filtered_by_present_files():
    """Suma solo las marcas de archivos presentes; las huérfanas se descartan."""
    cell = {
        "worker_marks": {
            "m.pdf": [{"page": 1, "count": 5}],
            "orphan.pdf": [{"page": 1, "count": 9}],
        }
    }
    assert compute_cell_count(cell, count_type="checks", present_files={"m.pdf"}) == 5


def test_checks_user_override_wins():
    """user_override sigue ganando incluso cuando count_type="checks"."""
    cell = {
        "worker_marks": {"m.pdf": [{"page": 1, "count": 5}]},
        "user_override": 2,
    }
    assert compute_cell_count(cell, count_type="checks", present_files={"m.pdf"}) == 2


def test_checks_empty_present_files_returns_zero():
    """Carpeta vacía (set explícito vacío) → 0 (no hay PDFs presentes)."""
    cell = {"worker_marks": {"m.pdf": [{"page": 1, "count": 5}]}}
    assert compute_cell_count(cell, count_type="checks", present_files=set()) == 0


def test_checks_no_marks_returns_zero():
    """Sin worker_marks → 0."""
    cell = {}
    assert compute_cell_count(cell, count_type="checks", present_files={"m.pdf"}) == 0


def test_documents_type_unaffected():
    """count_type='documents' (default) no toca la ruta de marcas."""
    cell = {
        "per_file": {"a.pdf": 3},
        "worker_marks": {"a.pdf": [{"page": 1, "count": 99}]},
    }
    # La ruta documentos suma per_file, no marks
    assert compute_cell_count(cell) == 3
    assert compute_cell_count(cell, count_type="documents") == 3


def test_checks_multiple_files_and_pages():
    """Suma marcas de múltiples archivos y múltiples páginas."""
    cell = {
        "worker_marks": {
            "a.pdf": [{"page": 1, "count": 3}, {"page": 2, "count": 4}],
            "b.pdf": [{"page": 1, "count": 7}],
            "c.pdf": [{"page": 1, "count": 100}],  # no presente
        }
    }
    assert compute_cell_count(cell, count_type="checks", present_files={"a.pdf", "b.pdf"}) == 14
