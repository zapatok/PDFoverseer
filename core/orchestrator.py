"""Orchestrator: enumerate month folder + dispatch scans to scanners."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.domain import CATEGORY_FOLDERS, HOSPITALS, SIGLAS

if TYPE_CHECKING:
    from core.scanners.base import ScanResult
    from core.scanners.cancellation import CancellationToken

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CellInventory:
    hospital: str
    sigla: str
    folder_path: Path
    folder_exists: bool
    pdf_count_hint: int  # quick rglob count, no parsing


@dataclass(frozen=True)
class MonthInventory:
    month_root: Path
    hospitals_present: list[str]
    hospitals_missing: list[str]
    cells: dict[str, list[CellInventory]]  # hospital → list of 18 cells


def _find_category_folder(hosp_dir: Path, sigla: str) -> Path:
    """Locate the folder for `sigla` inside a hospital dir, tolerating
    TOTAL/' 0' suffixes.

    Args:
        hosp_dir: Path to the hospital directory.
        sigla: The category sigla to look up.

    Returns:
        Path to the category folder (nominal path even if it doesn't exist).
    """
    canonical = CATEGORY_FOLDERS[sigla]
    direct = hosp_dir / canonical
    if direct.exists():
        return direct
    if not hosp_dir.exists():
        return direct  # nominal path when hospital dir is absent
    # search for a directory matching canonical name with a numeric/text suffix
    for sub in hosp_dir.iterdir():
        if not sub.is_dir():
            continue
        if sub.name == canonical or sub.name.startswith(canonical + " "):
            return sub
    return direct  # nominal path even if it doesn't exist


def enumerate_month(month_root: Path) -> MonthInventory:
    """Discover hospitals and their 18 category cells inside a month folder.

    A hospital directory is considered *present* only if at least one of its
    18 canonical category folders exists inside it.  Directories that exist on
    disk but contain no recognised category subfolders (e.g. HLL with only a
    OneDrive zip) are classified as *missing*.

    Args:
        month_root: Path to the month folder (e.g. ``A:/informe mensual/ABRIL``).

    Returns:
        A :class:`MonthInventory` with hospitals_present, hospitals_missing,
        and a cells dict mapping each present hospital to its 18
        :class:`CellInventory` entries.

    Raises:
        FileNotFoundError: If ``month_root`` does not exist.
    """
    if not month_root.exists():
        raise FileNotFoundError(f"Month folder not found: {month_root}")

    present: list[str] = []
    missing: list[str] = []
    cells: dict[str, list[CellInventory]] = {}

    for hosp in HOSPITALS:
        hosp_dir = month_root / hosp

        # Build the 18 cells regardless of whether the hospital dir exists.
        cell_list: list[CellInventory] = []
        if hosp_dir.exists():
            for sigla in SIGLAS:
                folder = _find_category_folder(hosp_dir, sigla)
                exists = folder.exists()
                pdf_hint = len(list(folder.rglob("*.pdf"))) if exists else 0
                cell_list.append(
                    CellInventory(
                        hospital=hosp,
                        sigla=sigla,
                        folder_path=folder,
                        folder_exists=exists,
                        pdf_count_hint=pdf_hint,
                    )
                )
        else:
            # Hospital directory is entirely absent — build nominal cells.
            for sigla in SIGLAS:
                folder = hosp_dir / CATEGORY_FOLDERS[sigla]
                cell_list.append(
                    CellInventory(
                        hospital=hosp,
                        sigla=sigla,
                        folder_path=folder,
                        folder_exists=False,
                        pdf_count_hint=0,
                    )
                )

        # A hospital is "present" if its directory exists AND either:
        #   (a) it has at least one recognised category folder, or
        #   (b) it is completely empty (newly created, no content yet).
        # A directory that exists but contains only non-canonical files/folders
        # (e.g. HLL with a OneDrive zip) is treated as "missing".
        has_any_category = any(c.folder_exists for c in cell_list)
        dir_is_empty = hosp_dir.exists() and not any(hosp_dir.iterdir())
        if has_any_category or dir_is_empty:
            present.append(hosp)
            cells[hosp] = cell_list
        else:
            missing.append(hosp)

    return MonthInventory(
        month_root=month_root,
        hospitals_present=present,
        hospitals_missing=missing,
        cells=cells,
    )


def scan_cell(cell: CellInventory) -> ScanResult:
    """Run the registered scanner for this cell's sigla.

    Args:
        cell: A :class:`CellInventory` describing the folder to scan.

    Returns:
        A :class:`ScanResult` with count, confidence, method, and flags.
    """
    from core import scanners as scanner_registry  # noqa: E402
    from core.scanners.base import ScanResult  # noqa: E402, F401

    scanner = scanner_registry.get(cell.sigla)
    return scanner.count(cell.folder_path)


def _scan_cell_worker(cell_tuple: tuple[str, str, str]) -> tuple[str, str, ScanResult]:
    """Pool worker entry — re-imports happen in subprocess.

    Args:
        cell_tuple: ``(hospital, sigla, folder_str)`` packed for pickling.

    Returns:
        ``(hospital, sigla, ScanResult)`` tuple.
    """
    from core import scanners as scanner_registry  # noqa: E402
    from core.scanners.base import ScanResult  # noqa: E402, F401

    hosp, sigla, folder_str = cell_tuple
    folder = Path(folder_str)
    scanner = scanner_registry.get(sigla)
    return (hosp, sigla, scanner.count(folder))


def scan_month(
    inv: MonthInventory,
    *,
    max_workers: int | None = None,
) -> dict[tuple[str, str], ScanResult]:
    """Scan all cells in the inventory in parallel.

    Args:
        inv: A :class:`MonthInventory` from :func:`enumerate_month`.
        max_workers: Process pool size. Defaults to ``min(8, cpu_count-1)``.

    Returns:
        Dict keyed by ``(hospital, sigla)`` mapping to :class:`ScanResult`.
    """
    import os  # noqa: E402
    from concurrent.futures import ProcessPoolExecutor  # noqa: E402

    from core.scanners.base import ScanResult  # noqa: E402, F401

    if max_workers is None:
        max_workers = max(1, min(8, (os.cpu_count() or 4) - 1))

    cell_tuples = [
        (c.hospital, c.sigla, str(c.folder_path)) for cells in inv.cells.values() for c in cells
    ]

    results: dict[tuple[str, str], ScanResult] = {}

    if max_workers == 1:
        for ct in cell_tuples:
            hosp, sigla, r = _scan_cell_worker(ct)
            results[(hosp, sigla)] = r
        return results

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        for hosp, sigla, r in pool.map(_scan_cell_worker, cell_tuples):
            results[(hosp, sigla)] = r
    return results


# ======================================================================
# Pase 2 — OCR orchestration
# ======================================================================

_WORKER_EVENT: Any = None  # set per-subprocess by _init_ocr_worker
_WORKER_PROGRESS_Q: Any = None  # mp.Queue for per-PDF progress (None in sync path)


def _init_ocr_worker(event: Any, progress_q: Any = None) -> None:
    """ProcessPoolExecutor initializer — caches the cancellation event AND the
    per-PDF progress queue in the subprocess, so the worker can report progress
    and build a CancellationToken without re-sending them with every call."""
    global _WORKER_EVENT, _WORKER_PROGRESS_Q
    _WORKER_EVENT = event
    _WORKER_PROGRESS_Q = progress_q


def _eta_ms(t0: float, done: int, total: int) -> int | None:
    """Linear ETA in milliseconds extrapolated from elapsed time.

    Returns None until there is at least one completed item to extrapolate
    from, and once the work is finished (``done >= total``).
    """
    if done <= 0 or total <= done:
        return None
    per_item = (time.perf_counter() - t0) / done
    return int(per_item * (total - done) * 1000)


def _ocr_worker(
    cell_tuple: tuple[str, str, str, list[str]],
    on_pdf: Callable[[str, int | None, str, list[dict]], None] | None = None,
) -> tuple[str, str, ScanResult | None, str | None]:
    """Run OCR for a single cell. Runs in a worker subprocess (multi-worker
    path) or in-process (synchronous ``max_workers==1`` path).

    Per-PDF progress is reported via ``on_pdf`` when passed directly (sync
    path) or, in the multi-worker path, via the cached IPC queue
    (``_WORKER_PROGRESS_Q``): the worker emits ``cell_started`` when the cell
    actually begins and ``pdf_done`` after each PDF is processed.

    On a transient failure the scan is retried up to ``OCR_RETRY_COUNT`` times
    with a short backoff (FASE 5 Feature 3). A cancelled token never triggers a
    retry. Returns ``(hospital, sigla, ScanResult | None, error_str | None)`` —
    exactly one of ScanResult or error_str is non-None.
    """
    from core import scanners as scanner_registry  # noqa: E402
    from core.scanners.cancellation import (  # noqa: E402
        CancellationToken,
        CancelledError,
    )
    from core.scanners.utils.cell_enumeration import (  # noqa: E402
        enumerate_cell_pdfs,
    )
    from core.utils import OCR_RETRY_BACKOFF_S, OCR_RETRY_COUNT  # noqa: E402

    hosp, sigla, folder_str, skip_list = cell_tuple
    folder = Path(folder_str)
    skip = set(skip_list)  # Incr. 1A: archivos ya confiables que el OCR de celda omite.
    scanner = scanner_registry.get(sigla)
    token = CancellationToken.from_event(_WORKER_EVENT) if _WORKER_EVENT else CancellationToken()

    def _finish(result: ScanResult) -> tuple[str, str, ScanResult, None]:
        # Multi-worker: encola la metadata de la celda en la MISMA cola que los
        # pdf_done y DESPUÉS de ellos, así el drain fusiona cada file_result antes
        # de emitir cell_done (finalize ve un per_file completo, sin carrera). En
        # el camino síncrono (_WORKER_PROGRESS_Q is None) el cell_done lo emite el
        # llamador tras retornar este worker.
        if _WORKER_PROGRESS_Q is not None:
            _WORKER_PROGRESS_Q.put(
                {
                    "type": "cell_meta",
                    "hospital": hosp,
                    "sigla": sigla,
                    "result": _cell_done_meta(result),
                }
            )
        return (hosp, sigla, result, None)

    # Signal that the cell actually started — multi-worker only (the sync
    # caller emits cell_scanning itself before invoking the worker). Fixes the
    # audit's #1b: cell_scanning used to be emitted only after fut.result().
    if _WORKER_PROGRESS_Q is not None:
        _WORKER_PROGRESS_Q.put({"type": "cell_started", "hospital": hosp, "sigla": sigla})

    # Resolve the per-PDF progress callback: direct (sync) or via the queue.
    pdf_cb = on_pdf
    if pdf_cb is None and _WORKER_PROGRESS_Q is not None:

        def pdf_cb(name: str, count: int | None, method: str, nm: list[dict]) -> None:  # noqa: F811
            # Incr. 1A: carga count/method/near_matches (ya dicts) para el merge
            # incremental por-archivo en el proceso principal (lo usa el _drain).
            _WORKER_PROGRESS_Q.put(
                {
                    "type": "pdf_done",
                    "hospital": hosp,
                    "sigla": sigla,
                    "pdf_name": name,
                    "count": count,
                    "method": method,
                    "near_matches": nm,
                }
            )

    fn = getattr(scanner, "count_ocr", None)
    if fn is None:
        # No OCR technique for this sigla (scan_strategy "none", e.g. reunion):
        # single filename_glob attempt, no retry. Still tick each PDF so the
        # progress bar's done matches the pre-counted total.
        try:
            result = scanner.count(folder)
        except Exception as exc:  # noqa: BLE001
            return (hosp, sigla, None, f"{type(exc).__name__}: {exc}")
        if pdf_cb is not None:
            pf = result.per_file or {}
            for pdf in enumerate_cell_pdfs(folder):
                if pdf.name in skip:
                    continue  # ya confiable; no se re-tickea (total_pdfs lo excluye)
                # method filename_glob → la ruta lo trata como solo-progreso.
                pdf_cb(pdf.name, pf.get(pdf.name, 0), "filename_glob", [])
        return _finish(result)

    last_err: str | None = None
    for attempt in range(OCR_RETRY_COUNT + 1):
        if token.cancelled:
            return (hosp, sigla, None, "cancelled")
        try:
            result = fn(folder, cancel=token, on_pdf=pdf_cb, skip=skip)
            return _finish(result)
        except CancelledError:
            return (hosp, sigla, None, "cancelled")
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < OCR_RETRY_COUNT:
                time.sleep(OCR_RETRY_BACKOFF_S)
    return (hosp, sigla, None, last_err)


def _serialize_near_matches(result: ScanResult) -> list[dict]:
    telemetry = result.telemetry
    if not telemetry:
        return []
    return [
        {
            "pdf_name": nm.pdf_name,
            "page_index": nm.page_index,
            "flavor_name": nm.flavor_name,
            "matched_anchors": list(nm.matched_anchors),
            "missing_anchors": list(nm.missing_anchors),
        }
        for nm in telemetry.near_matches
    ]


def _cell_done_meta(result: ScanResult) -> dict:
    """Payload de metadata para ``cell_done`` (Incr. 1A).

    ``per_file``/``near_matches`` se fusionan incrementalmente por archivo vía el
    evento ``file_result``, así que ``cell_done`` solo finaliza método/confianza/
    flags/errores/duración — lo consume ``finalize_cell_ocr`` en la ruta.
    """
    return {
        "ocr_count": result.count,
        "method": result.method,
        "confidence": result.confidence.value,
        "duration_ms_ocr": result.duration_ms,
        "flags": list(result.flags),
        "errors": list(result.errors),
        "breakdown": result.breakdown,
    }


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

    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_ocr_worker,
        initargs=(event, progress_q),
    ) as pool:
        future_to_cell = {pool.submit(_ocr_worker, ct): ct for ct in cell_tuples}
        for fut in as_completed(future_to_cell):
            # Cancel-fast: if the user pressed Cancel mid-batch, do NOT wait for
            # every in-flight future to drain. Workers observe the event and
            # return err="cancelled" at their next checkpoint (≤ a few seconds);
            # we just stop processing results and break out. The `with` block
            # exits and waits for the pool to settle.
            if cancel.cancelled and cancelled == 0:
                # First time we notice — request the pool to discard queued
                # futures (Python 3.9+). In-flight will still need to wind
                # down at their own next checkpoint.
                pool.shutdown(wait=False, cancel_futures=True)
            h, s, result, err = fut.result()
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

    # All workers have finished -> no more queue puts. The sentinel lets the
    # drain flush whatever's still buffered and stop cleanly (Queue.empty() is
    # racy across processes, so we don't rely on it).
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
