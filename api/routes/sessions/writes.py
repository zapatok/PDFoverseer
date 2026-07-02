"""Single-cell write routes: override, per-file override, near-match clear,
worker-count, note, confirm. Each enforces the M3 per-cell lock via the
``participant_id`` threaded into the SessionManager mutators.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.presence import is_agent
from api.state import SessionManager, compute_cell_count, compute_worker_count
from core.orchestrator import _find_category_folder
from core.scanners.patterns import count_type_for

from ._common import (
    _MAX_REASONABLE_COUNT,
    _broadcast_cell_updated,
    _broadcast_presence,
    _cell_total_pages,
    _is_capped_sigla,
    _validate_cell_coords,
    _validate_session_id,
    cell_page_counts,
    enrich_cell_worker_count,
    get_manager,
    present_file_names,
    refresh_all_reliable,
)

router = APIRouter()


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/override")
def patch_override(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    value = body.get("value")
    manual = bool(body.get("manual", False))
    participant_id: str | None = body.get("participant_id")
    if value is not None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(400, "value must be int or null")
        if value < 0 or value > _MAX_REASONABLE_COUNT:
            raise HTTPException(400, f"value must be in [0, {_MAX_REASONABLE_COUNT}]")
        if _is_capped_sigla(sigla):
            try:
                state = mgr.get_session_state(session_id)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            total_pages = _cell_total_pages(state, hospital, sigla)
            # total_pages == 0 means pages are unknowable (missing folder / all PDFs
            # unreadable) → don't block; 0 is "unknown", not "max is 0".
            if total_pages > 0 and value > total_pages:
                raise HTTPException(
                    422,
                    {"error": "count_exceeds_pages", "max": total_pages},
                )
    try:
        mgr.apply_user_override(
            session_id, hospital, sigla, value=value, manual=manual, participant_id=participant_id
        )
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "user_override": cell.get("user_override"),
    }


class PerFileOverrideRequest(BaseModel):
    count: int = Field(ge=0)  # F5: a per-file override can never be negative
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/files/{filename:path}/override")
def patch_per_file_override(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    body: PerFileOverrideRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Persist per-file count override. Spec §5.2 + §7.2."""
    _validate_cell_coords(hospital, sigla)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    month_root = Path(state.get("month_root", ""))
    try:
        folder = _find_category_folder(month_root / hospital, sigla)
    except KeyError as exc:
        # Unknown sigla → CATEGORY_FOLDERS miss. The cell can't exist → 404
        # (not a 500). Pre-existing gap: folder was resolved before the cell was
        # validated by apply_per_file_override below.
        raise HTTPException(status_code=404, detail=f"Unknown sigla: {sigla}") from exc
    if _is_capped_sigla(sigla) and folder.exists():
        file_pages = cell_page_counts(folder).get(filename, 0)
        if file_pages > 0 and body.count > file_pages:
            raise HTTPException(
                422,
                {"error": "count_exceeds_pages", "max": file_pages},
            )
    try:
        mgr.apply_per_file_override(
            session_id, hospital, sigla, filename, body.count, body.participant_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if folder.exists():  # best-effort metadata; skip (don't 500) if folder is gone
        refresh_all_reliable(
            mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla)
        )
    state, _ = mgr._load_and_migrate(session_id)
    cell = state["cells"][hospital][sigla]
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "filename": filename,
        "count": body.count,
        "new_cell_count": compute_cell_count(cell, count_type_for(sigla)),
    }


