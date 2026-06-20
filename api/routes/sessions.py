"""Sessions endpoints: create/get + trigger scan."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.batch import make_handle
from api.presence import AGENT_PARTICIPANT_ID, CellLockedError, is_agent
from api.routes.ws import _emit, broadcast
from api.state import (
    SessionManager,
    compute_cell_count,
    compute_worker_count,
)
from core.orchestrator import (
    enumerate_month,
    scan_cells_ocr,
    scan_month,
    scan_one_file_ocr,
)
from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs

# Single thread per session is plenty — Daniel's machine has one user, and
# scan_cells_ocr already uses a ProcessPoolExecutor internally for parallelism.
_DISPATCH_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-batch")

logger = logging.getLogger(__name__)

router = APIRouter()

_SESSION_ID_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _validate_session_id(session_id: str) -> None:
    """Raise 400 if session_id is not a valid YYYY-MM (format check, before any
    DB lookup). Shared by the session and presence routers."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")


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


import fitz  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from core.scanners.patterns import count_type_for  # noqa: E402

_MAX_REASONABLE_COUNT = 10_000

_OCR_METHODS = ("header_detect", "corner_count", "header_band_anchors", "v4")


def file_origin(
    *,
    method: str | None,
    override: int | None,
    page_count: int,
    per_file_count: int | None,
) -> str:
    """Per-file chip vocabulary (single source — reused by _origin_for and
    compute_settled). Priority: Manual override > unreadable Error > OCR/Revisar >
    RN (ratio_n) > R1 (page_count_pure) > R1/Pendiente (filename_glob by page count)
    > R1 default.
    """
    if override is not None:
        return "Manual"
    if page_count == 0:  # unreadable PDF
        return "Error"
    if method in _OCR_METHODS:
        return "Revisar" if per_file_count == 0 else "OCR"
    if method == "ratio_n":
        return "RN"
    if method == "page_count_pure":
        return "R1"
    if method == "filename_glob":
        return "R1" if page_count == 1 else "Pendiente"
    return "R1"


def cell_page_counts(folder: Path) -> dict[str, int]:
    """Lazy per-file page counts for a cell's folder: {pdf.name: page_count}.
    0 when a PDF can't be opened. Today reads from disk; the Incr-J persistence
    (per_file_pages) would slot in here without touching callers.
    """
    if not folder.exists():
        return {}  # missing folder → no pages (callers treat as unknowable, never throw)
    out: dict[str, int] = {}
    for pdf in sorted(folder.rglob("*.pdf")):
        try:
            with fitz.open(pdf) as doc:
                out[pdf.name] = doc.page_count
        except Exception:  # noqa: BLE001 — any fitz/IO failure → unreadable (0)
            out[pdf.name] = 0
    return out


def compute_settled(
    cell: dict, folder: Path, pages: dict[str, int] | None = None, count_type: str | None = None
) -> bool:
    """True iff the cell is 'listo' (green) by provenance.

    A ``por_resolver`` note blocks settlement unconditionally (checked first).
    checks (maquinaria): settled iff ``worker_status == 'terminado'`` (human
    verification of the manual tally) — short-circuits before touching the folder.
    Otherwise: every PDF in *folder* is reliable (origin ∈ {R1, RN, Manual});
    empty/missing folder → False. Lazy pages — pass a precomputed ``pages`` dict
    to avoid reopening PDFs the caller already read.
    """
    if cell.get("note_status") == "por_resolver":
        return False
    if count_type == "checks":
        return cell.get("worker_status") == "terminado"
    if pages is None:
        pages = cell_page_counts(folder)  # one walk; keys are every PDF.name in folder
    if not pages:
        return False  # empty/missing folder → a cell with no files is not 'listo'
    per_file = cell.get("per_file") or {}
    per_file_method = cell.get("per_file_method") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    cell_method = cell.get("method") or "filename_glob"
    for name, page_count in pages.items():
        origin = file_origin(
            method=per_file_method.get(name) or cell_method,
            override=per_file_overrides.get(name),
            page_count=page_count,
            per_file_count=per_file.get(name),
        )
        if origin not in ("R1", "RN", "Manual"):
            return False
    return True


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


def refresh_all_reliable(
    mgr: SessionManager,
    session_id: str,
    hospital: str,
    sigla: str,
    folder: Path,
    pages: dict[str, int] | None = None,
    count_type: str | None = None,
) -> None:
    """Recompute and persist all_reliable after an interactive per-file mutation.
    Pass ``pages`` when the caller already computed them (avoids reopening PDFs).
    Pass ``count_type`` so checks cells (maquinaria) settle on worker_status.
    """
    state = mgr.get_session_state(session_id)
    cell = state["cells"][hospital][sigla]
    mgr.set_all_reliable(
        session_id,
        hospital,
        sigla,
        compute_settled(cell, folder, pages=pages, count_type=count_type),
    )


