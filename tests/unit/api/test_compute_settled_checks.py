"""Task 2.2 — compute_settled rama checks.

Una celda checks (maquinaria) está 'lista' (settled) sii worker_status ==
'terminado' (verificación humana del tally). La rama corta temprano, antes de
cualquier walk de la carpeta — así que tmp_path vacío no la afecta.
"""

from api.routes.sessions import compute_settled


def test_checks_settled_when_terminado(tmp_path):
    cell = {"worker_status": "terminado", "worker_marks": {"m.pdf": [{"page": 1, "count": 5}]}}
    assert compute_settled(cell, tmp_path, count_type="checks") is True


def test_checks_not_settled_when_en_progreso(tmp_path):
    cell = {"worker_status": "en_progreso"}
    assert compute_settled(cell, tmp_path, count_type="checks") is False


def test_checks_not_settled_when_no_status(tmp_path):
    assert compute_settled({}, tmp_path, count_type="checks") is False