class ClearNearMatchBody(BaseModel):
    """Body for the near-matches clear route. Omit both fields = clear all."""

    pdf_name: str | None = None
    page_index: int | None = None
    participant_id: str | None = None


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/near-matches/clear")
def clear_near_matches(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: ClearNearMatchBody | None = Body(None),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Clear near-match suspects for a cell — all, or one entry (E5)."""
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    participant_id = body.participant_id if body else None
    mgr.clear_near_matches(
        session_id,
        hospital,
        sigla,
        pdf_name=body.pdf_name if body else None,
        page_index=body.page_index if body else None,
        participant_id=participant_id,
    )
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {"ok": True}


class WorkerCountPatch(BaseModel):
    """Body del PATCH worker-count. Patch parcial: los campos None no se tocan."""

    marks: dict | None = None
    status: Literal["en_progreso", "terminado"] | None = None
    cursor: dict | None = None
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/worker-count")
def patch_worker_count(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: WorkerCountPatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Autosalva el conteo de trabajadores de una celda (patch parcial)."""
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    try:
        mgr.apply_worker_count(
            session_id,
            hospital,
            sigla,
            marks=body.marks,
            status=body.status,
            cursor=body.cursor,
            participant_id=body.participant_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Sesión {session_id} no encontrada") from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    # F1: names-only present set (no PDF opens) — the same canonical filter GET +
    # the cell_updated snapshot use, so the PATCH response can never disagree.
    present = present_file_names(folder) if folder.exists() else None
    # checks cells (maquinaria) light green on worker_status=='terminado'; for
    # documents_workers this recomputes document settledness (no-op-ish). Closes
    # the gap that the worker PATCH didn't refresh all_reliable.
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla))
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "worker_marks": cell.get("worker_marks"),
        "worker_status": cell.get("worker_status"),
        "worker_cursor": cell.get("worker_cursor"),
        "worker_count": compute_worker_count(cell, present),
    }


class ReconcileWorkerMarksBody(BaseModel):
    """Body del POST worker-marks/reconcile (F1).

    ``action`` se valida a mano (no vía ``Literal``) para devolver un 400 limpio
    en una acción desconocida y en ``migrate`` sin ``to_file`` — dos reglas que
    un ``Literal`` no expresa junto.
    """

    action: str
    from_file: str
    to_file: str | None = None
    participant_id: str | None = None


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/worker-marks/reconcile")
def reconcile_worker_marks(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: ReconcileWorkerMarksBody,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Reconcile orphan worker/check marks: migrate them onto a present file, or
    discard them (F1). Returns the enriched cell (canonical worker_count)."""
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    if body.action not in ("migrate", "discard"):
        raise HTTPException(400, "action must be 'migrate' or 'discard'")
    if body.action == "migrate" and not body.to_file:
        raise HTTPException(400, "migrate requires to_file")
    try:
        mgr.reconcile_worker_marks(
            session_id,
            hospital,
            sigla,
            action=body.action,
            from_file=body.from_file,
            to_file=body.to_file,
            participant_id=body.participant_id,
        )
    except KeyError as exc:
        # Unknown from_file (or missing session) → 404. The lock check runs first
        # in the manager, so a contested cell 409s before reaching here.
        raise HTTPException(404, f"Sin marcas para el archivo: {body.from_file}") from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    month_root = Path(state.get("month_root", ""))
    enriched = enrich_cell_worker_count(cell, month_root, hospital, sigla)
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return enriched


class NotePatch(BaseModel):
    """Body del PATCH note. text vacío/None borra la nota.

    ``status`` no es nullable y nace en ``"por_resolver"`` (D4): una nota creada
    sin estado explícito queda pendiente (fuerza el punto ámbar), preservando el
    invariante nota⟺estado.
    """

    text: str | None = None
    status: Literal["por_resolver", "resuelto"] = "por_resolver"
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/note")
def patch_note(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: NotePatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Set or clear a cell's note; refresh all_reliable (por_resolver → amber)."""
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    try:
        mgr.set_note(
            session_id,
            hospital,
            sigla,
            text=body.text,
            status=body.status,
            participant_id=body.participant_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Sesión {session_id} no encontrada") from exc
    state = mgr.get_session_state(session_id)
    month_root = Path(state.get("month_root", ""))
    # _find_category_folder raises KeyError for an unknown sigla → 404 (distinct
    # from the unknown-session 404 above), not an unhandled 500.
    try:
        folder = _find_category_folder(month_root / hospital, sigla)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Categoría {sigla} desconocida") from exc
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla))
    cell = mgr.get_session_state(session_id)["cells"].get(hospital, {}).get(sigla, {})
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "note": cell.get("note"),
        "note_status": cell.get("note_status"),
        "all_reliable": cell.get("all_reliable"),
    }


class ConfirmRequest(BaseModel):
    confirmed: bool
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/confirm")
def patch_confirm(
    request: Request,
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
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    try:
        mgr.apply_confirmed(
            session_id,
            hospital,
            sigla,
            confirmed=body.confirmed,
            participant_id=body.participant_id,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {"confirmed": cell.get("confirmed", False)}
