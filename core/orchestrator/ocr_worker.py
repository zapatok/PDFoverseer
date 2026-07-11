"""Pase-2 OCR worker subprocess plumbing.

**Spawn-critical (do not split):** the module globals ``_WORKER_EVENT`` /
``_WORKER_PROGRESS_Q`` are set by the pool ``initializer`` (``_init_ocr_worker``)
in the re-imported worker process and read by ``_ocr_worker`` — they MUST live in
the same module object, so initializer + worker + globals stay co-located here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.scanners.base import ScanResult

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
    on_pdf_page: Callable[[str, str, int, int], None] | None = None,
) -> tuple[str, str, ScanResult | None, str | None]:
    """Run OCR for a single cell. Runs in a worker subprocess (multi-worker
    path) or in-process (synchronous ``max_workers==1`` path).

    Per-PDF progress is reported via ``on_pdf`` when passed directly (sync
    path) or, in the multi-worker path, via the cached IPC queue
    (``_WORKER_PROGRESS_Q``): the worker emits ``cell_started`` when the cell
    actually begins and ``pdf_done`` after each PDF is processed.

    Page-level progress (``pdf_page_progress``): within each PDF the engine's
    ``on_page`` counter is forwarded — throttled to one event per
    ``PDF_PAGE_PROGRESS_MIN_INTERVAL_S`` (the final page always emits) — via
    ``on_pdf_page(hospital, sigla, page_1based, pages_total)`` in the sync
    path or the IPC queue in the multi-worker path. The engines emit from
    their OCR worker threads under a lock; ``mp.Queue.put`` is thread-safe.

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
    from core.utils import (  # noqa: E402
        OCR_RETRY_BACKOFF_S,
        OCR_RETRY_COUNT,
        PDF_PAGE_PROGRESS_MIN_INTERVAL_S,
    )

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

    # Resolve the page-progress sink (direct in sync path, queue in multi) and
    # wrap it with the throttle. The engines call on_page from their OCR worker
    # threads under a lock, so this closure runs serialized per PDF.
    page_emit: Callable[[int, int], None] | None = None
    if on_pdf_page is not None:

        def page_emit(page: int, pages_total: int) -> None:
            on_pdf_page(hosp, sigla, page, pages_total)

    elif _WORKER_PROGRESS_Q is not None:

        def page_emit(page: int, pages_total: int) -> None:  # noqa: F811
            _WORKER_PROGRESS_Q.put(
                {
                    "type": "pdf_page_progress",
                    "hospital": hosp,
                    "sigla": sigla,
                    "page": page,
                    "pages_total": pages_total,
                }
            )

    page_cb: Callable[[int, int], None] | None = None
    if page_emit is not None:
        last_emit = [0.0]

        def page_cb(done_0based: int, pages_total: int) -> None:
            page = done_0based + 1
            now = time.perf_counter()
            if page < pages_total and now - last_emit[0] < PDF_PAGE_PROGRESS_MIN_INTERVAL_S:
                return
            last_emit[0] = now
            page_emit(page, pages_total)

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

    # U9: track filenames already ticked across retry attempts. A retry
    # re-scans the WHOLE cell (count_ocr has no partial-resume concept), so a
    # transient failure after some files already succeeded would otherwise
    # re-emit on_pdf for them on the next attempt — inflating pdf_progress
    # `done` past `total` (display-clamped, so the bar stalls at 100% early)
    # and re-merging a file_result that already merged with an identical value.
    # Wraps whichever pdf_cb was resolved above (direct on_pdf in the sync
    # path, or the queue-backed closure in the multi-worker path) — both route
    # through this single call site into `fn`, so one wrapper covers both.
    # Keyed by filename: assumes each PDF's name is a stable identity across
    # retry attempts (the folder isn't mutated mid-scan) — a rename/replace
    # between attempts would dedup against the wrong file.
    ticked: set[str] = set()
    retry_pdf_cb = pdf_cb
    if pdf_cb is not None:

        def retry_pdf_cb(name: str, count: int | None, method: str, nm: list[dict]) -> None:
            if name in ticked:
                return
            ticked.add(name)
            pdf_cb(name, count, method, nm)

    last_err: str | None = None
    for attempt in range(OCR_RETRY_COUNT + 1):
        if token.cancelled:
            return (hosp, sigla, None, "cancelled")
        try:
            result = fn(folder, cancel=token, on_pdf=retry_pdf_cb, skip=skip, on_page=page_cb)
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
