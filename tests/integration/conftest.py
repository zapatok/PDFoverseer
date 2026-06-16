"""Shared fixtures for integration tests (apply-ratio, override-cap)."""

from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from api.main import create_app


def _make_pdf(path: Path, n_pages: int) -> None:
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INFORME_MENSUAL_ROOT", str(tmp_path))
    monkeypatch.setenv("OVERSEER_DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    with TestClient(app) as c:
        yield c


def _build_pending_cell(tmp_path: Path, month_name: str, hosp: str, sigla: str) -> None:
    """Build a cell folder with one 1-page PDF (→ R1) and one 8-page PDF (→ Pendiente).

    odi → "3.-ODI Visitas" (count_type="documents", capped)
    """
    folder = tmp_path / month_name / hosp / "3.-ODI Visitas"
    folder.mkdir(parents=True)
    # Glob-matching names so pase-1 (filename scan) actually counts them, the way
    # real corpus files are named — otherwise per_file stays empty (unrealistic).
    _make_pdf(folder / "2026-04-10_odi_a.pdf", 1)
    _make_pdf(folder / "2026-04-15_odi_big.pdf", 8)


def _open_and_scan(client: TestClient, year: int = 2026, month: int = 4) -> str:
    r = client.post("/api/sessions", json={"year": year, "month": month})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    r2 = client.post(f"/api/sessions/{sid}/scan")
    assert r2.status_code == 200, r2.text
    return sid


@pytest.fixture
def session_with_pending_cell(tmp_path, client):
    """Session with HPV/odi: a.pdf=1pg (R1), big.pdf=8pg (Pendiente). Total pages = 9."""
    hosp = "HPV"
    sigla = "odi"
    _build_pending_cell(tmp_path, "ABRIL", hosp, sigla)
    sid = _open_and_scan(client)
    return sid, hosp, sigla


def _build_checks_cell(tmp_path: Path, month_name: str, hosp: str, sigla: str) -> None:
    """Build a maquinaria (checks) cell folder with a small PDF.

    maquinaria → "10.-Inspeccion de Maquinaria" (count_type="checks", uncapped)
    """
    folder = tmp_path / month_name / hosp / "10.-Inspeccion de Maquinaria"
    folder.mkdir(parents=True)
    _make_pdf(folder / "maq.pdf", 2)


@pytest.fixture
def session_with_checks_cell(tmp_path, client):
    """Session with HPV/maquinaria: maq.pdf=2pg. count_type='checks' (uncapped)."""
    hosp = "HPV"
    sigla = "maquinaria"
    _build_checks_cell(tmp_path, "ABRIL", hosp, sigla)
    sid = _open_and_scan(client)
    return sid, hosp, sigla
