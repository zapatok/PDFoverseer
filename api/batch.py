"""Batch lifecycle for pase 2 OCR scans.

A BatchHandle ties together: the session it belongs to, the multiprocessing
Event for cancellation, and the concurrent.futures.Future that resolves when
the orchestrator thread is done. Stored in ``app.state.batches[session_id]``
while the batch runs and removed on completion (terminal event sent).
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass
class BatchHandle:
    session_id: str
    total: int
    cancel_event: Any  # mp.Event (or None for tests that don't dispatch)
    future: Any  # concurrent.futures.Future (or None)


def make_handle(session_id: str, total: int) -> BatchHandle:
    """Create a fresh handle with a new mp.Event."""
    ctx = mp.get_context("spawn")
    return BatchHandle(
        session_id=session_id,
        total=total,
        cancel_event=ctx.Event(),
        future=None,
    )


def register_batch_handle(app: Any, session_id: str, total: int) -> BatchHandle:
    """Create a handle and atomically register it in ``app.state.batches``.

    Shared by ``scan_ocr`` and ``scan_file_ocr`` (api/routes/sessions/scan.py):
    both register into the same per-session slot, so a multi-cell batch and a
    single-file scan mutually exclude each other. ``setdefault`` returns the
    value already in the dict if one exists, otherwise installs and returns
    the new handle — the identity check below tells the two cases apart
    without a separate lock (dict.setdefault is atomic under the GIL).

    Raises:
        HTTPException: 409 if a batch is already running for this session.

    Returns:
        The registered BatchHandle (safe to mutate ``.future`` after dispatch).
    """
    handle = make_handle(session_id=session_id, total=total)
    if app.state.batches.setdefault(session_id, handle) is not handle:
        raise HTTPException(409, "another batch is already running for this session")
    return handle
