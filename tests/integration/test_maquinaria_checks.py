"""Task 2.4 — maquinaria (checks) end-to-end.

El tally del PATCH worker-count se vuelve la cuenta PRINCIPAL de la celda, enciende
el punto verde al terminar (verificación humana), y llega a la celda normal de
maquinaria del Excel — sin named range nuevo. Reusa session_with_checks_cell.
"""

from __future__ import annotations

import openpyxl


def test_maquinaria_checks_end_to_end(session_with_checks_cell, client):
    sid, hosp, sigla = session_with_checks_cell
    # Tally: 5 chequeos en p1 + 4 en p2 = 9 (supera las 2 páginas, por diseño).
    marks = {"maq.pdf": [{"page": 1, "count": 5}, {"page": 2, "count": 4}]}
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/worker-count",
        json={"marks": marks, "status": "terminado"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["worker_count"] == 9

    # Punto verde: all_reliable True tras terminar (verificación humana del tally).
    state = client.get(f"/api/sessions/{sid}").json()
    cell = state["cells"][hosp][sigla]
    assert cell.get("worker_status") == "terminado"
    assert cell.get("all_reliable") is True

    # Excel: el tally va a la celda normal de maquinaria de la grilla (no a HH).
    out = client.post(f"/api/sessions/{sid}/output", json={}).json()
    wb = openpyxl.load_workbook(out["output_path"])
    sheet, coord = list(wb.defined_names[f"{hosp}_{sigla}_count"].destinations)[0]
    assert wb[sheet][coord].value == 9


def test_maquinaria_not_green_until_terminado(session_with_checks_cell, client):
    """En progreso → no enciende verde (all_reliable False)."""
    sid, hosp, sigla = session_with_checks_cell
    r = client.patch(
        f"/api/sessions/{sid}/cells/{hosp}/{sigla}/worker-count",
        json={"marks": {"maq.pdf": [{"page": 1, "count": 3}]}, "status": "en_progreso"},
    )
    assert r.status_code == 200, r.text
    state = client.get(f"/api/sessions/{sid}").json()
    cell = state["cells"][hosp][sigla]
    assert cell.get("all_reliable") is False
