"""Sessions endpoints: create/get + trigger scan."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from api.batch import make_handle
from api.routes.ws import broadcast
from api.state import SessionManager
from core.orchestrator import (
    enumerate_month,
    scan_cells_ocr,
    scan_month,
)
from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken

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

    # Atomic check-then-set: setdefault returns the value already in the dict if
    # it existed, otherwise installs and returns the new one.
    handle = make_handle(session_id=session_id, total=len(cells_with_paths))
    if app.state.batches.setdefault(session_id, handle) is not handle:
        raise HTTPException(409, "another batch is already running for this session")
    loop = app.state.loop

    def on_progress(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
        if event.get("type") == "cell_done":
            r = event["result"]
            result = ScanResult(
                count=r["ocr_count"],
                confidence=ConfidenceLevel(r["confidence"]),
                method=r["method"],
                breakdown=None,
                flags=[],
                errors=[],
                duration_ms=r["duration_ms_ocr"],
                files_scanned=1,
            )
            mgr.apply_ocr_result(session_id, event["hospital"], event["sigla"], result)

    cancel_token = CancellationToken.from_event(handle.cancel_event)

    def _run():
        try:
            scan_cells_ocr(
                cells_with_paths,
                on_progress=on_progress,
                cancel=cancel_token,
                max_workers=2,
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
    return {"accepted": True, "total": len(cells_with_paths)}


@router.post("/sessions/{session_id}/cancel")
def cancel(request: Request, session_id: str) -> dict:
    """Always returns 200. If a batch is active, sets its cancel event."""
    handle = request.app.state.batches.get(session_id)
    if handle is not None and handle.cancel_event is not None:
        handle.cancel_event.set()
    return {"ok": True}


from core.orchestrator import _find_category_folder  # noqa: E402


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
    if value is not None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(400, "value must be int or null")
        if value < 0 or value > _MAX_REASONABLE_COUNT:
            raise HTTPException(400, f"value must be in [0, {_MAX_REASONABLE_COUNT}]")
    try:
        mgr.apply_user_override(session_id, hospital, sigla, value=value, note=note)
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    return {
        "user_override": cell.get("user_override"),
        "override_note": cell.get("override_note"),
    }


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
    out: list[dict] = []
    for pdf in sorted(folder.rglob("*.pdf")):
        try:
            with fitz.open(pdf) as doc:
                page_count = doc.page_count
        except Exception:  # noqa: BLE001
            page_count = 0
        subfolder = pdf.parent.name if pdf.parent != folder else None
        out.append(
            {
                "name": pdf.name,
                "subfolder": subfolder,
                "page_count": page_count,
                "suspect": page_count >= 10,
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
