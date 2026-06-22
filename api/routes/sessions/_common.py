"""Shared kernel for the sessions route package.

Constants, the DI placeholder (``get_manager``), session-id validation, month
resolution, the pure count-derivation helpers (``file_origin`` / ``compute_settled``
/ ``cell_page_counts``), the reliability/reorg-delta refreshers, and the M1
broadcast helpers. Every sessions sub-router imports from here; this module imports
nothing from the sub-routers (acyclic).
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
from fastapi import HTTPException, Request

from api.routes.ws import _emit
from api.state import SessionManager
from core.orchestrator import _find_category_folder
from core.scanners.patterns import count_type_for

logger = logging.getLogger(__name__)

# Single thread pool per process — Daniel's machine has one user, and
# scan_cells_ocr already uses a ProcessPoolExecutor internally for parallelism.
# One shared instance: the scan + single-file OCR routes submit onto it.
_DISPATCH_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-batch")

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

_MAX_REASONABLE_COUNT = 10_000

_OCR_METHODS = ("header_detect", "corner_count", "header_band_anchors", "v4", "pagination")


def _validate_session_id(session_id: str) -> None:
    """Raise 400 if session_id is not a valid YYYY-MM (format check, before any
    DB lookup). Shared by the session and presence routers."""
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(400, f"Invalid session_id: {session_id}")


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


# ── M1 broadcast helpers (shared by scan / writes / reorg routes) ─────────────


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
