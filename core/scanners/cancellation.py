"""Cooperative cancellation primitive shared by OCR scanners and the orchestrator.

Plain mutable state — no threading.Event. Workers run in subprocesses and the
orchestrator iterates `as_completed` on the main thread; the token is set on
the main thread and read by workers via the subprocess they were dispatched
into. Each scanner calls `cancel.check()` at natural checkpoints; if cancelled
the call raises `CancelledError`, which the orchestrator catches and converts
to a `scan_cancelled` WS event (see Chunk 4).
"""

from __future__ import annotations

from dataclasses import dataclass


class CancelledError(Exception):
    """Raised by CancellationToken.check() when cancel() has been invoked."""


@dataclass
class CancellationToken:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError()
