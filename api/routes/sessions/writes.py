"""Single-cell write routes: override, per-file override, near-match clear,
worker-count, note, confirm. Each enforces the M3 per-cell lock via the
``participant_id`` threaded into the SessionManager mutators.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from api.presence import is_agent
from api.state import SessionManager, compute_cell_count
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
    enrich_cell_colado_suspects,
    enrich_cell_worker_count,
    get_manager,
    refresh_all_reliable,
)

router = APIRouter()


class OverridePatch(BaseModel):
    """Cell-override body. `value` stays Any: the endpoint's hand-rolled
    validation must keep returning 400 (not Pydantic 422) for bad types."""

    model_config = ConfigDict(extra="forbid")

    value: Any = None
    manual: bool = False
    participant_id: str | None = None
    allow_over_pages: bool = False  # lifts ONLY the pages cap (2 docs/sheet corpus); not persisted


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/override")
def patch_override(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: OverridePatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    value = body.value
    manual = bool(body.manual)
    participant_id: str | None = body.participant_id
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
            if total_pages > 0 and value > total_pages and not body.allow_over_pages:
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
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)  # F5: a per-file override can never be negative
    participant_id: str | None = None
    allow_over_pages: bool = False  # lifts ONLY the pages cap (2 docs/sheet corpus); not persisted


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
    _validate_session_id(session_id)
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
        if file_pages > 0 and body.count > file_pages and not body.allow_over_pages:
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
    # Re-read AFTER the refresh (the patch_note/patch_worker_count pattern) — go
    # through the public, lock-guarded getter rather than the private helper; both
    # perform an identical fresh DB read + migration (no caching layer either way),
    # so this is freshness-neutral (D6).
    state = mgr.get_session_state(session_id)
    cell = state["cells"][hospital][sigla]
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "filename": filename,
        "count": body.count,
        "new_cell_count": compute_cell_count(cell, count_type_for(sigla)),
        # F15 follow-up: the pending-save guard drops this write's own
        # cell_updated echo, so the response must carry the recomputed
        # all_reliable itself (the patch_note pattern) — an override that
        # resolves the last unreliable file flips the green dot.
        "all_reliable": cell.get("all_reliable"),
    }


class ClearNearMatchBody(BaseModel):
    """Body for the near-matches clear route. Omit both fields = clear all."""

    model_config = ConfigDict(extra="forbid")

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

    model_config = ConfigDict(extra="forbid")

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
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    # checks cells (maquinaria) light green on worker_status=='terminado'; for
    # documents_workers this recomputes document settledness (no-op-ish). Closes
    # the gap that the worker PATCH didn't refresh all_reliable.
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla))
    # Re-read AFTER the refresh (the patch_note pattern) — the pre-refresh cell
    # dict would carry a stale all_reliable in the response below.
    cell = mgr.get_session_state(session_id)["cells"].get(hospital, {}).get(sigla, {})
    # F1: the shared enrichment helper is the ONE producer of worker_count (same
    # folder-missing legacy fallback as GET / the WS snapshot / the Excel builders).
    # Doc siglas are skipped by the helper → their response worker_count is None.
    enriched = enrich_cell_worker_count(cell, month_root, hospital, sigla, folder)
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "worker_marks": cell.get("worker_marks"),
        "worker_status": cell.get("worker_status"),
        "worker_cursor": cell.get("worker_cursor"),
        "worker_count": enriched.get("worker_count"),
        # M4: canonical present-filtered effective count for checks cells
        # (None for documents_workers) — the store merges it so the grid
        # number can't diverge from Excel/history.
        "checks_count": enriched.get("checks_count"),
        # F15 follow-up: the pending-save guard drops this write's own
        # cell_updated echo, so the response carries the recomputed
        # all_reliable (checks cells light green on 'terminado').
        "all_reliable": cell.get("all_reliable"),
    }


class ReconcileWorkerMarksBody(BaseModel):
    """Body del POST worker-marks/reconcile (F1).

    ``action`` se valida a mano (no vía ``Literal``) para devolver un 400 limpio
    en una acción desconocida y en ``migrate`` sin ``to_file`` — dos reglas que
    un ``Literal`` no expresa junto.
    """

    model_config = ConfigDict(extra="forbid")

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
    enriched = enrich_cell_colado_suspects(enriched, state.get("reorg_ops") or [], hospital, sigla)
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

    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

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

    El flag se preserva entre escaneos (apply_filename_result / finalize_cell_ocr
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


class DismissColadoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str | None = None


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/colado-suspects/{suspect_id}/dismiss")
def dismiss_colado_suspect(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    suspect_id: str,
    body: DismissColadoBody = Body(default=DismissColadoBody()),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Dismiss ONE colado suspect the operator judged legitimate (anti-colados §6).

    M3-gated (409 if another participant holds the cell); 404 when the suspect id
    is absent (so dismissing twice → 404 on the second). Recomputes all_reliable
    and returns the OPEN suspect list + all_reliable, since the pending-save guard
    drops this write's own cell_updated echo (the F15 pattern).
    """
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    try:
        mgr.dismiss_colado_suspect(
            session_id, hospital, sigla, suspect_id, participant_id=body.participant_id
        )
    except KeyError as exc:
        raise HTTPException(404, f"Sospechoso no encontrado: {suspect_id}") from exc
    state = mgr.get_session_state(session_id)
    month_root = Path(state.get("month_root", ""))
    try:
        folder = _find_category_folder(month_root / hospital, sigla)
    except KeyError as exc:
        raise HTTPException(404, f"Categoría {sigla} desconocida") from exc
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla))
    cell = mgr.get_session_state(session_id)["cells"].get(hospital, {}).get(sigla, {})
    enriched = enrich_cell_colado_suspects(cell, state.get("reorg_ops") or [], hospital, sigla)
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "colado_suspects": enriched.get("colado_suspects", []),
        "all_reliable": cell.get("all_reliable"),
    }
