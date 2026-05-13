"""Unit tests for scan_cells_ocr orchestration.

Scanners are stubbed via a tiny FakeScanner registered into the registry so we
exercise the orchestration shape (callback firing, cancellation propagation,
exception handling) without paying real-OCR latency. Run with max_workers=1
so the synchronous in-process path is exercised — the multi-worker path is
covered by the integration test in Chunk 4 Task 23.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import scanners as scanner_registry
from core.orchestrator import scan_cells_ocr
from core.scanners.base import ConfidenceLevel, ScanResult
from core.scanners.cancellation import CancellationToken


def _make_result(count: int) -> ScanResult:
    return ScanResult(
        count=count,
        confidence=ConfidenceLevel.HIGH,
        method="header_detect",
        breakdown=None,
        flags=[],
        errors=[],
        duration_ms=10,
        files_scanned=1,
    )


@pytest.fixture(autouse=True)
def restore_registry():
    yield
    scanner_registry.clear()
    scanner_registry.register_defaults()


def test_callback_fires_for_each_cell(tmp_path: Path) -> None:
    folder = tmp_path / "f"
    folder.mkdir()
    cells = [("HPV", "odi", folder), ("HRB", "art", folder)]

    events: list[dict] = []

    def on_progress(ev: dict) -> None:
        events.append(ev)

    scanner_registry.clear()
    for sigla in ("odi", "art"):
        s = MagicMock(sigla=sigla)
        s.count_ocr = MagicMock(return_value=_make_result(3))
        scanner_registry.register(s)

    results = scan_cells_ocr(
        cells, on_progress=on_progress, cancel=CancellationToken(), max_workers=1
    )

    assert (("HPV", "odi") in results) and (("HRB", "art") in results)
    types = [e["type"] for e in events]
    assert types.count("cell_scanning") == 2
    assert types.count("cell_done") == 2
    assert types[-1] == "scan_complete"


def test_cancellation_short_circuits(tmp_path: Path) -> None:
    folder = tmp_path / "f"
    folder.mkdir()
    cells = [("HPV", "odi", folder)] * 5

    cancel = CancellationToken()
    events: list[dict] = []

    def on_progress(ev: dict) -> None:
        events.append(ev)
        if (
            ev.get("type") == "cell_done"
            and sum(1 for e in events if e["type"] == "cell_done") == 2
        ):
            cancel.cancel()

    scanner_registry.clear()
    s = MagicMock(sigla="odi")
    s.count_ocr = MagicMock(return_value=_make_result(1))
    scanner_registry.register(s)

    scan_cells_ocr(cells, on_progress=on_progress, cancel=cancel, max_workers=1)

    types = [e["type"] for e in events]
    assert "scan_cancelled" in types
    assert "scan_complete" not in types


def test_worker_exception_emits_cell_error(tmp_path: Path) -> None:
    folder = tmp_path / "f"
    folder.mkdir()
    cells = [("HPV", "odi", folder)]

    events: list[dict] = []

    def on_progress(ev: dict) -> None:
        events.append(ev)

    scanner_registry.clear()
    s = MagicMock(sigla="odi")
    s.count_ocr = MagicMock(side_effect=RuntimeError("boom"))
    scanner_registry.register(s)

    results = scan_cells_ocr(
        cells, on_progress=on_progress, cancel=CancellationToken(), max_workers=1
    )

    assert ("HPV", "odi") not in results
    assert any(e["type"] == "cell_error" for e in events)


def test_pre_cancelled_token_emits_scan_cancelled_zero(tmp_path: Path) -> None:
    """A token already cancelled before the call → scan_cancelled(scanned=0) only."""
    folder = tmp_path / "f"
    folder.mkdir()
    cells = [("HPV", "odi", folder)]

    events: list[dict] = []

    def on_progress(ev: dict) -> None:
        events.append(ev)

    cancel = CancellationToken()
    cancel.cancel()

    scan_cells_ocr(cells, on_progress=on_progress, cancel=cancel, max_workers=1)

    assert len(events) == 1
    assert events[0] == {"type": "scan_cancelled", "scanned": 0, "total": 1}
