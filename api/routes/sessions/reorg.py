"""Reorg routes (Incr J T9–T11): create/delete a reorg op + export the manifest."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.presence import is_agent
from api.reorg import build_manifest, file_contribution, resolve_op_defaults, validate_op
from api.state import SessionManager
from core.orchestrator import _find_category_folder
from core.scanners.patterns import count_type_for

from ._common import (
    _broadcast_presence,
    _broadcast_session_refresh,
    _informe_root,
    _validate_cell_coords,
    _validate_session_id,
    cell_page_counts,
    get_manager,
    refresh_all_reliable,
)

router = APIRouter()


class ReorgSource(BaseModel):
    hospital: str
    sigla: str
    file: str
    page_range: list[int] | None = None


class ReorgDest(BaseModel):
    hospital: str
    sigla: str


class ReorgOpCreate(BaseModel):
    op_type: str
    source: ReorgSource
    dest: ReorgDest
    empresa: str | None = None
    preserve_date: bool = True
    rotation_deg: int = 0
    doc_count: int | None = Field(default=None, ge=0)  # F5: never negative
    worker_count: int | None = Field(default=None, ge=0)  # F5: never negative
    note: str | None = None
    participant_id: str | None = None


def _gate_reorg_cells(
    mgr: SessionManager,
    session_id: str,
    participant_id: str | None,
    cells: list[tuple[str, str]],
) -> None:
    """Gate a reorg op's affected cells on the M3 per-cell lock (F3). CHECK-ONLY.

    Raises ``CellLockedError`` (→ HTTP 409 via the ``main.py`` handler) if any
    cell is held by a DIFFERENT participant; never claims. ``check_cell_lock``
    excludes the caller, so one path serves humans, the Claude agent, and legacy
    (``participant_id=None`` is inert). The agent claims only AFTER the write
    succeeds (:func:`_claim_reorg_cells_for_agent`) — so a 409/400 can never
    leave a dangling "Claude está editando" badge for an op that never existed.
    """
    for hospital, sigla in cells:
        mgr.check_cell_lock(session_id, hospital, sigla, participant_id)


def _claim_reorg_cells_for_agent(
    request: Request,
    mgr: SessionManager,
    session_id: str,
    participant_id: str | None,
    cells: list[tuple[str, str]],
) -> None:
    """M3b: after a SUCCESSFUL agent write, claim the touched cells (badge) and
    broadcast the presence snapshot — mirrors the six write routes' agent path
    (``if is_agent(...): _broadcast_presence(...)``).

    The check→claim window this opens matches the codebase's accepted M3 model
    (see ``check_cell_lock``'s docstring); ``agent_claim_cell`` never steals a
    human-held cell, so its return value is deliberately ignored. Presence is
    single-focus per participant → the agent ends as editor of the last claimed
    cell (the op's dest).
    """
    if not is_agent(participant_id):
        return
    for hospital, sigla in cells:
        mgr.agent_claim_cell(session_id, hospital, sigla)
    _broadcast_presence(request, mgr, session_id)


@router.post("/sessions/{session_id}/reorg/ops")
def create_reorg_op(
    request: Request,
    session_id: str,
    body: ReorgOpCreate,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Create a reorg op; recompute deltas; return the op + affected cells."""
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    op = body.model_dump()
    src = op["source"]
    dst = op["dest"]
    # F13/F3: both endpoints must be canonical cell coordinates (400 if not) —
    # replaces the ad-hoc KeyError→404 "Unknown sigla" mapping.
    _validate_cell_coords(src["hospital"], src["sigla"])
    _validate_cell_coords(dst["hospital"], dst["sigla"])
    month_root = Path(state.get("month_root", ""))
    src_folder = _find_category_folder(month_root / src["hospital"], src["sigla"])
    src_cell = (state.get("cells", {}).get(src["hospital"], {}) or {}).get(src["sigla"])
    if src_cell is None:
        raise HTTPException(404, f"Cell not found: {src['hospital']}/{src['sigla']}")

    src_pages = cell_page_counts(src_folder) if src_folder.exists() else {}
    # F5: move_file doc_count is bounded by the file's real contribution to the
    # source cell — same rule as the doc_count default (api.reorg.file_contribution).
    errors = validate_op(
        op,
        src_pages=src_pages,
        existing_ops=state.get("reorg_ops", []),
        src_contribution=file_contribution(src_cell, src["file"]),
    )
    if errors:
        raise HTTPException(400, "; ".join(errors))

    op = resolve_op_defaults(op, src_cell=src_cell)
    cells = [(src["hospital"], src["sigla"]), (dst["hospital"], dst["sigla"])]
    # F3: the op mutates both endpoints' effective counts (reorg deltas), so both
    # must be free (or held by the caller) before it is recorded. Check-only.
    _gate_reorg_cells(mgr, session_id, body.participant_id, cells)
    # F4: append + delta recompute happen atomically under one lock (the overlap
    # re-check inside catches a race with a concurrent create).
    try:
        created = mgr.add_reorg_op_validated(session_id, op)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Agent claims only now — after the write succeeded (F3 follow-up).
    _claim_reorg_cells_for_agent(request, mgr, session_id, body.participant_id, cells)
    # Anti-colados §6: the new op suppresses the source cell's matching suspect
    # (derived), so recompute all_reliable there — "crear la op restaura el verde
    # sin re-scan". The session_refresh broadcast lands the value on clients.
    refresh_all_reliable(
        mgr,
        session_id,
        src["hospital"],
        src["sigla"],
        src_folder,
        count_type=count_type_for(src["sigla"]),
    )
    _broadcast_session_refresh(request, session_id)
    state = mgr.get_session_state(session_id)
    return {"op": created, "cells": state["cells"]}


@router.delete("/sessions/{session_id}/reorg/ops/{op_id}")
def delete_reorg_op(
    request: Request,
    session_id: str,
    op_id: str,
    participant_id: str | None = None,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Delete a reorg op; recompute deltas."""
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    month_root = Path(state.get("month_root", ""))
    # Look up the op BEFORE deleting so we can gate on the cells it touches (F3).
    op = next((o for o in state.get("reorg_ops", []) if o.get("id") == op_id), None)
    if op is None:
        raise HTTPException(404, f"Op not found: {op_id}")
    cells = [
        (op["source"]["hospital"], op["source"]["sigla"]),
        (op["dest"]["hospital"], op["dest"]["sigla"]),
    ]
    _gate_reorg_cells(mgr, session_id, participant_id, cells)  # check-only
    # F4: delete + delta recompute run atomically under one lock.
    if not mgr.delete_reorg_op_and_refresh(session_id, op_id):
        raise HTTPException(404, f"Op not found: {op_id}")
    # Agent claims only now — after the write succeeded (F3 follow-up).
    _claim_reorg_cells_for_agent(request, mgr, session_id, participant_id, cells)
    # Anti-colados §6: deleting the op un-suppresses the source cell's suspect
    # (derived) — recompute all_reliable there so the green dot drops again.
    src = op["source"]
    src_folder = _find_category_folder(month_root / src["hospital"], src["sigla"])
    refresh_all_reliable(
        mgr,
        session_id,
        src["hospital"],
        src["sigla"],
        src_folder,
        count_type=count_type_for(src["sigla"]),
    )
    _broadcast_session_refresh(request, session_id)
    state = mgr.get_session_state(session_id)
    return {"deleted": op_id, "cells": state["cells"]}


@router.post("/sessions/{session_id}/reorg/export")
def export_reorg_manifest(
    session_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Write the reorg manifest (pending ops) to OVERSEER_OUTPUT_DIR."""
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    manifest = build_manifest(state, month=session_id)
    if not manifest["operations"]:
        raise HTTPException(400, "No hay operaciones pendientes para exportar")
    from api.routes.output import _output_dir  # noqa: E402

    out_dir = _output_dir()
    # Data-safety: the corpus (INFORME_MENSUAL_ROOT) is read-only. Never write the
    # manifest there, even if OVERSEER_OUTPUT_DIR is ever misconfigured to point inside it.
    if out_dir.resolve().is_relative_to(_informe_root().resolve()):
        raise HTTPException(
            500, "OVERSEER_OUTPUT_DIR no puede estar dentro de INFORME_MENSUAL_ROOT"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"reorganizacion_{session_id}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(dest)
    return {"path": str(dest), "operation_count": len(manifest["operations"])}
