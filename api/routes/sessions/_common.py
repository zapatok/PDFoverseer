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
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fitz
from fastapi import HTTPException, Request

from api.routes.ws import _emit
from api.state import SessionManager, compute_cell_count, compute_worker_count
from core.domain import CATEGORY_FOLDERS, HOSPITALS, SIGLAS, folder_to_sigla
from core.orchestrator import _find_category_folder
from core.scanners.patterns import count_type_for
from core.scanners.utils.colado_guard import open_suspects

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


def _validate_cell_coords(hospital: str, sigla: str) -> None:
    """Raise 400 if ``(hospital, sigla)`` is not a canonical cell coordinate (F13).

    The only valid cells are ``HOSPITALS × SIGLAS`` (``core.domain``). Rejecting
    unknown coordinates at the route boundary stops a typo'd/stale sigla from
    minting a phantom cell in session state — the exact hole that left a
    ``no_existe`` cell in the production DB, which then leaked into history/Excel.
    """
    if hospital not in HOSPITALS or sigla not in SIGLAS:
        raise HTTPException(400, f"Unknown hospital/sigla: {hospital}/{sigla}")


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


# Page counts keyed by absolute path, invalidated by (st_mtime_ns, st_size).
# The corpus is read-only during a counting session (paso-1 rewrites files
# between months → the stat signature changes → that file re-reads), so this
# turns the per-request "open every PDF" cost of the files endpoint — ~0.75 s
# measured on HPV|art's 1,300 files, paid again on EVERY save via filesTick —
# into a stat() sweep (~tens of ms). Failed reads (0) are NOT cached: they
# retry on the next request.
_PAGE_COUNT_CACHE: dict[str, tuple[int, int, int]] = {}
_PAGE_COUNT_CACHE_LOCK = threading.Lock()


def cell_page_counts(folder: Path) -> dict[str, int]:
    """Lazy per-file page counts for a cell's folder: {pdf.name: page_count}.
    0 when a PDF can't be opened. Reads from disk through a stat-invalidated
    module cache; the Incr-J persistence (per_file_pages) would slot in here
    without touching callers.
    """
    if not folder.exists():
        return {}  # missing folder → no pages (callers treat as unknowable, never throw)
    out: dict[str, int] = {}
    for pdf in sorted(folder.rglob("*.pdf")):
        try:
            st = pdf.stat()
            key = str(pdf)
            with _PAGE_COUNT_CACHE_LOCK:
                hit = _PAGE_COUNT_CACHE.get(key)
            if hit is not None and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
                out[pdf.name] = hit[2]
                continue
            with fitz.open(pdf) as doc:
                pages = doc.page_count
            with _PAGE_COUNT_CACHE_LOCK:
                _PAGE_COUNT_CACHE[key] = (st.st_mtime_ns, st.st_size, pages)
            out[pdf.name] = pages
        except Exception:  # noqa: BLE001 — any fitz/IO failure → unreadable (0)
            out[pdf.name] = 0
    return out


def present_file_names(folder: Path) -> set[str]:
    """Names of the PDFs currently in a cell folder (no opens — cheap).

    The canonical present-file set for worker/checks mark filtering (F1). Unlike
    ``cell_page_counts`` this never opens a PDF, so it is safe to call on every
    cell payload.
    """
    if not folder.exists():
        return set()
    return {p.name for p in folder.rglob("*.pdf")}


def enrich_cell_worker_count(
    cell: dict, month_root: Path, hospital: str, sigla: str, folder: Path | None = None
) -> dict:
    """Return a copy of ``cell`` with the canonical present-filtered worker_count
    (worker/checks siglas), plus ``checks_count`` — the canonical effective CELL
    count — for checks siglas (M4).

    The frontend must never derive these totals (bug #2, F1): one producer, one
    filter. Document siglas are returned untouched.
    Unknown/phantom siglas (e.g. a stale ``no_existe``) default to ``"documents"``
    via ``count_type_for`` and are therefore skipped without crashing.

    A MISSING folder falls back to the legacy ``None`` filter (by ``per_file``
    keys) — the exact conditional ``patch_worker_count`` and the Excel worker
    builders use, so every producer agrees on that edge. An EMPTY-but-EXISTING
    folder still filters with an empty set (correct present-filtering: no files
    on disk → no countable marks, only the reorg delta remains).

    Args:
        cell: the persisted state dict of one cell.
        month_root: the session's month root directory.
        hospital: hospital code.
        sigla: category code.
        folder: pre-resolved category folder — pass it when the caller already
            resolved it (e.g. the batched GET-session path); ``None`` resolves
            via ``_find_category_folder``.
    """
    ct = count_type_for(sigla)
    if ct not in ("documents_workers", "checks"):
        return cell
    if folder is None:
        folder = _find_category_folder(month_root / hospital, sigla)
    present = present_file_names(folder) if folder.exists() else None
    enriched = {**cell, "worker_count": compute_worker_count(cell, present)}
    if ct == "checks":
        # M4: the checks CELL NUMBER (grid/panel total) must match Excel/history,
        # which derive it present-filtered on the backend. The JS mirror cannot
        # know present files, so ship the canonical effective count with the
        # payload (frontend computeCellCount prefers it for checks cells).
        enriched["checks_count"] = compute_cell_count(cell, "checks", present)
    return enriched


