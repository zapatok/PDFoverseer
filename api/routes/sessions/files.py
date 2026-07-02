"""Cell file routes: list a cell's PDFs (with per-file chips) + serve one PDF."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.state import SessionManager
from core.orchestrator import _find_category_folder

from ._common import (
    _informe_root,
    _validate_cell_coords,
    _validate_session_id,
    cell_page_counts,
    file_origin,
    get_manager,
)

router = APIRouter()


@router.get("/sessions/{session_id}/cells/{hospital}/{sigla}/files")
def get_cell_files(
    session_id: str,
    hospital: str,
    sigla: str,
    mgr: SessionManager = Depends(get_manager),
) -> list[dict]:
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    cell = state.get("cells", {}).get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    month_root = Path(state.get("month_root", ""))
    hosp_dir = month_root / hospital
    folder = _find_category_folder(hosp_dir, sigla)
    if not folder.exists():
        return []
    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    per_file_method = cell.get("per_file_method") or {}
    cell_method = cell.get("method") or "filename_glob"

    def _origin_for(
        filename: str,
        override: int | None,
        page_count: int,
        per_file_count: int | None,
    ) -> str:
        """Thin wrapper: resolves the per-file method then delegates to the
        module-level ``file_origin`` pure function (single source of chip vocab).
        """
        method = per_file_method.get(filename) or cell_method
        return file_origin(
            method=method,
            override=override,
            page_count=page_count,
            per_file_count=per_file_count,
        )

    pages = cell_page_counts(folder)
    out: list[dict] = []
    for pdf in sorted(folder.rglob("*.pdf")):
        page_count = pages.get(pdf.name, 0)
        subfolder = pdf.parent.name if pdf.parent != folder else None
        override = per_file_overrides.get(pdf.name)
        inferred = per_file.get(pdf.name)
        # effective_count defaults to 1 here — a PDF the operator is looking at
        # counts as at least one document. This is intentionally asymmetric with
        # api.state.compute_cell_count, which defaults a dataless cell to 0
        # (audit #7). The divergence is presentation-only and pre-scan: after a
        # scan, per_file covers every PDF and the two agree. Kept at 1 because
        # it is the intuitive per-file view for the operator.
        effective = override if override is not None else (inferred if inferred is not None else 1)
        out.append(
            {
                "name": pdf.name,
                "subfolder": subfolder,
                "page_count": page_count,
                "suspect": page_count >= 10,
                "per_file_count": inferred,
                "override_count": override,
                "effective_count": effective,
                "origin": _origin_for(pdf.name, override, page_count, inferred),
            }
        )
    return out


@router.get("/sessions/{session_id}/cells/{hospital}/{sigla}/pdf")
def get_cell_pdf(
    session_id: str,
    hospital: str,
    sigla: str,
    index: int = 0,
    mgr: SessionManager = Depends(get_manager),
) -> FileResponse:
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    if index < 0:
        raise HTTPException(400, "index must be ≥ 0")
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state.get("cells", {}).get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    month_root = Path(state.get("month_root", ""))
    hosp_dir = month_root / hospital
    folder = _find_category_folder(hosp_dir, sigla)
    pdfs = sorted(folder.rglob("*.pdf")) if folder.exists() else []
    if not pdfs:
        raise HTTPException(404, "no_pdfs_in_cell")
    if index >= len(pdfs):
        raise HTTPException(400, f"index out of range: {index} >= {len(pdfs)}")

    pdf_path = pdfs[index].resolve()
    cell_folder = folder.resolve()
    informe_root = _informe_root().resolve()
    # Two layers of containment per spec §4.6: PDF inside cell folder, cell
    # folder inside INFORME_MENSUAL_ROOT. Both must hold.
    if not pdf_path.is_relative_to(cell_folder):
        raise HTTPException(400, "invalid path")
    if not cell_folder.is_relative_to(informe_root):
        raise HTTPException(400, "cell folder outside informe root")

    return FileResponse(pdf_path, media_type="application/pdf")
