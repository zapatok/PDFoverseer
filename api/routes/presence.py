"""Presence endpoints (multiplayer M2). HTTP up-channel; WS carries the `presence`
snapshot down. No locking/enforcement here — that is M3 (spec §6.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from api.routes.sessions import _validate_session_id, get_manager
from api.routes.ws import _emit
from api.state import SessionManager

router = APIRouter()


class HeartbeatBody(BaseModel):
    participant_id: str
    name: str
    color: str


class FocusBody(BaseModel):
    participant_id: str
    cell: str | None = None


class LeaveBody(BaseModel):
    participant_id: str


def _presence_event(session_id: str, mgr: SessionManager) -> dict:
    return {
        "type": "presence",
        "session_id": session_id,
        "participants": mgr.presence_snapshot(session_id),
    }


@router.post("/sessions/{session_id}/presence/heartbeat")
def heartbeat(
    session_id: str,
    body: HeartbeatBody,
    request: Request,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Register or refresh a participant; return the full presence snapshot.

    Args:
        session_id: YYYY-MM session identifier.
        body: participant identity (id, display name, color).
        request: FastAPI request (used for WS broadcast).
        mgr: session manager (injected).

    Returns:
        Presence event dict with ``type="presence"`` and ``participants`` list.
    """
    _validate_session_id(session_id)
    changed = mgr.presence_heartbeat(
        session_id, body.participant_id, name=body.name, color=body.color
    )
    event = _presence_event(session_id, mgr)
    if changed:
        _emit(request, session_id, event)
    return event


@router.post("/sessions/{session_id}/presence/focus")
def focus(
    session_id: str,
    body: FocusBody,
    request: Request,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Update which cell a participant is focused on; broadcast if changed.

    Args:
        session_id: YYYY-MM session identifier.
        body: participant id and optional cell key (``None`` clears focus).
        request: FastAPI request (used for WS broadcast).
        mgr: session manager (injected).

    Returns:
        Presence event dict with current snapshot.
    """
    _validate_session_id(session_id)
    changed = mgr.presence_focus(session_id, body.participant_id, body.cell)
    event = _presence_event(session_id, mgr)
    if changed:
        _emit(request, session_id, event)
    return event


@router.post("/sessions/{session_id}/presence/leave")
def leave(
    session_id: str,
    body: LeaveBody,
    request: Request,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Remove a participant from the presence registry; broadcast if changed.

    Args:
        session_id: YYYY-MM session identifier.
        body: participant id to remove.
        request: FastAPI request (used for WS broadcast).
        mgr: session manager (injected).

    Returns:
        Presence event dict with updated snapshot (participant already removed).
    """
    _validate_session_id(session_id)
    changed = mgr.presence_leave(session_id, body.participant_id)
    event = _presence_event(session_id, mgr)
    if changed:
        _emit(request, session_id, event)
    return event
