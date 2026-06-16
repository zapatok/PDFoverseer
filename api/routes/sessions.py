"""Sessions endpoints: create/get + trigger scan."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel

from api.batch import make_handle
from api.routes.ws import broadcast
from api.state import (
    SessionManager,
    compute_cell_count,
    compute_worker_count,
)
from core.orchestrator import (
    enumerate_month,
    scan_cells_ocr,
    scan_month,
    scan_one_file_ocr,
)
from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs

# Single thread per session is plenty — Daniel's machine has one user, and
# scan_cells_ocr already uses a ProcessPoolExecutor internally for parallelism.
_DISPATCH_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-batch")

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

_MONTH_NAMES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


import fitz  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

_MAX_REASONABLE_COUNT = 10_000

_OCR_METHODS = ("header_detect", "corner_count", "header_band_anchors", "v4")


def file_origin(
    *,
    method: str | None,
    override: int | None,
    page_count: int,
    per_file_count: int | None,
) -> str:
    """Per-file chip vocabulary (single source — reused by _origin_for and
    compute_settled). Priority: Manual override > unreadable Error > OCR/Revisar >
    RN (ratio_n) > R1 (page_count_pure) > R1/Pendiente (filename_glob by page count)
    > R1 default.
    """
    if override is not None:
        return "Manual"
    if page_count == 0:  # unreadable PDF
        return "Error"
    if method in _OCR_METHODS:
        return "Revisar" if per_file_count == 0 else "OCR"
    if method == "ratio_n":
        return "RN"
    if method == "page_count_pure":
        return "R1"
    if method == "filename_glob":
        return "R1" if page_count == 1 else "Pendiente"
    return "R1"


def cell_page_counts(folder: Path) -> dict[str, int]:
    """Lazy per-file page counts for a cell's folder: {pdf.name: page_count}.
    0 when a PDF can't be opened. Today reads from disk; the Incr-J persistence
    (per_file_pages) would slot in here without touching callers.
    """
    out: dict[str, int] = {}
    for pdf in sorted(folder.rglob("*.pdf")):
        try:
            with fitz.open(pdf) as doc:
                out[pdf.name] = doc.page_count
        except Exception:  # noqa: BLE001 — any fitz/IO failure → unreadable (0)
            out[pdf.name] = 0
    return out


def compute_settled(cell: dict, folder: Path) -> bool:
    """True iff every PDF in *folder* is reliable (origin ∈ {R1, RN, Manual}).
    Empty/missing folder → False (a cell with no files is not 'listo'). Lazy pages.
    """
    pages = cell_page_counts(folder)
    files = sorted(folder.rglob("*.pdf"))
    if not files:
        return False
    per_file = cell.get("per_file") or {}
    per_file_method = cell.get("per_file_method") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    cell_method = cell.get("method") or "filename_glob"
    for f in files:
        origin = file_origin(
            method=per_file_method.get(f.name) or cell_method,
            override=per_file_overrides.get(f.name),
            page_count=pages.get(f.name, 0),
            per_file_count=per_file.get(f.name),
        )
        if origin not in ("R1", "RN", "Manual"):
            return False
    return True


def _informe_root() -> Path:
    return Path(os.environ.get("INFORME_MENSUAL_ROOT", "A:/informe mensual"))


def _resolve_month_dir(year: int, month: int) -> Path:
    target_name = next(
        (name for name, num in _MONTH_NAMES.items() if num == month),
        None,
    )
    if target_name is None:
        raise HTTPException(400, f"Invalid month: {month}")
    root = _informe_root()
    if not root.exists():
        raise HTTPException(404, f"INFORME_MENSUAL root not found: {root}")
    for p in root.iterdir():
        if p.is_dir() and p.name.upper() == target_name:
            return p
    raise HTTPException(404, f"Month folder not found: {target_name}")


def get_manager() -> SessionManager:
    """Dependency placeholder — overridden in tests + main.py."""
    raise RuntimeError("get_manager not configured")


@router.post("/sessions")
def create(
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Open or return an existing session for ``(year, month)``."""
    year = body.get("year")
    month = body.get("month")
    if not isinstance(year, int) or not isinstance(month, int):
        raise HTTPException(400, "year and month required (integers)")
    month_dir = _resolve_month_dir(year, month)
    return mgr.open_session(year=year, month=month, month_root=month_dir)


