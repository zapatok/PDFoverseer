"""Cooperative cancellation primitive shared by OCR scanners and the orchestrator.

Two construction modes:

- ``CancellationToken()`` — plain in-process bool. Use in unit tests.
- ``CancellationToken.from_event(mp_event)`` — wraps a ``multiprocessing.Event``.
  Use in production: the orchestrator creates the event, the executor's
  ``initializer`` injects it into each worker subprocess, and any process
  observes the cancellation immediately after ``.set()`` is called.

Both modes expose the same ``cancelled`` property + ``cancel()`` + ``check()`` API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CancelledError(Exception):
    """Raised by CancellationToken.check() when cancel() has been invoked."""


@dataclass
class CancellationToken:
    _event: Any = field(default=None, repr=False)
    _flag: bool = False

    @classmethod
    def from_event(cls, event: Any) -> CancellationToken:
        """Construct a token backed by a multiprocessing.Event (or similar)."""
        return cls(_event=event)

    @property
    def cancelled(self) -> bool:
        if self._event is not None:
            return bool(self._event.is_set())
        return self._flag

    def cancel(self) -> None:
        if self._event is not None:
            self._event.set()
        else:
            self._flag = True

    def check(self) -> None:
        if self.cancelled:
            raise CancelledError()