def refresh_reorg_deltas(
    mgr: SessionManager,
    session_id: str,
    *,
    check_applied: bool = False,
) -> None:
    """Recompute every cell's reorg delta from ``state["reorg_ops"]`` (session-wide).

    Pattern of ``refresh_all_reliable`` (cache derived from the source, refreshed
    after mutations), but session-scoped: it sweeps all cells. Call with
    ``check_applied=True`` only on a pase-1 re-scan — the one moment a source file
    could have moved physically: a ``pending`` op whose ``source.file`` is no longer
    present in its origin folder is marked ``applied`` and stops contributing a delta
    (the move is now physical reality; counting both would double-count).

    Two-call pattern (get-then-set, like ``refresh_all_reliable``): safe here because
    the only writer to ``reorg_ops`` is the same synchronous HTTP tier (scan + the
    op-CRUD endpoints). The background OCR drain thread never touches ``reorg_ops``
    (it only writes per-file/cell OCR fields), so no concurrent edit is lost.

    Args:
        mgr: The active SessionManager.
        session_id: Target session identifier.
        check_applied: When True, inspect each pending op's source folder on disk
            and mark it ``applied`` if the file is gone.
    """
    state = mgr.get_session_state(session_id)
    ops = state.get("reorg_ops", [])
    month_root = Path(state.get("month_root", ""))

    if check_applied:
        for op in ops:
            if op.get("status") != "pending":
                continue
            src = op["source"]
            file = src.get("file")
            if file is None:
                continue  # malformed op (validation requires a file); never auto-apply
            folder = _find_category_folder(month_root / src["hospital"], src["sigla"])
            present = set(cell_page_counts(folder)) if folder.exists() else set()
            if file not in present:
                op["status"] = "applied"

    deltas: dict[tuple[str, str], dict] = {}
    for op in ops:
        if op.get("status") != "pending":
            continue
        src_key = (op["source"]["hospital"], op["source"]["sigla"])
        dst_key = (op["dest"]["hospital"], op["dest"]["sigla"])
        doc = op.get("doc_count") or 0
        wrk = op.get("worker_count") or 0
        for key in (src_key, dst_key):
            deltas.setdefault(key, {"doc": 0, "worker": 0})
        deltas[src_key]["doc"] -= doc
        deltas[src_key]["worker"] -= wrk
        deltas[dst_key]["doc"] += doc
        deltas[dst_key]["worker"] += wrk

    mgr.set_reorg_state(session_id, ops=ops, deltas=deltas)


def _is_capped_sigla(sigla: str) -> bool:
    return count_type_for(sigla) in ("documents", "documents_workers")


def _cell_total_pages(state: dict, hospital: str, sigla: str) -> int:
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    return sum(cell_page_counts(folder).values()) if folder.exists() else 0