@router.get("/sessions/{session_id}")
def get(
    session_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Return the persisted state dict for a session."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        return mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc


@router.post("/sessions/{session_id}/scan")
def scan(
    session_id: str,
    body: dict = Body(default={"scope": "all"}),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Trigger a full scan of the session's month folder and persist results."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    month_root = Path(state["month_root"])
    try:
        inv = enumerate_month(month_root)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    results = scan_month(inv)
    for (hosp, sigla), r in results.items():
        mgr.apply_cell_result(session_id, hosp, sigla, r)
    return {
        "scanned": len(results),
        "summary": {f"{hosp}_{sigla}": r.count for (hosp, sigla), r in results.items()},
    }


def _skip_files(cell: dict) -> set[str]:
    """Archivos ya confiables que el OCR de celda NO re-escanea (Incr. 1A, spec §3.1).

    Son los que tienen un método OCR previo (∉ ``filename_glob``) o un override
    por-archivo. Los A7/``filename_glob`` NO entran al skip: se re-escanean (es
    barato — solo cuentan páginas) y su per_file ya lo fijó pase-1.
    """
    method = cell.get("per_file_method") or {}
    overrides = cell.get("per_file_overrides") or {}
    return {f for f, m in method.items() if m and m != "filename_glob"} | set(overrides)


def _apply_scan_event(mgr: SessionManager, session_id: str, event: dict) -> dict:
    """Aplica un evento de progreso del OCR de celda al estado y devuelve el evento
    a difundir (posiblemente enriquecido). Incr. 1A — núcleo del merge incremental:

    - ``file_result``: merge incremental por-archivo **solo** si el método es OCR
      real (∉ ``filename_glob``) y ``count`` no es ``None``; un tick ``filename_glob``
      (A7/sin-flavors/``none``) o ``count=None`` (ilegible) es solo-progreso (su
      per_file ya lo fijó pase-1; el batch no reescribe esa verdad — clobber-guard).
    - ``cell_done``: finaliza la metadata y **reinyecta** el snapshot fusionado
      (``per_file`` completo —incluidos los saltados—, ``ocr_count``, ``near_matches``)
      para que el contrato del frontend quede idéntico al de pre-1A.
    - cualquier otro evento se difunde tal cual.
    """
    etype = event.get("type")
    if etype == "file_result":
        count = event.get("count")
        method = event.get("method")
        if count is not None and method != "filename_glob":
            mgr.apply_per_file_ocr_result(
                session_id,
                event["hospital"],
                event["sigla"],
                event["filename"],
                count=count,
                method=method,
                near_matches=event.get("near_matches") or [],
            )
        return event
    if etype == "cell_done":
        cell = mgr.finalize_cell_ocr(
            session_id, event["hospital"], event["sigla"], _meta_result(event["result"])
        )
        event["result"]["per_file"] = cell.get("per_file")
        event["result"]["ocr_count"] = cell.get("ocr_count")
        event["result"]["near_matches"] = cell.get("near_matches") or []
        return event
    return event


def _meta_result(r: dict) -> ScanResult:
    """Reconstruye un ScanResult de *solo metadata* desde el dict de un evento
    ``cell_done`` (la salida de ``orchestrator._cell_done_meta``) para pasarlo a
    :meth:`SessionManager.finalize_cell_ocr`.

    ``count``/``per_file`` van dummy a propósito: ``finalize_cell_ocr`` ignora
    ambos (el total real lo deriva del ``per_file`` ya fusionado por archivo).
    """
    return ScanResult(
        count=r.get("ocr_count") or 0,
        confidence=ConfidenceLevel(r["confidence"]),
        method=r["method"],
        breakdown=r.get("breakdown"),
        flags=list(r.get("flags") or []),
        errors=list(r.get("errors") or []),
        duration_ms=r.get("duration_ms_ocr") or 0,
        files_scanned=0,
        per_file=None,
    )


@router.post("/sessions/{session_id}/scan-ocr")
def scan_ocr(
    request: Request,
    session_id: str,
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Pase 2 — launch OCR batch for the given cells.

    Body: ``{"cells": [["HPV", "odi"], ["HRB", "art"], ...]}``
    """
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc

    cells_pairs = body.get("cells", [])
    if not isinstance(cells_pairs, list) or not cells_pairs:
        raise HTTPException(400, "cells must be a non-empty list of [hospital, sigla] pairs")

    app = request.app

    # Cell folder_path is NOT persisted in session state — re-enumerate from the
    # month_root so OCR scanners receive the real on-disk folder. (Persisting it
    # would couple session state to a transient filesystem layout.)
    month_root = Path(state["month_root"])
    try:
        inv = enumerate_month(month_root)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    folder_by_key: dict[tuple[str, str], Path] = {
        (c.hospital, c.sigla): c.folder_path for cell_list in inv.cells.values() for c in cell_list
    }

    cells_with_paths: list[tuple[str, str, Path]] = []
    for pair in cells_pairs:
        if not (isinstance(pair, list) and len(pair) == 2):
            raise HTTPException(400, f"Invalid cell pair: {pair}")
        hosp, sigla = pair
        folder_path = folder_by_key.get((hosp, sigla))
        if folder_path is None or not folder_path.exists():
            raise HTTPException(404, f"Folder missing for {hosp}/{sigla}")
        cells_with_paths.append((hosp, sigla, folder_path))

    # Incr. 1A fusionar-y-saltar: por celda, los archivos ya confiables que el OCR
    # de celda NO re-escanea — los que tienen un método OCR previo (≠ filename_glob)
    # o un override por-archivo. Los A7/filename_glob se re-escanean (son baratos:
    # solo cuentan páginas), así que NO entran al skip.
    cells_state = state.get("cells", {})
    skip_by_cell: dict[tuple[str, str], set[str]] = {}
    for hosp, sigla, _folder in cells_with_paths:
        cell = (cells_state.get(hosp, {}) or {}).get(sigla) or {}
        sk = _skip_files(cell)
        if sk:
            skip_by_cell[(hosp, sigla)] = sk

    # Pre-count PDFs across the selected cells so the client can size the progress
    # bar immediately (audit #1), EXCLUDING the skipped files so the scan's per-PDF
    # `done` converges exactly on total_pdfs (the orchestrator counts the same way).
    total_pdfs = sum(
        sum(1 for p in enumerate_cell_pdfs(f) if p.name not in skip_by_cell.get((h, s), set()))
        for (h, s, f) in cells_with_paths
    )

    # Atomic check-then-set: setdefault returns the value already in the dict if
    # it existed, otherwise installs and returns the new one.
    handle = make_handle(session_id=session_id, total=len(cells_with_paths))
    if app.state.batches.setdefault(session_id, handle) is not handle:
        raise HTTPException(409, "another batch is already running for this session")
    loop = app.state.loop

    def _safe_broadcast(event: dict) -> None:
        # El scan corre en un hilo de fondo; si el event loop ya se cerró (apagado
        # del server, o teardown del TestClient antes de que termine el batch), dejar
        # caer el evento en vez de crashear el hilo de drain. is_closed() + except
        # cubren el TOCTOU (el loop podría cerrarse entre el chequeo y el schedule).
        try:
            if not loop.is_closed():
                asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
        except RuntimeError:
            pass

    def on_progress(event: dict) -> None:
        # Aplica el evento al estado (merge incremental / finalize) y difunde el
        # resultado. La lógica vive en _apply_scan_event (módulo-nivel) para poder
        # testearla sin la maquinaria async/ProcessPool.
        _safe_broadcast(_apply_scan_event(mgr, session_id, event))

    cancel_token = CancellationToken.from_event(handle.cancel_event)

    def _run():
        try:
            scan_cells_ocr(
                cells_with_paths,
                on_progress=on_progress,
                cancel=cancel_token,
                max_workers=2,
                skip_by_cell=skip_by_cell,
            )
        except Exception:
            logger.exception("scan_cells_ocr crashed for session %s", session_id)
            try:
                asyncio.run_coroutine_threadsafe(
                    broadcast(
                        session_id,
                        {
                            "type": "scan_complete",
                            "scanned": 0,
                            "errors": len(cells_with_paths),
                            "cancelled": 0,
                        },
                    ),
                    loop,
                )
            except Exception:
                logger.exception("failed to broadcast scan_complete after crash")
        finally:
            app.state.batches.pop(session_id, None)

    handle.future = _DISPATCH_POOL.submit(_run)
    return {"accepted": True, "total": len(cells_with_paths), "total_pdfs": total_pdfs}


@router.post("/sessions/{session_id}/cancel")
def cancel(request: Request, session_id: str) -> dict:
    """Always returns 200. If a batch is active, sets its cancel event."""
    handle = request.app.state.batches.get(session_id)
    if handle is not None and handle.cancel_event is not None:
        handle.cancel_event.set()
    return {"ok": True}


from core.orchestrator import _find_category_folder  # noqa: E402


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/files/{filename}/scan-ocr")
def scan_file_ocr(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Pase 2 for a single file (rev-2 #1): OCR-scan one PDF of a cell and merge.

    Resolves the cell folder like ``get_cell_files``, validates the file exists,
    then runs ``scan_one_file_ocr`` on the dispatch pool — broadcasting ``file_*``
    events over the session WS and merging the result on ``file_scan_done``.
    """
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    folder = _find_category_folder(Path(state.get("month_root", "")) / hospital, sigla)
    if not folder.exists() or filename not in {p.name for p in folder.rglob("*.pdf")}:
        raise HTTPException(404, f"File not found in cell: {filename}")

    app = request.app
    loop = app.state.loop

    def on_progress(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
        if event.get("type") == "file_scan_done":
            r = event["result"]
            mgr.apply_per_file_ocr_result(
                session_id,
                hospital,
                sigla,
                filename,
                count=r["ocr_count"],
                method=r["method"],
                near_matches=r.get("near_matches") or [],
            )

    cancel_token = CancellationToken()

    def _run() -> None:
        try:
            scan_one_file_ocr(
                hospital,
                sigla,
                folder,
                filename,
                on_progress=on_progress,
                cancel=cancel_token,
            )
        except Exception:
            logger.exception("scan_one_file_ocr crashed for %s/%s/%s", hospital, sigla, filename)

    _DISPATCH_POOL.submit(_run)
    return {"accepted": True, "filename": filename}


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/override")
def patch_override(
    session_id: str,
    hospital: str,
    sigla: str,
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    value = body.get("value")
    note = body.get("note")
    manual = bool(body.get("manual", False))
    if value is not None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(400, "value must be int or null")
        if value < 0 or value > _MAX_REASONABLE_COUNT:
            raise HTTPException(400, f"value must be in [0, {_MAX_REASONABLE_COUNT}]")
    try:
        mgr.apply_user_override(session_id, hospital, sigla, value=value, note=note, manual=manual)
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    return {
        "user_override": cell.get("user_override"),
        "override_note": cell.get("override_note"),
    }


class PerFileOverrideRequest(BaseModel):
    count: int


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/files/{filename:path}/override")
def patch_per_file_override(
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    body: PerFileOverrideRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Persist per-file count override. Spec §5.2 + §7.2."""
    try:
        mgr.apply_per_file_override(session_id, hospital, sigla, filename, body.count)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    state, _ = mgr._load_and_migrate(session_id)
    cell = state["cells"][hospital][sigla]
    return {
        "filename": filename,
        "count": body.count,
        "new_cell_count": compute_cell_count(cell),
    }


class ClearNearMatchBody(BaseModel):
    """Body for the near-matches clear route. Omit both fields = clear all."""

    pdf_name: str | None = None
    page_index: int | None = None


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/near-matches/clear")
def clear_near_matches(
    session_id: str,
    hospital: str,
    sigla: str,
    body: ClearNearMatchBody | None = Body(None),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Clear near-match suspects for a cell — all, or one entry (E5)."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    mgr.clear_near_matches(
        session_id,
        hospital,
        sigla,
        pdf_name=body.pdf_name if body else None,
        page_index=body.page_index if body else None,
    )
    return {"ok": True}


class WorkerCountPatch(BaseModel):
    """Body del PATCH worker-count. Patch parcial: los campos None no se tocan."""

    marks: dict | None = None
    status: Literal["en_progreso", "terminado"] | None = None
    cursor: dict | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/worker-count")
def patch_worker_count(
    session_id: str,
    hospital: str,
    sigla: str,
    body: WorkerCountPatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Autosalva el conteo de trabajadores de una celda (patch parcial)."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=422, detail="session_id inválido")
    try:
        mgr.apply_worker_count(
            session_id,
            hospital,
            sigla,
            marks=body.marks,
            status=body.status,
            cursor=body.cursor,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Sesión {session_id} no encontrada") from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    return {
        "worker_marks": cell.get("worker_marks"),
        "worker_status": cell.get("worker_status"),
        "worker_cursor": cell.get("worker_cursor"),
        "worker_count": compute_worker_count(cell),
    }


class ConfirmRequest(BaseModel):
    confirmed: bool


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/confirm")
def patch_confirm(
    session_id: str,
    hospital: str,
    sigla: str,
    body: ConfirmRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Marca/desmarca una celda como 'lista' a mano (flag confirmed).

    El flag se preserva entre escaneos (apply_filename_result / apply_ocr_result
    lo re-afirman con setdefault), así que confirmar una celda sobrevive a un
    re-escaneo de pase 1 u OCR.
    """
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        mgr.apply_confirmed(session_id, hospital, sigla, confirmed=body.confirmed)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    return {"confirmed": cell.get("confirmed", False)}


@router.get("/sessions/{session_id}/cells/{hospital}/{sigla}/files")
def get_cell_files(
    session_id: str,
    hospital: str,
    sigla: str,
    mgr: SessionManager = Depends(get_manager),
) -> list[dict]:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    cell = state.get("cells", {}).get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    month_root = Path(state.get("month_root", ""))
    hosp_dir = month_root / hospital
    folder = _find_category_folder(hosp_dir, sigla)
    if not folder.exists():
        return []
    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    per_file_method = cell.get("per_file_method") or {}
    cell_method = cell.get("method") or "filename_glob"

    def _origin_for(
        filename: str,
        override: int | None,
        page_count: int,
        per_file_count: int | None,
    ) -> str:
        """Thin wrapper: resolves the per-file method then delegates to the
        module-level ``file_origin`` pure function (single source of chip vocab).
        """
        method = per_file_method.get(filename) or cell_method
        return file_origin(
            method=method,
            override=override,
            page_count=page_count,
            per_file_count=per_file_count,
        )

    pages = cell_page_counts(folder)
    out: list[dict] = []
    for pdf in sorted(folder.rglob("*.pdf")):
        page_count = pages.get(pdf.name, 0)
        subfolder = pdf.parent.name if pdf.parent != folder else None
        override = per_file_overrides.get(pdf.name)
        inferred = per_file.get(pdf.name)
        # effective_count defaults to 1 here — a PDF the operator is looking at
        # counts as at least one document. This is intentionally asymmetric with
        # api.state.compute_cell_count, which defaults a dataless cell to 0
        # (audit #7). The divergence is presentation-only and pre-scan: after a
        # scan, per_file covers every PDF and the two agree. Kept at 1 because
        # it is the intuitive per-file view for the operator.
        effective = override if override is not None else (inferred if inferred is not None else 1)
        out.append(
            {
                "name": pdf.name,
                "subfolder": subfolder,
                "page_count": page_count,
                "suspect": page_count >= 10,
                "per_file_count": inferred,
                "override_count": override,
                "effective_count": effective,
                "origin": _origin_for(pdf.name, override, page_count, inferred),
            }
        )
    return out


@router.get("/sessions/{session_id}/cells/{hospital}/{sigla}/pdf")
def get_cell_pdf(
    session_id: str,
    hospital: str,
    sigla: str,
    index: int = 0,
    mgr: SessionManager = Depends(get_manager),
) -> FileResponse:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    if index < 0:
        raise HTTPException(400, "index must be ≥ 0")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state.get("cells", {}).get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    month_root = Path(state.get("month_root", ""))
    hosp_dir = month_root / hospital
    folder = _find_category_folder(hosp_dir, sigla)
    pdfs = sorted(folder.rglob("*.pdf")) if folder.exists() else []
    if not pdfs:
        raise HTTPException(404, "no_pdfs_in_cell")
    if index >= len(pdfs):
        raise HTTPException(400, f"index out of range: {index} >= {len(pdfs)}")

    pdf_path = pdfs[index].resolve()
    cell_folder = folder.resolve()
    informe_root = _informe_root().resolve()
    # Two layers of containment per spec §4.6: PDF inside cell folder, cell
    # folder inside INFORME_MENSUAL_ROOT. Both must hold.
    if not pdf_path.is_relative_to(cell_folder):
        raise HTTPException(400, "invalid path")
    if not cell_folder.is_relative_to(informe_root):
        raise HTTPException(400, "cell folder outside informe root")

    return FileResponse(pdf_path, media_type="application/pdf")
