"""Sessions endpoints: create/get + scan + per-cell/per-file editing + reorg.

Split into focused sub-routers over a shared ``_common`` kernel:

- ``lifecycle`` — open/return a session + fetch state.
- ``scan`` — pase-1 scan, pase-2 OCR batch, single-file OCR, cancel, apply-ratio
  (+ scan-progress handling and the M3b agent lock-skip policy).
- ``writes`` — the single-cell write routes (override / per-file / note / worker / …).
- ``files`` — list a cell's PDFs + serve one.
- ``reorg`` — reorg ops + manifest export.

This ``__init__`` composes the one ``router`` (so ``server.py`` registration is
unchanged) and re-exports the helpers other modules/tests import from
``api.routes.sessions``. Acyclic: ``__init__`` → sub-routers → ``_common``.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import files, lifecycle, reorg, scan, writes
from ._common import (
    _cell_updated_event,
    _validate_session_id,
    cell_page_counts,
    compute_settled,
    enrich_cell_worker_count,
    file_origin,
    get_manager,
    present_file_names,
    refresh_all_reliable,
    refresh_reorg_deltas,
)
from .scan import (
    _apply_scan_event,
    _handle_scan_progress,
    _scan_followup_event,
    _skip_files,
)

router = APIRouter()
router.include_router(lifecycle.router)
router.include_router(scan.router)
router.include_router(writes.router)
router.include_router(files.router)
router.include_router(reorg.router)

__all__ = [
    "router",
    "get_manager",
    "_validate_session_id",
    "cell_page_counts",
    "compute_settled",
    "enrich_cell_worker_count",
    "file_origin",
    "present_file_names",
    "refresh_all_reliable",
    "refresh_reorg_deltas",
    "_cell_updated_event",
    "_apply_scan_event",
    "_skip_files",
    "_scan_followup_event",
    "_handle_scan_progress",
]
