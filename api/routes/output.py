"""POST /api/sessions/{session_id}/output → generate RESUMEN xlsx."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from api.routes.sessions import get_manager
from api.state import SessionManager, compute_cell_count, compute_worker_count
from core.db.historical_repo import upsert_count
from core.domain import HOSPITALS, SIGLAS
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


_MESES = (
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
)

_REPORT_TITLE_TMPL = (
    "RESUMEN EJECUTIVO ACTIVIDADES DE PREVENCIÓN DE RIESGOS\n"
    "{mes} {year}\n"
    "PROYECTO RED LOS RÍOS - LOS LAGOS"
)


def _build_report_title(year: int, month: int) -> str:
    """Build the report's header title for a session's month.

    The month/year line is dynamic; the project line is constant. Replaces the
    template's hardcoded 'MARZO 2026' so every month's RESUMEN reads correctly.

    Args:
        year: session year.
        month: session month (1-12).

    Returns:
        The three-line title string for cell E2 (named range ``report_title``).
    """
    return _REPORT_TITLE_TMPL.format(mes=_MESES[month - 1], year=year)


def _build_cell_values(state: dict) -> dict[str, int]:
    """Translate session.cells into named-range-keyed dict for the writer.

    Iterates the full canonical HOSPITALS × SIGLAS grid (not just the cells
    present in state) so a hospital not yet counted writes explicit 0s instead of
    leaving the template blank. Excluded cells return None and are skipped.
    """
    from core.excel.writer import resolve_cell_value

    cells = state.get("cells", {})
    out: dict[str, int] = {}
    for hosp in HOSPITALS:
        hosp_cells = cells.get(hosp, {})
        for sigla in SIGLAS:
            value = resolve_cell_value(hosp_cells.get(sigla, {}))
            if value is None:
                continue
            out[f"{hosp}_{sigla}_count"] = value
    return out


# Sigla del sistema → "purpose" del rango de trabajadores en el Excel.
# El template usa "chgen" para charlas generales, no "charla".
WORKER_PURPOSE: dict[str, str] = {"charla": "chgen", "chintegral": "chintegral"}


def _build_worker_values(state: dict) -> dict[str, int]:
    """Emite ``{HOSP}_workers_{purpose}`` para las celdas charla/chintegral
    que tengan datos de conteo de trabajadores."""
    out: dict[str, int] = {}
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla, purpose in WORKER_PURPOSE.items():
            cell = sigla_map.get(sigla)
            if not cell:
                continue
            if "worker_marks" not in cell and "worker_status" not in cell:
                continue  # nunca se contó — no emitir; el template queda en blanco
            out[f"{hosp}_workers_{purpose}"] = compute_worker_count(cell)
    return out


def _build_worker_warnings(state: dict) -> list[dict]:
    """Celdas charla/chintegral con conteo de trabajadores incompleto.

    Una celda avisa si tiene PDFs (``per_file`` no vacío) y su ``worker_status``
    no es ``"terminado"`` — la regla única del spec §7.3. El frontend bloquea
    "Terminé esta categoría" cuando un PDF no abre, así que el disyuntor "algún
    PDF falló" queda cubierto por este mismo predicado.

    Args:
        state: el blob de estado de la sesión.

    Returns:
        Lista de ``{"hospital", "sigla"}``; vacía si nada está incompleto.
    """
    out: list[dict] = []
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla in WORKER_PURPOSE:
            cell = sigla_map.get(sigla)
            if not cell or not cell.get("per_file"):
                continue
            if cell.get("worker_status") != "terminado":
                out.append({"hospital": hosp, "sigla": sigla})
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
    cell_values.update(_build_worker_values(state))
    cell_values["report_title"] = _build_report_title(int(session_id[:4]), int(session_id[5:7]))
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
            effective_count = compute_cell_count(cell)
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
        "worker_warnings": _build_worker_warnings(state),
        "duration_ms": result.duration_ms,
    }


@router.get("/sessions/{session_id}/output")
def serve_output(session_id: str) -> FileResponse:
    """Serve the generated RESUMEN_<month>.xlsx so the home can open it (G5).

    Args:
        session_id: month id ``YYYY-MM``.

    Returns:
        The xlsx as a downloadable FileResponse.
    """
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, "invalid session_id")
    out_dir = _output_dir().resolve()
    path = (out_dir / f"RESUMEN_{session_id}.xlsx").resolve()
    # is_relative_to guards against any traversal once the name is templated.
    if not path.is_file() or not path.is_relative_to(out_dir):
        raise HTTPException(404, "no output for that month")
    # no-store: the file is regenerated in place on each /output POST, so the
    # browser must never serve a stale download for this stable URL.
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"RESUMEN_{session_id}.xlsx",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/outputs")
def list_outputs() -> list[dict]:
    """List every generated RESUMEN xlsx, most recent first (G5).

    Returns:
        ``[{session_id, filename, mtime_iso, size}]`` — empty if none exist.
    """
    d = _output_dir()
    if not d.exists():
        return []
    out: list[dict] = []
    for p in d.glob("RESUMEN_*.xlsx"):
        st = p.stat()
        out.append(
            {
                "session_id": p.stem.removeprefix("RESUMEN_"),
                "filename": p.name,
                "mtime_iso": datetime.fromtimestamp(st.st_mtime).isoformat(),
                "size": st.st_size,
            }
        )
    out.sort(key=lambda o: o["mtime_iso"], reverse=True)
    return out
