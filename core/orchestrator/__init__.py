"""Orchestrator: enumerate month folder + dispatch scans to scanners.

Split into focused, import-only submodules:

- ``enumeration`` — month/cell discovery (``enumerate_month``, ``CellInventory``, …).
- ``filename_scan`` — pase-1 filename-glob parallel scan (``scan_month``, ``scan_cell``).
- ``ocr_worker`` — pase-2 worker subprocess plumbing (spawn-critical globals + worker).
- ``ocr_scan`` — pase-2 orchestration (``scan_cells_ocr``, ``scan_one_file_ocr``).

This package re-exports the public surface so ``from core.orchestrator import X`` is
unchanged. Keep this module import-only: under Windows ``spawn`` a worker child re-imports
``core.orchestrator.ocr_worker``, which runs this ``__init__`` first.
"""

from __future__ import annotations

from core.orchestrator.enumeration import (
    CellInventory,
    MonthInventory,
    _find_category_folder,
    enumerate_month,
)
from core.orchestrator.filename_scan import _scan_cell_worker, scan_cell, scan_month
from core.orchestrator.ocr_scan import scan_cells_ocr, scan_one_file_ocr
from core.orchestrator.ocr_worker import (
    _cell_done_meta,
    _eta_ms,
    _init_ocr_worker,
    _ocr_worker,
    _serialize_near_matches,
)

__all__ = [
    "CellInventory",
    "MonthInventory",
    "_find_category_folder",
    "enumerate_month",
    "scan_cell",
    "_scan_cell_worker",
    "scan_month",
    "scan_cells_ocr",
    "scan_one_file_ocr",
    "_init_ocr_worker",
    "_eta_ms",
    "_ocr_worker",
    "_serialize_near_matches",
    "_cell_done_meta",
]
