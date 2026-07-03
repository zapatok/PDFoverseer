"""Session lifecycle routes: open/return a session + fetch its persisted state."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from api.state import SessionManager
from core.scanners.patterns import count_type_for

from ._common import (
    _resolve_month_dir,
    _validate_session_id,
    enrich_cell_worker_count,
    get_manager,
    hospital_category_folders,
)

router = APIRouter()


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
    """Return the persisted state dict for a session.

    Every worker/checks cell is enriched with the canonical present-filtered
    ``worker_count`` in the RESPONSE copy only (F1) — the field is never persisted
    into state (its single producer is this derivation).
    """
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    month_root = Path(state.get("month_root", ""))
    enriched_cells: dict = {}
    for hosp, cell_map in state.get("cells", {}).items():
        # One directory listing per hospital (not one per worker sigla): resolve
        # every worker/checks folder up front, then enrich with the pre-resolved
        # paths. Request-scoped only.
        # Phantom/unknown siglas can't slip in: count_type_for defaults them to
        # "documents", so only canonical worker/checks siglas reach the resolver.
        worker_siglas = [
            s for s in cell_map if count_type_for(s) in ("documents_workers", "checks")
        ]
        folders = hospital_category_folders(month_root / hosp, worker_siglas)
        enriched_cells[hosp] = {
            sigla: enrich_cell_worker_count(cell, month_root, hosp, sigla, folders.get(sigla))
            for sigla, cell in cell_map.items()
        }
    return {**state, "cells": enriched_cells}
