"""POST /api/sessions/{session_id}/output → generate RESUMEN xlsx."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException

from api.routes.sessions import get_manager
from api.state import SessionManager
from core.db.historical_repo import upsert_count
from core.excel.writer import generate_resumen

router = APIRouter()


def _method_for_history(cell: dict) -> str:
    """Derive the historical_counts.method value from a cell's state.

    Priority cascade (matches Excel writer in Chunk 1):
      user_override -> 'override'
      ocr_count     -> cell['method'] (header_detect / corner_count / page_count_pure / filename_glob)
      filename_count -> 'filename_glob'
      legacy count  -> 'filename_glob'
      none          -> 'filename_glob' (default for un-scanned)
    """
    if cell.get("user_override") is not None:
        return "override"
    if cell.get("ocr_count") is not None:
        return cell.get("method") or "filename_glob"
    return "filename_glob"


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

    # Persist to historical_counts (UPSERT). Idempotent — regenerating the
    # same month overwrites with the same values. Excluded cells (FASE 1
    # carryover) are NOT written.
    year, month = int(session_id[:4]), int(session_id[5:7])
    for hospital, hosp_cells in state.get("cells", {}).items():
        for sigla, cell in hosp_cells.items():
            if cell.get("excluded"):
                continue
            effective_count = (
                cell.get("user_override")
                if cell.get("user_override") is not None
                else cell.get("ocr_count")
                if cell.get("ocr_count") is not None
                else cell.get("filename_count")
                if cell.get("filename_count") is not None
                else cell.get("count", 0)
            )
            upsert_count(
                mgr._conn,
                year=year,
                month=month,
                hospital=hospital,
                sigla=sigla,
                count=int(effective_count or 0),
                confidence=cell.get("confidence", "high"),
                method=_method_for_history(cell),
            )
    mgr._conn.commit()

    return {
        "output_path": str(result.output_path),
        "cells_written": result.cells_written,
        "warnings": result.warnings,
        "duration_ms": result.duration_ms,
    }
