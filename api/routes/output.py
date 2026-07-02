"""POST /api/sessions/{session_id}/output → generate RESUMEN xlsx."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from api.routes.sessions import cell_page_counts, get_manager, present_file_names
from api.state import SessionManager, compute_cell_count, compute_worker_count
from core.db.historical_repo import upsert_count
from core.domain import HOSPITALS, SIGLAS
from core.excel.writer import generate_resumen
from core.orchestrator import _find_category_folder
from core.scanners.patterns import count_type_for

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


# chps (CPHS — Comité Paritario) is modeled + counted but NOT written to the
# RESUMEN (Daniel, 2026-06-23: "solo cphs no va al excel"). The template carries no
# {HOSP}_chps_count range either; history still persists it. Excluded here only.
EXCEL_EXCLUDED_SIGLAS: frozenset[str] = frozenset({"chps"})


def _build_cell_values(state: dict) -> dict[str, int]:
    """Translate session.cells into named-range-keyed dict for the writer.

    Iterates the full canonical HOSPITALS × SIGLAS grid (not just the cells
    present in state) so a hospital not yet counted writes explicit 0s instead of
    leaving the template blank. Excluded cells return None and are skipped.
    """
    from core.excel.writer import resolve_cell_value

    cells = state.get("cells", {})
    month_root = Path(state.get("month_root", ""))
    out: dict[str, int] = {}
    for hosp in HOSPITALS:
        hosp_cells = cells.get(hosp, {})
        for sigla in SIGLAS:
            if sigla in EXCEL_EXCLUDED_SIGLAS:
                continue
            ct = count_type_for(sigla)
            present = None
            if ct == "checks":
                # checks (maquinaria): the cell value is the tally → filter marks
                # by present files. Resolved only here (1 sigla/hosp) to avoid
                # walking folders for the 16 document siglas.
                folder = _find_category_folder(month_root / hosp, sigla)
                present = set(cell_page_counts(folder)) if folder.exists() else None
            value = resolve_cell_value(
                hosp_cells.get(sigla, {}), count_type=ct, present_files=present
            )
            if value is None:
                continue
            out[f"{hosp}_{sigla}_count"] = value
    return out


# Sigla del sistema → "purpose" del rango de trabajadores en el Excel.
# El template usa "chgen" para charlas generales, no "charla".
WORKER_PURPOSE: dict[str, str] = {"charla": "chgen", "chintegral": "chintegral"}

# dif_pts: el total de trabajadores va a la celda HH de su propia fila (fila 15),
# por hospital. HOY solo HPV (→ N15). Para HABILITAR otra obra "sin más":
#   1. añadirla a este set,
#   2. crear el rango {HOSP}_workers_difpts → {col_HH}15 en el template,
#   3. limpiar la fórmula =col*0.5 de esa celda (ver build_template_v1.py docstring).
# Las obras NO incluidas conservan su estimación docs×0.5 intacta.
DIFPTS_WORKER_HOSPITALS: frozenset[str] = frozenset({"HPV"})


def _build_worker_values(state: dict) -> dict[str, int]:
    """Emite ``{HOSP}_workers_{purpose}`` para las celdas charla/chintegral
    que tengan datos de conteo de trabajadores. Además emite
    ``{HOSP}_workers_difpts`` para los hospitales en ``DIFPTS_WORKER_HOSPITALS``
    (hoy solo HPV) — siempre, con 0 si no se contó (Incr 3B, decisión D2)."""
    out: dict[str, int] = {}
    month_root = Path(state.get("month_root", ""))
    for hosp, sigla_map in state.get("cells", {}).items():
        for sigla, purpose in WORKER_PURPOSE.items():
            cell = sigla_map.get(sigla)
            if not cell:
                continue
            if "worker_marks" not in cell and "worker_status" not in cell:
                continue  # nunca se contó — no emitir; el template queda en blanco
            folder = _find_category_folder(month_root / hosp, sigla)
            # F1: canonical present-filtered set via names only (no PDF opens). The
            # folder-missing branch keeps its legacy ``None`` filtering, unchanged by
            # design (output-conservative — never flips an existing Excel value).
            present = present_file_names(folder) if folder.exists() else None
            out[f"{hosp}_workers_{purpose}"] = compute_worker_count(cell, present)

    # dif_pts (Incr 3B): worker total → HH cell of its own row, scoped to HPV.
    # Always emits (0 if uncounted) — NO "never counted → skip" guard (D2: explicit
    # 0, never the =M15*0.5 fallback). Do NOT harmonize with the charla/chintegral
    # loop above, which deliberately skips uncounted cells.
    for hosp in DIFPTS_WORKER_HOSPITALS:
        cell = state.get("cells", {}).get(hosp, {}).get("dif_pts")
        if cell is None:
            continue  # no dif_pts cell → N15 stays at the template's 0
        folder = _find_category_folder(month_root / hosp, "dif_pts")
        # F1: names-only present set (see the charla/chintegral loop above).
        present = present_file_names(folder) if folder.exists() else None
        out[f"{hosp}_workers_difpts"] = compute_worker_count(cell, present)
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

    # dif_pts (Incr 3B): warn HPV when worker count is pending. Same predicate as
    # charla/chintegral (has PDFs + not terminado), scoped to DIFPTS_WORKER_HOSPITALS.
    # The N15 = 0 / formula-cleared decision (D2) makes this warning load-bearing.
    for hosp in DIFPTS_WORKER_HOSPITALS:
        cell = state.get("cells", {}).get(hosp, {}).get("dif_pts")
        if cell and cell.get("per_file") and cell.get("worker_status") != "terminado":
            out.append({"hospital": hosp, "sigla": "dif_pts"})
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
    history_root = Path(state.get("month_root", ""))
    for hospital, hosp_cells in state.get("cells", {}).items():
        if hospital not in HOSPITALS:
            continue  # F13: never write a phantom hospital (symmetric with the sigla filter)
        for sigla, cell in hosp_cells.items():
            if sigla not in SIGLAS:
                continue  # F13: never write a phantom sigla (e.g. a stale no_existe cell)
            if cell.get("excluded"):
                continue
            # Single source of truth (2026-06-06): history must match the Excel.
            # checks cells (maquinaria) → the manual tally, filtered by present
            # files; document cells are unchanged (ct="documents", present=None).
            ct = count_type_for(sigla)
            present = None
            if ct == "checks":
                folder = _find_category_folder(history_root / hospital, sigla)
                present = set(cell_page_counts(folder)) if folder.exists() else None
            effective_count = compute_cell_count(cell, ct, present)
            upsert_count(
                mgr._conn,
                year=year,
                month=month,
                hospital=hospital,
                sigla=sigla,
                count=int(effective_count or 0),
                # D5: a cell with no confidence field was never really counted —
                # record honest "low", not a fabricated "high".
                confidence=cell.get("confidence") or "low",
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
