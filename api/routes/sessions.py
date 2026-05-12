"""Sessions endpoints: create/get + trigger scan."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from api.state import SessionManager
from core.orchestrator import enumerate_month, scan_month

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
