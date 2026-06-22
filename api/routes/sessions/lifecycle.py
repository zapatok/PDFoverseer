"""Session lifecycle routes: open/return a session + fetch its persisted state."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from api.state import SessionManager

from ._common import _resolve_month_dir, _validate_session_id, get_manager

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
    """Return the persisted state dict for a session."""
    _validate_session_id(session_id)
    try:
        return mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
