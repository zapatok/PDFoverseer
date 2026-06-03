"""Orchestrator: enumerate month folder + dispatch scans to scanners."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.domain import CATEGORY_FOLDERS, HOSPITALS, SIGLAS

if TYPE_CHECKING:
    from core.scanners.base import ScanResult
    from core.scanners.cancellation import CancellationToken


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
    cell_tuple: tuple[str, str, str],
    on_pdf: Callable[[str], None] | None = None,
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

    hosp, sigla, folder_str = cell_tuple
    folder = Path(folder_str)
    scanner = scanner_registry.get(sigla)
    token = CancellationToken.from_event(_WORKER_EVENT) if _WORKER_EVENT else CancellationToken()

    # Signal that the cell actually started — multi-worker only (the sync
    # caller emits cell_scanning itself before invoking the worker). Fixes the
    # audit's #1b: cell_scanning used to be emitted only after fut.result().
    if _WORKER_PROGRESS_Q is not None:
        _WORKER_PROGRESS_Q.put({"type": "cell_started", "hospital": hosp, "sigla": sigla})

    # Resolve the per-PDF progress callback: direct (sync) or via the queue.
    pdf_cb = on_pdf
    if pdf_cb is None and _WORKER_PROGRESS_Q is not None:

        def pdf_cb(name: str) -> None:  # noqa: F811
            _WORKER_PROGRESS_Q.put(
                {"type": "pdf_done", "hospital": hosp, "sigla": sigla, "pdf_name": name}
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
            for pdf in enumerate_cell_pdfs(folder):
                pdf_cb(pdf.name)
        return (hosp, sigla, result, None)

    last_err: str | None = None
    for attempt in range(OCR_RETRY_COUNT + 1):
        if token.cancelled:
            return (hosp, sigla, None, "cancelled")
        try:
            result = fn(folder, cancel=token, on_pdf=pdf_cb)
            return (hosp, sigla, result, None)
        except CancelledError:
            return (hosp, sigla, None, "cancelled")
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < OCR_RETRY_COUNT:
                time.sleep(OCR_RETRY_BACKOFF_S)
    return (hosp, sigla, None, last_err)


def scan_cells_ocr(
    cells: list[tuple[str, str, Path]],
    *,
    on_progress: Callable[[dict], None],
    cancel: CancellationToken,
    max_workers: int = 2,
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

    results: dict[tuple[str, str], ScanResult] = {}
    total = len(cells)
    cell_tuples = [(h, s, str(f)) for (h, s, f) in cells]

    if cancel.cancelled:
        on_progress({"type": "scan_cancelled", "scanned": 0, "total": total})
        return results

    # Pre-count PDFs across the selected cells so the bar has a real
    # denominator. Uses the same enumeration the scanners iterate, so `done`
    # (one tick per processed PDF) converges exactly on `total_pdfs`.
    total_pdfs = sum(len(enumerate_cell_pdfs(f)) for (_, _, f) in cells)
    on_progress({"type": "scan_started", "total_cells": total, "total_pdfs": total_pdfs})
    t0 = time.perf_counter()
    pdfs_done = 0

    if max_workers == 1:
        scanned = 0
        errors = 0

        def _emit_pdf(name: str) -> None:
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

        for ct in cell_tuples:
            if cancel.cancelled:
                on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
                return results
            hosp, sigla, _ = ct
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
                telemetry = result.telemetry
                near_matches = (
                    [
                        {
                            "pdf_name": nm.pdf_name,
                            "page_index": nm.page_index,
                            "flavor_name": nm.flavor_name,
                            "matched_anchors": list(nm.matched_anchors),
                            "missing_anchors": list(nm.missing_anchors),
                        }
                        for nm in telemetry.near_matches
                    ]
                    if telemetry
                    else []
                )
                on_progress(
                    {
                        "type": "cell_done",
                        "hospital": h,
                        "sigla": s,
                        "result": {
                            "ocr_count": result.count,
                            "method": result.method,
                            "confidence": result.confidence.value,
                            "duration_ms_ocr": result.duration_ms,
                            "near_matches": near_matches,
                            "per_file": result.per_file,
                        },
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
                results[(h, s)] = result  # type: ignore[assignment]
                telemetry = result.telemetry
                near_matches = (
                    [
                        {
                            "pdf_name": nm.pdf_name,
                            "page_index": nm.page_index,
                            "flavor_name": nm.flavor_name,
                            "matched_anchors": list(nm.matched_anchors),
                            "missing_anchors": list(nm.missing_anchors),
                        }
                        for nm in telemetry.near_matches
                    ]
                    if telemetry
                    else []
                )
                on_progress(
                    {
                        "type": "cell_done",
                        "hospital": h,
                        "sigla": s,
                        "result": {
                            "ocr_count": result.count,
                            "method": result.method,
                            "confidence": result.confidence.value,
                            "duration_ms_ocr": result.duration_ms,
                            "near_matches": near_matches,
                            "per_file": result.per_file,
                        },
                    }
                )
            scanned += 1
            on_progress({"type": "scan_progress", "done": scanned, "total": total})

    # All workers have finished -> no more queue puts. The sentinel lets the
    # drain flush whatever's still buffered and stop cleanly (Queue.empty() is
    # racy across processes, so we don't rely on it).
    progress_q.put({"type": _DRAIN_STOP})
    drain_thread.join(timeout=5.0)

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