def enrich_cell_colado_suspects(
    cell: dict, reorg_ops: list[dict], hospital: str, sigla: str
) -> dict:
    """Return a copy of ``cell`` whose ``colado_suspects`` is the OPEN list.

    The §5 dedupe is DERIVED, not persisted: every serialization of a cell to a
    client goes through here so the panel never shows a suspect an existing
    pending reorg op already covers — and deleting that op un-suppresses the
    suspect with no extra bookkeeping. A no-op for cells without suspects.

    Args:
        cell: the persisted (worker-enriched) cell dict.
        reorg_ops: the session's reorg ops (``state["reorg_ops"]``).
        hospital: the cell's hospital.
        sigla: the cell's sigla.
    """
    raw = cell.get("colado_suspects") or []
    if not raw:
        return cell
    return {**cell, "colado_suspects": open_suspects(raw, reorg_ops, hospital, sigla)}


def hospital_category_folders(hosp_dir: Path, siglas: list[str]) -> dict[str, Path]:
    """Resolve several siglas' category folders under ONE hospital with a single
    directory listing (the GET-session hot path — one ``iterdir`` instead of one
    per sigla).

    Resolution rule per sigla is identical to ``_find_category_folder``: the
    canonical ``CATEGORY_FOLDERS`` name if it exists on disk, else the first
    subdirectory whose name maps back to the sigla (renumber-tolerant via
    ``folder_to_sigla``), else the nominal canonical path (absent). Request-scoped
    only — no caching across requests.

    Args:
        hosp_dir: the hospital directory (``month_root / hospital``).
        siglas: the sigla codes to resolve (must exist in ``CATEGORY_FOLDERS``).

    Returns:
        ``{sigla: folder_path}`` for every requested sigla.
    """
    mapped: dict[str, Path] = {}
    if hosp_dir.exists():
        for sub in hosp_dir.iterdir():
            if sub.is_dir():
                s = folder_to_sigla(sub.name)
                if s is not None and s not in mapped:
                    mapped[s] = sub
    out: dict[str, Path] = {}
    for sigla in siglas:
        direct = hosp_dir / CATEGORY_FOLDERS[sigla]
        out[sigla] = direct if direct.exists() else mapped.get(sigla, direct)
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

    This is the single chokepoint every interactive write (override/per-file/
    worker/note) and both OCR completions funnel through. Thin delegation to
    the atomic ``SessionManager.recompute_all_reliable`` (§B4): that does ONE
    load→compute→persist under the single RLock (the anti-colados §4.5 gate —
    an open COUNTED suspect blocks green — lives inside it), so a concurrent
    write can't interleave with a stale compute. This wrapper's public
    signature is unchanged for its callers.
    """
    mgr.recompute_all_reliable(
        session_id, hospital, sigla, folder, pages=pages, count_type=count_type
    )


def refresh_reorg_deltas(
    mgr: SessionManager,
    session_id: str,
    *,
    check_applied: bool = False,
) -> None:
    """Recompute every cell's reorg delta from ``state["reorg_ops"]`` (session-wide).

    Thin delegation to the atomic ``SessionManager.recompute_reorg_deltas`` (F4):
    that does ONE load → mutate → ONE write under the single RLock, so a concurrent
    ``add_reorg_op``/``delete`` can't be lost to a get-then-set race. (This wrapper
    used to do the get-then-set itself — hence the race.) The pase-1 ``scan`` route
    call site passes ``check_applied=True`` to retire ops whose source file moved.

    Args:
        mgr: The active SessionManager.
        session_id: Target session identifier.
        check_applied: When True, mark each pending op ``applied`` if its source
            file is gone from disk.
    """
    mgr.recompute_reorg_deltas(session_id, check_applied=check_applied)


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
        state = mgr.get_session_state(session_id)
        cell = state["cells"][hospital][sigla]
    except KeyError:
        return None
    # F1: carry the canonical present-filtered worker_count so remote clients never
    # re-derive it (worker/checks siglas only; enrich is a no-op for document cells).
    month_root = Path(state.get("month_root", ""))
    cell = enrich_cell_worker_count(cell, month_root, hospital, sigla)
    # Anti-colados: broadcast the OPEN suspect list (op-suppressed ones hidden).
    cell = enrich_cell_colado_suspects(cell, state.get("reorg_ops") or [], hospital, sigla)
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
