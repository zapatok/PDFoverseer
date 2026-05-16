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


def _init_ocr_worker(event: Any) -> None:
    """ProcessPoolExecutor initializer — caches the cancellation event in the
    subprocess so the worker can build a CancellationToken without re-sending
    the event with every call."""
    global _WORKER_EVENT
    _WORKER_EVENT = event


def _ocr_worker(
    cell_tuple: tuple[str, str, str],
) -> tuple[str, str, ScanResult | None, str | None]:
    """Run OCR for a single cell. Runs in a worker subprocess.

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
    from core.utils import OCR_RETRY_BACKOFF_S, OCR_RETRY_COUNT  # noqa: E402

    hosp, sigla, folder_str = cell_tuple
    folder = Path(folder_str)
    scanner = scanner_registry.get(sigla)
    token = CancellationToken.from_event(_WORKER_EVENT) if _WORKER_EVENT else CancellationToken()

    fn = getattr(scanner, "count_ocr", None)
    if fn is None:
        # No OCR technique for this sigla — single filename_glob attempt, no retry.
        try:
            result = scanner.count(folder)
        except Exception as exc:  # noqa: BLE001
            return (hosp, sigla, None, f"{type(exc).__name__}: {exc}")
        return (hosp, sigla, result, None)

    last_err: str | None = None
    for attempt in range(OCR_RETRY_COUNT + 1):
        if token.cancelled:
            return (hosp, sigla, None, "cancelled")
        try:
            result = fn(folder, cancel=token)
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
    from concurrent.futures import (  # noqa: E402
        ProcessPoolExecutor,
        as_completed,
    )

    from core.scanners.cancellation import CancellationToken  # noqa: E402, F401

    results: dict[tuple[str, str], ScanResult] = {}
    total = len(cells)
    cell_tuples = [(h, s, str(f)) for (h, s, f) in cells]

    if cancel.cancelled:
        on_progress({"type": "scan_cancelled", "scanned": 0, "total": total})
        return results

    if max_workers == 1:
        scanned = 0
        errors = 0
        for ct in cell_tuples:
            if cancel.cancelled:
                on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
                return results
            hosp, sigla, _ = ct
            on_progress({"type": "cell_scanning", "hospital": hosp, "sigla": sigla})
            h, s, result, err = _ocr_worker(ct)
            if err == "cancelled":
                on_progress({"type": "scan_cancelled", "scanned": scanned, "total": total})
                return results
            if err:
                errors += 1
                on_progress({"type": "cell_error", "hospital": h, "sigla": s, "error": err})
            else:
                results[(h, s)] = result  # type: ignore[assignment]
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

    # Multi-worker path — real ProcessPoolExecutor.
    event = getattr(cancel, "_event", None)
    scanned = 0
    errors = 0
    cancelled = 0
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_ocr_worker,
        initargs=(event,),
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
            on_progress({"type": "cell_scanning", "hospital": h, "sigla": s})
            if err == "cancelled":
                cancelled += 1
            elif err:
                errors += 1
                on_progress({"type": "cell_error", "hospital": h, "sigla": s, "error": err})
            else:
                results[(h, s)] = result  # type: ignore[assignment]
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
                        },
                    }
                )
            scanned += 1
            on_progress({"type": "scan_progress", "done": scanned, "total": total})

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
