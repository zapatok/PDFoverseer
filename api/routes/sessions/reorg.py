"""Reorg routes (Incr J T9–T11): create/delete a reorg op + export the manifest."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.reorg import build_manifest, resolve_op_defaults, validate_op
from api.state import SessionManager
from core.orchestrator import _find_category_folder

from ._common import (
    _broadcast_session_refresh,
    _informe_root,
    _validate_session_id,
    cell_page_counts,
    get_manager,
    refresh_reorg_deltas,
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
    doc_count: int | None = None
    worker_count: int | None = None
    note: str | None = None


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
    month_root = Path(state.get("month_root", ""))
    try:
        src_folder = _find_category_folder(month_root / src["hospital"], src["sigla"])
        _find_category_folder(month_root / op["dest"]["hospital"], op["dest"]["sigla"])
    except KeyError as exc:
        raise HTTPException(404, f"Unknown sigla: {exc}") from exc
    src_cell = (state.get("cells", {}).get(src["hospital"], {}) or {}).get(src["sigla"])
    if src_cell is None:
        raise HTTPException(404, f"Cell not found: {src['hospital']}/{src['sigla']}")

    src_pages = cell_page_counts(src_folder) if src_folder.exists() else {}
    errors = validate_op(op, src_pages=src_pages, existing_ops=state.get("reorg_ops", []))
    if errors:
        raise HTTPException(400, "; ".join(errors))

    op = resolve_op_defaults(op, src_cell=src_cell)
    created = mgr.add_reorg_op(session_id, op)
    refresh_reorg_deltas(mgr, session_id, check_applied=False)
    _broadcast_session_refresh(request, session_id)
    state = mgr.get_session_state(session_id)
    return {"op": created, "cells": state["cells"]}


@router.delete("/sessions/{session_id}/reorg/ops/{op_id}")
def delete_reorg_op(
    request: Request,
    session_id: str,
    op_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Delete a reorg op; recompute deltas."""
    _validate_session_id(session_id)
    try:
        mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not mgr.delete_reorg_op(session_id, op_id):
        raise HTTPException(404, f"Op not found: {op_id}")
    refresh_reorg_deltas(mgr, session_id, check_applied=False)
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
