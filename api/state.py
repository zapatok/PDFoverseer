"""SessionManager — bridge between API requests and DB."""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
from pathlib import Path

from core.cell_count import compute_cell_count  # noqa: F401  re-exported for api consumers
from core.db.sessions_repo import (
    SessionRecord,
    create_session,
    finalize_session,
    get_session,
    update_session_state,
)
from core.scanners.base import ScanResult
from core.state.migrations import migrate_state_v1_to_v2


def _cell_has_work(cell: dict) -> bool:
    """True when a cell carries OCR results or user edits that a bulk filename
    re-scan must not overwrite.

    A pase-1 re-scan ("Escanear todos los hospitales", e.g. to add a new
    hospital) runs over every cell. For a cell that was already counted by OCR
    or touched by the user, overwriting ``per_file`` with filename counts would
    silently revert its total (which sums ``per_file``) — the 2026-06-05
    incident. A cell is considered worked when it has any of: a full-cell OCR
    count, a cell-level override, a manual "marcar listo", a per-file override,
    a per-file OCR method (a single file OCR'd from the viewer leaves
    ``ocr_count`` None, so the per-file methods must be inspected too), or
    worker-signer marks (Feature 1 charla/chintegral counting, which
    ``compute_worker_count`` links to ``per_file`` — clobbering per_file would
    orphan the marks).
    """
    if cell.get("ocr_count") is not None:
        return True
    if cell.get("user_override") is not None:
        return True
    if cell.get("confirmed"):
        return True
    if cell.get("per_file_overrides"):
        return True
    if cell.get("worker_marks"):
        return True
    per_file_method = cell.get("per_file_method") or {}
    return any(m and m != "filename_glob" for m in per_file_method.values())


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


