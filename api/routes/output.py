"""POST /api/sessions/{session_id}/output → generate RESUMEN xlsx."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from api.routes.sessions import get_manager
from api.state import SessionManager
from core.excel.writer import generate_resumen

router = APIRouter()

_SESSION_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _output_dir() -> Path:
    return Path(
        os.environ.get(
            "OVERSEER_OUTPUT_DIR",
            "A:/PROJECTS/PDFoverseer/data/outputs",
        )
    )


def _build_cell_values(state: dict) -> dict[str, int]:
    """Translate session.cells into named-range-keyed dict for the writer."""
    from core.excel.writer import resolve_cell_value

    out: dict[str, int] = {}
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla, cell in sigla_map.items():
            value = resolve_cell_value(cell)
            if value is None:
                continue
            out[f"{hosp}_{sigla}_count"] = value
    return out


@router.post("/sessions/{session_id}/output")
def generate(
    session_id: str,
    body: dict = Body(default={}),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError:
        raise HTTPException(404, f"Session not found: {session_id}")
    cell_values = _build_cell_values(state)
    output_dir = _output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"RESUMEN_{session_id}.xlsx"
    result = generate_resumen(
        cell_values=cell_values,
        output_path=output_path,
    )
    return {
        "output_path": str(result.output_path),
        "cells_written": result.cells_written,
        "warnings": result.warnings,
        "duration_ms": result.duration_ms,
    }
