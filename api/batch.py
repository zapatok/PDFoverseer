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
