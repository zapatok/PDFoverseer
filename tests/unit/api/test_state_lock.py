"""El SessionManager serializa el read-modify-write del blob de sesión.

Sin lock, dos hilos que mutan celdas distintas del mismo blob (load → mutate →
dump → UPDATE, en autocommit, sobre una conexión compartida) se pisan: el último
en escribir gana el blob entero y deja la otra celda con un valor viejo
(lost update). Con un RLock por mutador, cada read-modify-write es atómico.
"""

from __future__ import annotations

import threading

import pytest

from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def mgr(tmp_path):
    conn = open_connection(tmp_path / "lock.db")
    init_schema(conn)
    m = SessionManager(conn=conn)
    m.open_session(year=2026, month=5, month_root=tmp_path)
    yield m
    close_all()


def test_concurrent_mutations_no_lost_update(mgr):
    # apply_per_file_ocr_result usa setdefault → crea la celda (sin KeyError) y
    # muta per_file[filename]; dos hilos sobre celdas distintas del mismo blob.
    barrier = threading.Barrier(2)

    def bump(hosp, sigla, fname):
        barrier.wait()
        for i in range(50):
            mgr.apply_per_file_ocr_result(
                "2026-05",
                hosp,
                sigla,
                fname,
                count=i,
                method="header_band_anchors",
                near_matches=[],
            )

    t1 = threading.Thread(target=bump, args=("HLL", "odi", "a.pdf"))
    t2 = threading.Thread(target=bump, args=("HRB", "art", "b.pdf"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    state = mgr.get_session_state("2026-05")
    # Sin lock, el último writer pisa el blob → una de las dos celdas queda con
    # un valor viejo. Con lock, ambas llegan a 49.
    assert state["cells"]["HLL"]["odi"]["per_file"]["a.pdf"] == 49
    assert state["cells"]["HRB"]["art"]["per_file"]["b.pdf"] == 49


def test_rlock_allows_reentrant_mutator(mgr):
    """apply_cell_result delega en apply_filename_result; con un Lock NO reentrante
    esto deadlockea. Con RLock no debe colgar ni lanzar."""
    if hasattr(mgr, "apply_cell_result"):
        from core.scanners.base import ConfidenceLevel, ScanResult

        r = ScanResult(
            count=1,
            confidence=ConfidenceLevel.HIGH,
            method="filename_glob",
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=0,
            files_scanned=1,
            per_file={"x.pdf": 1},
        )
        mgr.apply_cell_result("2026-05", "HLL", "odi", r)  # no debe deadlockear