def _synchronized(method):
    """Serializa el método bajo ``self._lock`` (RLock): protege el
    read-modify-write del blob de sesión contra escrituras concurrentes (merge
    incremental por-PDF desde el hilo de drain + ediciones HTTP durante un scan).

    RLock (no Lock): ``apply_cell_result`` delega en ``apply_filename_result``,
    así que un hilo re-adquiere el mismo lock — con un Lock no reentrante eso
    deadlockea.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class SessionManager:
    """Wrap session DB operations + maintain in-memory cell state."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.RLock()

    @_synchronized
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

    @_synchronized
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

    @_synchronized
    def apply_filename_result(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> None:
        """Persist a filename_glob scanner result. Touches the filename pass
        fields and shared metadata (method, confidence, flags, errors,
        breakdown). Never touches ocr_count, user_override, or override_note.

        A bulk re-scan runs over every cell, including ones already counted by
        OCR or edited by the user (e.g. "Escanear todos los hospitales" to add a
        new hospital). For those (see :func:`_cell_has_work`) only the plain
        filename hint and scan telemetry are refreshed; ``per_file``,
        ``per_file_method``, ``near_matches`` and the OCR/manual state are left
        intact so the displayed count never silently regresses (2026-06-05).
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})

        if _cell_has_work(cell):
            cell["filename_count"] = result.count
            cell["files_scanned"] = result.files_scanned
            cell["duration_ms_filename"] = result.duration_ms
            cell.setdefault("per_file_overrides", {})
            cell.setdefault("manual_entry", False)
            cell.setdefault("ocr_count", None)
            cell.setdefault("user_override", None)
            cell.setdefault("override_note", None)
            cell.setdefault("excluded", False)
            cell.setdefault("confirmed", False)
            update_session_state(self._conn, session_id, state_json=json.dumps(state))
            return

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

    @_synchronized
    def apply_ocr_result(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> None:
        """Persist an OCR scanner result (whole-cell ``per_file`` replacement).

        .. deprecated:: Incr. 1A — el OCR de celda fusiona por archivo
            (:meth:`apply_per_file_ocr_result`) + :meth:`finalize_cell_ocr` para la
            metadata. Se mantiene para compat de tests legacy (migrar en Task 9).

        Touches ocr_count, method,
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

    @_synchronized
    def finalize_cell_ocr(
        self, session_id: str, hospital: str, sigla: str, result: ScanResult
    ) -> None:
        """Finaliza la metadata de celda tras un OCR de celda *incremental* (Incr. 1A).

        NO toca ``per_file``/``per_file_method``: esos se fusionaron por archivo vía
        :meth:`apply_per_file_ocr_result` a medida que cada PDF terminó. Aquí solo se
        escribe metadata de la corrida (método/confianza/flags/errores/duración) y un
        ``ocr_count`` belt-and-suspenders = suma del ``per_file`` actual (fallback de
        ``compute_cell_count``; el total real sale de ``per_file``). Preserva
        user_override, per_file_overrides, manual_entry, confirmed, worker_marks,
        filename_count.

        Args:
            session_id: sesión objetivo.
            hospital: sigla del hospital.
            sigla: sigla de la categoría.
            result: ScanResult de metadata de la corrida (su ``per_file`` se ignora).
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        cell["method"] = result.method
        cell["confidence"] = result.confidence.value
        cell["breakdown"] = result.breakdown
        cell["flags"] = list(result.flags)
        cell["errors"] = list(result.errors)
        cell["duration_ms_ocr"] = result.duration_ms
        # Fallback only — compute_cell_count prioriza per_file. Suma del per_file
        # YA fusionado por archivo, no el del result (que se ignora).
        cell["ocr_count"] = sum((cell.get("per_file") or {}).values())
        cell.setdefault("per_file_overrides", {})
        cell.setdefault("manual_entry", False)
        cell.setdefault("user_override", None)
        cell.setdefault("override_note", None)
        cell.setdefault("excluded", False)
        cell.setdefault("confirmed", False)
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
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

    @_synchronized
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

    @_synchronized
    def apply_per_file_ocr_result(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        filename: str,
        *,
        count: int,
        method: str,
        near_matches: list[dict],
    ) -> None:
        """Merge a single-file OCR scan into the cell (rev-2 #1 / §4.2).

        Updates only this file's ``per_file`` count and ``per_file_method``, and
        replaces its near-matches while keeping the others' — leaving the rest of
        the cell untouched (other files, overrides, confirmed, cell-level method).
        The cell total is derived elsewhere via ``compute_cell_count``.

        Args:
            session_id: target session.
            hospital: hospital code.
            sigla: category code.
            filename: the scanned PDF's name.
            count: documents found in that file (0 is valid → its chip reads Revisar).
            method: the OCR method used (e.g. ``"header_band_anchors"``).
            near_matches: serialized near-match dicts for this file (may be empty).
        """
        state, _ = self._load_and_migrate(session_id)
        cell = state.setdefault("cells", {}).setdefault(hospital, {}).setdefault(sigla, {})
        # per_file may be an explicit None (a filename scan can leave it unset),
        # so setdefault is not enough — coerce to a dict before assigning.
        per_file = cell["per_file"] = cell.get("per_file") or {}
        per_file[filename] = count
        per_file_method = cell["per_file_method"] = cell.get("per_file_method") or {}
        per_file_method[filename] = method
        others = [nm for nm in (cell.get("near_matches") or []) if nm.get("pdf_name") != filename]
        cell["near_matches"] = others + list(near_matches or [])
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
    def clear_near_matches(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        *,
        pdf_name: str | None = None,
        page_index: int | None = None,
    ) -> None:
        """Drop near-match suspects from a cell — one entry or the whole list (E5).

        A near-match is only a maintenance hint (a candidate for a new flavor), so
        clearing it never changes a count. When ``pdf_name``/``page_index`` identify
        an entry, only that one is dropped; otherwise the whole list is cleared.
        No-op when the cell or its list is absent.

        Args:
            session_id: target session.
            hospital: hospital code.
            sigla: category code.
            pdf_name: with ``page_index``, the specific entry to drop.
            page_index: page index of the entry to drop.
        """
        state, _ = self._load_and_migrate(session_id)
        cell = (state.get("cells", {}).get(hospital, {}) or {}).get(sigla)
        if not cell or not cell.get("near_matches"):
            return
        if pdf_name is None and page_index is None:
            cell["near_matches"] = []
        else:
            cell["near_matches"] = [
                nm
                for nm in cell["near_matches"]
                if not (nm.get("pdf_name") == pdf_name and nm.get("page_index") == page_index)
            ]
        update_session_state(self._conn, session_id, state_json=json.dumps(state))

    @_synchronized
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

    @_synchronized
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

    @_synchronized
    def apply_cell_result(
        self,
        session_id: str,
        hospital: str,
        sigla: str,
        result: ScanResult,
    ) -> None:
        """Deprecated. Use apply_filename_result for pase 1 results."""
        self.apply_filename_result(session_id, hospital, sigla, result)

    @_synchronized
    def finalize(self, session_id: str) -> None:
        """Mark a session as finalized.

        Args:
            session_id: Target session identifier.
        """
        finalize_session(self._conn, session_id)
