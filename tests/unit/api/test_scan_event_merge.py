"""Incr. 1A — núcleo del merge incremental de la ruta scan-ocr, sin async.

Prueba directamente los dos helpers módulo-nivel que extraen la lógica de
``scan_ocr`` para hacerla testeable:

- ``_skip_files``: qué archivos NO re-escanea el OCR de celda (fusionar-y-saltar).
- ``_apply_scan_event``: el merge incremental por-archivo (``file_result``) + la
  finalización de metadata (``cell_done``), contra un ``SessionManager`` real.
"""

from __future__ import annotations

import pytest

from api.routes.sessions import _apply_scan_event, _skip_files
from api.state import SessionManager
from core.db.connection import close_all, open_connection
from core.db.migrations import init_schema


@pytest.fixture
def mgr(tmp_path):
    conn = open_connection(tmp_path / "scan_event.db")
    init_schema(conn)
    yield SessionManager(conn=conn)
    close_all()


@pytest.fixture
def sid(mgr, tmp_path):
    return mgr.open_session(year=2026, month=4, month_root=tmp_path)["session_id"]


# ---------- _skip_files ----------


def test_skip_files_includes_ocr_method_files():
    cell = {"per_file_method": {"a.pdf": "header_band_anchors", "b.pdf": "v4"}}
    assert _skip_files(cell) == {"a.pdf", "b.pdf"}


def test_skip_files_excludes_filename_glob():
    # A7 / pase-1: filename_glob NO se salta (se re-escanea barato — solo páginas).
    cell = {"per_file_method": {"a.pdf": "filename_glob", "b.pdf": "header_band_anchors"}}
    assert _skip_files(cell) == {"b.pdf"}


def test_skip_files_includes_per_file_overrides():
    cell = {"per_file_method": {}, "per_file_overrides": {"c.pdf": 3}}
    assert _skip_files(cell) == {"c.pdf"}


def test_skip_files_empty_cell():
    assert _skip_files({}) == set()


# ---------- _apply_scan_event: file_result ----------


def _file_result(filename: str, count, method: str) -> dict:
    return {
        "type": "file_result",
        "hospital": "HPV",
        "sigla": "odi",
        "filename": filename,
        "count": count,
        "method": method,
        "near_matches": [],
    }


def test_file_result_ocr_method_merges(mgr, sid):
    _apply_scan_event(mgr, sid, _file_result("doc.pdf", 4, "header_band_anchors"))
    cell = mgr.get_session_state(sid)["cells"]["HPV"]["odi"]
    assert cell["per_file"]["doc.pdf"] == 4
    assert cell["per_file_method"]["doc.pdf"] == "header_band_anchors"


def test_file_result_filename_glob_is_progress_only(mgr, sid):
    # Solo-progreso: NO toca per_file — su valor lo fija pase-1 (clobber-guard).
    _apply_scan_event(mgr, sid, _file_result("a7.pdf", 1, "filename_glob"))
    cell = (mgr.get_session_state(sid)["cells"].get("HPV", {}) or {}).get("odi") or {}
    assert not cell.get("per_file")


def test_file_result_unreadable_count_none_is_progress_only(mgr, sid):
    _apply_scan_event(mgr, sid, _file_result("broken.pdf", None, "header_band_anchors"))
    cell = (mgr.get_session_state(sid)["cells"].get("HPV", {}) or {}).get("odi") or {}
    assert "broken.pdf" not in (cell.get("per_file") or {})


# ---------- _apply_scan_event: cell_done ----------


def test_cell_done_finalizes_sum_and_injects_snapshot(mgr, sid):
    # Dos archivos fusionados por file_result → cell_done finaliza ocr_count = suma
    # del per_file YA fusionado (ignora el ocr_count del evento) y reinyecta el
    # snapshot completo en el evento (contrato de cell_done idéntico a pre-1A).
    for fn, n in (("a.pdf", 2), ("b.pdf", 3)):
        _apply_scan_event(mgr, sid, _file_result(fn, n, "header_band_anchors"))

    done = {
        "type": "cell_done",
        "hospital": "HPV",
        "sigla": "odi",
        "result": {
            "ocr_count": 999,  # se ignora: finalize usa la suma del per_file fusionado
            "method": "header_band_anchors",
            "confidence": "high",
            "duration_ms_ocr": 10,
            "flags": [],
            "errors": [],
            "breakdown": None,
        },
    }
    out = _apply_scan_event(mgr, sid, done)

    # snapshot reinyectado en el evento difundido
    assert out["result"]["per_file"] == {"a.pdf": 2, "b.pdf": 3}
    assert out["result"]["ocr_count"] == 5
    assert out["result"]["near_matches"] == []

    # persistido en el estado
    cell = mgr.get_session_state(sid)["cells"]["HPV"]["odi"]
    assert cell["ocr_count"] == 5
    assert cell["per_file"] == {"a.pdf": 2, "b.pdf": 3}
    assert cell["method"] == "header_band_anchors"


def test_cell_done_preserves_skipped_file_counts(mgr, sid):
    # Un archivo ya confiable (no re-escaneado este run) conserva su conteo: el
    # finalize NO toca per_file, así que ocr_count lo incluye en la suma.
    _apply_scan_event(mgr, sid, _file_result("old.pdf", 7, "header_band_anchors"))
    # Nuevo run: solo se re-escanea new.pdf (old.pdf habría estado en skip).
    _apply_scan_event(mgr, sid, _file_result("new.pdf", 1, "header_band_anchors"))
    done = {
        "type": "cell_done",
        "hospital": "HPV",
        "sigla": "odi",
        "result": {
            "ocr_count": 0,
            "method": "header_band_anchors",
            "confidence": "high",
            "duration_ms_ocr": 5,
            "flags": [],
            "errors": [],
            "breakdown": None,
        },
    }
    out = _apply_scan_event(mgr, sid, done)
    assert out["result"]["ocr_count"] == 8  # 7 (conservado) + 1 (nuevo)


def test_other_events_pass_through_untouched(mgr, sid):
    ev = {"type": "pdf_progress", "done": 1, "total": 3, "pdf_name": "x.pdf"}
    assert _apply_scan_event(mgr, sid, ev) is ev
    # No crea ninguna celda.
    assert mgr.get_session_state(sid)["cells"] == {}
