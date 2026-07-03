"""Pase-2 OCR scan orchestration: single-file re-scan + multi-cell batch."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from core.orchestrator.ocr_worker import (
    _cell_done_meta,
    _eta_ms,
    _init_ocr_worker,
    _ocr_worker,
    _serialize_near_matches,
)

if TYPE_CHECKING:
    from core.scanners.base import ScanResult
    from core.scanners.cancellation import CancellationToken

logger = logging.getLogger(__name__)


def scan_one_file_ocr(
    hospital: str,
    sigla: str,
    folder: Path,
    filename: str,
    *,
    on_progress: Callable[[dict], None],
    cancel: CancellationToken,
) -> None:
    """OCR-scan a single PDF of a cell with its sigla's engine (rev-2 #1).

    Runs in-process (the route submits it to the executor). Emits
    ``file_scan_started`` → ``file_page_progress`` (per page, anchors siglas) →
    ``file_scan_done`` (or ``file_scan_error``). The terminal event carries the
    single file's ``per_file``/``method`` so the route can merge it into the cell
    without touching the other files.

    Args:
        hospital: hospital key.
        sigla: category key (must have an OCR strategy).
        folder: the cell's category folder.
        filename: the PDF name to scan (must live in ``folder``).
        on_progress: sink for the ``file_*`` events.
        cancel: cooperative cancellation token.
    """
    from core import scanners as scanner_registry
    from core.scanners.utils.pdf_render import get_page_count

    scanner = scanner_registry.get(sigla)
    try:
        pages_total = get_page_count(folder / filename)
    except Exception:  # noqa: BLE001 — a broken header still reports a started/done pair
        pages_total = 0

    on_progress(
        {
            "type": "file_scan_started",
            "hospital": hospital,
            "sigla": sigla,
            "filename": filename,
            "pages_total": pages_total,
        }
    )

    def _on_page(page_idx: int, total: int) -> None:
        on_progress(
            {
                "type": "file_page_progress",
                "hospital": hospital,
                "sigla": sigla,
                "filename": filename,
                "page": page_idx + 1,
                "pages_total": total,
            }
        )

    try:
        result = scanner.count_ocr(folder, cancel=cancel, only=filename, on_page=_on_page)
    except Exception as exc:  # noqa: BLE001 — surface any scan failure to the UI
        on_progress(
            {
                "type": "file_scan_error",
                "hospital": hospital,
                "sigla": sigla,
                "filename": filename,
                "error": str(exc),
            }
        )
        return

    on_progress(
        {
            "type": "file_scan_done",
            "hospital": hospital,
            "sigla": sigla,
            "filename": filename,
            "result": {
                "ocr_count": result.count,
                "method": result.method,
                "per_file": result.per_file,
                "near_matches": _serialize_near_matches(result),
            },
        }
    )


def scan_cells_ocr(
    cells: list[tuple[str, str, Path]],
    *,
    on_progress: Callable[[dict], None],
    cancel: CancellationToken,
    max_workers: int = 2,
    skip_by_cell: dict[tuple[str, str], set[str]] | None = None,
) -> dict[tuple[str, str], ScanResult]:
    """Pase 2 — OCR scan a subset of cells with progress events.

    Args:
        cells: ``[(hospital, sigla, folder_path), ...]`` to scan.
        on_progress: Invoked on the orchestrator thread with event dicts.
            Events: ``cell_scanning`` (before each cell), ``cell_done`` /
            ``cell_error`` (after each cell), ``scan_progress`` (after each
            cell), and the terminal ``scan_complete`` or ``scan_cancelled``.
        cancel: Pre-flight short-circuits with ``scan_cancelled(scanned=0)``.
        max_workers: ProcessPoolExecutor size. Default 2 (OCR is CPU+RAM
            heavy). Tests pass ``max_workers=1`` to run synchronously without
            spawning subprocesses.

    Returns:
        Dict of successful ``(hospital, sigla) → ScanResult``. Cells that
        errored or were cancelled are absent from the dict — their state is
        reported only via events.
    """
    import concurrent.futures as futures  # noqa: E402
    import multiprocessing as mp  # noqa: E402
    import queue as _queue  # noqa: E402
    import threading  # noqa: E402
    from concurrent.futures import (  # noqa: E402
        ProcessPoolExecutor,
        as_completed,
    )

    from core.scanners.cancellation import CancellationToken  # noqa: E402, F401
    from core.scanners.utils.cell_enumeration import (  # noqa: E402
        enumerate_cell_pdfs,
    )

    skip_by_cell = skip_by_cell or {}
    results: dict[tuple[str, str], ScanResult] = {}
    total = len(cells)
    # 4-tupla: el skip por celda viaja al worker (subproceso) como lista picklable.
    cell_tuples = [(h, s, str(f), sorted(skip_by_cell.get((h, s), set()))) for (h, s, f) in cells]

    if cancel.cancelled:
        on_progress({"type": "scan_cancelled", "scanned": 0, "total": total})
        return results

    # Pre-count PDFs across the selected cells so the bar has a real denominator.
    # Excluye los archivos saltados (skip) — `done` (un tick por PDF procesado)
    # converge exactamente en `total_pdfs`.
    total_pdfs = sum(
        sum(1 for p in enumerate_cell_pdfs(f) if p.name not in skip_by_cell.get((h, s), set()))
        for (h, s, f) in cells
    )
    on_progress({"type": "scan_started", "total_cells": total, "total_pdfs": total_pdfs})
    t0 = time.perf_counter()
    pdfs_done = 0

    if max_workers == 1:
        scanned = 0
        errors = 0
        cur_cell: dict[str, str] = {}  # (h, s) en curso, para anotar cada file_result

        def _emit_pdf(name: str, count: int | None, method: str, nm: list[dict]) -> None:
            # Incr. 1A: un tick de progreso por PDF + el file_result que la ruta
            # fusiona incrementalmente (merge por-archivo + escritura por PDF). En
            # síncrono corre inline dentro de _ocr_worker, antes del cell_done.
            nonlocal pdfs_done
            pdfs_done += 1
            on_progress(
                {
                    "type": "pdf_progress",
                    "done": min(pdfs_done, total_pdfs),
                    "total": total_pdfs,
                    "pdf_name": name,
                    "eta_ms": _eta_ms(t0, pdfs_done, total_pdfs),
                }
            )
            on_progress(
                {
                    "type": "file_result",
                    "hospital": cur_cell["h"],
                    "sigla": cur_cell["s"],
                    "filename": name,
                    "count": count,
                    "method": method,
                    "near_matches": nm,
                }
            )

        for ct in cell_tuples:
            if cancel.cancelled:
                on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
                return results
            hosp, sigla, _, _ = ct
            cur_cell["h"], cur_cell["s"] = hosp, sigla
            on_progress({"type": "cell_scanning", "hospital": hosp, "sigla": sigla})
            h, s, result, err = _ocr_worker(ct, on_pdf=_emit_pdf)
            if err == "cancelled":
                on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
                return results
            if err:
                errors += 1
                on_progress({"type": "cell_error", "hospital": h, "sigla": s, "error": err})
            else:
                results[(h, s)] = result  # type: ignore[assignment]
                # Los file_result (emitidos inline por _emit_pdf durante _ocr_worker)
                # ya fusionaron el per_file de la celda; cell_done solo lleva la
                # metadata de la corrida para finalize_cell_ocr.
                on_progress(
                    {
                        "type": "cell_done",
                        "hospital": h,
                        "sigla": s,
                        "result": _cell_done_meta(result),
                    }
                )
            scanned += 1
            on_progress({"type": "scan_progress", "done": scanned, "total": total})
        on_progress(
            {
                "type": "scan_complete",
                "scanned": scanned,
                "errors": errors,
                "cancelled": 0,
            }
        )
        return results

    # Multi-worker path — real ProcessPoolExecutor with an IPC progress queue.
    event = getattr(cancel, "_event", None)
    scanned = 0
    errors = 0
    cancelled = 0

    # Workers (subprocesses) push cell_started / pdf_done onto this queue; a
    # daemon drain thread on the main process forwards them as cell_scanning /
    # pdf_progress. on_progress is safe to call from both this thread and the
    # as_completed loop: it only schedules a coroutine (run_coroutine_threadsafe)
    # and mutates session state on cell_done, which is emitted solely here.
    progress_q = mp.Queue()
    _DRAIN_STOP = "__drain_stop__"

    def _drain() -> None:
        nonlocal pdfs_done
        while True:
            try:
                ev = progress_q.get(timeout=0.5)
            except _queue.Empty:
                continue
            if ev.get("type") == _DRAIN_STOP:
                return
            if ev["type"] == "cell_started":
                on_progress(
                    {"type": "cell_scanning", "hospital": ev["hospital"], "sigla": ev["sigla"]}
                )
            elif ev["type"] == "pdf_done":
                pdfs_done += 1
                on_progress(
                    {
                        "type": "pdf_progress",
                        "done": min(pdfs_done, total_pdfs),
                        "total": total_pdfs,
                        "pdf_name": ev["pdf_name"],
                        "eta_ms": _eta_ms(t0, pdfs_done, total_pdfs),
                    }
                )
                # Incr. 1A: tras el tick de la barra, el file_result que la ruta
                # fusiona por archivo. Mismo hilo que el cell_meta de abajo ⇒ cada
                # merge precede al cell_done de su celda (orden FIFO de la cola).
                on_progress(
                    {
                        "type": "file_result",
                        "hospital": ev["hospital"],
                        "sigla": ev["sigla"],
                        "filename": ev["pdf_name"],
                        "count": ev["count"],
                        "method": ev["method"],
                        "near_matches": ev["near_matches"],
                    }
                )
            elif ev["type"] == "cell_meta":
                # Finalización de celda — encolada por el worker tras todos sus
                # pdf_done, así llega después de fusionar todo su per_file.
                on_progress(
                    {
                        "type": "cell_done",
                        "hospital": ev["hospital"],
                        "sigla": ev["sigla"],
                        "result": ev["result"],
                    }
                )

    drain_thread = threading.Thread(target=_drain, daemon=True)
    drain_thread.start()

    try:
        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=_init_ocr_worker,
            initargs=(event, progress_q),
        ) as pool:
            future_to_cell = {pool.submit(_ocr_worker, ct): ct for ct in cell_tuples}
            pending_futs = set(future_to_cell)

            def _consume(fut: futures.Future) -> None:
                nonlocal scanned, errors, cancelled
                pending_futs.discard(fut)
                try:
                    h, s, result, err = fut.result()
                except futures.CancelledError:
                    # F2: a queued future discarded by pool.shutdown(cancel_futures=
                    # True) below — it never ran, so there is no cell_error to report.
                    cancelled += 1
                    scanned += 1
                    on_progress({"type": "scan_progress", "done": scanned, "total": total})
                    return
                # cell_scanning is emitted by the drain (worker's cell_started) when
                # the cell actually starts — not here after the result (audit #1b).
                if err == "cancelled":
                    cancelled += 1
                elif err:
                    errors += 1
                    on_progress({"type": "cell_error", "hospital": h, "sigla": s, "error": err})
                else:
                    # cell_done lo emite el hilo de drain (desde el cell_meta del worker)
                    # DESPUÉS de fusionar cada file_result de esta celda, así
                    # finalize_cell_ocr ve un per_file completo. Aquí solo guardamos el
                    # ScanResult para el valor de retorno de scan_cells_ocr.
                    results[(h, s)] = result  # type: ignore[assignment]
                scanned += 1
                on_progress({"type": "scan_progress", "done": scanned, "total": total})

            shutdown_requested = False
            for fut in as_completed(future_to_cell):
                # Cancel-fast: if the user pressed Cancel mid-batch, do NOT wait for
                # every in-flight future to drain. Workers observe the event and
                # return err="cancelled" at their next checkpoint (≤ a few seconds);
                # queued (not-yet-dispatched) futures are discarded outright below.
                if cancel.cancelled and not shutdown_requested:
                    shutdown_requested = True
                    # F2: cancel_futures=True cancels every queued future via a bare
                    # Future.cancel() (see concurrent.futures.thread/process
                    # shutdown()), which never routes through
                    # set_running_or_notify_cancel() — so as_completed()'s waiter is
                    # never notified for a discarded future and would wait for it
                    # forever (verified empirically: a cancelled-but-unnotified
                    # future is invisible to as_completed()/wait(), not just
                    # "raises CancelledError" — it silently hangs the batch instead
                    # of crashing it). So: stop trusting as_completed() for anything
                    # still pending the instant we request the shutdown, and resolve
                    # the rest directly below — Future.result() checks state
                    # immediately regardless of notification, so it raises
                    # CancelledError for a discarded future without blocking, and
                    # still correctly awaits any future that is genuinely in flight.
                    pool.shutdown(wait=False, cancel_futures=True)
                    _consume(fut)
                    break
                _consume(fut)

            for fut in list(pending_futs):
                _consume(fut)
    finally:
        # All workers have finished (or been discarded) -> no more queue puts. The
        # sentinel lets the drain flush whatever's still buffered and stop cleanly
        # (Queue.empty() is racy across processes, so we don't rely on it). In a
        # `finally` so any raise out of the pool block can never leak this thread +
        # its mp.Queue (F2).
        progress_q.put({"type": _DRAIN_STOP})
        drain_thread.join(timeout=5.0)
        if drain_thread.is_alive():
            # No debería pasar: tras cerrar el pool y encolar el sentinel, el drain
            # vacía unos pocos eventos y sale. Si sigue vivo, un on_progress se trabó
            # (p. ej. contención de DB) — lo dejamos como daemon, pero avisamos: en ese
            # caso un cell_done tardío podría escribir tras el cierre de la DB (review #4).
            logger.warning(
                "drain thread no terminó en 5 s; un cell_done tardío podría perderse "
                "o escribir tras el cierre de la DB"
            )

    if cancelled > 0:
        on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
    else:
        on_progress(
            {
                "type": "scan_complete",
                "scanned": scanned,
                "errors": errors,
                "cancelled": 0,
            }
        )
    return results
