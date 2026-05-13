"""Integration: real ProcessPoolExecutor path over scanners_ocr fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from core import scanners as scanner_registry
from core.orchestrator import scan_cells_ocr
from core.scanners.cancellation import CancellationToken

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "scanners_ocr"


@pytest.mark.slow
def test_scan_cells_ocr_two_workers_real_scanners() -> None:
    """Dispatch 2 cells across 2 workers using real specialized scanners."""
    if not (FIXTURE_ROOT / "odi_compilation").exists():
        pytest.skip("scanners_ocr fixtures missing — run tools/extract_fase2_fixtures.py")
    scanner_registry.clear()
    scanner_registry.register_defaults()

    cells = [
        ("HRB", "odi", FIXTURE_ROOT / "odi_compilation"),
        ("HPV", "charla", FIXTURE_ROOT / "charla_compilation"),
    ]
    events: list[dict] = []
    cancel = CancellationToken.from_event(
        __import__("multiprocessing").get_context("spawn").Event()
    )
    results = scan_cells_ocr(cells, on_progress=events.append, cancel=cancel, max_workers=2)
    assert len(results) == 2
    assert events[-1]["type"] == "scan_complete"
    assert events[-1]["errors"] == 0
