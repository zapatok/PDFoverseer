"""SessionManager — bridge between API requests and DB."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.db.sessions_repo import (
    SessionRecord,
    create_session,
    finalize_session,
    get_session,
    update_session_state,
)
from core.scanners.base import ScanResult
from core.state.migrations import migrate_state_v1_to_v2


def compute_cell_count(cell: dict) -> int:
    """Cell count derivation per FASE 4 §6.2 precedence.

    1. user_override (FASE 2 escape hatch) wins absolutely.
    2. per_file_overrides ∪ per_file → suma derivada.
    3. Fallback: ocr_count or filename_count or 0.
    """
    if cell.get("user_override") is not None:
        return cell["user_override"]

    per_file = cell.get("per_file") or {}
    per_file_overrides = cell.get("per_file_overrides") or {}
    if per_file or per_file_overrides:
        all_files = set(per_file) | set(per_file_overrides)
        return sum(per_file_overrides.get(f, per_file.get(f, 0)) for f in all_files)

    return cell.get("ocr_count") or cell.get("filename_count") or 0


def compute_worker_count(cell: dict) -> int:
    """Total de trabajadores firmantes de una celda charla/chintegral.

    Suma los ``count`` de todas las marcas. Solo cuenta archivos presentes en
    ``per_file``: las marcas huérfanas de un PDF renombrado o eliminado se
    ignoran. Si ``per_file`` está vacío (celda sin escanear), no se filtra.

    Args:
        cell: el dict de estado de una celda.

    Returns:
        La suma de trabajadores firmantes; 0 si no hay marcas.
    """
    marks: dict = cell.get("worker_marks") or {}
    per_file: dict = cell.get("per_file") or {}
    total = 0
    for filename, page_marks in marks.items():
        if per_file and filename not in per_file:
            continue
        for mark in page_marks or []:
            if isinstance(mark, dict):
                total += mark.get("count") or 0
    return total


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
        state, rec = self._load_and_migrate(session_id)
        state["session_id"] = rec.session_id
        state["status"] = rec.status
        return state

    def _load_and_migrate(self, session_id: str) -> tuple[dict, SessionRecord]:
        """Load session state, run lazy migration, return (state, record).

        Internal helper used by all setters + getter. Persists migrated state
        back via update_session_state only when migration actually changed
        something — idempotent on subsequent calls.
        """
        rec = get_session(self._conn, session_id)
        if rec is None:
            raise KeyError(session_id)
        state = json.loads(rec.state_json)
        state, changed = migrate_state_v1_to_v2(state)
        if changed:
            update_session_state(self._conn, session_id, state_json=json.dumps(state))
        return state, rec

    def apply_filename_result(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> None:
        """Persist a filename_glob scanner result. Touches the filename pass
        fields and shared metadata (method, confidence, flags, errors,
        breakdown). Never touches ocr_count, user_override, or override_note.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["filename_count"] = result.count
        cell["confidence"] = result.confidence.value
        cell["method"] = result.method
        cell["breakdown"] = result.breakdown
        cell["flags"] = list(result.flags)
        cell["errors"] = list(result.errors)
        cell["files_scanned"] = result.files_scanned
        cell["duration_ms_filename"] = result.duration_ms
        cell["per_file"] = result.per_file
        # Each file carries how it was counted (rev-2 §3) so _origin_for picks the
        # per-file chip without depending on the cell-level method.
        cell["per_file_method"] = {f: result.method for f in (result.per_file or {})}
        # Pase 1 produces no near-matches; clear any left over from a prior OCR
        # run so the DetailPanel never points "Ver portada" at a PDF that the
        # fresh per_file no longer contains (Bug B).
        cell["near_matches"] = []
        cell.setdefault("per_file_overrides", {})
        cell.setdefault("manual_entry", False)
        cell.setdefault("ocr_count", None)
        cell.setdefault("user_override", None)
        cell.setdefault("override_note", None)
        cell.setdefault("excluded", False)
        # Preserve a manual "marcar listo" across re-scans (never clear it here).
        cell.setdefault("confirmed", False)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    def apply_ocr_result(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> None:
        """Persist an OCR scanner result. Touches ocr_count, method,
        confidence, flags, errors, breakdown, duration_ms_ocr. method =
        ``result.method`` (header_detect, corner_count, page_count_pure, or
        filename_glob when the OCR scanner fell back internally).

        flags/errors/breakdown are written unconditionally — an empty list/dict
        means "no flags this run" (NOT "preserve previous"). Stale data from
        a previous OCR run is overwritten, which is the correct semantic for
        a fresh scan.

        A14: near_matches from result.telemetry are persisted so the UI can
        surface them in the DetailPanel "Casi-matches" section.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["ocr_count"] = result.count
        cell["confidence"] = result.confidence.value
        cell["method"] = result.method
        cell["breakdown"] = result.breakdown
        cell["flags"] = list(result.flags)
        cell["errors"] = list(result.errors)
        cell["duration_ms_ocr"] = result.duration_ms
        cell["per_file"] = result.per_file
        # Each file carries how it was counted (rev-2 §3); for a full-cell OCR run
        # that is this run's OCR method for every scanned file.
        cell["per_file_method"] = {f: result.method for f in (result.per_file or {})}
        # A14: persist near-match telemetry so the UI can surface candidates.
        telemetry = result.telemetry
        cell["near_matches"] = (
            [
                {
                    "pdf_name": nm.pdf_name,
                    "page_index": nm.page_index,
                    "flavor_name": nm.flavor_name,
                    "matched_anchors": list(nm.matched_anchors),
                    "missing_anchors": list(nm.missing_anchors),
                }
                for nm in telemetry.near_matches
            ]
            if telemetry
            else []
        )
        cell.setdefault("per_file_overrides", {})
        cell.setdefault("manual_entry", False)
        cell.setdefault("filename_count", None)
        cell.setdefault("user_override", None)
        cell.setdefault("override_note", None)
        cell.setdefault("excluded", False)
        # Preserve a manual "marcar listo" across re-scans (never clear it here).
        cell.setdefault("confirmed", False)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    def apply_user_override(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        value: int | None,
        note: str | None,
        manual: bool = False,
    ) -> None:
        """Set or clear the user override + note.

        When ``value=None``, both ``user_override`` AND ``override_note`` are
        forced to None regardless of the ``note`` parameter (a note without
        an override is meaningless). When ``value`` is an int, ``note`` is
        persisted verbatim (may be None or a string).

        Args:
            session_id: Target session identifier.
            hospital: Hospital code (e.g. ``"HLL"``).
            sigla: Category code (e.g. ``"reunion"``).
            value: Override count (int) or None to clear.
            note: Optional override note string.
            manual: When True, marks ``cell.manual_entry = True`` to indicate
                the value was entered via the HLL manual-entry flow (no scan
                data available). Defaults to False, preserving FASE 2 behavior.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["user_override"] = value
        cell["override_note"] = note if value is not None else None
        cell.setdefault("filename_count", None)
        cell.setdefault("ocr_count", None)
        cell.setdefault("excluded", False)
        cell.setdefault("manual_entry", False)
        if manual:
            cell["manual_entry"] = True
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    def apply_per_file_override(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        filename: str,
        count: int,
    ) -> None:
        """Persist per-file count override. Spec §5.2.

        Args:
            session_id: Target session identifier.
            hospital: Hospital code (e.g. ``"HRB"``).
            sigla: Category code (e.g. ``"odi"``).
            filename: PDF filename to override.
            count: New count value (0 is valid — discards the file's contribution).

        Raises:
            KeyError: if (hospital, sigla) cell is not in session state.
        """
        state, _ = self._load_and_migrate(session_id)
        cells = state.setdefault("cells", {})
        if hospital not in cells or sigla not in cells.get(hospital, {}):
            raise KeyError(f"Cell ({hospital}, {sigla}) not in session {session_id}")
        cell = cells[hospital][sigla]
        cell.setdefault("per_file_overrides", {})
        cell["per_file_overrides"][filename] = count
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    def apply_worker_count(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        marks: dict | None = None,
        status: str | None = None,
        cursor: dict | None = None,
    ) -> None:
        """Mezcla los campos de conteo de trabajadores en una celda.

        Patch parcial: cada argumento que no sea ``None`` se escribe; los que
        son ``None`` se dejan intactos. Para vaciar las marcas, pasar
        ``marks={}``. La celda se crea si no existe.

        Args:
            session_id: id de la sesión (``YYYY-MM``).
            hospital: sigla del hospital (HLL/HLU/HRB/HPV).
            sigla: la sigla de la celda (``charla`` o ``chintegral``).
            marks: dict ``{archivo: [{page, count}, ...]}``, o None.
            status: ``"en_progreso"`` | ``"terminado"``, o None.
            cursor: ``{file, page}`` con la última posición, o None.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        if marks is not None:
            cell["worker_marks"] = marks
        if status is not None:
            cell["worker_status"] = status
        if cursor is not None:
            cell["worker_cursor"] = cursor
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    def apply_confirmed(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        confirmed: bool,
    ) -> None:
        """Set the manual 'confirmed' (marcar listo) flag on a cell.

        The flag is preserved across re-scans: both apply_filename_result and
        apply_ocr_result re-assert it via ``setdefault``, so confirming a cell
        survives a later pase-1 or OCR scan.

        Args:
            session_id: Target session identifier.
            hospital: Hospital code (e.g. ``"HRB"``).
            sigla: Category code (e.g. ``"exc"``).
            confirmed: New flag value.

        Raises:
            KeyError: if the (hospital, sigla) cell is not in session state.
        """
        state, _ = self._load_and_migrate(session_id)
        cells = state.setdefault("cells", {})
        if hospital not in cells or sigla not in cells.get(hospital, {}):
            raise KeyError(f"Cell ({hospital}, {sigla}) not in session {session_id}")
        cells[hospital][sigla]["confirmed"] = confirmed
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    def apply_cell_result(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        result: ScanResult,
    ) -> None:
        """Deprecated. Use apply_filename_result for pase 1 results."""
        self.apply_filename_result(session_id, hospital, sigla, result)

    def finalize(self, session_id: str) -> None:
        """Mark a session as finalized.

        Args:
            session_id: Target session identifier.
        """
        finalize_session(self._conn, session_id)
