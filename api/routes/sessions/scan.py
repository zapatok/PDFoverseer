"""Scan orchestration routes: pase-1 filename scan, pase-2 OCR batch, single-file
OCR, cancel, and apply-ratio (RN) — plus the scan-progress event handling and the
M3b agent lock-skip policy.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.batch import make_handle
from api.presence import AGENT_PARTICIPANT_ID, CellLockedError, is_agent
from api.routes.ws import _emit, broadcast
from api.state import SessionManager
from core.orchestrator import (
    _find_category_folder,
    enumerate_month,
    scan_cells_ocr,
    scan_month,
    scan_one_file_ocr,
)
from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken
from core.scanners.patterns import count_type_for
from core.scanners.utils.cell_enumeration import enumerate_cell_pdfs

from ._common import (
    _DISPATCH_POOL,
    _broadcast_cell_updated,
    _broadcast_presence,
    _broadcast_session_refresh,
    _cell_updated_event,
    _validate_cell_coords,
    _validate_session_id,
    cell_page_counts,
    file_origin,
    get_manager,
    logger,
    refresh_all_reliable,
    refresh_reorg_deltas,
)

router = APIRouter()


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
    _validate_cell_coords(hospital, sigla)
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
        # Copy before enriching — never mutate the orchestrator's event dict in place.
        # It originates on the drain thread; in-place edits would alias shared state if
        # the event were ever fanned to a second consumer. Mirrors the scan_complete copy.
        event = {
            **event,
            "result": {
                **event["result"],
                "per_file": cell.get("per_file"),
                "ocr_count": cell.get("ocr_count"),
                "near_matches": cell.get("near_matches") or [],
            },
        }
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
        ctx["current_cell_skipped"] = False  # reset first; the skip path below overwrites to True
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
                            # `skipped` intentionally absent on the crash path (the normal
                            # path enriches it via _handle_scan_progress); frontend uses
                            # `event.skipped ?? []`.
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


class ScanFileOcrRequest(BaseModel):
    participant_id: str | None = None


@router.post("/sessions/{session_id}/cells/{hospital}/{sigla}/files/{filename}/scan-ocr")
def scan_file_ocr(
    request: Request,
    session_id: str,
    hospital: str,
    sigla: str,
    filename: str,
    body: ScanFileOcrRequest | None = Body(None),
    mgr: SessionManager = Depends(get_manager),
) -> dict:
    """Pase 2 for a single file (rev-2 #1): OCR-scan one PDF of a cell and merge.

    Resolves the cell folder like ``get_cell_files``, validates the file exists,
    then runs ``scan_one_file_ocr`` on the dispatch pool — broadcasting ``file_*``
    events over the session WS and merging the result on ``file_scan_done``.

    U6: registers the same ``app.state.batches[session_id]`` slot a multi-cell
    batch uses (``total=1``) — a single-file scan and a batch scan for the same
    session mutually exclude each other (409 "another batch is already
    running"), and the existing ``POST /cancel`` endpoint cancels this scan too.
    The handle is popped once the scan ends (success, error, or cancelled), so a
    later scan (single-file or batch) is free to start.
    """
    _validate_session_id(session_id)
    _validate_cell_coords(hospital, sigla)
    participant_id = body.participant_id if body else None
    try:
        state = mgr.get_session_state(session_id)
    except KeyError as exc:
        raise HTTPException(404, f"Session not found: {session_id}") from exc
    folder = _find_category_folder(Path(state.get("month_root", "")) / hospital, sigla)
    if not folder.exists() or filename not in {p.name for p in folder.rglob("*.pdf")}:
        raise HTTPException(404, f"File not found in cell: {filename}")
    # B1: gate starting the scan on the M3 per-cell lock (apply_ratio's human gate;
    # editorship-exclusivity holds — the operator focus-claimed the cell by opening the
    # viewer). check_cell_lock raises CellLockedError → 409 via the main.py handler.
    mgr.check_cell_lock(session_id, hospital, sigla, participant_id)

    app = request.app
    # U6: same atomic check-then-set dedup as scan_ocr — mutually excludes a
    # concurrent batch (or another single-file scan) on this session.
    handle = make_handle(session_id=session_id, total=1)
    if app.state.batches.setdefault(session_id, handle) is not handle:
        raise HTTPException(409, "another batch is already running for this session")
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
        if event.get("type") == "file_scan_done":
            # F12: re-check the M3 lock at merge time. The entry gate (above) ran
            # before the scan started; a lease can expire (45s) or another
            # participant can claim the cell while OCR is in flight — a stale
            # merge would clobber their edit. This check + the merge below are
            # NOT atomic (accepted check→write TOCTOU, mirrors apply_ratio's
            # check_cell_lock model — see its docstring), but it closes the much
            # larger entry-only gap.
            try:
                mgr.check_cell_lock(session_id, hospital, sigla, participant_id)
            except CellLockedError as exc:
                _safe_bc(
                    {
                        "type": "file_scan_error",
                        "hospital": hospital,
                        "sigla": sigla,
                        "filename": filename,
                        "error": "cell_locked",
                        "lock_holder": exc.holder,
                    }
                )
                return
            _safe_bc(event)
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
            return
        _safe_bc(event)

    cancel_token = CancellationToken.from_event(handle.cancel_event)

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
        finally:
            app.state.batches.pop(session_id, None)

    handle.future = _DISPATCH_POOL.submit(_run)
    return {"accepted": True, "filename": filename}