class ApplyRatioRequest(BaseModel):
    n: int = Field(ge=1)
    participant_id: str | None = None


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/apply-ratio")
def apply_ratio(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: ApplyRatioRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Treat every Pendiente file as round(pages/N) documents (RN treatment)."""
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state["cells"].get(hospital, {}).get(sigla)
    if cell is None:
        raise HTTPException(404, f"Cell not found: {hospital}/{sigla}")
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    if not folder.exists():
        raise HTTPException(404, "Cell folder not found")
    pages = cell_page_counts(folder)
    per_file = cell.get("per_file") or {}
    per_file_method = cell.get("per_file_method") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    cell_method = cell.get("method") or "filename_glob"
    n = body.n
    participant_id = body.participant_id
    # M3b: agent path uses agent_claim_cell (auto-claim on free cell; 409 if human
    # holds it). Human/legacy path keeps the existing check_cell_lock gate.
    if is_agent(participant_id):
        holder = mgr.agent_claim_cell(session_id, hospital, sigla)
        if holder is not None:
            raise CellLockedError(hospital, sigla, holder)
    else:
        mgr.check_cell_lock(session_id, hospital, sigla, participant_id)
    for pdf in sorted(folder.rglob("*.pdf")):
        origin = file_origin(
            method=per_file_method.get(pdf.name) or cell_method,
            override=per_file_overrides.get(pdf.name),
            page_count=pages.get(pdf.name, 0),
            per_file_count=per_file.get(pdf.name),
        )
        if origin != "Pendiente":
            continue  # clobber-guard: only untouched multipage files (R1/Manual/OCR/RN intact)
        count = max(1, round(pages.get(pdf.name, 0) / n))
        mgr.apply_per_file_ocr_result(
            session_id,
            hospital,
            sigla,
            pdf.name,
            count=count,
            method="ratio_n",
            near_matches=[],
        )
    # finalize metadata (ocr_count = sum per_file) with a metadata-only ScanResult.
    # PRESERVE the cell-level method (don't set it to "ratio_n"): RN is a PER-FILE
    # treatment (per_file_method["f"]="ratio_n"), not a cell method. Files without a
    # per_file_method entry fall back to cell["method"] in file_origin — clobbering it
    # to "ratio_n" would wrongly flip those (e.g. an R1 file) to an RN chip.
    mgr.finalize_cell_ocr(
        session_id,
        hospital,
        sigla,
        ScanResult(
            count=0,
            confidence=ConfidenceLevel.LOW,
            method=cell_method,
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=0,
            files_scanned=0,
            per_file=None,
        ),
    )
    refresh_all_reliable(
        mgr, session_id, hospital, sigla, folder, pages=pages, count_type=count_type_for(sigla)
    )
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(participant_id):
        _broadcast_presence(request, mgr, session_id)
    state = mgr.get_session_state(session_id)
    return state["cells"][hospital][sigla]


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


@router.post("/sessions/{session_id}/scan")
def scan(
    request: Request,
    session_id: str,
    body: dict = Body(default={"scope": "all"}),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Trigger a full scan of the session's month folder and persist results."""
    _validate_session_id(session_id)
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
    skipped: list[dict] = []
    skipped_keys: set[tuple[str, str]] = set()
    for (hosp, sigla), r in results.items():
        # M3b Task 6: skip cells that a human is currently editing (pase-1).
        # exclude=AGENT_PARTICIPANT_ID so a concurrent pase-2 Claude claim never
        # causes pase-1 to skip the same cell (only humans block pase-1).
        holder = mgr.presence_lock_holder(
            session_id, f"{hosp}|{sigla}", exclude=AGENT_PARTICIPANT_ID
        )
        if holder is not None:
            skipped.append({"hospital": hosp, "sigla": sigla})
            skipped_keys.add((hosp, sigla))
            _emit(
                request,
                session_id,
                {
                    "type": "cell_skipped",
                    "hospital": hosp,
                    "sigla": sigla,
                    "reason": "locked",
                    "lock_holder": holder,
                },
            )
            continue
        mgr.apply_cell_result(session_id, hosp, sigla, r)
    refresh_reorg_deltas(mgr, session_id, check_applied=True)
    _broadcast_session_refresh(request, session_id)
    return {
        "scanned": len(results) - len(skipped),
        "skipped": skipped,
        "summary": {
            f"{hosp}_{sigla}": r.count
            for (hosp, sigla), r in results.items()
            if (hosp, sigla) not in skipped_keys
        },
    }


def _skip_files(cell: dict) -> set[str]:
    """Archivos ya confiables que el OCR de celda NO re-escanea (Incr. 1A, spec §3.1).

    Son los que tienen un método OCR previo (∉ ``filename_glob``) o un override
    por-archivo. Los A7/``filename_glob`` NO entran al skip: se re-escanean (es
    barato — solo cuentan páginas) y su per_file ya lo fijó pase-1.
    """
    method = cell.get("per_file_method") or {}
    overrides = cell.get("per_file_overrides") or {}
    return {f for f, m in method.items() if m and m != "filename_glob"} | set(overrides)


def _apply_scan_event(mgr: SessionManager, session_id: str, event: dict) -> dict:
    """Aplica un evento de progreso del OCR de celda al estado y devuelve el evento
    a difundir (posiblemente enriquecido). Incr. 1A — núcleo del merge incremental:

    - ``file_result``: merge incremental por-archivo **solo** si el método es OCR
      real (∉ ``filename_glob``) y ``count`` no es ``None``; un tick ``filename_glob``
      (A7/sin-flavors/``none``) o ``count=None`` (ilegible) es solo-progreso (su
      per_file ya lo fijó pase-1; el batch no reescribe esa verdad — clobber-guard).
    - ``cell_done``: finaliza la metadata y **reinyecta** el snapshot fusionado
      (``per_file`` completo —incluidos los saltados—, ``ocr_count``, ``near_matches``)
      para que el contrato del frontend quede idéntico al de pre-1A.
    - cualquier otro evento se difunde tal cual.
    """
    etype = event.get("type")
    if etype == "file_result":
        count = event.get("count")
        method = event.get("method")
        if count is not None and method != "filename_glob":
            mgr.apply_per_file_ocr_result(
                session_id,
                event["hospital"],
                event["sigla"],
                event["filename"],
                count=count,
                method=method,
                near_matches=event.get("near_matches") or [],
            )
        return event
    if etype == "cell_done":
        hosp = event["hospital"]
        sigla = event["sigla"]
        cell = mgr.finalize_cell_ocr(session_id, hosp, sigla, _meta_result(event["result"]))
        event["result"]["per_file"] = cell.get("per_file")
        event["result"]["ocr_count"] = cell.get("ocr_count")
        event["result"]["near_matches"] = cell.get("near_matches") or []
        # Recompute all_reliable now that every file has been OCR-merged (RLock is
        # reentrant so calling get_session_state + set_all_reliable here is safe).
        # Best-effort: skip when the folder isn't on disk (synthetic-event tests) —
        # the reliability signal is metadata; it must never break the count merge.
        month_root = Path(mgr.get_session_state(session_id).get("month_root", ""))
        hosp_dir = month_root / hosp
        if hosp_dir.exists():
            folder = _find_category_folder(hosp_dir, sigla)
            refresh_all_reliable(
                mgr, session_id, hosp, sigla, folder, count_type=count_type_for(sigla)
            )
        return event
    return event


def _cell_updated_event(
    mgr: SessionManager, session_id: str, hospital: str, sigla: str
) -> dict | None:
    """Arma el evento ``cell_updated`` con el snapshot COMPLETO de la celda (M1).

    Lleva la celda entera (no un merge por campos) porque un cambio remoto puede
    tocar cualquier campo; el frontend reemplaza la celda completa. ``actor`` es
    ``None`` en M1 (la identidad llega en M2). Devuelve ``None`` si la celda no
    existe (nunca revienta el camino de escritura).
    """
    try:
        cell = mgr.get_session_state(session_id)["cells"][hospital][sigla]
    except KeyError:
        return None
    return {
        "type": "cell_updated",
        "hospital": hospital,
        "sigla": sigla,
        "actor": None,
        "cell": cell,
    }


def _scan_followup_event(mgr: SessionManager, session_id: str, event: dict) -> dict | None:
    """Tras un ``cell_done`` del escaneo, arma el ``cell_updated`` con la celda
    completa (el ``cell_done`` solo lleva los 6 campos del progreso). Cualquier otro
    evento → ``None`` (no genera seguimiento). M1.
    """
    if event.get("type") != "cell_done":
        return None
    return _cell_updated_event(mgr, session_id, event["hospital"], event["sigla"])


def _handle_scan_progress(
    mgr: SessionManager,
    session_id: str,
    event: dict,
    ctx: dict,
    emit,
) -> None:
    """Apply one scan progress event under the agent lock-skip policy (M3b).

    ``ctx`` is a per-scan dict: {
        "skipped_set": set[tuple[str, str]],   # (hospital, sigla) pairs
        "skipped_cells": list[dict],            # [{hospital, sigla}, ...]
        "agent_active": bool,                   # True once the agent has claimed any cell
        "current_cell_skipped": bool,           # True while the current cell is skipped
    }.

    - ``cell_scanning``: claim the cell as the Claude agent.
      If a human holds it → record the skip, emit ``cell_skipped``, set
      ``current_cell_skipped=True``, do NOT broadcast cell_scanning.
      Else → mark agent_active, emit a presence snapshot (badge appears),
      set ``current_cell_skipped=False``, fall through to the normal path.
    - ``pdf_progress`` while ``current_cell_skipped`` → drop silently.
    - ``file_result`` / ``cell_done`` while ``(h, s) in skipped_set`` → drop.
    - ``scan_complete`` / ``scan_cancelled``: release the agent once; enrich
      ``scan_complete`` with ``ctx["skipped_cells"]``; broadcast and return.
    - Otherwise: normal path (``_apply_scan_event`` + ``cell_done`` followup).
    """
    etype = event.get("type")
    h, s = event.get("hospital"), event.get("sigla")

    if etype == "cell_scanning":
        ctx["current_cell_skipped"] = False  # reset per cell
        holder = mgr.agent_claim_cell(session_id, h, s)
        if holder is not None:
            ctx["skipped_set"].add((h, s))
            ctx["skipped_cells"].append({"hospital": h, "sigla": s})
            ctx["current_cell_skipped"] = True
            emit(
                {
                    "type": "cell_skipped",
                    "hospital": h,
                    "sigla": s,
                    "reason": "locked",
                    "lock_holder": holder,
                }
            )
            return
        ctx["agent_active"] = True
        emit(
            {
                "type": "presence",
                "session_id": session_id,
                "participants": mgr.presence_snapshot(session_id),
            }
        )
        # Fall through: emit the cell_scanning event normally.

    if etype == "pdf_progress" and ctx["current_cell_skipped"]:
        return

    if etype in ("file_result", "cell_done") and (h, s) in ctx["skipped_set"]:
        return

    if etype in ("scan_complete", "scan_cancelled"):
        if ctx["agent_active"]:
            mgr.agent_leave(session_id)
            ctx["agent_active"] = False
            emit(
                {
                    "type": "presence",
                    "session_id": session_id,
                    "participants": mgr.presence_snapshot(session_id),
                }
            )
        if etype == "scan_complete":
            event = {**event, "skipped": ctx["skipped_cells"]}
        emit(event)
        return

    emit(_apply_scan_event(mgr, session_id, event))
    followup = _scan_followup_event(mgr, session_id, event)
    if followup is not None:
        emit(followup)


def _broadcast_cell_updated(
    request: Request, mgr: SessionManager, session_id: str, hospital: str, sigla: str
) -> None:
    """Difunde ``cell_updated`` para una celda tras escribirla (M1, punto único)."""
    event = _cell_updated_event(mgr, session_id, hospital, sigla)
    if event is not None:
        _emit(request, session_id, event)


def _broadcast_presence(request: Request, mgr: SessionManager, session_id: str) -> None:
    """Difunde el snapshot de presencia (el badge del agente aparece/salta tras su escritura).

    Same event shape as ``_presence_event`` in ``api/routes/presence.py`` (M2) — keep
    the two in sync if the ``presence`` payload ever gains a field.
    """
    _emit(
        request,
        session_id,
        {
            "type": "presence",
            "session_id": session_id,
            "participants": mgr.presence_snapshot(session_id),
        },
    )


def _broadcast_session_refresh(request: Request, session_id: str) -> None:
    """Difunde ``session_refresh`` tras una operación que toca varias celdas (M1)."""
    _emit(request, session_id, {"type": "session_refresh"})


def _meta_result(r: dict) -> ScanResult:
    """Reconstruye un ScanResult de *solo metadata* desde el dict de un evento
    ``cell_done`` (la salida de ``orchestrator._cell_done_meta``) para pasarlo a
    :meth:`SessionManager.finalize_cell_ocr`.

    ``count``/``per_file`` van dummy a propósito: ``finalize_cell_ocr`` ignora
    ambos (el total real lo deriva del ``per_file`` ya fusionado por archivo).
    """
    return ScanResult(
        count=r.get("ocr_count") or 0,
        confidence=ConfidenceLevel(r["confidence"]),
        method=r["method"],
        breakdown=r.get("breakdown"),
        flags=list(r.get("flags") or []),
        errors=list(r.get("errors") or []),
        duration_ms=r.get("duration_ms_ocr") or 0,
        files_scanned=0,
        per_file=None,
    )


@router.post("/sessions/{session_id}/scan-ocr")
def scan_ocr(
    request: Request,
    session_id: str,
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Pase 2 — launch OCR batch for the given cells.

    Body: ``{"cells": [["HPV", "odi"], ["HRB", "art"], ...]}``
    """
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc

    cells_pairs = body.get("cells", [])
    if not isinstance(cells_pairs, list) or not cells_pairs:
        raise HTTPException(400, "cells must be a non-empty list of [hospital, sigla] pairs")

    app = request.app

    # Cell folder_path is NOT persisted in session state — re-enumerate from the
    # month_root so OCR scanners receive the real on-disk folder. (Persisting it
    # would couple session state to a transient filesystem layout.)
    month_root = Path(state["month_root"])
    try:
        inv = enumerate_month(month_root)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    folder_by_key: dict[tuple[str, str], Path] = {
        (c.hospital, c.sigla): c.folder_path for cell_list in inv.cells.values() for c in cell_list
    }

    cells_with_paths: list[tuple[str, str, Path]] = []
    for pair in cells_pairs:
        if not (isinstance(pair, list) and len(pair) == 2):
            raise HTTPException(400, f"Invalid cell pair: {pair}")
        hosp, sigla = pair
        folder_path = folder_by_key.get((hosp, sigla))
        if folder_path is None or not folder_path.exists():
            raise HTTPException(404, f"Folder missing for {hosp}/{sigla}")
        cells_with_paths.append((hosp, sigla, folder_path))

    # Incr. 1A fusionar-y-saltar: por celda, los archivos ya confiables que el OCR
    # de celda NO re-escanea — los que tienen un método OCR previo (≠ filename_glob)
    # o un override por-archivo. Los A7/filename_glob se re-escanean (son baratos:
    # solo cuentan páginas), así que NO entran al skip.
    cells_state = state.get("cells", {})
    skip_by_cell: dict[tuple[str, str], set[str]] = {}
    for hosp, sigla, _folder in cells_with_paths:
        cell = (cells_state.get(hosp, {}) or {}).get(sigla) or {}
        sk = _skip_files(cell)
        if sk:
            skip_by_cell[(hosp, sigla)] = sk

    # Pre-count PDFs across the selected cells so the client can size the progress
    # bar immediately (audit #1), EXCLUDING the skipped files so the scan's per-PDF
    # `done` converges exactly on total_pdfs (the orchestrator counts the same way).
    total_pdfs = sum(
        sum(1 for p in enumerate_cell_pdfs(f) if p.name not in skip_by_cell.get((h, s), set()))
        for (h, s, f) in cells_with_paths
    )

    # Atomic check-then-set: setdefault returns the value already in the dict if
    # it existed, otherwise installs and returns the new one.
    handle = make_handle(session_id=session_id, total=len(cells_with_paths))
    if app.state.batches.setdefault(session_id, handle) is not handle:
        raise HTTPException(409, "another batch is already running for this session")
    loop = app.state.loop

    # M3b: per-scan context for the agent lock-skip policy (mutated by
    # _handle_scan_progress; lives in the route scope so on_progress closes over it).
    ctx: dict = {
        "skipped_set": set(),
        "skipped_cells": [],
        "agent_active": False,
        "current_cell_skipped": False,
    }

    def _safe_broadcast(event: dict) -> None:
        # El scan corre en un hilo de fondo; si el event loop ya se cerró (apagado
        # del server, o teardown del TestClient antes de que termine el batch), dejar
        # caer el evento en vez de crashear el hilo de drain. is_closed() + except
        # cubren el TOCTOU (el loop podría cerrarse entre el chequeo y el schedule).
        try:
            if not loop.is_closed():
                asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
        except RuntimeError:
            pass

    def on_progress(event: dict) -> None:
        # M3b: delegate to the module-level handler which applies the agent
        # lock-skip policy and then falls through to the normal apply+broadcast
        # path for non-skipped events. ctx is in the enclosing scope.
        _handle_scan_progress(mgr, session_id, event, ctx, _safe_broadcast)

    cancel_token = CancellationToken.from_event(handle.cancel_event)

    def _run():
        try:
            scan_cells_ocr(
                cells_with_paths,
                on_progress=on_progress,
                cancel=cancel_token,
                max_workers=2,
                skip_by_cell=skip_by_cell,
            )
        except Exception:
            logger.exception("scan_cells_ocr crashed for session %s", session_id)
            # M3b: release the agent on crash so it doesn't haunt the roster.
            if ctx["agent_active"]:
                mgr.agent_leave(session_id)
                ctx["agent_active"] = False
                try:
                    asyncio.run_coroutine_threadsafe(
                        broadcast(
                            session_id,
                            {
                                "type": "presence",
                                "session_id": session_id,
                                "participants": mgr.presence_snapshot(session_id),
                            },
                        ),
                        loop,
                    )
                except RuntimeError:
                    pass
            try:
                asyncio.run_coroutine_threadsafe(
                    broadcast(
                        session_id,
                        {
                            "type": "scan_complete",
                            "scanned": 0,
                            "errors": len(cells_with_paths),
                            "cancelled": 0,
                        },
                    ),
                    loop,
                )
            except Exception:
                logger.exception("failed to broadcast scan_complete after crash")
        finally:
            app.state.batches.pop(session_id, None)

    handle.future = _DISPATCH_POOL.submit(_run)
    return {"accepted": True, "total": len(cells_with_paths), "total_pdfs": total_pdfs}


@router.post("/sessions/{session_id}/cancel")
def cancel(request: Request, session_id: str) -> dict:
    """Always returns 200. If a batch is active, sets its cancel event."""
    handle = request.app.state.batches.get(session_id)
    if handle is not None and handle.cancel_event is not None:
        handle.cancel_event.set()
    return {"ok": True}


from core.orchestrator import _find_category_folder  # noqa: E402


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/files/{filename}/scan-ocr")
def scan_file_ocr(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Pase 2 for a single file (rev-2 #1): OCR-scan one PDF of a cell and merge.

    Resolves the cell folder like ``get_cell_files``, validates the file exists,
    then runs ``scan_one_file_ocr`` on the dispatch pool — broadcasting ``file_*``
    events over the session WS and merging the result on ``file_scan_done``.
    """
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    folder = _find_category_folder(Path(state.get("month_root", "")) / hospital, sigla)
    if not folder.exists() or filename not in {p.name for p in folder.rglob("*.pdf")}:
        raise HTTPException(404, f"File not found in cell: {filename}")

    app = request.app
    loop = app.state.loop

    def _safe_bc(event: dict) -> None:
        # on_progress corre en el hilo del pool; marshalea al loop del app y
        # descarta el evento si ya se cerró (teardown del TestClient) en vez de
        # reventar el hilo. Espejo de scan_ocr._safe_broadcast.
        try:
            if not loop.is_closed():
                asyncio.run_coroutine_threadsafe(broadcast(session_id, event), loop)
        except RuntimeError:
            pass

    def on_progress(event: dict) -> None:
        _safe_bc(event)
        if event.get("type") == "file_scan_done":
            r = event["result"]
            mgr.apply_per_file_ocr_result(
                session_id,
                hospital,
                sigla,
                filename,
                count=r["ocr_count"],
                method=r["method"],
                near_matches=r.get("near_matches") or [],
            )
            # M1: tras fusionar el per_file, difunde la celda completa para los demás clientes.
            cu = _cell_updated_event(mgr, session_id, hospital, sigla)
            if cu is not None:
                _safe_bc(cu)

    cancel_token = CancellationToken()

    def _run() -> None:
        try:
            scan_one_file_ocr(
                hospital,
                sigla,
                folder,
                filename,
                on_progress=on_progress,
                cancel=cancel_token,
            )
        except Exception:
            logger.exception("scan_one_file_ocr crashed for %s/%s/%s", hospital, sigla, filename)

    _DISPATCH_POOL.submit(_run)
    return {"accepted": True, "filename": filename}


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/override")
def patch_override(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: dict = Body(...),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    _validate_session_id(session_id)
    value = body.get("value")
    manual = bool(body.get("manual", False))
    participant_id: str | None = body.get("participant_id")
    if value is not None:
        if not isinstance(value, int) or isinstance(value, bool):
            raise HTTPException(400, "value must be int or null")
        if value < 0 or value > _MAX_REASONABLE_COUNT:
            raise HTTPException(400, f"value must be in [0, {_MAX_REASONABLE_COUNT}]")
        if _is_capped_sigla(sigla):
            try:
                state = mgr.get_session_state(session_id)
            except KeyError as exc:
                raise HTTPException(404, str(exc)) from exc
            total_pages = _cell_total_pages(state, hospital, sigla)
            # total_pages == 0 means pages are unknowable (missing folder / all PDFs
            # unreadable) → don't block; 0 is "unknown", not "max is 0".
            if total_pages > 0 and value > total_pages:
                raise HTTPException(
                    422,
                    {"error": "count_exceeds_pages", "max": total_pages},
                )
    try:
        mgr.apply_user_override(
            session_id, hospital, sigla, value=value, manual=manual, participant_id=participant_id
        )
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "user_override": cell.get("user_override"),
    }


class PerFileOverrideRequest(BaseModel):
    count: int
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/files/{filename:path}/override")
def patch_per_file_override(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    body: PerFileOverrideRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Persist per-file count override. Spec §5.2 + §7.2."""
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    month_root = Path(state.get("month_root", ""))
    try:
        folder = _find_category_folder(month_root / hospital, sigla)
    except KeyError as exc:
        # Unknown sigla → CATEGORY_FOLDERS miss. The cell can't exist → 404
        # (not a 500). Pre-existing gap: folder was resolved before the cell was
        # validated by apply_per_file_override below.
        raise HTTPException(status_code=404, detail=f"Unknown sigla: {sigla}") from exc
    if _is_capped_sigla(sigla) and folder.exists():
        file_pages = cell_page_counts(folder).get(filename, 0)
        if file_pages > 0 and body.count > file_pages:
            raise HTTPException(
                422,
                {"error": "count_exceeds_pages", "max": file_pages},
            )
    try:
        mgr.apply_per_file_override(
            session_id, hospital, sigla, filename, body.count, body.participant_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if folder.exists():  # best-effort metadata; skip (don't 500) if folder is gone
        refresh_all_reliable(
            mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla)
        )
    state, _ = mgr._load_and_migrate(session_id)
    cell = state["cells"][hospital][sigla]
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "filename": filename,
        "count": body.count,
        "new_cell_count": compute_cell_count(cell, count_type_for(sigla)),
    }


class ClearNearMatchBody(BaseModel):
    """Body for the near-matches clear route. Omit both fields = clear all."""

    pdf_name: str | None = None
    page_index: int | None = None
    participant_id: str | None = None


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/near-matches/clear")
def clear_near_matches(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: ClearNearMatchBody | None = Body(None),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Clear near-match suspects for a cell — all, or one entry (E5)."""
    _validate_session_id(session_id)
    participant_id = body.participant_id if body else None
    mgr.clear_near_matches(
        session_id,
        hospital,
        sigla,
        pdf_name=body.pdf_name if body else None,
        page_index=body.page_index if body else None,
        participant_id=participant_id,
    )
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {"ok": True}


class WorkerCountPatch(BaseModel):
    """Body del PATCH worker-count. Patch parcial: los campos None no se tocan."""

    marks: dict | None = None
    status: Literal["en_progreso", "terminado"] | None = None
    cursor: dict | None = None
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/worker-count")
def patch_worker_count(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: WorkerCountPatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Autosalva el conteo de trabajadores de una celda (patch parcial)."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=422, detail="session_id inválido")
    try:
        mgr.apply_worker_count(
            session_id,
            hospital,
            sigla,
            marks=body.marks,
            status=body.status,
            cursor=body.cursor,
            participant_id=body.participant_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Sesión {session_id} no encontrada") from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    month_root = Path(state.get("month_root", ""))
    folder = _find_category_folder(month_root / hospital, sigla)
    present = set(cell_page_counts(folder)) if folder.exists() else None
    # checks cells (maquinaria) light green on worker_status=='terminado'; for
    # documents_workers this recomputes document settledness (no-op-ish). Closes
    # the gap that the worker PATCH didn't refresh all_reliable.
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla))
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "worker_marks": cell.get("worker_marks"),
        "worker_status": cell.get("worker_status"),
        "worker_cursor": cell.get("worker_cursor"),
        "worker_count": compute_worker_count(cell, present),
    }


class NotePatch(BaseModel):
    """Body del PATCH note. text vacío/None borra la nota.

    ``status`` no es nullable y nace en ``"por_resolver"`` (D4): una nota creada
    sin estado explícito queda pendiente (fuerza el punto ámbar), preservando el
    invariante nota⟺estado.
    """

    text: str | None = None
    status: Literal["por_resolver", "resuelto"] = "por_resolver"
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/note")
def patch_note(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: NotePatch,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Set or clear a cell's note; refresh all_reliable (por_resolver → amber)."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=422, detail="session_id inválido")
    try:
        mgr.set_note(
            session_id,
            hospital,
            sigla,
            text=body.text,
            status=body.status,
            participant_id=body.participant_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Sesión {session_id} no encontrada") from exc
    state = mgr.get_session_state(session_id)
    month_root = Path(state.get("month_root", ""))
    # _find_category_folder raises KeyError for an unknown sigla → 404 (distinct
    # from the unknown-session 404 above), not an unhandled 500.
    try:
        folder = _find_category_folder(month_root / hospital, sigla)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Categoría {sigla} desconocida") from exc
    refresh_all_reliable(mgr, session_id, hospital, sigla, folder, count_type=count_type_for(sigla))
    cell = mgr.get_session_state(session_id)["cells"].get(hospital, {}).get(sigla, {})
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {
        "note": cell.get("note"),
        "note_status": cell.get("note_status"),
        "all_reliable": cell.get("all_reliable"),
    }


class ConfirmRequest(BaseModel):
    confirmed: bool
    participant_id: str | None = None


@router.patch("/sessions/{session_id}/cells/{hospital}/{sigla}/confirm")
def patch_confirm(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    body: ConfirmRequest,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Marca/desmarca una celda como 'lista' a mano (flag confirmed).

    El flag se preserva entre escaneos (apply_filename_result / apply_ocr_result
    lo re-afirman con setdefault), así que confirmar una celda sobrevive a un
    re-escaneo de pase 1 u OCR.
    """
    _validate_session_id(session_id)
    try:
        mgr.apply_confirmed(
            session_id,
            hospital,
            sigla,
            confirmed=body.confirmed,
            participant_id=body.participant_id,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    state = mgr.get_session_state(session_id)
    cell = state["cells"].get(hospital, {}).get(sigla, {})
    _broadcast_cell_updated(request, mgr, session_id, hospital, sigla)
    if is_agent(body.participant_id):
        _broadcast_presence(request, mgr, session_id)
    return {"confirmed": cell.get("confirmed", False)}


@router.get("/sessions/{session_id}/cells/{hospital}/{sigla}/files")
def get_cell_files(
    session_id: str,
    hospital: str,
    sigla: str,
    mgr: SessionManager = Depends(get_manager),
) -> list[dict]:
    _validate_session_id(session_id)
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


# ── Reorg endpoints (Incr J T9–T11) ──────────────────────────────────────

from api.reorg import build_manifest, resolve_op_defaults, validate_op  # noqa: E402


class ReorgSource(BaseModel):
    hospital: str
    sigla: str
    file: str
    page_range: list[int] | None = None


class ReorgDest(BaseModel):
    hospital: str
    sigla: str


class ReorgOpCreate(BaseModel):
    op_type: str
    source: ReorgSource
    dest: ReorgDest
    empresa: str | None = None
    preserve_date: bool = True
    rotation_deg: int = 0
    doc_count: int | None = None
    worker_count: int | None = None
    note: str | None = None


@router.post("/sessions/{session_id}/reorg/ops")
def create_reorg_op(
    request: Request,
    session_id: str,
    body: ReorgOpCreate,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Create a reorg op; recompute deltas; return the op + affected cells."""
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    op = body.model_dump()
    src = op["source"]
    month_root = Path(state.get("month_root", ""))
    try:
        src_folder = _find_category_folder(month_root / src["hospital"], src["sigla"])
        _find_category_folder(month_root / op["dest"]["hospital"], op["dest"]["sigla"])
    except KeyError as exc:
        raise HTTPException(404, f"Unknown sigla: {exc}") from exc
    src_cell = (state.get("cells", {}).get(src["hospital"], {}) or {}).get(src["sigla"])
    if src_cell is None:
        raise HTTPException(404, f"Cell not found: {src['hospital']}/{src['sigla']}")

    src_pages = cell_page_counts(src_folder) if src_folder.exists() else {}
    errors = validate_op(op, src_pages=src_pages, existing_ops=state.get("reorg_ops", []))
    if errors:
        raise HTTPException(400, "; ".join(errors))

    op = resolve_op_defaults(op, src_cell=src_cell)
    created = mgr.add_reorg_op(session_id, op)
    refresh_reorg_deltas(mgr, session_id, check_applied=False)
    _broadcast_session_refresh(request, session_id)
    state = mgr.get_session_state(session_id)
    return {"op": created, "cells": state["cells"]}


@router.delete("/sessions/{session_id}/reorg/ops/{op_id}")
def delete_reorg_op(
    request: Request,
    session_id: str,
    op_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Delete a reorg op; recompute deltas."""
    _validate_session_id(session_id)
    try:
        mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not mgr.delete_reorg_op(session_id, op_id):
        raise HTTPException(404, f"Op not found: {op_id}")
    refresh_reorg_deltas(mgr, session_id, check_applied=False)
    _broadcast_session_refresh(request, session_id)
    state = mgr.get_session_state(session_id)
    return {"deleted": op_id, "cells": state["cells"]}


@router.post("/sessions/{session_id}/reorg/export")
def export_reorg_manifest(
    session_id: str,
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Write the reorg manifest (pending ops) to OVERSEER_OUTPUT_DIR."""
    _validate_session_id(session_id)
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    manifest = build_manifest(state, month=session_id)
    if not manifest["operations"]:
        raise HTTPException(400, "No hay operaciones pendientes para exportar")
    from api.routes.output import _output_dir  # noqa: E402

    out_dir = _output_dir()
    # Data-safety: the corpus (INFORME_MENSUAL_ROOT) is read-only. Never write the
    # manifest there, even if OVERSEER_OUTPUT_DIR is ever misconfigured to point inside it.
    if out_dir.resolve().is_relative_to(_informe_root().resolve()):
        raise HTTPException(
            500, "OVERSEER_OUTPUT_DIR no puede estar dentro de INFORME_MENSUAL_ROOT"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"reorganizacion_{session_id}.json"
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(dest)
    return {"path": str(dest), "operation_count": len(manifest["operations"])}
