"""F1 end-to-end: el total del PATCH worker-count y el del Excel cuentan las
marcas sobre archivos presentes en la carpeta, no solo los de per_file.

Escenario:
  - Celda HPV/charla con dos PDFs en disco: charla_a.pdf y charla_b.pdf.
  - Pase-1 escanea con solo charla_a.pdf presente → per_file solo tiene charla_a.
  - Añadimos charla_b.pdf al disco SIN re-escanear → per_file sigue teniendo
    solo charla_a.
  - Enviamos PATCH con marcas en AMBOS archivos.
  - Assert: worker_count = suma de ambos (present_files = ambos archivos en disco),
    NO solo el de charla_a (que sería el comportamiento buggy pre-F1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import _make_pdf


@pytest.fixture
def session_f1(tmp_path, client):
    """Celda HPV/charla: a.pdf escaneado (en per_file), b.pdf añadido después."""
    folder = tmp_path / "ABRIL" / "HPV" / "4.-Charlas"
    folder.mkdir(parents=True)
    # Solo charla_a presente al momento del escaneo.
    _make_pdf(folder / "charla_a.pdf", 2)

    r = client.post("/api/sessions", json={"year": 2026, "month": 4})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]

    r2 = client.post(f"/api/sessions/{sid}/scan")
    assert r2.status_code == 200, r2.text

    # Ahora añadir charla_b.pdf SIN re-escanear → per_file sigue solo con charla_a.
    _make_pdf(folder / "charla_b.pdf", 1)

    return sid


_MARKS = {
    "charla_a.pdf": [{"page": 1, "count": 10}],
    "charla_b.pdf": [{"page": 1, "count": 36}],
}


def test_patch_worker_count_uses_present_files(session_f1, client):
    """PATCH devuelve worker_count = marcas de a + b, no solo de a."""
    sid = session_f1
    r = client.patch(
        f"/api/sessions/{sid}/cells/HPV/charla/worker-count",
        json={"marks": _MARKS, "status": "terminado"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # F1: debe contar ambos (charla_b no está en per_file pero está en disco).
    assert body["worker_count"] == 46, (
        f"Expected 46 (10+36), got {body['worker_count']}. "
        "F1 bug: only per_file files are being counted."
    )


def test_output_excel_uses_present_files(session_f1, client):
    """La OTRA mitad de F1: el Excel escribe el total de AMBOS archivos
    (present_files), no solo el de per_file. Es el síntoma reportado en vivo
    ('el visor guarda 6070 pero el Excel quedó en 6034')."""
    import openpyxl

    sid = session_f1
    r = client.patch(
        f"/api/sessions/{sid}/cells/HPV/charla/worker-count",
        json={"marks": _MARKS, "status": "terminado"},
    )
    assert r.status_code == 200, r.text

    out = client.post(f"/api/sessions/{sid}/output", json={}).json()
    wb = openpyxl.load_workbook(out["output_path"])
    sheet, coord = list(wb.defined_names["HPV_workers_chgen"].destinations)[0]
    assert wb[sheet][coord].value == 46, (
        f"Excel HPV_workers_chgen should be 46 (present-files), got {wb[sheet][coord].value}"
    )
