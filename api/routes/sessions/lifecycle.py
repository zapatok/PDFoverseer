"""Session lifecycle routes: open/return a session + fetch its persisted state."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.state import SessionManager
from core.scanners.patterns import count_type_for

from ._common import (
    _PAGE_COUNT_CACHE,
    _resolve_month_dir,
    _validate_session_id,
    enrich_cell_colado_suspects,
    enrich_cell_worker_count,
    get_manager,
    hospital_category_folders,
)

router = APIRouter()


class OpenSessionRequest(BaseModel):
    """Body for opening/returning a session (§B6, 2026-07-11).

    Joins the ``extra="forbid"`` doctrine the rest of the write surface
    follows, and bounds ``year``/``month`` so a typo can't mint an orphan
    session row (``_validate_session_id`` would reject its id downstream, but
    only after ``open_session`` already wrote it). Decision: the missing/out-
    of-range 400 this used to return is now a 422 validation error, consistent
    with every other forbid-guarded endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=2020, le=2100)
    month: int = Field(ge=1, le=12)


@router.post("/sessions")
def create(
    body: OpenSessionRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Open or return an existing session for ``(year, month)``."""
    month_dir = _resolve_month_dir(body.year, body.month)
    # §B8.5: purge the page-count cache on every session open — see its
    # comment in _common.py for the (theoretical) staleness hole this closes
    # and the cross-month growth cap it doubles as.
    _PAGE_COUNT_CACHE.clear()
    return mgr.open_session(year=body.year, month=body.month, month_root=month_dir)


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
        reorg_ops = state.get("reorg_ops") or []
        enriched_cells[hosp] = {
            sigla: enrich_cell_colado_suspects(
                enrich_cell_worker_count(cell, month_root, hosp, sigla, folders.get(sigla)),
                reorg_ops,
                hosp,
                sigla,
            )
            for sigla, cell in cell_map.items()
        }
    return {**state, "cells": enriched_cells}
