"""count_type por sigla (Decisión 4 / grupo F del triage 2026-06-09).

Tres tipos: documents (mayoría) · documents_workers (charla/chintegral/dif_pts:
documentos + trabajadores) · checks (maquinaria: chequeos = columnas de fecha).
"""

from __future__ import annotations

from core.domain import SIGLAS
from core.scanners.patterns import COUNT_TYPE_BY_SIGLA, count_type_for
from core.scanners.scan_info import scan_info_for
from core.utils import COUNT_TYPES

WORKERS = {"charla", "chintegral", "dif_pts"}
CHECKS = {"maquinaria"}


def test_every_sigla_has_valid_count_type():
    for sigla in SIGLAS:
        assert count_type_for(sigla) in COUNT_TYPES, sigla
    # el mapeo cubre exactamente las 20 siglas (gate de completitud)
    assert set(COUNT_TYPE_BY_SIGLA) == set(SIGLAS)


def test_count_type_classification():
    for sigla in SIGLAS:
        ct = count_type_for(sigla)
        if sigla in WORKERS:
            assert ct == "documents_workers", sigla
        elif sigla in CHECKS:
            assert ct == "checks", sigla
        else:
            assert ct == "documents", sigla


def test_scan_info_exposes_count_type():
    assert scan_info_for("charla")["count_type"] == "documents_workers"
    assert scan_info_for("maquinaria")["count_type"] == "checks"
    assert scan_info_for("odi")["count_type"] == "documents"
