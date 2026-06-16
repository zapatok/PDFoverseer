"""F1: el total de marcas debe filtrar por archivos PRESENTES en la carpeta,
no por las claves de per_file. Una marca sobre un PDF que existe pero no fue
registrado por pase-1 (no está en per_file) debe contar; una marca huérfana
(PDF ya no presente) NO debe contar."""

from core.cell_count import _sum_marks


def _cell(marks, per_file=None):
    return {"worker_marks": marks, "per_file": per_file or {}}


def test_present_files_counts_marks_on_unregistered_pdf():
    # f_b.pdf existe en la carpeta pero NO está en per_file → su marca DEBE contar.
    cell = _cell(
        marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_b.pdf": [{"page": 1, "count": 36}]},
        per_file={"f_a.pdf": 1},  # pase-1 solo registró f_a
    )
    present = {"f_a.pdf", "f_b.pdf"}
    assert _sum_marks(cell, present) == 46  # 10 + 36, no 10


def test_present_files_drops_orphan_marks():
    # f_old.pdf fue renombrado/borrado → no está presente → su marca NO cuenta.
    cell = _cell(
        marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_old.pdf": [{"page": 1, "count": 99}]}
    )
    assert _sum_marks(cell, {"f_a.pdf"}) == 10


def test_empty_present_files_is_zero():
    # carpeta vacía (set explícito vacío) → todas las marcas son huérfanas → 0.
    cell = _cell(marks={"f_a.pdf": [{"page": 1, "count": 10}]})
    assert _sum_marks(cell, set()) == 0


def test_none_present_files_falls_back_to_per_file():
    # legacy (present_files=None): filtra por per_file cuando no está vacío.
    cell = _cell(
        marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_b.pdf": [{"page": 1, "count": 36}]},
        per_file={"f_a.pdf": 1},
    )
    assert _sum_marks(cell, None) == 10  # filtra f_b (no en per_file) — comportamiento viejo


def test_none_present_files_no_per_file_sums_all():
    cell = _cell(
        marks={"f_a.pdf": [{"page": 1, "count": 10}], "f_b.pdf": [{"page": 1, "count": 5}]}
    )
    assert _sum_marks(cell, None) == 15  # per_file vacío → no filtra
