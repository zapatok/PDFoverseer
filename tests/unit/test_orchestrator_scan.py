"""Tests for scan_cell and scan_month orchestrator functions."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.orchestrator import enumerate_month, scan_cell, scan_month
from core.scanners.base import ConfidenceLevel  # noqa: F401 (used by callers)

ABRIL = Path("A:/informe mensual/ABRIL")


@pytest.mark.corpus
def test_scan_cell_hpv_art_returns_count():
    inv = enumerate_month(ABRIL)
    cell = next(c for c in inv.cells["HPV"] if c.sigla == "art")
    result = scan_cell(cell)
    assert result.count > 0
    assert result.method == "filename_glob"


@pytest.mark.corpus
def test_scan_month_returns_result_per_cell():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # 4 hospitals × 20 cats = 80 cells
    assert len(results) == 80
    # All have a count (possibly zero)
    for (hosp, sigla), r in results.items():
        assert r.count >= 0


@pytest.mark.corpus
def test_scan_month_flags_known_compilations():
    inv = enumerate_month(ABRIL)
    results = scan_month(inv)
    # HRB ODI and HLU ODI are known compilations
    assert "compilation_suspect" in results[("HRB", "odi")].flags
    assert "compilation_suspect" in results[("HLU", "odi")].flags


# ── F2: batch-cancel with queued cells ──────────────────────────────────────


def test_scan_cells_ocr_cancel_with_queued_futures_ends_cancelled(tmp_path, monkeypatch):
    """F2: cancelling a multi-cell OCR batch while cells are still queued in the
    pool must end the batch as a real ``scan_cancelled`` — never an unhandled
    ``CancelledError`` (which used to escape ``scan_cells_ocr``, get caught by the
    route as a crash, and mislabel the batch ``scan_complete {errors: N}``), and
    never a silent hang (a subtlety beyond the original finding: a future
    discarded by ``pool.shutdown(cancel_futures=True)`` is never routed through
    ``set_running_or_notify_cancel()``, so ``as_completed()``'s waiter is never
    notified for it — verified empirically against this project's exact
    Python 3.10.11 venv before writing this test).

    Swaps ``ProcessPoolExecutor`` for a deterministic fake pool (the in-function
    ``from concurrent.futures import ProcessPoolExecutor`` resolves the attribute
    at call time, so patching ``concurrent.futures.ProcessPoolExecutor`` takes
    effect) so the scenario — one cell already finished, several still queued
    when Cancel is pressed — is reproduced without any real thread/process
    scheduling race.
    """
    import concurrent.futures as futures_mod
    import threading

    from core.orchestrator import scan_cells_ocr
    from core.scanners.base import ScanResult
    from core.scanners.cancellation import CancellationToken

    cancel_token = CancellationToken()

    def _ok_result(hosp: str, sigla: str) -> ScanResult:
        return ScanResult(
            count=0,
            confidence=ConfidenceLevel.HIGH,
            method="header_band_anchors",
            breakdown=None,
            flags=[],
            errors=[],
            duration_ms=1,
            files_scanned=0,
            per_file={},
        )

    class _FakeExecutor:
        """Deterministic stand-in for ProcessPoolExecutor: the first submitted
        cell completes immediately (a cell that finished before Cancel was
        pressed) and flags cancellation as a side effect (a concurrent POST
        /cancel); the rest stay pending, exactly as a real pool would have left
        cells queued behind busy workers — so ``shutdown(cancel_futures=True)``
        discards them deterministically, no thread-scheduling race involved."""

        def __init__(self, max_workers=None, initializer=None, initargs=()):
            self._submitted = 0
            self._pending: list[futures_mod.Future] = []

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def submit(self, fn, cell_tuple):
            fut: futures_mod.Future = futures_mod.Future()
            hosp, sigla, _folder, _skip = cell_tuple
            if self._submitted == 0:
                fut.set_result((hosp, sigla, _ok_result(hosp, sigla), None))
                cancel_token.cancel()  # simulates a concurrent POST /cancel
            else:
                self._pending.append(fut)
            self._submitted += 1
            return fut

        def shutdown(self, wait=True, cancel_futures=False):
            if cancel_futures:
                for fut in self._pending:
                    fut.cancel()

    monkeypatch.setattr(futures_mod, "ProcessPoolExecutor", _FakeExecutor)

    captured_threads: list[threading.Thread] = []
    real_thread_cls = threading.Thread

    class _CapturingThread(real_thread_cls):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            captured_threads.append(self)

    monkeypatch.setattr(threading, "Thread", _CapturingThread)

    cells = [("H", f"cell{i}", tmp_path) for i in range(4)]
    events: list[dict] = []
    result = scan_cells_ocr(cells, on_progress=events.append, cancel=cancel_token, max_workers=2)

    # Returned normally — no unhandled CancelledError escaped scan_cells_ocr.
    assert isinstance(result, dict)

    terminal = [e for e in events if e["type"] in ("scan_complete", "scan_cancelled")]
    assert len(terminal) == 1
    assert terminal[0]["type"] == "scan_cancelled"

    # No fabricated cell_error for the discarded (never-ran) queued cells.
    assert not any(e["type"] == "cell_error" for e in events)

    # The drain thread (the only Thread created inside scan_cells_ocr here — the
    # fake pool spawns none) must have stopped: proves the drain-stop sentinel +
    # join moved into a `finally` that always runs.
    assert captured_threads, "no drain thread was captured"
    assert not captured_threads[0].is_alive()
