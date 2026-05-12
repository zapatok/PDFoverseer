"""SessionManager — bridge between API requests and DB."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.db.sessions_repo import (
    create_session,
    finalize_session,
    get_session,
    update_session_state,
)
from core.scanners.base import ScanResult


class SessionManager:
    """Wrap session DB operations + maintain in-memory cell state."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def open_session(
        self,
        *,
        year: int,
        month: int,
        month_root: Path,
    ) -> dict:
        """Open or create a session for (year, month).

        Args:
            year: Calendar year of the session.
            month: Calendar month (1-12).
            month_root: Root directory for the monthly report.

        Returns:
            Session state dict with ``session_id``, ``status``, ``month_root``,
            and ``cells`` keys.
        """
        rec = get_session(self._conn, f"{year:04d}-{month:02d}")
        if rec is None:
            empty_state = {"month_root": month_root.as_posix(), "cells": {}}
            rec = create_session(
                self._conn,
                year=year,
                month=month,
                state_json=json.dumps(empty_state),
            )
        state = json.loads(rec.state_json)
        state["session_id"] = rec.session_id
        state["status"] = rec.status
        return state

    def get_session_state(self, session_id: str) -> dict:
        """Return full session state dict for an existing session.

        Args:
            session_id: The session identifier (e.g. ``"2026-04"``).

        Returns:
            Session state dict with ``session_id``, ``status``, ``month_root``,
            and ``cells`` keys.

        Raises:
            KeyError: If no session with that ID exists.
        """
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        state["session_id"] = rec.session_id
        state["status"] = rec.status
        return state

    def apply_cell_result(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        result: ScanResult,
    ) -> None:
        """Persist a scanner result into the session cell grid.

        Args:
            session_id: Target session identifier.
            hospital: Hospital key (e.g. ``"HPV"``).
            sigla: Document type sigla (e.g. ``"art"``).
            result: The ScanResult to record.

        Raises:
            KeyError: If no session with that ID exists.
        """
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        cells = state.setdefault("cells", {})
        hosp_cells = cells.setdefault(hospital, {})
        hosp_cells[sigla] = {
            "count": result.count,
            "confidence": result.confidence.value,
            "method": result.method,
            "breakdown": result.breakdown,
            "flags": result.flags,
            "errors": result.errors,
            "duration_ms": result.duration_ms,
            "files_scanned": result.files_scanned,
            "user_override": None,
            "excluded": False,
        }
        update_session_state(
            self._conn,
            session_id,
            state_json=json.dumps(state),
        )

    def apply_user_override(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        override: int | None,
    ) -> None:
        """Set a user override count on a cell.

        Args:
            session_id: Target session identifier.
            hospital: Hospital key.
            sigla: Document type sigla.
            override: User-supplied count, or ``None`` to clear.

        Raises:
            KeyError: If no session with that ID exists.
        """
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        cell = state["cells"].setdefault(hospital, {}).setdefault(sigla, {})
        cell["user_override"] = override
        update_session_state(
            self._conn,
            session_id,
            state_json=json.dumps(state),
        )

    def finalize(self, session_id: str) -> None:
        """Mark a session as finalized.

        Args:
            session_id: Target session identifier.
        """
        finalize_session(self._conn, session_id)
